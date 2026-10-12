# 任务：热量管理前端英文本地化与语言切换

## 目标
为前端完成英文本地化，设置页提供语言切换：简体中文（zh-CN，默认）与 English（en）。语言保存在 localStorage（键名 `ct.lang`），切换后界面立即生效，已渲染的动态内容（每日明细、报告、LLM 档案、提示词、草稿表格、更新日志弹窗）同步重绘。

## 改动文件清单
- `frontend/i18n.js`（新建）：字典 `{ "zh-CN", "en" }`，提供 `t(key, vars)`（支持 `{name}` 占位）、`getLang`/`setLang`（localStorage `ct.lang`，缺省 zh-CN）、`applyI18n()`（处理 `data-i18n` / `data-i18n-html` / `data-i18n-placeholder` / `data-i18n-title`）。
- `frontend/index.html`：可见文字改为带 `data-i18n` 的元素，默认内容保留中文；`<title>` 仍为「热量管理」；设置页顶部新增「语言 / Language」卡片（下拉：简体中文 / English）；`i18n.js` 在 `app.js` 之前加载。
- `frontend/app.js`：所有前端文案（toast、状态、confirm、表格动态文本、餐次显示、运动/饮食、置信度、热量差、报告、LLM、提示词、搜索）改为 `t()`；新增 `refreshLanguage()` 在切换语言时重绘动态内容，并保留未保存的草稿/提示词/任务映射输入。图片上传相关函数（`readImage`、`onFoodFiles`、`renderFoodPreview`、`estimate` 中的图片逻辑）保留并翻译文字。
- `tests/test_e2e.py`：新增 3 个用例（未删除或弱化原有断言）。
- 未修改：`backend/`、`frontend/changelog.json`、`README.md`、`CLAUDE.md`、`frontend/style.css`。

## 设计要点
- **餐次存储值保持中文**：存储与提交的仍是「早餐/午餐/晚餐/加餐」，仅显示经 `mealLabel()` 翻译；草稿餐次输入框通过 `mealFromInput()` 把任一语言的输入反查回中文。
- **更新日志**：en 时优先 `items_en`（非空数组），缺失则回退 `items`；`changelog.json` 当前已含 `items_en`。
- **提示词模板**默认文本（`backend/prompts.py`）未改；后端错误信息仍为中文（按要求不处理）。
- 日期、数字格式未改。

## 字典 key 数量
- zh-CN：224 个；en：224 个；两者 key 集合完全一致（已用脚本核对，输出仅为数量与差集，未打印任何密钥）。
- 所有 `data-i18n*` 引用的 key（123 个）都存在于 zh-CN 字典中。

## 测试结果
- `node --check frontend/app.js`：通过
- `node --check frontend/i18n.js`：通过
- `python -W ignore -m unittest tests.test_e2e`：**Ran 34 tests, OK**（原 31 项 + 新增 3 项，数量只增不减）
- 新增用例：
  1. `test_i18n_js_served`：`GET /i18n.js` 返回 200，且包含 `zh-CN` 与 `"en"`。
  2. `test_index_has_i18n_hooks_and_title`：`GET /` 返回的 HTML 含 `data-i18n`，且 `index.html` 仍含「热量管理」（并确认 `<title>` 存在）。
  3. `test_i18n_dict_keys_match`：静态解析 `i18n.js`，核对两个字典 key 集合一致。

## 未覆盖 / 已知限制
- **未在真实浏览器中逐项点击验证**：语言切换后的各页面重绘、报告/LLM/提示词重绘、图片上传预览、更新日志弹窗的英文显示均只经过语法检查与代码审阅，未做人工交互测试。
- 英文译文为本次撰写，未经母语者校对，个别措辞可能需要润色。
- 后端返回的错误信息（中文）、以及 `console.warn` 的开发者日志仍为中文（按要求不处理）。
- 未验证 `style.css` 在英文文本长度下的换行/布局（英文通常比中文更长，窄屏表格和按钮可能需要微调）。
- 未修改 `style.css`，仅确认其无依赖中文字符的选择器。
- 未重新生成 Android 副本（`sync_app.py`）与 APK；本任务未要求。CLAUDE.md 要求改动 `frontend/` 后执行同步与打包，需由主代理另行执行。

## 结果摘要
为热量管理前端完成英文本地化。新增 `frontend/i18n.js`（zh-CN/en 各 224 个 key，key 集合一致），提供 `t()`、`applyI18n()` 与 localStorage `ct.lang` 的读写。`index.html` 全部可见文字改为 `data-i18n`，默认中文保留，`<title>` 仍为「热量管理」，设置页新增语言下拉。`app.js` 所有前端文案改用 `t()`，切换语言时重绘每日明细、报告、LLM 档案、提示词、草稿与更新日志，并保留未保存输入。餐次存储值保持中文，仅显示翻译；更新日志在 en 下优先 `items_en`。图片上传逻辑保留。测试新增 3 项，`python -W ignore -m unittest tests.test_e2e` 共 34 项全部通过（原 31 项）。未在真实浏览器中逐项点击验证，英文译文未经母语校对，未重新生成 Android 副本与 APK。
