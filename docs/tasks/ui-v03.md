# 任务：v0.3.0 界面重做（Verdant Cream 配色）+ 版本 0.3.0

总指挥：主脑（本会话，Sonnet 角色）。真机验证由用户亲自完成，不在本任务范围。

## 范围与禁令
- 允许改：`frontend/{index.html,style.css,app.js,i18n.js,changelog.json}`；版本号所在行（`backend/__init__.py`、`backend/server.py`、`android/app/build.gradle.kts`、`.android-build/finalize_apk.py`、`tests/test_e2e.py` 的版本断言）；安卓壳**仅配色**（`res/values/{colors,themes}.xml`、`res/layout/activity_main.xml`、`MainActivity.java` 中的颜色常量与错误页样式）；`tests/`；文档。
- 禁止：改后端业务逻辑与 API 形状；读 `data/config.json`、keystore；直接改 `android/app/src/main/python/` 副本；改应用图标；引入外部字体 / CDN / 图片资源。
- `app.js` 对后端 API 的调用（路径、方法、请求体）一个字符都不改。

## 参考图的用法（AI 生成图，仅借气质，不照抄）
借鉴：奶油底 + 深森林绿主色 + 石板蓝次色；大圆角卡片；激活标签为实心绿胶囊；大号热量差卡 + 摄入/消耗并排磁贴；蛋白/碳水/脂肪分段条；图标圆底的列表行；饮食/运动分段控件；身体数据拆成「基础信息 / 日常与目标 / 代谢指标」。
不得带入：图中的乱码文案、错误数据（"分量 1g / 2190"、"含运动消耗 0" 等）、iOS 样机元素。

## 设计决策
1. 配色（CSS 变量，全部走令牌）：奶油底 `#eef0e6`、卡片 `#fbfcf7`、森林绿 `#2f5d2c`、石板蓝 `#46667c`；宏量三色 = 石板蓝（蛋白）/ 琥珀（碳水）/ 珊瑚（脂肪），与参考图的暖灰/青/珊瑚刻意区分。热量差：赤字=绿、盈余=珊瑚红。
2. 增添配色：设置页新增「界面配色」，三套浅色方案（森林奶油 / 海盐蓝 / 蜜桃橘），`localStorage["ct.theme"]` 记忆。不做深色（安卓壳状态栏图标静态为深色，深色页面会看不清）。
3. 导航：手机为底部标签栏（图标+文字，激活=实心绿胶囊，保留 v0.2 已在真机验证过的位置）；桌面为顶部胶囊标签。
4. 记录页：饮食/运动用分段控件切换（面板用 `hidden`，不销毁输入）；餐次只属于饮食面板（运动草稿不再带餐次）。
5. 每日页：日期条（前一天/后一天）→ 热量差大卡 → 摄入/总消耗磁贴（含运动消耗、维持消耗小字）→ 宏量条 → 图标行明细（名称与热量仍可编辑，保存/删除不变）。
6. 表格→卡片：`#dayBody`、`#draftBody`、`#profileHistory`、`#llmList` 由 `<tbody>` 改为 `<div>` 容器；行模板重写，事件委托从 `closest("tr")` 改为 `closest(".entry")`。报告页每日明细保留 `<table>`（5 列，窄屏可横滚）。
7. 草稿餐次由文本框改为下拉（`readDraftEdits` 同步读取 select）。

## 钩子契约（回归测试 `FrontendContract` 守护）
`app.js` 引用的每个 `#id` 必须存在于 `index.html`；`nav button[data-tab]` ↔ `#tab-*`；表单 `name`（profile/llm/search）不变；`data-f/data-save/data-remove/data-del/data-edit/data-test/data-activate/data-delete/data-report/data-rm-img/data-save-prompt/data-reset-prompt/data-task` 全部保留；`withBusy` 的按钮保持纯文本（不放图标）；顶层 `[hidden]` 必须 `display:none !important`。

## 分工（避免杀鸡用牛刀）
| 子任务 | 执行 | 理由 |
|---|---|---|
| 设计、CSS/HTML/JS 重构、视觉迭代 | 主脑 | 高难度，需读图迭代（路由表：前端归 Sonnet） |
| 演示数据服务 + 截图自检工具 | 主脑 | 一次性小脚本，写简报比直接写更贵 |
| 版本号替换 | 主脑（单行 edit） | 约 6 处单行改动，无需 AI |
| README / README-Android / CLAUDE.md 文档同步 | Haiku | 低难度文本同步，限定文件范围 |
| 前端 diff 只读评审（XSS 转义、事件委托、空态、a11y） | GLM 5.3 | 独立第二视角，价格低 |
| APK 构建 | 主脑直跑；失败两次再升级 GLM | 命令固定 |

## 验收
- `python -m unittest tests.test_e2e` 全过，用例数不少于 34（基线）。
- `node --check frontend/app.js` 通过。
- 无头浏览器在 390×844 / 360×740 / 1280×900 逐页截图：无横向滚动、无截断、控制台无报错；中英文各检查。
- `sync_app.py → build_apk.js assembleRelease → finalize_apk.py` 产出 `CalorieTracker-0.3.0-arm64.apk`，versionName 0.3.0 / versionCode 5，签名校验通过。
- 更新日志（中英）写入 `frontend/changelog.json`（顶层 + history 最前）与 README。


## 结果摘要（ui-v03，已完成，待真机复测）

- 界面：按参考图气质重做为「森林奶油」（奶油底 / 森林绿 / 石板蓝），未照抄样机；新增三套浅色配色（森林奶油、海盐蓝、桑葚紫），设置页可切换并记忆。
- 结构：每日页=热量差大卡+摄入/消耗磁贴+宏量条+按餐次分组的图标行（可前后翻日）；记录页=饮食/运动分段；身体数据=三张分卡+时间线；LLM 档案、历史版本表格改为卡片。
- 功能：app.js 对后端 API 的调用未改动；表单 name、事件钩子全部保留，由 6 个新契约测试守护。
- 评审：GLM 只读评审无阻断问题；已修 4 处（搜索结果链接仅放行 http/https、kcal 空值、变量遮蔽等）。
- 验证：`python -m unittest tests.test_e2e` 40 项通过（基线 34）；`node --check` 通过；无头 Edge 在 390×844 / 360×740 / 1280×900、中英文、三套配色下逐页截图，无横向溢出、无控制台报错。踩坑已修：窄屏顶栏 backdrop-filter 会使内部 fixed 底栏错位。
- 构建：`CalorieTracker-0.3.0-arm64.apk`（22.11 MB，versionName 0.3.0 / versionCode 5，签名校验通过）。
- 未验证：真机（用户负责）；Edge 渲染不等于 Android WebView，需关注真机上的 `color-mix()`、`backdrop-filter` 回退。

分工：主脑=设计/重构/视觉迭代/构建；Haiku=三份文档同步；GLM=前端只读评审。

改动文件：frontend/{index.html,style.css,app.js,i18n.js,changelog.json}；backend/{__init__,server}.py（仅版本号）；android/app/build.gradle.kts、res/values/{colors,themes}.xml、res/layout/activity_main.xml、MainActivity.java（仅配色）；tests/test_e2e.py、tests/tools/{ui_demo.py,cdp.mjs,shoot.mjs}；README.md、android/README-Android.md、CLAUDE.md；.android-build/finalize_apk.py。