# 热量管理（独立前端 + 后端）

规则框架由程序搭建，食物热量、运动消耗、基础代谢和报告分析都由你配置的 LLM 完成（可选联网搜索）。程序不内置食物库或 MET 表。

> English version: see [English](#english) at the bottom of this file.

## 电脑版

### 下载与解压

电脑版发布包为 `calorie-tracker-0.4.0-windows.zip`（约 107 KB，只含程序代码，不含个人数据；含《隐私政策》《用户协议》两份协议页）。解压到任意目录即可，例如 `C:\Apps\calorie-tracker`。重新打包：`python .android-build/make_windows_zip.py`。

### 环境要求

- Windows，已安装 Python（并勾选「Add python.exe to PATH」）。开发与测试环境为 Python 3.14；更低版本未经验证。
- 后端只使用 Python 标准库，**无需 `pip install`**。

### 启动方式

**方式一：双击 `start-windows.bat`**（推荐）。脚本会自动切换到自身所在目录再启动，因此解压到哪里都能用。

**方式二：手动启动**。先在解压后的 `calorie-tracker` 文件夹中打开终端（资源管理器地址栏输入 `cmd` 回车即可），然后执行：

```powershell
python -m backend serve --port 8787
```

启动后，浏览器打开 http://127.0.0.1:8787 即可使用。服务只监听本机回环地址（127.0.0.1），不会对局域网开放。关闭终端窗口即停止服务。

可选参数：`--port` 修改端口，`--data-dir` 指定数据目录（默认为程序目录下的 `data/`）。

前端是纯静态页面（frontend/），不依赖构建，也可以用任何静态服务器单独托管；若后端不在同一地址，在「设置」页底部「高级：后端地址」中填入后端地址。

### 数据位置

数据默认保存在解压目录下的 `data/`（`ct.db` 为记录，`config.json` 为 LLM 与提示词配置，含明文 API Key，请勿分享）。**升级时请保留旧目录中的 `data/` 文件夹**，或直接覆盖解压新版本（发布包不包含 `data/`，不会覆盖已有数据）。

## 安卓版 APK

本仓库同时提供打包好的安卓应用（0.4.0）：APK 内嵌 Python 运行时与后端，**不需要电脑即可使用**，数据保存在手机应用私有目录。

```
android/CalorieTracker-0.4.0-arm64.apk   约 22.1 MB，仅 arm64-v8a，Android 7.0+
```

安装后首次启动会先显示《隐私政策》与《用户协议》的同意页，然后需在「设置」页填一次 LLM 档案（地址 / 模型 / API Key）。0.4.0 的真机复测尚未完成，详见 [android/README-Android.md](android/README-Android.md)。构建方法、与电脑版的差异、已验证与未验证事项也在该文件中。

## 目录

```
backend/
  __main__.py  命令行入口：python -m backend serve
  server.py    HTTP API + 静态文件（标准库，无第三方依赖）
  engine.py    业务规则：组装提示词、调用 AI、校验、热量差、周/月统计
  config.py    LLM 档案、搜索服务、提示词、任务到模型映射（持久化为 JSON）
  llm.py       通用 LLM 调用：OpenAI 兼容 / Anthropic 协议，支持 extra_body 合并，支持图片输入
  search.py    联网搜索适配：SearXNG / Tavily / Brave
  prompts.py   四类 AI 任务的默认提示词与输出格式约定
  schemas.py   AI 输出的类型与取值范围校验
  store.py     SQLite：身体数据历史版本、记录、报告
frontend/
  index.html / style.css / app.js   独立前端（记录、每日、报告、身体数据、设置）
  privacy.html / terms.html         隐私政策与用户协议（中英双语，可单独托管给商店审核）
  i18n.js / changelog.json         中英文文案与更新日志
tests/
  test_e2e.py  端到端测试（真实后端 HTTP + 本地模拟 LLM 与搜索服务）
  mock_llm.py  模拟 OpenAI / Anthropic / SearXNG
tests/tools/   ui_demo.py 演示数据服务、cdp.mjs / shoot.mjs 无头浏览器截图自检（开发用）
start-windows.bat  Windows 启动脚本
android/       安卓壳（Chaquopy + WebView）与 APK
```

## AI 任务（四类）

| 任务 | 输入 | 输出（由程序校验） |
|---|---|---|
| 饮食估算 food_estimate | 描述、可选食物图片、餐次、身体数据 | 名称、克数、热量、蛋白/碳水/脂肪、置信度、依据 |
| 运动估算 activity_estimate | 描述、身体数据 | 名称、分钟、净增量热量、依据 |
| 代谢估算 metabolism_estimate | 身体数据 | BMR、维持消耗、依据 |
| 报告分析 report_analysis | 周期、身体数据、统计 JSON | 饮食分、运动分、运动水平、点评、建议、风险 |

每类任务可在设置页单独指定 LLM 档案；未指定则用默认档案。提示词可自由修改，输出 JSON 结构由程序固定追加。

## 功能概览

- **记录**：「饮食 / 运动」分段切换。饮食可输入文字描述，也可上传食物图片（最多 4 张，每张不超过 5 MB，自动压缩后上传）；AI 估算后生成草稿卡片，餐次通过下拉选择。
- **自定义条目库（0.4.0）**：不想让 AI 估算时，可手动录入自己的食物（每份热量、克数、蛋白质／碳水／脂肪、份量说明）或运动（每次消耗热量、对应时长）。选中条目后按份数或分钟数「加入草稿」，与 AI 估算一样核对后再保存；运动按时长比例换算热量。数据只保存在本机，并包含在导出与清除中。
- **每日**：大号热量差卡片，摄入与消耗并排，三大营养素分段条；明细按早餐 / 午餐 / 晚餐 / 加餐 / 运动分组，可前后翻日期，支持修改与删除。
- **报告**：周 / 月报告，统计由程序完成，分数带进度条；可勾选交给 AI 做分析；历史报告可再次打开。
- **身体数据**：分为「基础信息 / 日常与目标 / 代谢指标」，按生效日期保存历史版本（时间线展示），修改不会改写过去的报告。
- **设置**：
  - 多套 LLM 档案（OpenAI 兼容 / Anthropic 协议），可设默认、测试连接；
  - 额外参数 extra_body（JSON 对象，会合并进请求体）；
  - 联网搜索：SearXNG / Tavily / Brave / 不启用；
  - 提示词模板：系统提示词、用户模板、搜索查询模板，可单独恢复默认；
  - 界面配色：森林奶油 / 海盐蓝 / 桑葚紫，立即生效并记住（仅保存在本设备）；
  - 界面语言：简体中文（默认）/ English，切换后立即生效；
  - 高级：后端地址。
- **更新日志**：首次使用或升级后自动弹出（中英文均有），设置页可再次查看。
- **手机适配**：窄屏下表格改为卡片，底部标签栏导航。

## 配置页能做的事

- **LLM 档案**：多套，协议选 OpenAI 兼容或 Anthropic，填写地址、模型、Key、temperature、max_tokens；可设为默认、测试连接。
- **预设提供商（0.4.0）**：表单顶部「预设提供商」可一键填入 DeepSeek、智谱 GLM、Kimi（月之暗面）、阿里云百炼（通义千问）、OpenAI、Anthropic、Google Gemini、OpenRouter、硅基流动、xAI、火山方舟（豆包）、Mistral、MiniMax 的接口地址与协议。预设的模型名仅作参考，模型会更新，请点「获取可用模型」向服务商查询最新列表，再从下拉中选择。
- **获取可用模型（0.4.0）**：新增或编辑档案时，点「获取可用模型」会调用服务商的模型列表接口（OpenAI 协议 `GET /models`，Anthropic 协议 `GET /v1/models`）。未保存的档案也可直接查询，使用表单里临时填写的协议、地址与 Key。
- **额外参数 extra_body**：JSON 对象，会合并进请求体。例如启用 Anthropic 原生联网搜索：{"tools":[{"type":"web_search_20250305","name":"web_search","max_uses":3}]}
- **联网搜索**：SearXNG / Tavily / Brave / 不启用。搜索结果拼进提示词；搜索失败会跳过并在结果中提示，不中断估算。
- **提示词模板**：系统提示词、用户模板、搜索查询模板，可单独恢复默认。

## 数据流程

1. 在「记录」页输入饮食或运动描述（饮食还可上传图片），AI 估算后生成草稿（未保存）。
2. 在草稿中逐条修改名称、克数、热量等，可删除不要的条目。
3. 保存后进入当日记录；在「每日」页可再次修改热量或删除，热量差实时重算。
4. 热量差 = 摄入 − (维持消耗 + 运动消耗)。维持消耗来自「身体数据」页（手动填写或让 AI 估算）。
5. 「报告」页生成周/月报告：统计在程序内完成，勾选后交给 AI 做分析。

## 验证情况

已通过的自动化测试（均在本机运行，退出码为 0）：

- `python -m unittest tests.test_e2e`：68 项端到端测试（0.4.0 新增：自定义条目库增删改与校验、库条目记入日汇总、预设提供商列表、模型列表查询的 URL 与认证头、错误映射、导出与清除覆盖条目库、前端契约与双语文案）。此前覆盖：覆盖 LLM 档案增删改与 Key 脱敏、非法配置拦截、提示词覆盖与恢复、饮食估算（含搜索结果拼接与自定义提示词）、运动估算（Anthropic 协议）、extra_body 合并、搜索失败降级、AI 输出不合规返回 422、上游 500 返回 502、未配置 LLM 时的提示、保存与修改记录、热量差计算、身体数据版本、代谢估算、周/月报告（有无 AI 分析）、报告删除、静态页面与路径穿越防护、数据导出（不含 API Key 明文）、清除全部数据、本机访问口令校验、DNS rebinding 防护、CORS 收敛，以及前端结构契约与合规契约（同意层先于联网、协议页中英双语、免责声明）。
- 前端 frontend/app.js 通过 node --check 语法检查。
- 真实启动 `python -m backend serve`，健康检查返回正常，首页返回 200，四个 AI 任务已注册。

**尚未验证的部分**

- 没有在浏览器中逐个点击过 0.3.1 与 0.4.0 的页面。按钮交互、表格渲染、配色切换、以及首次启动的同意页需要你在浏览器里走一遍。
- 没有接入真实大模型。测试全部使用本地模拟服务，AI 估算的准确度、提示词效果、各家协议的细节差异都需要用真实 Key 验证。图片识别同样只在模拟服务上测试。
- 联网搜索只在模拟 SearXNG 上测试，Tavily 与 Brave 的适配代码未经真实请求验证。

## 注意事项

- AI 估算有误差，保存前请核对草稿；草稿中的 confidence 与 basis 可以帮助判断。
- 报告分析是 AI 生成的生活方式参考，不是医疗建议。
- API Key 以明文存在本地 `data/config.json`，界面只显示末 4 位；请勿把该文件或 `data/` 目录分享或提交到公开仓库。

## 更新日志

### v0.4.0（2026-10-13）

自定义条目库：

- 新增自定义食物：名称、每份热量、每份克数、蛋白质／碳水／脂肪、份量说明、备注
- 新增自定义运动：名称、每次消耗热量、对应时长、备注
- 选中条目后按份数（食物）或分钟数（运动）「加入草稿」，与 AI 估算共用同一套「核对后保存」的流程；运动按时长比例换算热量
- 条目只保存在本机 SQLite；「导出全部数据」与「清除全部数据」已覆盖

LLM 配置：

- 新增「预设提供商」：一键填入 13 家服务商的协议与接口地址——DeepSeek、智谱 GLM、Kimi（月之暗面）、阿里云百炼（通义千问）、OpenAI、Anthropic、Google Gemini、OpenRouter、硅基流动、xAI、火山方舟（豆包）、Mistral、MiniMax
- 新增「获取可用模型」：按 OpenAI 协议 `GET /models` 或 Anthropic 协议 `GET /v1/models` 查询上游模型列表并下拉选择；未保存的档案也能用表单里临时填写的协议、地址与 Key 查询
- 预设的模型名仅作初始参考，模型更新较快，请以「获取可用模型」的结果为准

### v0.3.1（2026-10-12）

合规与隐私（本次重点，为应用市场上架准备）：

- 新增首次启动同意页：必须阅读并勾选同意《隐私政策》与《用户协议》后才能使用；**同意之前不向任何服务器发送用户数据**（安卓壳仅探测本机内置服务是否就绪，不发送用户数据）
- 新增《隐私政策》与《用户协议》完整文档（中英文双语，`frontend/privacy.html` / `terms.html`），设置页「隐私与协议」可随时查看
- 隐私政策如实写明：开发者不运营服务器、不收集个人信息；使用 AI 估算时数据会发送到你自己配置的第三方接口，并提示优先使用 https 地址、说明数据出境风险
- 新增「数据管理」：导出全部数据为 JSON（不含 API Key 明文）、清除全部数据、撤回隐私政策同意
- AI 估算草稿与报告分析加「AI 生成，仅供参考」标识；报告页与设置页加免责声明（不构成医疗建议）
- 修复：报告无法删除（新增删除报告接口）

安全加固：

- 本地内置服务增加随机访问口令（安卓端由 `MainActivity` 生成并注入 WebView），设备上其他应用无法再直接调用本机接口
- 接口拒绝非回环 `Host`（DNS rebinding 防护）；CORS 由通配符改为仅回显回环来源；响应加 `Referrer-Policy: no-referrer` 与 `X-Content-Type-Options: nosniff`
- 安卓：关闭应用数据备份（`allowBackup=false` + 备份/迁移规则），健康记录与明文 API Key 不再可能被 adb 或云备份导出
- 安卓：默认禁止明文 HTTP，仅对 `127.0.0.1` 本机服务放行，用户填写的 `http://` 接口会被系统阻断
- 安卓：WebView 混合内容改为 `NEVER_ALLOW`

打包：

- 启用 v3 签名方案；补充英文 `strings.xml` 与自适应图标的 monochrome 层
- 版本号更新为 0.3.1（versionCode 6）

### v0.3.0（2026-10-11）

- 全新界面「森林奶油」：奶油底色、森林绿主色、石板蓝点缀，卡片更圆润
- 设置页新增「界面配色」，可切换森林奶油 / 海盐蓝 / 桑葚紫，立即生效并记住
- 每日页重做：大号热量差卡片，摄入与消耗并排，三大营养素分段条
- 每日明细按早餐 / 午餐 / 晚餐 / 加餐 / 运动分组，带图标与小计，可前后翻日期
- 记录页新增「饮食 / 运动」分段切换，草稿以卡片呈现，餐次改为下拉选择
- 身体数据页拆为「基础信息 / 日常与目标 / 代谢指标」，历史版本改为时间线
- 报告页分数加进度条；LLM 档案改为卡片，手机上更易操作
- 手机底部导航加图标，激活项为实心胶囊；安卓启动页与状态栏同步浅色
- 所有功能与数据保持不变，可直接覆盖安装升级
- 版本号更新为 0.3.0

### v0.2.1（2026-10-10）

- 饮食记录支持上传食物图片，由 AI 识别后估算热量
- 图片最多 4 张，每张不超过 5 MB，自动压缩后上传
- 设置页新增语言切换：简体中文（默认）与 English
- 英文界面覆盖全部页面，切换后立即生效
- 更新日志弹窗支持中英文显示
- 版本号更新为 0.2.1

### v0.2.0（2026-10-09）

- 全新应用图标：深色底配绿橙双环，象征摄入与消耗的平衡
- 手机窄屏下表格改为卡片，不再横向滚动
- 手机新增底部标签栏导航，桌面仍在顶部
- 全新极简风格：浅色渐变背景、柔和阴影、统一圆角
- 「后端地址」移入设置页底部「高级」折叠区
- 设置页提示词模板改为折叠显示，页面更短
- 每日页热量差更醒目，各项数据两列排布
- 首次使用或升级后自动弹出更新日志，设置页可再看
- 修复凌晨 0–8 点默认日期显示为前一天的问题
- 版本号更新为 0.2.0

---

<a id="english"></a>

# Calorie Tracker (standalone frontend + backend)

The program provides the rule framework. Food calories, exercise burn, basal metabolism and report analysis are all produced by an LLM you configure (optional web search). The program does not ship a food database or a MET table.

## Desktop version

### Download and unzip

The desktop release is `calorie-tracker-0.4.0-windows.zip` (about 107 KB). It contains program code only, no personal data, including both the Privacy Policy and the User Agreement pages. Unzip it anywhere, e.g. `C:\Apps\calorie-tracker`. To rebuild it: `python .android-build/make_windows_zip.py`.

### Requirements

- Windows with Python on PATH (tick "Add python.exe to PATH" during installation). Development and testing used Python 3.14; older versions are not verified.
- The backend uses only the Python standard library, so **no `pip install` is needed**.

### How to start

**Option 1: double-click `start-windows.bat`** (recommended). The script switches to its own folder first, so it works wherever you unzipped the project.

**Option 2: start manually.** Open a terminal inside the unzipped `calorie-tracker` folder (type `cmd` in the Explorer address bar and press Enter), then run:

```powershell
python -m backend serve --port 8787
```

Then open http://127.0.0.1:8787 in your browser. The server listens on the loopback address (127.0.0.1) only and is not exposed to your LAN. Close the terminal window to stop it.

Optional flags: `--port` to change the port, `--data-dir` to choose the data folder (default: `data/` inside the program folder).

The frontend (frontend/) is a plain static page with no build step. It can also be hosted by any static web server. If the backend is on a different address, fill it in under "Settings → Advanced: backend address" at the bottom of the page.

### Where data is stored

By default, data lives in `data/` inside the program folder: `ct.db` holds your records, and `config.json` holds the LLM and prompt settings, including your API key in plain text. Do not share it. **When upgrading, keep the old `data/` folder**. The release zip does not contain `data/`, so overwriting with a new version will not delete your data.

## Android APK

The repository also ships a packaged Android app (0.4.0). The APK embeds the Python runtime and backend, so **a computer is not needed**. Data is stored in the app's private storage on the phone. First launch shows the Privacy Policy and User Agreement consent screen; the bilingual pages ship inside the APK.

```
android/CalorieTracker-0.4.0-arm64.apk   about 22.1 MB, arm64-v8a only, Android 7.0+
```

On first use, enter one LLM profile (URL / model / API key) in the Settings page. Real-device testing of 0.4.0 is not finished yet. See [android/README-Android.md](android/README-Android.md) for build steps, differences from the desktop version, and what has and has not been verified.

## Project layout

```
backend/
  __main__.py  CLI entry: python -m backend serve
  server.py    HTTP API + static files (standard library only)
  engine.py    Business rules: prompt assembly, AI calls, validation, calorie balance, weekly/monthly stats
  config.py    LLM profiles, search service, prompts, task-to-model mapping (persisted as JSON)
  llm.py       Generic LLM client: OpenAI-compatible / Anthropic protocols, extra_body merge, image input
  search.py    Web search adapters: SearXNG / Tavily / Brave
  prompts.py   Default prompts and output format for the four AI tasks
  schemas.py   Type and range validation of AI output
  store.py     SQLite: body-data version history, records, reports
frontend/
  index.html / style.css / app.js   Standalone frontend (log, daily, report, body data, settings)
  privacy.html / terms.html         Privacy Policy and User Agreement (bilingual, hostable for store review)
  i18n.js / changelog.json         Chinese/English strings and changelog
tests/
  test_e2e.py  End-to-end tests (real backend over HTTP + local mock LLM and search services)
  mock_llm.py  Mock OpenAI / Anthropic / SearXNG
tests/tools/   ui_demo.py demo data service, cdp.mjs / shoot.mjs headless-browser screenshot checks (dev only)
start-windows.bat  Windows launcher
android/       Android shell (Chaquopy + WebView) and APK
```

## AI tasks (four types)

| Task | Input | Output (validated by the program) |
|---|---|---|
| Food estimate `food_estimate` | description, optional food images, meal, body data | name, grams, calories, protein/carbs/fat, confidence, basis |
| Activity estimate `activity_estimate` | description, body data | name, minutes, net calories, basis |
| Metabolism estimate `metabolism_estimate` | body data | BMR, maintenance burn, basis |
| Report analysis `report_analysis` | period, body data, statistics JSON | food score, activity score, activity level, comments, suggestions, risks |

Each task can use its own LLM profile in Settings; otherwise the default profile is used. Prompts are editable. The JSON output structure is always appended by the program.

## Features

- **Log**: switch between "Food / Exercise". Food can be typed as text or with up to 4 food photos (each ≤ 5 MB, compressed automatically). After AI estimation, a draft appears as cards; meals are chosen from a dropdown.
- **Daily**: a large calorie-balance card, intake and burn side by side, and segmented macro bars. Entries are grouped into breakfast / lunch / dinner / snacks / exercise, with date navigation, editing and deletion.
- **Report**: weekly or monthly reports. Statistics are computed by the program, scores show progress bars, and you can optionally send the data to the AI for analysis. Past reports can be reopened.
- **Body data**: split into "Basic / Daily & goals / Metabolic"; history is kept as dated versions shown on a timeline. Changes never rewrite past reports.
- **Settings**:
  - multiple LLM profiles (OpenAI-compatible / Anthropic), with a default and a connection test;
  - extra_body (a JSON object merged into the request body);
  - web search: SearXNG / Tavily / Brave / off;
  - prompt templates (system, user, search query), each restorable to default;
  - color theme: Forest cream / Sea salt blue / Mulberry plum, applied instantly and remembered on this device only;
  - interface language: 简体中文 (default) / English, applied instantly;
  - Advanced: backend address.
- **Changelog**: shown automatically on first use or after an upgrade (both languages); can be reopened from Settings.
- **Mobile**: tables become cards on narrow screens, with a bottom tab bar.

## Calorie balance

Calorie balance = intake − (maintenance burn + exercise burn). Maintenance burn comes from the Body data page (entered manually or estimated by AI).

## Verification

Automated tests that passed locally (exit code 0):

- `python -m unittest tests.test_e2e`: 55 end-to-end tests covering LLM profile CRUD and key masking, invalid config rejection, prompt override and restore, food estimation (with search results and custom prompts), activity estimation (Anthropic protocol), extra_body merge, search failure fallback, non-compliant AI output returning 422, upstream 500 returning 502, the hint when no LLM is configured, record save and edit, calorie balance, body-data versions, metabolism estimation, weekly/monthly reports (with and without AI analysis), report deletion, static pages and path-traversal protection, data export (without API key secrets), clearing all data, the local access token, DNS-rebinding protection, CORS scoping, and the frontend structure and compliance contracts (consent before any network call, bilingual policy pages, disclaimers).
- frontend/app.js passes `node --check`.
- `python -m backend serve` was started for real: the health check is OK, the home page returns 200, and the four AI tasks are registered.

**Not yet verified**

- The 0.3.1 and 0.4.0 pages have not been clicked through one by one in a real browser. Button behavior, table rendering, theme switching and the new first-launch consent screen need a manual check.
- No real LLM has been connected. All tests use local mock services, so estimation accuracy, prompt quality and differences between provider protocols must be checked with a real key. Image recognition has only been tested against the mock service.
- Web search was tested only against a mock SearXNG. The Tavily and Brave adapters have not been verified with real requests.

## Notes

- AI estimates have errors; review drafts before saving. The `confidence` and `basis` fields help you judge.
- Report analysis is a lifestyle reference generated by AI, not medical advice.
- The API key is stored in plain text in the local `data/config.json`; the UI shows only the last 4 characters. Do not share or commit that file or the `data/` folder to a public repository.

## Changelog

### v0.4.0 (2026-10-13)

Custom food & exercise library (log without AI):

- New custom foods: name, energy per serving, grams per serving, protein/carbs/fat, serving description, notes
- New custom exercises: name, energy per session, matching duration, notes
- Pick an item and "Add to draft" by servings (foods) or minutes (exercises); it then follows the same review-and-save flow as AI estimates, with exercise energy converted by duration
- Items live only in the local SQLite file; "Export all data" and "Clear all data" cover them

LLM setup (easier onboarding):

- New "Provider preset": one tap fills the protocol and base URL for 13 providers — DeepSeek, Zhipu GLM, Kimi (Moonshot), Alibaba Cloud Bailian (Qwen), OpenAI, Anthropic, Google Gemini, OpenRouter, SiliconFlow, xAI, Volcano Ark (Doubao), Mistral and MiniMax
- New "Fetch available models": queries the upstream model list via OpenAI-style `GET /models` or Anthropic-style `GET /v1/models` and lets you pick from a dropdown; a profile that is not saved yet can query with the protocol, URL and key typed in the form
- Preset model names are only a starting point; models change quickly, so trust the "Fetch available models" result

### v0.3.1 (2026-10-12)

Compliance and privacy (the focus of this release, in preparation for store submission):

- New first-launch consent screen: the Privacy Policy and User Agreement must be read and accepted before use, and **no user data is sent to any server before you agree** (the Android shell only probes whether the built-in local service is ready)
- New full Privacy Policy and User Agreement documents (bilingual, `frontend/privacy.html` / `terms.html`), reachable from Settings → Privacy & terms
- The Privacy Policy states plainly that the developer runs no server and collects nothing; AI estimates send data to the third-party endpoint you configure, with guidance to prefer https and a note on cross-border transfer risk
- New Data management: export all data as JSON (without API key secrets), clear all data, withdraw privacy consent
- AI estimate drafts and report analyses carry an "AI-generated, for reference only" label; reports and Settings show a disclaimer that this is not medical advice
- Fixed: reports could not be deleted (delete-report endpoint added)

Security hardening:

- The built-in local service now requires a random access token (generated by `MainActivity` on Android and injected into the WebView), so other apps on the device can no longer call the local API
- The API rejects non-loopback `Host` headers (DNS-rebinding protection); CORS no longer uses a wildcard and only echoes loopback origins; responses add `Referrer-Policy: no-referrer` and `X-Content-Type-Options: nosniff`
- Android: app data backup disabled (`allowBackup=false` plus backup/transfer rules), so health records and the plain-text API key can no longer be pulled out via adb or cloud backup
- Android: cleartext HTTP blocked by default, allowed only for the `127.0.0.1` local service; an `http://` endpoint you enter is blocked by the system
- Android: WebView mixed content set to `NEVER_ALLOW`

Packaging:

- v3 signature scheme enabled; English `strings.xml` and a monochrome adaptive-icon layer added
- Version updated to 0.3.1 (versionCode 6)

### v0.3.0 (2026-10-11)

- New "Forest cream" look: cream background, forest-green primary color, slate-blue accents, rounder cards
- Settings adds a "Color theme" option (Forest cream / Sea salt blue / Mulberry plum), applied instantly and remembered
- Daily page redone: large calorie-balance card, intake and burn side by side, segmented macro bars
- Daily entries grouped into breakfast / lunch / dinner / snacks / exercise, with icons and subtotals, date navigation
- Log page adds a "Food / Exercise" switch, drafts shown as cards, meals chosen from a dropdown
- Body data page split into "Basic / Daily & goals / Metabolic"; history shown as a timeline
- Report scores with progress bars; LLM profiles as cards, easier on phones
- Bottom mobile navigation with icons; active item is a solid pill; Android splash screen and status bar match the light theme
- All features and data unchanged; install over the previous version to upgrade
- Version updated to 0.3.0

### v0.2.1 (2026-10-10)

- Food logging supports uploading food photos, which AI recognizes to estimate calories
- Up to 4 images, each ≤ 5 MB, compressed automatically before upload
- Settings adds a language switch: 简体中文 (default) and English
- English interface covers all pages and applies instantly
- Changelog popup shows Chinese and English
- Version updated to 0.2.1

### v0.2.0 (2026-10-09)

- New app icon: dark background with green and orange rings, representing the balance of intake and burn
- Tables become cards on narrow screens, no horizontal scrolling
- Bottom tab bar on mobile; top navigation on desktop
- New minimal style: light gradient background, soft shadows, consistent corner radius
- "Backend address" moved to a collapsible "Advanced" section at the bottom of Settings
- Prompt templates in Settings are collapsed by default for a shorter page
- Calorie balance on the Daily page is more prominent, with two-column data layout
- Changelog popup shows automatically on first use or after upgrade; can be reopened from Settings
- Fixed the default date showing the previous day between 00:00 and 08:00
- Version updated to 0.2.0
