/* 热量管理前端：独立静态页面，只通过 HTTP API 与后端通信。 */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (x, d = 0) => (x === null || x === undefined || x === "" ? "—" : Number(x).toFixed(d));
const today = () => new Date().toISOString().slice(0, 10);

const state = { config: null, draft: [], draftNotes: "", dayLoaded: null };

/* ---------------- API ---------------- */
function apiBase() {
  const v = localStorage.getItem("ct.apiBase") || "";
  return v.replace(/\/+$/, "");
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(apiBase() + path, opts);
  } catch (err) {
    throw new Error(`无法连接后端（${apiBase() || "同源"}）：${err.message}`);
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
  const el = $(sel);
  el.textContent = msg;
  el.className = "status " + kind;
}

async function withBusy(btn, fn) {
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "处理中…";
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

function showTab(name) {
  $$("nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (name === "day") loadDay();
  if (name === "report") loadReportList();
  if (name === "profile") loadProfile();
  if (name === "settings") loadConfig();
}

/* ---------------- 健康检查 ---------------- */
async function checkHealth() {
  const pill = $("#health");
  try {
    const h = await api("GET", "/api/health");
    pill.textContent = `已连接 v${h.version}`;
    pill.className = "pill ok";
    return true;
  } catch (err) {
    pill.textContent = "未连接";
    pill.className = "pill bad";
    pill.title = err.message;
    return false;
  }
}

/* ================= 记录 ================= */
function draftRow(it, i) {
  const isAct = it.kind === "activity";
  const amount = isAct ? it.minutes : it.grams;
  return `<tr data-i="${i}">
    <td><span class="badge ${it.kind}">${isAct ? "运动" : "饮食"}</span></td>
    <td><input data-f="name" value="${esc(it.name)}"></td>
    <td>${isAct ? "" : `<input data-f="meal" value="${esc(it.meal || "")}" size="4">`}</td>
    <td><input data-f="${isAct ? "minutes" : "grams"}" type="number" step="0.1" value="${amount ?? ""}"></td>
    <td><input data-f="kcal" type="number" step="0.1" value="${it.kcal ?? ""}"></td>
    <td>${isAct ? "" : `<input data-f="protein_g" type="number" step="0.1" value="${it.protein_g ?? ""}">`}</td>
    <td>${isAct ? "" : `<input data-f="carb_g" type="number" step="0.1" value="${it.carb_g ?? ""}">`}</td>
    <td>${isAct ? "" : `<input data-f="fat_g" type="number" step="0.1" value="${it.fat_g ?? ""}">`}</td>
    <td>${it.confidence ? `<span class="badge ${esc(it.confidence)}">${esc(it.confidence)}</span>` : ""}</td>
    <td title="${esc(it.basis || "")}">${esc((it.basis || "").slice(0, 28))}</td>
    <td><button class="small danger" data-del="${i}">移除</button></td>
  </tr>`;
}

function renderDraft() {
  const card = $("#draftCard");
  card.hidden = state.draft.length === 0 && !state.draftNotes;
  $("#draftNotes").textContent = state.draftNotes || "";
  $("#draftBody").innerHTML = state.draft.map(draftRow).join("");
}

function readDraftEdits() {
  $$("#draftBody tr").forEach((tr) => {
    const i = Number(tr.dataset.i);
    const it = state.draft[i];
    if (!it) return;
    $$("input", tr).forEach((inp) => {
      const f = inp.dataset.f;
      if (f === "minutes" || f === "grams") it[it.kind === "activity" ? "minutes" : "grams"] = numOrNull(inp.value);
      else if (f === "name" || f === "meal") it[f] = inp.value.trim();
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
  if (!text.trim()) return toast(kind === "food" ? "请先输入饮食描述" : "请先输入运动描述", true);
  setStatus("#estStatus", "AI 正在估算（可能会联网搜索，请稍候）…", "busy");
  try {
    const path = kind === "food" ? "/api/estimate/food" : "/api/estimate/activity";
    const body = kind === "food" ? { text, date, meal } : { text, date };
    const res = await withBusy(btn, () => api("POST", path, body));
    state.draft.push(...res.items.map((it) => ({ ...it, meal: it.meal || meal || "" })));
    state.draftNotes = [res.notes, ...(res.warnings || [])].filter(Boolean).join("；");
    renderDraft();
    const extra = res.search_used ? "（已参考联网搜索）" : "";
    setStatus("#estStatus", `估算完成，共 ${res.items.length} 条${extra}，请核对后保存`, "ok");
    text && (kind === "food" ? ($("#foodText").value = "") : ($("#actText").value = ""));
  } catch (err) {
    setStatus("#estStatus", err.message, "err");
    if (err.detail && err.detail.raw) console.warn("LLM 原始输出：", err.detail.raw);
  }
}

async function saveDraft() {
  readDraftEdits();
  const valid = state.draft.filter((it) => it.name && it.kcal !== null && it.kcal !== undefined);
  if (!valid.length) return toast("没有可保存的条目（名称和热量必填）", true);
  const date = $("#recDate").value || today();
  try {
    await withBusy($("#btnSaveDraft"), () => api("POST", "/api/entries", { date, items: valid }));
    toast(`已保存 ${valid.length} 条到 ${date}`);
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
    const d = await api("GET", `/api/days/${date}`);
    state.dayLoaded = d;
    const bal = d.balance;
    const balCls = bal === null ? "" : bal < 0 ? "neg" : "pos";
    $("#daySummary").innerHTML = [
      kpi("摄入 kcal", fmt(d.intake)),
      kpi("运动消耗 kcal", fmt(d.exercise)),
      kpi("维持消耗 kcal", fmt(d.maintenance_kcal)),
      kpi("总消耗 kcal", fmt(d.burn)),
      kpi("热量差 kcal", fmt(bal), balCls),
      kpi("蛋白/碳水/脂肪 g", `${fmt(d.protein_g)} / ${fmt(d.carb_g)} / ${fmt(d.fat_g)}`),
    ].join("");
    $("#dayWarn").innerHTML = (d.warnings || []).map((w) => `<p class="status err">${esc(w)}</p>`).join("");
    $("#dayBody").innerHTML = d.entries.length
      ? d.entries.map(entryRow).join("")
      : `<tr><td colspan="10" class="hint">这一天还没有记录</td></tr>`;
  } catch (err) {
    toast(err.message, true);
  }
}

function entryRow(e) {
  const isAct = e.kind === "activity";
  return `<tr data-id="${e.id}">
    <td><span class="badge ${e.kind}">${isAct ? "运动" : "饮食"}</span></td>
    <td>${esc(e.meal || "")}</td>
    <td><input data-f="name" value="${esc(e.name)}"></td>
    <td class="num">${isAct ? fmt(e.minutes, 0) : fmt(e.grams, 0)}</td>
    <td><input data-f="kcal" type="number" step="0.1" value="${e.kcal}" style="width:90px"></td>
    <td class="num">${isAct ? "" : fmt(e.protein_g, 1)}</td>
    <td class="num">${isAct ? "" : fmt(e.carb_g, 1)}</td>
    <td class="num">${isAct ? "" : fmt(e.fat_g, 1)}</td>
    <td><small>${esc(e.llm_name || "")}</small></td>
    <td>
      <button class="small" data-save="${e.id}">保存</button>
      <button class="small danger" data-remove="${e.id}">删除</button>
    </td>
  </tr>`;
}

async function saveEntry(id, tr) {
  const fields = {};
  $$("input", tr).forEach((inp) => {
    const f = inp.dataset.f;
    fields[f] = f === "name" ? inp.value.trim() : numOrNull(inp.value);
  });
  try {
    await api("PUT", `/api/entries/${id}`, fields);
    toast("已保存");
    loadDay();
  } catch (err) {
    toast(err.message, true);
  }
}

async function removeEntry(id) {
  if (!confirm("确定删除这条记录？")) return;
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

function renderReport(r) {
  const s = r.stats;
  const a = r.analysis;
  const label = r.period === "week" ? "周报告" : "月报告";
  const header = `<h2>${label}：${s.start} ~ ${s.end}</h2>`;
  const kpis = `<div class="kpis">
    ${kpi("记录天数", `${s.days_logged} / ${s.days_total}`)}
    ${kpi("记录日均摄入 kcal", fmt(s.avg_intake_logged_days))}
    ${kpi("记录日均运动 kcal", fmt(s.avg_exercise_logged_days))}
    ${kpi("运动总量 kcal", fmt(s.total_exercise))}
    ${kpi("记录日均热量差 kcal", fmt(s.avg_balance_logged_days), (s.avg_balance_logged_days ?? 0) < 0 ? "neg" : "pos")}
    ${kpi("累计热量差 kcal", fmt(s.total_balance), (s.total_balance ?? 0) < 0 ? "neg" : "pos")}
    ${kpi("体重变化 kg", s.weight_change_kg === null ? "—" : fmt(s.weight_change_kg, 1))}
  </div>`;
  const daily = `<div class="table-wrap"><table>
      <thead><tr><th>日期</th><th>条数</th><th>摄入</th><th>运动</th><th>热量差</th></tr></thead>
      <tbody>${s.daily.map((d) => `<tr><td>${d.date}</td><td>${d.entries}</td><td class="num">${fmt(d.intake)}</td>
        <td class="num">${fmt(d.exercise)}</td><td class="num">${fmt(d.balance)}</td></tr>`).join("")}</tbody>
    </table></div>`;
  let analysis = `<p class="hint">未调用 AI 分析。</p>`;
  if (a) {
    analysis = `<div class="scores">
        <div class="score">${fmt(a.diet_score)}<small>饮食健康</small></div>
        <div class="score">${fmt(a.exercise_score)}<small>运动评分</small></div>
        <div class="score">${esc(a.exercise_level || "—")}<small>运动水平</small></div>
      </div>
      <p>${esc(a.summary || "")}</p>
      ${listBullets("饮食点评", a.diet_comments)}
      ${listBullets("运动点评", a.exercise_comments)}
      ${listBullets("建议", a.suggestions)}
      ${listBullets("风险提示", a.risks)}
      <p class="hint">分析模型：${esc(a.llm || "")}${a.model ? "（" + esc(a.model) + "）" : ""}</p>`;
  }
  const warn = (r.warnings || []).map((w) => `<p class="status err">${esc(w)}</p>`).join("");
  $("#reportView").innerHTML = `<div class="card">${header}${warn}${kpis}${analysis}<h3>每日明细</h3>${daily}
    <details><summary class="hint">查看原始统计 JSON</summary><pre>${esc(JSON.stringify(s, null, 2))}</pre></details></div>`;
}

async function generateReport(period, btn) {
  const date = $("#repDate").value || today();
  const analyze = $("#repAnalyze").checked;
  setStatus("#repStatus", analyze ? "正在统计并请求 AI 分析，可能需要几十秒…" : "正在统计…", "busy");
  try {
    const r = await withBusy(btn, () => api("POST", "/api/reports", { period, date, analyze }));
    renderReport(r);
    (r.warnings || []).length ? setStatus("#repStatus", "已生成（部分提示见报告）", "ok") : setStatus("#repStatus", "已生成", "ok");
    loadReportList();
  } catch (err) {
    setStatus("#repStatus", err.message, "err");
  }
}

async function loadReportList() {
  try {
    const { reports } = await api("GET", "/api/reports");
    $("#reportList").innerHTML = reports.length
      ? reports.map((r) => `<li><a href="#" data-report="${r.id}">${r.period === "week" ? "周" : "月"} ${r.start} ~ ${r.end}</a><small>${esc(r.created_at)}</small></li>`).join("")
      : `<li class="hint">还没有历史报告</li>`;
  } catch (err) {
    toast(err.message, true);
  }
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
    $("#profileHistory").innerHTML = history.map((h) => `<tr>
        <td>${h.effective_date}</td><td>${fmt(h.data.weight_kg, 1)}</td><td>${fmt(h.data.bmr_kcal)}</td>
        <td>${fmt(h.data.maintenance_kcal)}</td><td>${esc(h.data.activity_text || "")}</td><td><small>${esc(h.created_at)}</small></td>
      </tr>`).join("") || `<tr><td colspan="6" class="hint">暂无</td></tr>`;
  } catch (err) {
    toast(err.message, true);
  }
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
    toast("身体数据已保存");
    loadProfile();
  } catch (err) {
    toast(err.message, true);
  }
}

async function estimateMeta() {
  const btn = $("#btnEstMeta");
  $("#metaResult").textContent = "AI 正在估算…";
  try {
    const r = await withBusy(btn, () => api("POST", "/api/profile/estimate-metabolism", { date: today() }));
    $("#metaResult").innerHTML = `AI 估算：BMR <b>${fmt(r.bmr_kcal)}</b> kcal，维持消耗 <b>${fmt(r.maintenance_kcal)}</b> kcal。
      依据：${esc(r.basis || "")}（模型：${esc(r.llm)}）。点击「保存」后生效。`;
    const form = $("#profileForm");
    form.elements.bmr_kcal.value = r.bmr_kcal;
    form.elements.maintenance_kcal.value = r.maintenance_kcal;
  } catch (err) {
    $("#metaResult").textContent = err.message;
  }
}

/* ================= 设置：LLM ================= */
function resetLlmForm() {
  const f = $("#llmForm");
  f.reset();
  f.elements.id.value = "";
  f.elements.temperature.value = "0.2";
  f.elements.max_tokens.value = "4096";
  f.elements.json_mode.checked = true;
  $("#llmFormTitle").textContent = "新增档案";
}

function fillLlmForm(p) {
  const f = $("#llmForm");
  ["id", "name", "protocol", "model", "base_url", "temperature", "max_tokens", "extra_body"].forEach((k) => {
    f.elements[k].value = p[k] ?? "";
  });
  f.elements.api_key.value = "";
  f.elements.json_mode.checked = !!p.json_mode;
  $("#llmFormTitle").textContent = `编辑：${p.name}（留空 Key 则保持不变）`;
  f.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderLlmList(c) {
  const active = c.active_llm_id;
  $("#llmList").innerHTML = c.llm_profiles.length
    ? c.llm_profiles.map((p) => `<tr>
        <td><b>${esc(p.name)}</b></td><td>${esc(p.protocol)}</td><td>${esc(p.model)}</td>
        <td><small>${esc(p.base_url)}</small></td>
        <td>${p.api_key_set ? esc(p.api_key_hint) : '<span class="pill bad">未设置</span>'}</td>
        <td>${p.id === active ? '<span class="pill ok">默认</span>' : `<button class="small" data-activate="${p.id}">设为默认</button>`}</td>
        <td>
          <button class="small" data-test="${p.id}">测试连接</button>
          <button class="small" data-edit="${p.id}">编辑</button>
          <button class="small danger" data-delete="${p.id}">删除</button>
        </td></tr>`).join("")
    : `<tr><td colspan="7" class="hint">还没有 LLM 档案。请在下方添加。</td></tr>`;
}

function renderTaskMap(c) {
  const opts = (sel) => `<option value="">跟随默认</option>` + c.llm_profiles.map((p) =>
    `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.name)} · ${esc(p.model)}</option>`).join("");
  $("#taskMap").innerHTML = c.tasks.map((t) => `<label>${esc(t.label)}
      <select data-task="${t.id}">${opts(c.task_llm[t.id] || "")}</select></label>`).join("");
}

function renderSearch(c) {
  const f = $("#searchForm");
  f.elements.provider.value = c.search.provider;
  f.elements.base_url.value = c.search.base_url || "";
  f.elements.api_key.value = "";
  f.elements.api_key.placeholder = c.search.api_key_set ? `已设置（${c.search.api_key_hint}），留空保持不变` : "";
}

function renderPrompts(c) {
  $("#promptList").innerHTML = c.tasks.map((t) => {
    const p = c.prompts[t.id];
    return `<div class="prompt-block" data-task="${t.id}">
      <h3>${esc(t.label)}</h3>
      <div class="grid two">
        <label>系统提示词<textarea rows="5" data-f="system">${esc(p.system)}</textarea></label>
        <label>用户模板<textarea rows="5" data-f="user">${esc(p.user)}</textarea></label>
        <label>联网搜索查询模板<input data-f="search_query" value="${esc(p.search_query)}"></label>
        <label class="check"><input type="checkbox" data-f="use_search" ${p.use_search ? "checked" : ""}> 使用程序搜索结果</label>
      </div>
      <div class="row">
        <button class="primary small" data-save-prompt="${t.id}">保存此模板</button>
        <button class="small" data-reset-prompt="${t.id}">恢复默认</button>
      </div>
    </div>`;
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
    toast("LLM 档案已保存");
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
      if (!confirm("删除这个 LLM 档案？")) return;
      state.config = await api("DELETE", `/api/config/llm/${id}`);
      resetLlmForm();
    } else if (action === "edit") {
      const p = (state.config?.llm_profiles || []).find((x) => x.id === id);
      if (p) fillLlmForm(p);
      return;
    } else if (action === "test") {
      $("#llmTestResult").textContent = "测试中…";
      $("#llmTestResult").className = "status busy";
      const r = await api("POST", "/api/llm/test", { id });
      setStatus("#llmTestResult", `连接成功：${r.name}（${r.model}），耗时 ${r.latency_ms} ms`, "ok");
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
    toast("任务映射已保存");
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
    toast("搜索设置已保存");
    renderSearch(state.config);
  } catch (err) {
    toast(err.message, true);
  }
}

async function testSearch() {
  setStatus("#searchTestResult", "搜索中…", "busy");
  try {
    const r = await api("POST", "/api/search/test", { query: $("#searchTestQ").value.trim() });
    setStatus("#searchTestResult", `返回 ${r.count} 条结果`, "ok");
    $("#searchTestResult").innerHTML = `<ul class="bullets">${r.results.map((x) =>
      `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>：${esc(x.snippet)}</li>`).join("")}</ul>`;
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
    toast("提示词已保存");
  } catch (err) {
    toast(err.message, true);
  }
}

async function resetPrompt(task) {
  if (!confirm("恢复该任务的默认提示词？")) return;
  try {
    state.config = await api("DELETE", `/api/config/prompts/${task}`);
    renderPrompts(state.config);
    toast("已恢复默认");
  } catch (err) {
    toast(err.message, true);
  }
}

/* ================= 初始化与事件绑定 ================= */
function init() {
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
  $("#btnEstAct").addEventListener("click", () => estimate("activity"));
  $("#btnSaveDraft").addEventListener("click", saveDraft);
  $("#btnClearDraft").addEventListener("click", () => {
    state.draft = [];
    state.draftNotes = "";
    renderDraft();
  });
  $("#draftBody").addEventListener("click", (e) => {
    const i = e.target.dataset.del;
    if (i === undefined) return;
    readDraftEdits();
    state.draft.splice(Number(i), 1);
    renderDraft();
  });

  $("#dayDate").addEventListener("change", loadDay);
  $("#dayBody").addEventListener("click", (e) => {
    const save = e.target.dataset.save;
    const remove = e.target.dataset.remove;
    if (save) saveEntry(save, e.target.closest("tr"));
    if (remove) removeEntry(remove);
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
    const t = e.target;
    if (t.dataset.activate) llmAction("activate", t.dataset.activate);
    if (t.dataset.delete) llmAction("delete", t.dataset.delete);
    if (t.dataset.edit) llmAction("edit", t.dataset.edit);
    if (t.dataset.test) llmAction("test", t.dataset.test);
  });
  $("#btnSaveTaskMap").addEventListener("click", saveTaskMap);
  $("#searchForm").addEventListener("submit", saveSearch);
  $("#btnSearchTest").addEventListener("click", testSearch);
  $("#promptList").addEventListener("click", (e) => {
    const t = e.target;
    if (t.dataset.savePrompt) savePrompt(t.dataset.savePrompt, t.closest(".prompt-block"));
    if (t.dataset.resetPrompt) resetPrompt(t.dataset.resetPrompt);
  });

  renderDraft();
  checkHealth().then((ok) => { if (ok) loadDay(); });
}

document.addEventListener("DOMContentLoaded", init);
