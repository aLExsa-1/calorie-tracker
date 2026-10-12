# 任务：前端 v0.2 布局优化 + 极简美化 + 首次更新日志弹窗

执行方：前端（Kimi 角色）。只允许修改：`frontend/index.html`、`frontend/style.css`、`frontend/app.js`。
禁止：改后端、改 `android/` 下任何文件（含 `android/app/src/main/python/` 副本）、读 `data/`、`.android-build/`。
读取范围仅限上述三个文件。

## 背景
纯静态前端（无构建），后端 API 不变。Android WebView 内运行，主要在手机竖屏（360–412px）使用，也在桌面浏览器使用。
手机实拍暴露的问题：
- 顶栏：导航、「后端」输入框、连接状态挤成多行，后端输入框占掉约 1/6 屏高。
- 每日页：10 列表格只能横滚，名称输入框被压成细条，表头竖排，蛋白/碳水/脂肪被截断；KPI 单列占满整屏。
- 身体数据页：历史版本表格逐字换行，「保存时间」被截断。
- 设置页：LLM 档案表 7 列被截断（看不到「默认」和操作按钮）；接口地址占位符过长被截断；提示词模板 3–4 大块全部展开，页面极长。
- 记录页：草稿表 11 列，手机不可用。

## 要求

### A. 布局
1. 顶栏：第一行 = 品牌名 + 连接状态 pill（保持 `#health`，文本形如「已连接 v0.2」）。
   导航 `nav`（按钮仍为 `nav button[data-tab]`）：宽度 ≤ 780px 时固定在屏幕底部成为标签栏（用 `env(safe-area-inset-bottom)`；main 底部留足 padding 不被遮挡）；> 780px 时仍在顶部。
2. 「后端」输入框保留 `#apiBase`（localStorage 键 `ct.apiBase`，change 逻辑不变），整块从顶栏移到「设置」页最底部的 `<details>`（标题「高级：后端地址」，默认收起）。
3. 表格 → 卡片：宽度 ≤ 780px 时，下列表格不再横向滚动，每行 `tr` 变成块状卡片，单元格用 `data-label` + CSS `::before` 显示字段名：
   每日明细 `#dayBody`、记录草稿 `#draftBody`、身体数据历史 `#profileHistory`、LLM 档案 `#llmList`。
   做法：修改 `entryRow` / `draftRow` / `renderLlmList` / `loadProfile` 的模板，给 `<td>` 加 `data-label`；卡片内输入框占满宽，操作按钮一行排列。
   **必须保留所有现有 data 属性、id、class、`closest("tr")` 依赖和事件绑定**（`data-f`、`data-save`、`data-remove`、`data-del`、`data-edit`、`data-test`、`data-activate`、`data-delete`、`data-report` 等）。桌面宽度保持表格形式。
4. 每日 KPI（`.kpis`）：窄屏两列；「热量差」突出（更大字号，占满一行）。每日页标题与日期选择器分两行，不挤一行。
5. 设置页「提示词模板」：`renderPrompts` 里每个 `.prompt-block` 改用 `<details>`（summary 为任务名），默认收起；`savePrompt` / `resetPrompt` 逻辑不变（它们依赖 `.prompt-block` 和其中的字段，请读代码确认后保持兼容）。
6. 表单：手机单列；input/select/textarea 统一高度约 40px、字号 ≥ 16px（避免 iOS/安卓聚焦缩放）；`.row` 按钮可换行；主按钮在窄屏可占满宽。
7. LLM 接口地址 input 的 placeholder 缩短为「https://api.deepseek.com/v1」，说明文字放到 label 下方的小字提示（OpenAI 与 Anthropic 示例各一行）。

### B. 美化（极简）
- 白/灰为主，单一强调色（#2f6fed 或略柔和），用 CSS 变量统一管理：颜色、圆角、间距、阴影、字号刻度。
- 背景：纯 CSS，`linear-gradient`（浅蓝灰 → 近白）叠加极淡 `radial-gradient` 光晕；`background-attachment: fixed`。不使用图片、外部字体、CDN。
- 卡片：圆角 14px，去重边框改为极淡阴影（如 `0 1px 2px rgba(0,0,0,.04), 0 4px 16px rgba(20,30,60,.04)`），内边距充足。
- 按钮/标签 150ms 过渡；激活标签用强调色浅底；`@media (prefers-reduced-motion: reduce)` 关闭动画。
- 表头、badge、pill、toast 与新风格一致；保留 `.pill.ok/.bad`、`.badge.*`、`.status.*` 语义色。

### C. 首次使用更新日志弹窗
- 新增模态框（遮罩 + 居中卡片，窄屏近全宽）：标题「更新日志 v{version}」，条目 `<ul>`，底部「知道了」按钮。点击遮罩或按钮关闭。
- 数据来自静态文件 `changelog.json`（由另一任务写入 `frontend/changelog.json`），格式：
  `{"version":"0.2","date":"2026-10-12","items":["…","…"]}`。用 `fetch("changelog.json")`（相对路径，**同源，不加 apiBase 前缀**）。条目用 `esc()` 转义。
- 触发：`init()` 中 `checkHealth()` 完成后（无论成功失败）拉取 changelog；若 `localStorage["ct.seenVersion"]` !== changelog.version，则弹出；关闭时写入 `ct.seenVersion = changelog.version`。拉取失败则静默跳过且不写入 seenVersion，不影响应用。
- 「设置」页最底部（「高级」details 之前或之后均可）加按钮「查看更新日志」，可手动弹出（不改 seenVersion 逻辑以外的状态）。
- 开发时若 `changelog.json` 尚不存在，可自行临时建一个用于验证，但 **最终不要覆盖** 另一任务已写入的版本（先检查文件是否存在；存在则不要改）。

## 验收
- 用 Node/静态服务器或 `python -m backend serve` 打开，在 390×844 视口逐页检查：记录、每日、报告、身体数据、设置，无横向滚动、无截断。
- `app.js` 对后端 API 的调用（路径、方法、请求体）一个字符都不要改。
- 运行 `node --check frontend/app.js` 通过。
- 完成后在本文件末尾追加「结果摘要」（≤ 300 字）和改动文件清单。


## 结果摘要（ui-v02，已完成）

- 布局：顶栏仅保留品牌 + `#health`；≤780px 时 `nav` 固定底部（safe-area），main 留出底部 padding；>780px 仍在顶部。`#apiBase` 移入设置页底部「关于」卡片的 `<details>`「高级：后端地址」，并新增「查看更新日志」按钮。
- 表格卡片化：`#dayBody`/`#draftBody`/`#profileHistory`/`#llmList` 的 `<td>` 加 `data-label`，窄屏 `table.cards` 以 `::before` 显示字段名；所有 data 属性、class、id、事件绑定、API 调用均未改动。
- KPI 窄屏两列，热量差整行突出；每日标题与日期分两行；提示词模板改为 `<details class="prompt-block">`（默认收起，savePrompt/resetPrompt 逻辑未改）；表单控件 40px 高、16px 字号；LLM 接口地址 placeholder 缩短，示例移入小字提示。
- 美化：CSS 变量统一颜色/圆角/间距/阴影/字号；渐变+径向光晕固定背景；卡片 14px 圆角淡阴影；150ms 过渡；`prefers-reduced-motion` 关闭动画。
- 更新日志弹窗：`fetch("changelog.json")` 同源；`checkHealth()` 完成后（finally）按 `ct.seenVersion` 判断弹出；关闭写入 seenVersion；失败静默。`frontend/changelog.json` 已存在，未改动。
- 验证：`node --check frontend/app.js` 通过；`python -m backend serve --port 8799` 临时数据目录下首页、changelog.json、/api/health 均 200，进程已关闭。未做 390×844 浏览器视觉检查（无浏览器截图工具），建议真机/浏览器复核。

改动文件：`frontend/index.html`、`frontend/style.css`、`frontend/app.js`、`docs/tasks/ui-v02.md`