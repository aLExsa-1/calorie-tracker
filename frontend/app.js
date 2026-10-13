/* 热量管理前端：独立静态页面，只通过 HTTP API 与后端通信。文案统一经 i18n.js 的 t() 获取。 */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (x, d = 0) => (x === null || x === undefined || x === "" ? "—" : Number(x).toFixed(d));
const today = () => {
  const d = new Date();  // 用本地日期；toISOString 是 UTC，中国时区 0–8 点会差一天
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/* 餐次：存储值保持中文，这里只负责显示文字与输入反查 */
const MEALS = [["早餐", "meal.breakfast"], ["午餐", "meal.lunch"], ["晚餐", "meal.dinner"], ["加餐", "meal.snack"]];
function mealLabel(v) {
  const s = v || "";
  const m = MEALS.find(([zh]) => zh === s);
  return m ? t(m[1]) : s;
}
/* 把用户输入（任一语言）反查为存储值（中文）；切换语言时输入框可能仍是旧语言文字 */
function mealFromInput(v) {
  const s = String(v ?? "").trim();
  if (!s) return "";
  const low = s.toLowerCase();
  const m = MEALS.find(([zh, key]) => {
    if (s === zh) return true;
    return Object.keys(I18N.DICT).some((lang) => {
      const txt = I18N.DICT[lang][key];
      return txt !== undefined && low === String(txt).toLowerCase();
    });
  });
  return m ? m[0] : s;
}
function confLabel(c) {
  const key = { high: "conf.high", medium: "conf.medium", low: "conf.low" }[c];
  return key ? t(key) : c;
}

const state = {
  config: null, draft: [], draftNotes: "", dayLoaded: null,
  health: null, changelog: null, report: null, reportList: null,
  profileHistory: null, llmEditing: null,
};

/* 需要随语言重绘的状态框：sel -> { fn, kind, html }，fn 返回文本/HTML */
const memo = {};
function setBox(sel, msg, kind, html = false) {
  const fn = typeof msg === "function" ? msg : () => msg;
  memo[sel] = { fn, kind, html };
  paintBox(sel);
}
function paintBox(sel) {
  const m = memo[sel];
  if (!m) return;
  const el = $(sel);
  const v = m.fn();
  if (m.html) el.innerHTML = v;
  else el.textContent = v;
  if (m.kind !== undefined) el.className = "status " + m.kind;
}
function repaintBoxes() {
  Object.keys(memo).forEach(paintBox);
}

/* 食物图片：先在前端压缩到 1600px 以内再转 base64，减小请求体积 */
const MAX_IMAGES = 4;
const MAX_IMAGE_MB = 5;
state.foodImages = [];  // [{ name, mime, data(dataURL) }]

function readImage(file) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) return reject(new Error(t("err.notImage", { name: file.name })));
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const max = 1600;
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
      resolve({ name: file.name, mime: "image/jpeg", data: dataUrl });
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error(t("err.decode", { name: file.name }))); };
    img.src = url;
  });
}

function renderFoodPreview() {
  $("#foodPreview").innerHTML = state.foodImages.map((im, i) =>
    `<div class="thumb"><img src="${im.data}" alt="${esc(im.name)}"><button type="button" class="small danger" data-rm-img="${i}">${t("btn.remove")}</button></div>`
  ).join("");
}

async function onFoodFiles(e) {
  const files = Array.from(e.target.files || []);
  e.target.value = "";
  for (const f of files) {
    if (state.foodImages.length >= MAX_IMAGES) { toast(t("toast.maxImages", { max: MAX_IMAGES }), true); break; }
    if (f.size > MAX_IMAGE_MB * 1024 * 1024) { toast(t("toast.imgTooBig", { name: f.name, mb: MAX_IMAGE_MB }), true); continue; }
    try {
      state.foodImages.push(await readImage(f));
    } catch (err) {
      toast(err.message, true);
    }
  }
  renderFoodPreview();
}

/* ---------------- API ---------------- */
function apiBase() {
  const v = localStorage.getItem("ct.apiBase") || "";
  return v.replace(/\/+$/, "");
}

/* 本机访问口令：安卓壳启动 WebView 时用 URL 片段注入（片段不会发给服务器）。
 * 电脑版没有口令，返回空字符串，请求头不带该字段。 */
function apiToken() {
  return localStorage.getItem("ct.token") || "";
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  const token = apiToken();
  if (token) opts.headers["X-CT-Token"] = token;
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(apiBase() + path, opts);
  } catch (err) {
    throw new Error(t("common.noBackend", { base: apiBase() || t("common.sameOrigin"), msg: err.message }));
  }
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: text.slice(0, 200) }; }
  if (!res.ok) {
    const err = new Error(data.error || `HTTP ${res.status}`);
    err.detail = data.detail;
    throw err;
  }
  return data;
}

/* ---------------- 通用 UI ---------------- */
function toast(msg, isErr = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (isErr ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 3500);
}

function setStatus(sel, msg, kind = "") {
  setBox(sel, msg, kind);
}

async function withBusy(btn, fn) {
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = t("common.busy");
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.textContent = btn.dataset.i18n ? t(btn.dataset.i18n) : old;
  }
}

/* 配色：三套浅色方案，仅存本机 localStorage；init 前 index.html 内联脚本已提前套用，避免闪色 */
const THEMES = ["forest", "ocean", "plum"];
function setTheme(name, persist = true) {
  const theme = THEMES.includes(name) ? name : "forest";
  document.documentElement.setAttribute("data-theme", theme);
  if (persist) { try { localStorage.setItem("ct.theme", theme); } catch (_) { /* 隐私模式忽略 */ } }
  $$("#themePicker [data-theme]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.theme === theme)));
  const meta = $('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", getComputedStyle(document.documentElement).getPropertyValue("--bg").trim());
}

/* 记录页分段：饮食 / 运动；两个面板只是显隐，输入内容不会丢 */
function setSegment(seg) {
  $$("[data-seg]").forEach((b) => {
    const on = b.dataset.seg === seg;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  $("#paneFood").hidden = seg !== "food";
  $("#paneAct").hidden = seg !== "activity";
}

/* 每日页前后翻一天（按本地日期计算，避免 toISOString 的时区偏差） */
function shiftDay(delta) {
  const cur = $("#dayDate").value || today();
  const [y, m, d] = cur.split("-").map(Number);
  const nd = new Date(y, m - 1, d + delta);
  $("#dayDate").value = `${nd.getFullYear()}-${String(nd.getMonth() + 1).padStart(2, "0")}-${String(nd.getDate()).padStart(2, "0")}`;
  loadDay();
}

function showTab(name) {
  $$("nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.id === "tab-" + name));
  if (name === "day") loadDay();
  if (name === "report") loadReportList();
  if (name === "profile") loadProfile();
  if (name === "settings") loadConfig();
}

/* ---------------- 健康检查 ---------------- */
async function checkHealth() {
  try {
    const h = await api("GET", "/api/health");
    state.health = { ok: true, version: h.version };
    renderHealth();
    return true;
  } catch (err) {
    state.health = { ok: false, msg: err.message };
    renderHealth();
    return false;
  }
}

function renderHealth() {
  const pill = $("#health");
  const h = state.health;
  if (h && h.ok) {
    pill.textContent = t("health.online", { version: h.version });
    pill.className = "pill ok";
    return;
  }
  pill.textContent = t("health.offline");
  pill.className = h ? "pill bad" : "pill";
  pill.title = h ? h.msg : "";
}

/* ================= 记录 ================= */
/* 图标：餐次 → 精灵 id；运动单独一个。图标只做装饰（aria-hidden），不影响文字与事件。 */
const MEAL_ICONS = { "早餐": "i-breakfast", "午餐": "i-lunch", "晚餐": "i-dinner", "加餐": "i-snack" };
function iconSvg(id) {
  return `<svg class="ico" aria-hidden="true"><use href="#${id}"/></svg>`;
}
function entryIcon(e) {
  const isAct = e.kind === "activity";
  const id = isAct ? "i-activity" : (MEAL_ICONS[e.meal] || "i-plate");
  return `<span class="ent-ico ${isAct ? "activity" : "food"}">${iconSvg(id)}</span>`;
}

function mealOptions(selected) {
  const cur = selected || "";
  const known = MEALS.some(([zh]) => zh === cur);
  return `<option value=""${cur === "" ? " selected" : ""}>${t("meal.none")}</option>`
    + MEALS.map(([zh, key]) => `<option value="${zh}"${zh === cur ? " selected" : ""}>${t(key)}</option>`).join("")
    + (cur && !known ? `<option value="${esc(cur)}" selected>${esc(cur)}</option>` : "");
}

function draftRow(it, i) {
  const isAct = it.kind === "activity";
  const amount = isAct ? it.minutes : it.grams;
  const macro = (f, label) => `<label>${label}<input data-f="${f}" type="number" step="0.1" inputmode="decimal" value="${it[f] ?? ""}"></label>`;
  return `<div class="entry draft" data-i="${i}">
    ${entryIcon(it)}
    <div class="ent-main">
      <input class="ent-name" data-f="name" value="${esc(it.name)}" aria-label="${t("th.name")}">
      <div class="ent-meta">
        <span class="badge ${esc(it.kind)}">${isAct ? t("kind.activity") : t("kind.food")}</span>
        ${it.confidence ? `<span class="badge ${esc(it.confidence)}">${t("th.conf")} ${esc(confLabel(it.confidence))}</span>` : ""}
      </div>
    </div>
    <div class="ent-fields">
      ${isAct ? "" : `<label>${t("th.meal")}<select data-f="meal">${mealOptions(it.meal)}</select></label>`}
      <label>${isAct ? t("th.minutes") : t("th.grams")}<input data-f="${isAct ? "minutes" : "grams"}" type="number" step="0.1" inputmode="decimal" value="${amount ?? ""}"></label>
      <label>${t("th.kcal")}<input data-f="kcal" type="number" step="0.1" inputmode="decimal" value="${it.kcal ?? ""}"></label>
      ${isAct ? "" : macro("protein_g", t("th.protein_g")) + macro("carb_g", t("th.carb_g")) + macro("fat_g", t("th.fat_g"))}
    </div>
    ${it.basis ? `<div class="ent-basis">${t("th.basis")}：${esc(it.basis)}</div>` : ""}
    <div class="ent-actions"><button type="button" class="small danger" data-del="${i}">${t("btn.remove")}</button></div>
  </div>`;
}

function renderDraft() {
  const card = $("#draftCard");
  card.hidden = state.draft.length === 0 && !state.draftNotes;
  $("#draftNotes").textContent = state.draftNotes || "";
  $("#draftBody").innerHTML = state.draft.map(draftRow).join("");
}

function readDraftEdits() {
  $$("#draftBody .entry").forEach((row) => {
    const i = Number(row.dataset.i);
    const it = state.draft[i];
    if (!it) return;
    $$("input, select", row).forEach((inp) => {
      const f = inp.dataset.f;
      if (!f) return;
      if (f === "minutes" || f === "grams") it[it.kind === "activity" ? "minutes" : "grams"] = numOrNull(inp.value);
      else if (f === "meal") it.meal = mealFromInput(inp.value);
      else if (f === "name") it[f] = inp.value.trim();
      else it[f] = numOrNull(inp.value);
    });
  });
}

function numOrNull(v) {
  if (v === "" || v === null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

async function estimate(kind) {
  const btn = kind === "food" ? $("#btnEstFood") : $("#btnEstAct");
  const text = kind === "food" ? $("#foodText").value : $("#actText").value;
  const date = $("#recDate").value || today();
  const meal = $("#recMeal").value;
  const hasImages = kind === "food" && state.foodImages.length > 0;
  if (!text.trim() && !hasImages) return toast(kind === "food" ? t("toast.needFoodOrImg") : t("toast.needAct"), true);
  setStatus("#estStatus", () => t("est.busy"), "busy");
  try {
    const path = kind === "food" ? "/api/estimate/food" : "/api/estimate/activity";
    const body = kind === "food"
      ? { text, date, meal, images: state.foodImages.map((im) => im.data) }
      : { text, date };
    const res = await withBusy(btn, () => api("POST", path, body));
    state.draft.push(...res.items.map((it) => ({ ...it, meal: kind === "food" ? (it.meal || meal || "") : "" })));
    state.draftNotes = [res.notes, ...(res.warnings || [])].filter(Boolean).join(I18N.getLang() === "en" ? "; " : "；");
    renderDraft();
    const n = res.items.length;
    setStatus("#estStatus", () => (res.search_used ? t("est.doneSearched", { n }) : t("est.done", { n })), "ok");
    if (kind === "food") { $("#foodText").value = ""; state.foodImages = []; renderFoodPreview(); }
    else { $("#actText").value = ""; }
  } catch (err) {
    setStatus("#estStatus", err.message, "err");
    if (err.detail && err.detail.raw) console.warn("LLM 原始输出：", err.detail.raw);
  }
}

async function saveDraft() {
  readDraftEdits();
  const valid = state.draft.filter((it) => it.name && it.kcal !== null && it.kcal !== undefined);
  if (!valid.length) return toast(t("toast.noSaveable"), true);
  const date = $("#recDate").value || today();
  try {
    await withBusy($("#btnSaveDraft"), () => api("POST", "/api/entries", { date, items: valid }));
    toast(t("toast.savedN", { n: valid.length, date }));
    state.draft = [];
    state.draftNotes = "";
    renderDraft();
    $("#dayDate").value = date;
    loadDay();
  } catch (err) {
    toast(err.message, true);
  }
}

/* ================= 每日 ================= */
function kpi(label, value, cls = "") {
  return `<div class="kpi ${cls}"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

async function loadDay() {
  const date = $("#dayDate").value || today();
  $("#dayDate").value = date;
  try {
    state.dayLoaded = await api("GET", `/api/days/${date}`);
    renderDay();
  } catch (err) {
    toast(err.message, true);
  }
}

/* 每日摘要：热量差大卡 + 摄入/消耗磁贴 + 宏量分段条。数值与 API 字段一一对应，不在前端重算。 */
function sumCard(cls, label, value, unit, sub = "") {
  return `<div class="sum-card ${cls}"><div class="sum-label">${label}</div>
    <div class="sum-value">${value}${unit ? `<small>${unit}</small>` : ""}</div>${sub}</div>`;
}

function dayHero(d) {
  const bal = d.balance;
  if (bal === null || bal === undefined) {
    return `<div class="sum-card sum-hero"><div class="sum-label">${t("sum.balance")}</div>
      <div class="sum-value">—<small>kcal</small></div><span class="sum-state">${t("sum.noMaint")}</span></div>`;
  }
  const cls = bal < 0 ? "neg" : bal > 0 ? "pos" : "";
  const stateText = bal < 0 ? t("sum.deficit") : bal > 0 ? t("sum.surplus") : t("sum.even");
  const shown = bal > 0 ? `+${fmt(bal)}` : bal < 0 ? `−${fmt(Math.abs(bal))}` : fmt(bal);
  return `<div class="sum-card sum-hero ${cls}"><div class="sum-label">${t("sum.balance")}</div>
    <div class="sum-value">${shown}<small>kcal</small></div><span class="sum-state">${stateText}</span></div>`;
}

function macroCard(d) {
  const p = Number(d.protein_g) || 0, c = Number(d.carb_g) || 0, f = Number(d.fat_g) || 0;
  const bar = (p + c + f) > 0
    ? `<i style="flex-grow:${p}"></i><i style="flex-grow:${c}"></i><i style="flex-grow:${f}"></i>` : "";
  return `<div class="sum-card macro-card"><div class="sum-label">${t("sum.macros")}</div>
    <div class="macro-bar" role="img" aria-label="${t("sum.macros")}">${bar}</div>
    <div class="macro-legend">
      <span style="--c:var(--m-protein)">${t("th.protein")} <b>${fmt(d.protein_g)}</b> g</span>
      <span style="--c:var(--m-carb)">${t("th.carb")} <b>${fmt(d.carb_g)}</b> g</span>
      <span style="--c:var(--m-fat)">${t("th.fat")} <b>${fmt(d.fat_g)}</b> g</span>
    </div></div>`;
}

function renderDay() {
  const d = state.dayLoaded;
  if (!d) return;
  const burnSub = `<div class="sum-sub">${t("sum.exerciseBurn")} <b>${fmt(d.exercise)}</b><br>${t("sum.maintBurn")} <b>${fmt(d.maintenance_kcal)}</b></div>`;
  $("#daySummary").innerHTML = dayHero(d)
    + sumCard("", t("sum.intake"), fmt(d.intake), "kcal")
    + sumCard("", t("sum.burn"), fmt(d.burn), "kcal", burnSub)
    + macroCard(d);
  $("#dayWarn").innerHTML = (d.warnings || []).map((w) => `<p class="status err">${esc(w)}</p>`).join("");
  $("#dayBody").innerHTML = d.entries.length ? dayGroups(d.entries) : `<div class="empty">${t("day.empty")}</div>`;
}

/* 明细按「早餐 / 午餐 / 晚餐 / 加餐 / 其它 / 运动」分组，组头显示小计 */
function dayGroups(entries) {
  const order = [...MEALS.map(([zh]) => zh), ""];
  const groups = order.map((zh) => ({
    key: zh, title: zh ? mealLabel(zh) : t("sum.otherMeal"),
    list: entries.filter((e) => e.kind === "food" && (MEALS.some(([m]) => m === zh) ? e.meal === zh : !MEALS.some(([m]) => m === e.meal))),
  }));
  groups.push({ key: "act", title: t("kind.activity"), list: entries.filter((e) => e.kind === "activity") });
  return groups.filter((g) => g.list.length).map((g) => {
    const sum = g.list.reduce((s, e) => s + (Number(e.kcal) || 0), 0);
    return `<div class="group"><div class="group-head"><span>${esc(g.title)}</span><b>${fmt(sum)} kcal</b></div>
      <div class="entries">${g.list.map(entryRow).join("")}</div></div>`;
  }).join("");
}

function entryRow(e) {
  const isAct = e.kind === "activity";
  const amount = isAct ? (e.minutes != null ? `${fmt(e.minutes, 0)} ${t("unit.min")}` : "") : (e.grams != null ? `${fmt(e.grams, 0)} ${t("unit.g")}` : "");
  const macros = isAct || (e.protein_g == null && e.carb_g == null && e.fat_g == null) ? ""
    : `<span>${t("th.protein")} ${fmt(e.protein_g, 1)}</span><span>${t("th.carb")} ${fmt(e.carb_g, 1)}</span><span>${t("th.fat")} ${fmt(e.fat_g, 1)}</span>`;
  return `<div class="entry" data-id="${e.id}">
    ${entryIcon(e)}
    <div class="ent-main">
      <input class="ent-name" data-f="name" value="${esc(e.name)}" aria-label="${t("th.name")}">
      <div class="ent-meta">${amount ? `<span>${amount}</span>` : ""}${macros}${e.llm_name ? `<span>${esc(e.llm_name)}</span>` : ""}</div>
    </div>
    <label class="ent-kcal"><input class="kcal-in" data-f="kcal" type="number" step="0.1" inputmode="decimal" value="${e.kcal ?? ""}" aria-label="${t("th.kcal")}">kcal</label>
    <div class="ent-actions">
      <button type="button" class="small" data-save="${e.id}">${t("btn.save")}</button>
      <button type="button" class="small danger" data-remove="${e.id}">${t("btn.delete")}</button>
    </div>
  </div>`;
}

async function saveEntry(id, row) {
  const fields = {};
  $$("input", row).forEach((inp) => {
    const f = inp.dataset.f;
    if (!f) return;
    fields[f] = f === "name" ? inp.value.trim() : numOrNull(inp.value);
  });
  try {
    await api("PUT", `/api/entries/${id}`, fields);
    toast(t("toast.saved"));
    loadDay();
  } catch (err) {
    toast(err.message, true);
  }
}

async function removeEntry(id) {
  if (!confirm(t("confirm.deleteEntry"))) return;
  try {
    await api("DELETE", `/api/entries/${id}`);
    loadDay();
  } catch (err) {
    toast(err.message, true);
  }
}

/* ================= 报告 ================= */
function listBullets(title, arr) {
  if (!arr || !arr.length) return "";
  return `<h3>${title}</h3><ul class="bullets">${arr.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
}

function buildReportHtml(r) {
  const s = r.stats;
  const a = r.analysis;
  const label = r.period === "week" ? t("rep.week") : t("rep.month");
  const header = `<h2>${t("rep.range", { label, start: s.start, end: s.end })}</h2>`;
  const kpis = `<div class="kpis">
    ${kpi(t("kpi.logDays"), `${s.days_logged} / ${s.days_total}`)}
    ${kpi(t("kpi.avgIntakeLogged"), fmt(s.avg_intake_logged_days))}
    ${kpi(t("kpi.avgExerciseLogged"), fmt(s.avg_exercise_logged_days))}
    ${kpi(t("kpi.totalExercise"), fmt(s.total_exercise))}
    ${kpi(t("kpi.avgBalanceLogged"), fmt(s.avg_balance_logged_days), (s.avg_balance_logged_days ?? 0) < 0 ? "neg" : "pos")}
    ${kpi(t("kpi.totalBalance"), fmt(s.total_balance), (s.total_balance ?? 0) < 0 ? "neg" : "pos")}
    ${kpi(t("kpi.weightChange"), s.weight_change_kg === null ? "—" : fmt(s.weight_change_kg, 1))}
  </div>`;
  const daily = `<div class="table-wrap"><table>
      <thead><tr><th>${t("th.date")}</th><th>${t("th.count")}</th><th>${t("th.intake")}</th><th>${t("th.exercise")}</th><th>${t("th.balance")}</th></tr></thead>
      <tbody>${s.daily.map((d) => `<tr><td>${d.date}</td><td>${d.entries}</td><td class="num">${fmt(d.intake)}</td>
        <td class="num">${fmt(d.exercise)}</td><td class="num">${fmt(d.balance)}</td></tr>`).join("")}</tbody>
    </table></div>`;
  let analysis = `<p class="hint">${t("rep.notAnalyzed")}</p>`;
  if (a) {
    const pct = (v) => Math.max(0, Math.min(100, Number(v) || 0));
    analysis = `<div class="ai-block">
        <p class="ai-badge" data-ai-badge>${t("ai.badge")}</p>
        <div class="scores">
        <div class="score-tile"><div class="score">${fmt(a.diet_score)}<small>${t("rep.scoreDiet")}</small></div><div class="meter"><i style="width:${pct(a.diet_score)}%"></i></div></div>
        <div class="score-tile"><div class="score">${fmt(a.exercise_score)}<small>${t("rep.scoreExercise")}</small></div><div class="meter"><i style="width:${pct(a.exercise_score)}%"></i></div></div>
        <div class="score-tile"><div class="score">${esc(a.exercise_level || "—")}<small>${t("rep.scoreLevel")}</small></div></div>
      </div>
      <p>${esc(a.summary || "")}</p>
      ${listBullets(t("rep.dietComments"), a.diet_comments)}
      ${listBullets(t("rep.exComments"), a.exercise_comments)}
      ${listBullets(t("rep.suggestions"), a.suggestions)}
      ${listBullets(t("rep.risks"), a.risks)}
      <p class="hint" data-ai-disclaimer>${t("ai.disclaimer")}</p>
      <p class="hint">${t("rep.analysisModel", { llm: esc(a.llm || "") })}${a.model ? t("rep.modelSuffix", { model: esc(a.model) }) : ""}</p>
      </div>`;
  }
  const warn = (r.warnings || []).map((w) => `<p class="status err">${esc(w)}</p>`).join("");
  return `<div class="card">${header}${warn}${kpis}${analysis}<h3>${t("rep.dailyDetail")}</h3>${daily}
    <details><summary class="hint">${t("rep.rawJson")}</summary><pre>${esc(JSON.stringify(s, null, 2))}</pre></details>
    <p class="hint" data-legal-disclaimer>${t("legal.footerDisclaimer")}</p></div>`;
}

function renderReportView() {
  const r = state.report;
  if (!r) return;
  $("#reportView").innerHTML = buildReportHtml(r);
}

function renderReport(r) {
  state.report = r;
  renderReportView();
}

async function generateReport(period, btn) {
  const date = $("#repDate").value || today();
  const analyze = $("#repAnalyze").checked;
  setStatus("#repStatus", () => (analyze ? t("rep.generating") : t("rep.calculating")), "busy");
  try {
    const r = await withBusy(btn, () => api("POST", "/api/reports", { period, date, analyze }));
    renderReport(r);
    (r.warnings || []).length
      ? setStatus("#repStatus", () => t("rep.doneWarn"), "ok")
      : setStatus("#repStatus", () => t("rep.done"), "ok");
    loadReportList();
  } catch (err) {
    setStatus("#repStatus", err.message, "err");
  }
}

async function loadReportList() {
  try {
    const { reports } = await api("GET", "/api/reports");
    state.reportList = reports;
    renderReportList();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderReportList() {
  const reports = state.reportList;
  if (!reports) return;
  $("#reportList").innerHTML = reports.length
    ? reports.map((r) => {
        const period = r.period === "week" ? t("period.week") : t("period.month");
        return `<li><a href="#" data-report="${r.id}">${esc(t("rep.listItem", { period, start: r.start, end: r.end }))}</a><small>${esc(r.created_at)}</small></li>`;
      }).join("")
    : `<li class="hint">${t("rep.noHistory")}</li>`;
}

/* ================= 身体数据 ================= */
async function loadProfile() {
  try {
    const { profile } = await api("GET", `/api/profile?date=${today()}`);
    const form = $("#profileForm");
    ["sex", "age", "height_cm", "weight_kg", "activity_text", "goal_text", "bmr_kcal", "maintenance_kcal"].forEach((k) => {
      if (form.elements[k]) form.elements[k].value = profile[k] ?? "";
    });
    form.elements.effective_date.value = today();
    const { history } = await api("GET", "/api/profile/history");
    state.profileHistory = history;
    renderProfileHistory();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderProfileHistory() {
  const list = state.profileHistory;
  if (!list) return;
  $("#profileHistory").innerHTML = list.map((h) => `<div class="tl-item">
        <div class="tl-head"><span class="tl-date">${esc(h.effective_date)}</span><span class="tl-saved">${t("th.savedAt")} ${esc(h.created_at)}</span></div>
        <div class="tl-chips">
          <span class="chip">${t("th.weightKg")} <b>${fmt(h.data.weight_kg, 1)}</b></span>
          <span class="chip">${t("th.bmr")} <b>${fmt(h.data.bmr_kcal)}</b></span>
          <span class="chip">${t("th.maint")} <b>${fmt(h.data.maintenance_kcal)}</b></span>
        </div>
        ${h.data.activity_text ? `<div class="tl-note">${esc(h.data.activity_text)}</div>` : ""}
      </div>`).join("") || `<div class="empty">${t("common.none")}</div>`;
}

function profileBody() {
  const form = $("#profileForm");
  const body = {};
  ["sex", "age", "height_cm", "weight_kg", "activity_text", "goal_text", "bmr_kcal", "maintenance_kcal"].forEach((k) => {
    const v = form.elements[k].value.trim();
    if (v === "") return;
    body[k] = ["age", "height_cm", "weight_kg", "bmr_kcal", "maintenance_kcal"].includes(k) ? Number(v) : v;
  });
  if (form.elements.effective_date.value) body.effective_date = form.elements.effective_date.value;
  return body;
}

async function saveProfile(e) {
  e.preventDefault();
  try {
    await api("PUT", "/api/profile", profileBody());
    toast(t("prof.saved"));
    loadProfile();
  } catch (err) {
    toast(err.message, true);
  }
}

async function estimateMeta() {
  const btn = $("#btnEstMeta");
  setBox("#metaResult", () => t("prof.metaBusy"));
  try {
    const r = await withBusy(btn, () => api("POST", "/api/profile/estimate-metabolism", { date: today() }));
    setBox("#metaResult", () => t("prof.metaResult", {
      bmr: fmt(r.bmr_kcal), maint: fmt(r.maintenance_kcal), basis: esc(r.basis || ""), llm: esc(r.llm),
    }), undefined, true);
    const form = $("#profileForm");
    form.elements.bmr_kcal.value = r.bmr_kcal;
    form.elements.maintenance_kcal.value = r.maintenance_kcal;
  } catch (err) {
    setBox("#metaResult", err.message);
  }
}

/* ================= 设置：语言 / LLM ================= */
function renderLlmFormTitle() {
  $("#llmFormTitle").textContent = state.llmEditing
    ? t("llm.formEdit", { name: state.llmEditing })
    : t("llm.formNew");
}

function resetLlmForm() {
  const f = $("#llmForm");
  f.reset();
  f.elements.id.value = "";
  f.elements.temperature.value = "0.2";
  f.elements.max_tokens.value = "4096";
  f.elements.json_mode.checked = true;
  state.llmEditing = null;
  renderLlmFormTitle();
}

function fillLlmForm(p) {
  const f = $("#llmForm");
  ["id", "name", "protocol", "model", "base_url", "temperature", "max_tokens", "extra_body"].forEach((k) => {
    f.elements[k].value = p[k] ?? "";
  });
  f.elements.api_key.value = "";
  f.elements.json_mode.checked = !!p.json_mode;
  state.llmEditing = p.name;
  renderLlmFormTitle();
  f.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderLlmList(c) {
  if (!c) return;
  const active = c.active_llm_id;
  $("#llmList").innerHTML = c.llm_profiles.length
    ? c.llm_profiles.map((p) => `<div class="llm-card">
        <div class="llm-top"><b>${esc(p.name)}</b>${p.id === active ? `<span class="pill ok">${t("llm.default")}</span>` : `<button type="button" class="small" data-activate="${p.id}">${t("btn.setDefault")}</button>`}</div>
        <div class="llm-meta"><span>${esc(p.protocol)} · ${esc(p.model)}</span><span>Key ${p.api_key_set ? esc(p.api_key_hint) : `<span class="pill bad">${t("llm.unset")}</span>`}</span></div>
        <div class="llm-meta"><small>${esc(p.base_url)}</small></div>
        <div class="llm-actions">
          <button type="button" class="small" data-test="${p.id}">${t("btn.test")}</button>
          <button type="button" class="small" data-edit="${p.id}">${t("btn.edit")}</button>
          <button type="button" class="small danger" data-delete="${p.id}">${t("btn.delete")}</button>
        </div></div>`).join("")
    : `<div class="empty">${t("llm.none")}</div>`;
}

function renderTaskMap(c) {
  if (!c) return;
  const opts = (sel) => `<option value="">${t("opt.followDefault")}</option>` + c.llm_profiles.map((p) =>
    `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.name)} · ${esc(p.model)}</option>`).join("");
  $("#taskMap").innerHTML = c.tasks.map((task) => `<label>${esc(task.label)}
      <select data-task="${task.id}">${opts(c.task_llm[task.id] || "")}</select></label>`).join("");
}

function renderSearch(c) {
  if (!c) return;
  const f = $("#searchForm");
  f.elements.provider.value = c.search.provider;
  f.elements.base_url.value = c.search.base_url || "";
  f.elements.api_key.value = "";
  renderSearchKeyPlaceholder();
}

function renderSearchKeyPlaceholder() {
  const c = state.config;
  if (!c) return;
  $("#searchForm").elements.api_key.placeholder = c.search.api_key_set
    ? t("search.keySet", { hint: c.search.api_key_hint })
    : "";
}

function renderPrompts(c) {
  if (!c) return;
  $("#promptList").innerHTML = c.tasks.map((task) => {
    const p = c.prompts[task.id];
    return `<details class="prompt-block" data-task="${task.id}">
      <summary>${esc(I18N.DICT[I18N.getLang()]["task." + task.id] ? t("task." + task.id) : task.label)}</summary>
      <div class="grid two">
        <label>${t("prompt.system")}<textarea rows="5" data-f="system">${esc(p.system)}</textarea></label>
        <label>${t("prompt.user")}<textarea rows="5" data-f="user">${esc(p.user)}</textarea></label>
        <label>${t("prompt.searchQuery")}<input data-f="search_query" value="${esc(p.search_query)}"></label>
        <label class="check"><input type="checkbox" data-f="use_search" ${p.use_search ? "checked" : ""}> ${t("prompt.useSearch")}</label>
      </div>
      <div class="row">
        <button class="primary small" data-save-prompt="${task.id}">${t("btn.savePrompt")}</button>
        <button class="small" data-reset-prompt="${task.id}">${t("btn.resetPrompt")}</button>
      </div>
    </details>`;
  }).join("");
}

async function loadConfig() {
  try {
    state.config = await api("GET", "/api/config");
    renderLlmList(state.config);
    renderTaskMap(state.config);
    renderSearch(state.config);
    renderPrompts(state.config);
  } catch (err) {
    toast(err.message, true);
  }
}

async function saveLlm(e) {
  e.preventDefault();
  const f = $("#llmForm");
  const body = {};
  ["id", "name", "protocol", "model", "base_url", "api_key", "temperature", "max_tokens", "extra_body"].forEach((k) => {
    body[k] = f.elements[k].value.trim();
  });
  body.temperature = Number(body.temperature || 0.2);
  body.max_tokens = Number(body.max_tokens || 4096);
  body.json_mode = f.elements.json_mode.checked;
  try {
    state.config = await api("POST", "/api/config/llm", body);
    toast(t("toast.llmSaved"));
    resetLlmForm();
    renderLlmList(state.config);
    renderTaskMap(state.config);
  } catch (err) {
    toast(err.message, true);
  }
}

async function llmAction(action, id) {
  try {
    if (action === "activate") {
      state.config = await api("POST", `/api/config/llm/${id}/activate`);
    } else if (action === "delete") {
      if (!confirm(t("confirm.deleteLlm"))) return;
      state.config = await api("DELETE", `/api/config/llm/${id}`);
      resetLlmForm();
    } else if (action === "edit") {
      const p = (state.config?.llm_profiles || []).find((x) => x.id === id);
      if (p) fillLlmForm(p);
      return;
    } else if (action === "test") {
      setStatus("#llmTestResult", () => t("llm.testing"), "busy");
      const r = await api("POST", "/api/llm/test", { id });
      setStatus("#llmTestResult", () => t("llm.testOk", { name: r.name, model: r.model, ms: r.latency_ms }), "ok");
      return;
    }
    renderLlmList(state.config);
    renderTaskMap(state.config);
  } catch (err) {
    if (action === "test") setStatus("#llmTestResult", err.message, "err");
    else toast(err.message, true);
  }
}

async function saveTaskMap() {
  const mapping = {};
  $$("#taskMap select").forEach((s) => { mapping[s.dataset.task] = s.value; });
  try {
    state.config = await api("PUT", "/api/config/task-llm", mapping);
    toast(t("toast.taskSaved"));
  } catch (err) {
    toast(err.message, true);
  }
}

async function saveSearch(e) {
  e.preventDefault();
  const f = $("#searchForm");
  const body = {
    provider: f.elements.provider.value,
    base_url: f.elements.base_url.value.trim(),
    api_key: f.elements.api_key.value.trim(),
  };
  try {
    state.config = await api("PUT", "/api/config/search", body);
    toast(t("toast.searchSaved"));
    renderSearch(state.config);
  } catch (err) {
    toast(err.message, true);
  }
}

async function testSearch() {
  setStatus("#searchTestResult", () => t("search.testing"), "busy");
  try {
    const r = await api("POST", "/api/search/test", { query: $("#searchTestQ").value.trim() });
    setBox("#searchTestResult", () => `<ul class="bullets">${r.results.map((x) =>
      `<li><a href="${esc(/^https?:\/\//i.test(x.url) ? x.url : "#")}" target="_blank" rel="noopener noreferrer">${esc(x.title)}</a>${I18N.getLang() === "en" ? ": " : "："}${esc(x.snippet)}</li>`).join("")}</ul>`, "ok", true);
  } catch (err) {
    setStatus("#searchTestResult", err.message, "err");
  }
}

async function savePrompt(task, block) {
  const body = {};
  $$("[data-f]", block).forEach((el) => {
    body[el.dataset.f] = el.type === "checkbox" ? el.checked : el.value;
  });
  try {
    state.config = await api("PUT", `/api/config/prompts/${task}`, body);
    toast(t("toast.promptSaved"));
  } catch (err) {
    toast(err.message, true);
  }
}

async function resetPrompt(task) {
  if (!confirm(t("confirm.resetPrompt"))) return;
  try {
    state.config = await api("DELETE", `/api/config/prompts/${task}`);
    renderPrompts(state.config);
    toast(t("toast.resetDone"));
  } catch (err) {
    toast(err.message, true);
  }
}

/* ================= 同意与数据处理 =================
 * 合规要点：
 *   1. 首次启动必须先取得同意，同意之前不发起任何网络请求（包括健康检查）；
 *   2. 政策版本升级时重新征求同意；
 *   3. 提供数据导出（可携带）与一键删除入口。
 * 同意状态仅保存在本机 localStorage，不上传任何地方。 */
const CONSENT_KEY = "ct.consent";
const POLICY_VERSION = "0.1";   // 隐私政策 / 用户协议的内容版本，改动条款时递增

function consentState() {
  try { return localStorage.getItem(CONSENT_KEY) || ""; } catch (_) { return ""; }
}

/* 版本号一致即视为已同意；政策条款更新时递增 POLICY_VERSION 会让旧同意自动失效 */
function hasConsented() {
  return consentState() === POLICY_VERSION;
}

function saveConsent() {
  try { localStorage.setItem(CONSENT_KEY, POLICY_VERSION); } catch (_) { /* 隐私模式忽略 */ }
}

function withdrawConsent() {
  try { localStorage.removeItem(CONSENT_KEY); } catch (_) { /* 忽略 */ }
}

function consentInputs() {
  return { privacy: $("#consentPrivacy"), terms: $("#consentTerms") };
}

function syncConsentButton() {
  const { privacy, terms } = consentInputs();
  $("#consentAgree").disabled = !(privacy.checked && terms.checked);
}

function showConsentAsk() {
  const { privacy, terms } = consentInputs();
  privacy.checked = false;
  terms.checked = false;
  syncConsentButton();
  $("#consentAsk").classList.remove("hidden");
  $("#consentDeclined").classList.add("hidden");
}

function showConsentDeclined() {
  $("#consentAsk").classList.add("hidden");
  $("#consentDeclined").classList.remove("hidden");
}

/* 仅展示同意层，不发起任何请求 */
function openConsentGate() {
  I18N.applyI18n();
  showConsentAsk();
  $("#consentGate").classList.remove("hidden");
}

function closeConsentGate() {
  $("#consentGate").classList.add("hidden");
}

/* ================= 数据管理 ================= */
function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportData() {
  setStatus("#dataResult", () => t("common.busy"), "busy");
  try {
    const data = await api("GET", "/api/data/export");
    const n = (data.entries || []).length;
    downloadJson(`calorie-tracker-backup-${today()}.json`, data);
    setStatus("#dataResult", () => t("data.exported", { n }), "ok");
  } catch (err) {
    setStatus("#dataResult", () => t("data.exportFail", { msg: err.message }), "err");
  }
}

async function clearData() {
  if (!window.confirm(t("confirm.clear"))) return;
  if (!window.confirm(t("confirm.clearAgain"))) return;
  setStatus("#dataResult", () => t("common.busy"), "busy");
  try {
    const res = await api("POST", "/api/data/clear", {});
    const r = res.removed || {};
    setStatus("#dataResult", () => t("data.cleared", {
      profiles: r.profiles || 0, entries: r.entries || 0, reports: r.reports || 0,
    }), "ok");
    state.report = null;
    state.draft = [];
    state.draftNotes = "";
    renderDraft();
    $("#reportView").innerHTML = "";
    await loadDay();
    await loadProfile();
  } catch (err) {
    setStatus("#dataResult", () => t("data.clearFail", { msg: err.message }), "err");
  }
}

/* ================= 更新日志 ================= */
async function fetchChangelog() {
  try {
    const res = await fetch("changelog.json", { cache: "no-cache" });
    if (!res.ok) return null;
    const cl = await res.json();
    if (!cl || cl.version === undefined || !Array.isArray(cl.items)) return null;
    return cl;
  } catch {
    return null;
  }
}

/* en 时优先 items_en（非空数组），缺失则回退到 items */
function changelogItems(cl) {
  const useEn = I18N.getLang() === "en" && Array.isArray(cl.items_en) && cl.items_en.length > 0;
  return useEn ? cl.items_en : cl.items;
}

/* 历史版本：history 数组（新版在前）；缺失时回退为顶层最新版本 */
function changelogVersions(cl) {
  if (Array.isArray(cl.history) && cl.history.length) return cl.history;
  return [{ version: cl.version, date: cl.date, items: cl.items, items_en: cl.items_en }];
}

function paintChangelog() {
  const cl = state.changelog;
  if (!cl) return;
  $("#clTitle").textContent = t("cl.titleV", { version: cl.version });
  $("#clDate").textContent = cl.date || "";
  $("#clItems").innerHTML = changelogVersions(cl).map((v) => `
    <div class="cl-version">
      <h3>v${esc(v.version)}${v.date ? ` <span class="hint">${esc(v.date)}</span>` : ""}</h3>
      <ul class="bullets">${changelogItems(v).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    </div>`).join("");
}

function showChangelog(cl) {
  state.changelog = cl;
  paintChangelog();
  $("#changelogModal").classList.remove("hidden");
}

function closeChangelog() {
  $("#changelogModal").classList.add("hidden");
  const cl = state.changelog;
  if (cl) localStorage.setItem("ct.seenVersion", String(cl.version));
}

async function maybeShowChangelog() {
  const cl = await fetchChangelog();
  if (!cl) return;
  if (localStorage.getItem("ct.seenVersion") !== String(cl.version)) showChangelog(cl);
}

/* ================= 语言切换：保留未保存的输入，重绘所有动态内容 ================= */
function snapshotPanels() {
  return {
    tasks: $$("#taskMap select").map((el) => el.value),
    dayInputs: $$("#dayBody input").map((el) => el.value),
    prompts: $$("#promptList .prompt-block").map((b) => ({
      open: b.open,
      fields: $$("[data-f]", b).map((el) => (el.type === "checkbox" ? el.checked : el.value)),
    })),
  };
}

function restorePanels(s) {
  $$("#taskMap select").forEach((el, i) => { if (s.tasks[i] !== undefined) el.value = s.tasks[i]; });
  $$("#dayBody input").forEach((el, i) => { if (s.dayInputs[i] !== undefined) el.value = s.dayInputs[i]; });
  $$("#promptList .prompt-block").forEach((b, i) => {
    const snap = s.prompts[i];
    if (!snap) return;
    b.open = snap.open;
    $$("[data-f]", b).forEach((el, j) => {
      const v = snap.fields[j];
      if (v === undefined) return;
      if (el.type === "checkbox") el.checked = v;
      else el.value = v;
    });
  });
}

function refreshLanguage() {
  readDraftEdits();
  const snap = snapshotPanels();
  I18N.applyI18n();
  renderHealth();
  renderDraft();
  renderFoodPreview();
  setTheme(document.documentElement.getAttribute("data-theme"), false);
  renderDay();
  renderReportView();
  renderReportList();
  renderProfileHistory();
  renderLlmFormTitle();
  renderLlmList(state.config);
  renderTaskMap(state.config);
  renderSearchKeyPlaceholder();
  renderPrompts(state.config);
  restorePanels(snap);
  repaintBoxes();
  paintChangelog();
  $("#langSelect").value = I18N.getLang();
}

/* ================= 初始化与事件绑定 ================= */
function init() {
  setTheme((() => { try { return localStorage.getItem("ct.theme"); } catch (_) { return null; } })(), false);
  I18N.setLang(I18N.getLang());   // 确保 <html lang> 与生效语言一致
  I18N.applyI18n();
  $("#langSelect").value = I18N.getLang();

  /* ---- 本机访问口令：安卓壳以 URL 片段注入（片段不会发送给服务器） ---- */
  try {
    const m = /(?:^|[#&])token=([A-Za-z0-9_-]{8,})/.exec(location.hash || "");
    if (m) {
      localStorage.setItem("ct.token", m[1]);
      history.replaceState(null, "", location.pathname + location.search);
    }
  } catch (_) { /* 忽略：无口令时后端也不校验 */ }

  /* ---- 同意流程：未同意前不发起任何网络请求 ---- */
  $("#consentPrivacy").addEventListener("change", syncConsentButton);
  $("#consentTerms").addEventListener("change", syncConsentButton);
  $("#consentAgree").addEventListener("click", () => {
    const { privacy, terms } = consentInputs();
    if (!privacy.checked || !terms.checked) return;
    saveConsent();
    closeConsentGate();
    startApp();
  });
  $("#consentDecline").addEventListener("click", showConsentDeclined);
  $("#consentRetry").addEventListener("click", showConsentAsk);

  $("#langSelect").addEventListener("change", (e) => {
    readDraftEdits();  // 先保存草稿输入，再切换语言
    I18N.setLang(e.target.value);
    if (!$("#consentGate").classList.contains("hidden")) {
      I18N.applyI18n();          // 同意层可见时只刷新文案，不触碰数据
      $("#langSelect").value = I18N.getLang();
      return;
    }
    refreshLanguage();
  });

  const dateInputs = ["#recDate", "#dayDate", "#repDate"];
  dateInputs.forEach((s) => { $(s).value = today(); });

  $("#apiBase").value = localStorage.getItem("ct.apiBase") || "";
  $("#apiBase").addEventListener("change", (e) => {
    localStorage.setItem("ct.apiBase", e.target.value.trim());
    checkHealth();
    loadDay();
  });

  $$("nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

  $("#btnEstFood").addEventListener("click", () => estimate("food"));
  $("#foodImages").addEventListener("change", onFoodFiles);
  $("#foodPreview").addEventListener("click", (e) => {
    const i = e.target.dataset.rmImg;
    if (i === undefined) return;
    state.foodImages.splice(Number(i), 1);
    renderFoodPreview();
  });
  $("#btnEstAct").addEventListener("click", () => estimate("activity"));
  $("#btnSaveDraft").addEventListener("click", saveDraft);
  $("#btnClearDraft").addEventListener("click", () => {
    state.draft = [];
    state.draftNotes = "";
    renderDraft();
  });
  $("#draftBody").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-del]");
    if (!btn) return;
    readDraftEdits();
    state.draft.splice(Number(btn.dataset.del), 1);
    renderDraft();
  });

  $$("[data-seg]").forEach((b) => b.addEventListener("click", () => setSegment(b.dataset.seg)));

  $("#dayDate").addEventListener("change", loadDay);
  $("#dayPrev").addEventListener("click", () => shiftDay(-1));
  $("#dayNext").addEventListener("click", () => shiftDay(1));
  $("#dayBody").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-save],[data-remove]");
    if (!btn) return;
    if (btn.dataset.save) saveEntry(btn.dataset.save, btn.closest(".entry"));
    if (btn.dataset.remove) removeEntry(btn.dataset.remove);
  });

  $("#themePicker").addEventListener("click", (e) => {
    const sw = e.target.closest("[data-theme]");
    if (sw) setTheme(sw.dataset.theme);
  });

  $("#btnWeek").addEventListener("click", (e) => generateReport("week", e.currentTarget));
  $("#btnMonth").addEventListener("click", (e) => generateReport("month", e.currentTarget));
  $("#reportList").addEventListener("click", async (e) => {
    const id = e.target.dataset.report;
    if (!id) return;
    e.preventDefault();
    try {
      const r = await api("GET", `/api/reports/${id}`);
      renderReport({ ...r, period: r.period, warnings: [] });
    } catch (err) {
      toast(err.message, true);
    }
  });

  $("#profileForm").addEventListener("submit", saveProfile);
  $("#btnEstMeta").addEventListener("click", estimateMeta);

  $("#llmForm").addEventListener("submit", saveLlm);
  $("#btnLlmReset").addEventListener("click", resetLlmForm);
  $("#llmList").addEventListener("click", (e) => {
    const tgt = e.target.closest("button");
    if (!tgt) return;
    if (tgt.dataset.activate) llmAction("activate", tgt.dataset.activate);
    if (tgt.dataset.delete) llmAction("delete", tgt.dataset.delete);
    if (tgt.dataset.edit) llmAction("edit", tgt.dataset.edit);
    if (tgt.dataset.test) llmAction("test", tgt.dataset.test);
  });
  $("#btnSaveTaskMap").addEventListener("click", saveTaskMap);
  $("#searchForm").addEventListener("submit", saveSearch);
  $("#btnSearchTest").addEventListener("click", testSearch);
  $("#promptList").addEventListener("click", (e) => {
    const tgt = e.target.closest("button");
    if (!tgt) return;
    if (tgt.dataset.savePrompt) savePrompt(tgt.dataset.savePrompt, tgt.closest(".prompt-block"));
    if (tgt.dataset.resetPrompt) resetPrompt(tgt.dataset.resetPrompt);
  });

  /* ---- 数据管理 ---- */
  $("#btnExportData").addEventListener("click", exportData);
  $("#btnClearData").addEventListener("click", clearData);
  $("#btnWithdrawConsent").addEventListener("click", () => {
    if (!window.confirm(t("confirm.withdraw"))) return;
    withdrawConsent();
    location.reload();
  });

  $("#clClose").addEventListener("click", closeChangelog);
  $("#changelogModal").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeChangelog(); });
  $("#btnChangelog").addEventListener("click", async () => {
    const cl = await fetchChangelog();
    if (cl) showChangelog(cl); else toast(t("toast.noChangelog"), true);
  });

  renderDraft();
  renderHealth();

  /* 未同意：只显示同意层并结束初始化——不联网、不加载任何数据。
     同意按钮的回调会调用 startApp() 继续。 */
  if (!hasConsented()) {
    openConsentGate();
  } else {
    startApp();
  }
}

/* 取得同意后才执行：健康检查、加载数据、必要时弹更新日志 */
function startApp() {
  checkHealth().then((ok) => { if (ok) loadDay(); }).finally(maybeShowChangelog);
}

document.addEventListener("DOMContentLoaded", init);
