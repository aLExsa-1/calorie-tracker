// 逐页截图自检：node tests/tools/shoot.mjs <outDir> [baseUrl] [viewport=phone|small|desktop] [lang=zh-CN|en] [theme]
import { openPage, savePng, sleep } from "./cdp.mjs";

const out = process.argv[2] || "tests/.data/shots";
const base = process.argv[3] || "http://127.0.0.1:8799";
const vp = process.argv[4] || "phone";
const lang = process.argv[5] || "zh-CN";
const theme = process.argv[6] || "";
const VIEWPORTS = {
  phone: { width: 390, height: 844, dpr: 1.5, mobile: true },
  small: { width: 360, height: 740, dpr: 1.5, mobile: true },
  desktop: { width: 1280, height: 900, dpr: 1, mobile: false },
};

const page = await openPage(VIEWPORTS[vp]);
const problems = [];
try {
  await page.goto(base + "/");
  await page.eval(`localStorage.setItem("ct.lang", ${JSON.stringify(lang)}); localStorage.setItem("ct.seenVersion","x-shoot"); ${theme ? `localStorage.setItem("ct.theme", ${JSON.stringify(theme)});` : `localStorage.removeItem("ct.theme");`} true`);
  await page.goto(base + "/");
  await page.waitFor(`document.querySelector("#health").classList.contains("ok")`);
  await page.waitFor(`document.querySelector("#daySummary").children.length > 0`);
  // 先收掉更新日志弹窗，并单独截一张
  await page.waitFor(`!document.querySelector("#changelogModal").classList.contains("hidden")`, 4000).catch(() => {});
  if (await page.eval(`!document.querySelector("#changelogModal").classList.contains("hidden")`)) {
    savePng(await page.shotViewport(), `${out}/${vp}-${lang}-00-changelog.png`);
    await page.click("#clClose");
  }

  const tabs = ["record", "day", "report", "profile", "settings"];
  for (const tab of tabs) {
    await page.click(`nav button[data-tab="${tab}"]`);
    await sleep(500);
    if (tab === "record") {
      // 造一份草稿，看草稿卡片
      await page.set("#foodText", "早餐：米饭一碗、两个鸡蛋、一盒牛奶");
      await page.click("#btnEstFood");
      await page.waitFor(`document.querySelector("#draftBody .entry")`, 8000);
      await sleep(300);
    }
    if (tab === "report") {
      await page.click("#btnWeek");
      await page.waitFor(`document.querySelector("#reportView .card")`, 10000);
      await sleep(300);
    }
    if (tab === "settings") {
      // 展开所有折叠，便于整页检查
      await page.eval(`document.querySelectorAll("#tab-settings details.fold").forEach(d => d.open = true); document.querySelectorAll("#promptList details").forEach((d,i) => d.open = i===0); true`);
      await sleep(300);
    }
    const ov = await page.overflowReport();
    if (ov.overflow || ov.offenders.length) problems.push({ tab, ...ov });
    // 首屏（真实视口，含底栏）必须先截：整页分段会临时改视口
    await page.eval("window.scrollTo(0, 0); true");
    await sleep(200);
    savePng(await page.shotViewport(), `${out}/${vp}-${lang}-${tab}-view.png`);
    const segs = await page.shotSegments(vp === "desktop" ? 1000 : 1100);
    segs.forEach((b, i) => savePng(b, `${out}/${vp}-${lang}-${tab}-${i}.png`));
  }
} catch (err) {
  problems.push({ fatal: String(err.message || err) });
} finally {
  const logs = page.logs.slice();
  await page.close();
  console.log(JSON.stringify({ viewport: vp, lang, theme, problems, consoleLogs: logs }, null, 2));
}
