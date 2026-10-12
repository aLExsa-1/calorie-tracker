// 最小 CDP 客户端（Node 24 全局 WebSocket），仅用于 UI 截图自检。不是产品代码。
import fs from "node:fs";
import path from "node:path";

const CDP_PORT = process.env.CDP_PORT || 9333;
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function openPage({ width = 390, height = 844, dpr = 1.5, mobile = true } = {}) {
  const ver = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`)).json();
  const ws = new WebSocket(ver.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("CDP websocket 连接失败")); });

  let nextId = 0;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(`${msg.error.message}`)) : res(msg.result);
    } else if (msg.method) {
      listeners.forEach((fn) => fn(msg));
    }
  };
  const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
    const id = ++nextId;
    pending.set(id, { res, rej });
    ws.send(JSON.stringify({ id, method, params, sessionId }));
  });

  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const cmd = (m, p) => send(m, p, sessionId);

  const logs = [];
  listeners.push((msg) => {
    if (msg.sessionId !== sessionId) return;
    if (msg.method === "Runtime.exceptionThrown") {
      const d = msg.params.exceptionDetails;
      logs.push(`[exception] ${d.exception?.description || d.text} @${d.url || ""}:${d.lineNumber}`);
    } else if (msg.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(msg.params.type)) {
      logs.push(`[console.${msg.params.type}] ` + msg.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
    } else if (msg.method === "Log.entryAdded" && ["error", "warning"].includes(msg.params.entry.level)) {
      logs.push(`[log.${msg.params.entry.level}] ${msg.params.entry.text} ${msg.params.entry.url || ""}`);
    }
  });

  await cmd("Page.enable");
  await cmd("Runtime.enable");
  await cmd("Log.enable");
  await cmd("Network.enable");
  await cmd("Network.setCacheDisabled", { cacheDisabled: true });
  const viewport = { width, height, dpr, mobile };
  const setViewport = (v = viewport) => cmd("Emulation.setDeviceMetricsOverride", {
    width: v.width, height: v.height, deviceScaleFactor: v.dpr, mobile: v.mobile,
    screenWidth: v.width, screenHeight: v.height,
  });
  await setViewport();
  if (mobile) await cmd("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });

  const page = {
    logs,
    cmd,
    viewport,
    async goto(url) {
      const loaded = new Promise((res) => {
        const fn = (msg) => { if (msg.sessionId === sessionId && msg.method === "Page.loadEventFired") { listeners.splice(listeners.indexOf(fn), 1); res(); } };
        listeners.push(fn);
      });
      await cmd("Page.navigate", { url });
      await Promise.race([loaded, sleep(15000)]);
      await sleep(250);
    },
    async reload() { return this.goto(await this.eval("location.href")); },
    async eval(expression) {
      const r = await cmd("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error("eval 失败：" + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
      return r.result.value;
    },
    async click(selector) {
      const ok = await this.eval(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.click(); return true; })()`);
      if (!ok) throw new Error("找不到元素：" + selector);
      await sleep(120);
    },
    async set(selector, value, eventName = "input") {
      const ok = await this.eval(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.value = ${JSON.stringify(value)}; el.dispatchEvent(new Event(${JSON.stringify(eventName)}, { bubbles: true })); if (${JSON.stringify(eventName)} !== "change") el.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`);
      if (!ok) throw new Error("找不到元素：" + selector);
      await sleep(150);
    },
    async waitFor(expr, timeout = 8000) {
      const t0 = Date.now();
      while (Date.now() - t0 < timeout) {
        if (await this.eval(`!!(${expr})`)) return true;
        await sleep(120);
      }
      throw new Error("等待超时：" + expr);
    },
    /** 视口截图（真实首屏，含 fixed 元素），返回 Buffer */
    async shotViewport() {
      const r = await cmd("Page.captureScreenshot", { format: "png", fromSurface: true });
      return Buffer.from(r.data, "base64");
    },
    /** 整页分段截图：临时把视口拉到整页高度，使 fixed 底栏出现在页面底部。返回分段 Buffer 数组 */
    async shotSegments(segH = 900) {
      let H = await this.eval("Math.ceil(document.documentElement.scrollHeight)");
      await setViewport({ ...viewport, height: H });
      await sleep(250);
      const H2 = await this.eval("Math.ceil(document.documentElement.scrollHeight)");
      if (H2 !== H) { H = Math.max(H, H2); await setViewport({ ...viewport, height: H }); await sleep(250); }
      const segs = [];
      for (let y = 0; y < H; y += segH) {
        const h = Math.min(segH, H - y);
        const r = await cmd("Page.captureScreenshot", {
          format: "png", fromSurface: true, captureBeyondViewport: false,
          clip: { x: 0, y, width: viewport.width, height: h, scale: 1 },
        });
        segs.push(Buffer.from(r.data, "base64"));
      }
      await setViewport();
      await sleep(150);
      return segs;
    },
    /** 检查横向溢出，返回 { overflow, scrollW, clientW, offenders[] } */
    async overflowReport() {
      return this.eval(`(() => {
        const vw = document.documentElement.clientWidth;
        const offenders = [];
        document.querySelectorAll("body *").forEach((el) => {
          const cs = getComputedStyle(el);
          if (cs.display === "none" || cs.visibility === "hidden" || el.closest("[hidden]")) return;
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) return;
          if (r.right > vw + 1 || r.left < -1) {
            let p = el.parentElement, clipped = false;
            while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") { clipped = true; break; } p = p.parentElement; }
            if (!clipped) offenders.push((el.id ? "#" + el.id : el.tagName.toLowerCase()) + "." + String(el.className).split(" ").join(".") + " right=" + Math.round(r.right));
          }
        });
        return { overflow: document.documentElement.scrollWidth > vw, scrollW: document.documentElement.scrollWidth, clientW: vw, offenders: offenders.slice(0, 12) };
      })()`);
    },
    async close() {
      try { await send("Target.closeTarget", { targetId }); } catch { /* ignore */ }
      ws.close();
    },
  };
  return page;
}

export function savePng(buf, file) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, buf);
  return file;
}
