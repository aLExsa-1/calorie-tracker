# 任务：编写 v0.2 更新日志（Haiku 角色）

只允许修改/新建：`frontend/changelog.json`、`README.md`。
读取范围仅限：`README.md`、本简报。禁止读 `data/`、`.android-build/`、`android/`。

## 内容
v0.2 相对 0.1beta 的变化（据此写，不要编造其它功能）：
- 手机界面布局重构：窄屏下表格改为卡片，不再横向滚动。
- 底部标签栏导航（手机），桌面仍在顶部。
- 全新极简风格界面：浅色渐变背景、柔和卡片阴影、统一配色与圆角。
- 「后端地址」收进「设置」页底部的「高级」折叠区，顶栏更清爽。
- 设置页的提示词模板改为折叠显示，页面更短。
- 每日页热量差更醒目，各项数据两列排布。
- 首次使用（或升级后首次打开）自动弹出更新日志，设置页可随时再次查看。
- 版本号更新为 0.2。

## 产出
1. `frontend/changelog.json`（UTF-8，无 BOM），格式严格如下，`items` 5–8 条，简明中文，每条 ≤ 30 字：
   `{"version":"0.2","date":"2026-10-12","items":["…"]}`
2. `README.md`：把所有「0.1beta」版本描述改为「0.2」（APK 文件名 `CalorieTracker-0.1beta-arm64.apk` → `CalorieTracker-0.2-arm64.apk`），并新增一个「## 更新日志」小节，列出 v0.2 条目（与 json 一致）。其余内容不动。

## 验收
- `python -c "import json;print(json.load(open('frontend/changelog.json',encoding='utf-8')))"` 能解析。
- 完成后在本文件末尾追加「结果摘要」（≤ 100 字）和改动文件清单。


## 结果摘要

已新建 frontend/changelog.json（8 条，均 ≤30 字，UTF-8 无 BOM，json 解析通过）；README.md 中 0.1beta 全部改为 0.2（含 APK 文件名），并在末尾新增「## 更新日志」v0.2 小节，条目与 json 一致。

改动文件：frontend/changelog.json、README.md、docs/tasks/changelog-v02.md（追加本摘要）
