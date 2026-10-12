# 热量管理（独立前端 + 后端）

规则框架由程序搭建，食物热量、运动消耗、基础代谢和报告分析都由你配置的 LLM 完成（可选联网搜索）。程序不内置食物库或 MET 表。

## 安卓版 APK

本仓库同时提供打包好的安卓应用（0.1beta）：APK 内嵌 Python 运行时与后端，
**不需要电脑即可使用**，数据保存在手机应用私有目录。

```
android/CalorieTracker-0.1beta-arm64.apk   约 21.9 MB，仅 arm64-v8a，Android 7.0+
```

安装后首次使用需在「设置」页填一次 LLM 档案（地址 / 模型 / API Key）。
构建方法、与电脑版的差异、已验证与未验证事项详见
[android/README-Android.md](android/README-Android.md)。

## 启动

```powershell
cd "D:\deepseek workspace\calorie-tracker"
python -m backend serve --port 8787
```

浏览器打开 http://127.0.0.1:8787 即可使用。前端是纯静态页面（frontend/），不依赖构建，也可以用任何静态服务器单独托管；若后端不在同一地址，在页面右上角「后端」输入框填入后端地址。

数据默认保存在 data/（ct.db 为记录，config.json 为 LLM 与提示词配置，含明文 API Key，请勿分享）。

## 目录

```
backend/
  server.py    HTTP API + 静态文件（标准库，无第三方依赖）
  engine.py    业务规则：组装提示词、调用 AI、校验、热量差、周/月统计
  config.py    LLM 档案、搜索服务、提示词、任务到模型映射（持久化为 JSON）
  llm.py       通用 LLM 调用：OpenAI 兼容 / Anthropic 协议，支持 extra_body 合并
  search.py    联网搜索适配：SearXNG / Tavily / Brave
  prompts.py   四类 AI 任务的默认提示词与输出格式约定
  schemas.py   AI 输出的类型与取值范围校验
  store.py     SQLite：身体数据历史版本、记录、报告
frontend/
  index.html / style.css / app.js   独立前端（记录、每日、报告、身体数据、设置）
tests/
  test_e2e.py  端到端测试（真实后端 HTTP + 本地模拟 LLM 与搜索服务）
  mock_llm.py  模拟 OpenAI / Anthropic / SearXNG
_v1_local_rules/  上一版本（本地食物库与公式），仅留作对比，可删除
```

## AI 任务（四类）

| 任务 | 输入 | 输出（由程序校验） |
|---|---|---|
| 饮食估算 food_estimate | 描述、餐次、身体数据 | 名称、克数、热量、蛋白/碳水/脂肪、置信度、依据 |
| 运动估算 activity_estimate | 描述、身体数据 | 名称、分钟、净增量热量、依据 |
| 代谢估算 metabolism_estimate | 身体数据 | BMR、维持消耗、依据 |
| 报告分析 report_analysis | 周期、身体数据、统计 JSON | 饮食分、运动分、运动水平、点评、建议、风险 |

每类任务可在设置页单独指定 LLM 档案；未指定则用默认档案。提示词可自由修改，输出 JSON 结构由程序固定追加。

## 配置页能做的事

- **LLM 档案**：多套，协议选 OpenAI 兼容或 Anthropic，填写地址、模型、Key、temperature、max_tokens；可设为默认、测试连接。
- **额外参数 extra_body**：JSON 对象，会合并进请求体。例如启用 Anthropic 原生联网搜索：{"tools":[{"type":"web_search_20250305","name":"web_search","max_uses":3}]}
- **联网搜索**：SearXNG / Tavily / Brave / 不启用。搜索结果拼进提示词；搜索失败会跳过并在结果中提示，不中断估算。
- **提示词模板**：系统提示词、用户模板、搜索查询模板，可单独恢复默认。

## 数据流程

1. 在「记录」页输入饮食或运动描述，AI 估算后生成草稿（未保存）。
2. 在草稿表格中逐条修改名称、克数、热量等，可删除不要的条目。
3. 保存后进入当日记录；在「每日」页可再次修改热量或删除，热量差实时重算。
4. 热量差 = 摄入 − (维持消耗 + 运动消耗)。维持消耗来自「身体数据」页（手动填写或让 AI 估算）。身体数据按生效日期保存历史版本，修改不会改写过去的报告。
5. 「报告」页生成周/月报告：统计在程序内完成，勾选后交给 AI 做分析；历史报告可再次打开。

## 验证情况

已通过的自动化测试（均在本机运行，退出码为 0）：

- python -m unittest tests.test_e2e：24 项端到端测试。覆盖 LLM 档案增删改与 Key 脱敏、非法配置拦截、提示词覆盖与恢复、饮食估算（含搜索结果拼接与自定义提示词）、运动估算（Anthropic 协议）、extra_body 合并、搜索失败降级、AI 输出不合规返回 422、上游 500 返回 502、未配置 LLM 时的提示、保存与修改记录、热量差计算、身体数据版本、代谢估算、周/月报告（有无 AI 分析）、静态页面与路径穿越防护。
- 前端 frontend/app.js 通过 node --check 语法检查。
- 真实启动 python -m backend serve，健康检查返回正常，首页返回 200，四个 AI 任务已注册。

**尚未验证的部分**

- 没有在浏览器中逐个点击过页面。前端只做了语法检查和页面可访问性检查，按钮交互、表格渲染的实际效果需要你在浏览器里走一遍。
- 没有接入真实大模型。测试全部使用本地模拟服务，AI 估算的准确度、提示词效果、各家协议的细节差异都需要用你的真实 Key 验证。
- 联网搜索只在模拟 SearXNG 上测试，Tavily 与 Brave 的适配代码未经真实请求验证。

## 注意事项

- AI 估算有误差，保存前请核对草稿；草稿中的 confidence 与 basis 可以帮助判断。
- 报告分析是 AI 生成的生活方式参考，不是医疗建议。
- API Key 以明文存在本地 data/config.json，界面只显示末 4 位；请勿把该文件提交到公开仓库。