# CLAUDE.md — calorie-tracker 多模型协作规则

本文件是热量管理 App 的多 AI 分工规范。会话开始时必须加载并遵守。
适用模型：Claude Sonnet 5.5 / Claude Haiku 5.5 / GLM 5.3 / Kimi K3（均经 OpenRouter 接入 Claude Desktop）。
价格数据核实于 2026-10-12，开大任务前建议复查 OpenRouter 加权实付价。

## 项目导航

三层异构结构，任务按层路由：

- `backend/` — Python 标准库后端（server/engine/config/llm/search/prompts/schemas/store），无第三方依赖
- `frontend/` — 纯静态前端（index.html / style.css / app.js），无构建
- `android/` — 安卓壳：Chaquopy 17（CPython 3.14）+ WebView + `MainActivity.java` + `ctserver.py` 引导
- `.android-build/` — 离线构建工具链：`sync_app.py` → `build_apk.js` → `finalize_apk.py`
- `tests/` — `test_e2e.py`（24 项端到端）+ `mock_llm.py`（模拟 OpenAI/Anthropic/SearXNG）
- 修改后端/前端后必须先跑 `python .android-build\sync_app.py` 再构建 APK

## 模型分工路由表（主脑 = Sonnet 5.5）

| 任务类型 | 执行模型 | effort | 说明 |
|---|---|---|---|
| 需求理解、拆任务、定验收标准 | Sonnet 5.5 | — | 主会话默认模型 |
| 跨层改动合并后的最终审查 | Sonnet 5.5 | — | 只审 diff，不重写 |
| 后端 Python 改动 / bug 修复 | GLM 5.3 | low | 简单改动一律 low |
| 测试编写与维护（test_e2e.py） | GLM 5.3 | low→high | 复杂断言才 high |
| Chaquopy Java↔Python 边界问题 | GLM 5.3 | high | 先读本文件「已知坑」 |
| 构建脚本执行与报错排查 | GLM 5.3 | high | 涉及 Gradle/JDK 环境坑 |
| 跨模块大型重构方案设计 | GLM 5.3 | max | 输出 $4.3/M，比 Sonnet 便宜 |
| frontend/ 交互重构、UI 组件 | Kimi K3 | — | 视觉榜单四者最强 |
| 对着截图/错误页/logcat 迭代的问题 | Kimi K3 | — | 原生多模态，迭代看图 |
| WebView 真机疑难杂症分析 | Kimi K3 | — | Androidnative 榜前 14% |
| 超大范围仓库调研（读多写少） | Kimi K3 | — | 1M 上下文 + 93% 缓存命中 |
| 侦察子代理（查代码/找定义/读日志） | Haiku 5.5 | — | 只读权限，只回摘要 |
| 长文档/长日志压缩摘要 | Haiku 5.5 | — | 输入 $0.10/M |
| lint/格式化/重命名/批量小改 | Haiku 5.5 | — | 改完必须过测试 |
| commit message / README 同步 | Haiku 5.5 | — | — |

## 各模型使用纪律

**Sonnet 5.5（$2/$10，缓存读 $0.10）**
- 职责是编排与审查，不是写码主力。让 Sonnet 逐行实现功能是成本浪费。
- 每轮对话尽量让它"派任务 + 收结果"，而不是亲自翻资料。

**GLM 5.3（OpenRouter 加权实付约 $0.22/$4.29，多 provider 低至 $0.07/$3.40）**
- 主力工兵。reasoning effort 三档（low/high/max，默认 max）：**简单任务必须显式传 low**，默认 max 会白烧推理 token。
- Terminal-Bench 4.0 得分 41.9，是 K3（12.6）的 3 倍——工兵活交给它，不要交给 K3。

**Kimi K3（加权实付约 $0.46/$14.72）**
- 只派"少而重"的任务：前端硬骨头、视觉迭代、大仓库研究。禁止派碎活（默认持续思考，碎活推理 token 不划算）。
- 省钱关键：同一任务线保持上下文稳定，吃 93% 缓存折扣（有效输入价降到 ~$0.485）；频繁换上下文最亏。
- 走 Standard 路由即可，不必锁 Nitro 端点。

**Haiku 5.5（≤10 万 token 请求 $0.10/$0.50）**
- ⚠️ 计费断崖：单次请求提示词一旦超过 10 万 token，价格跳到 $0.50/$2.50（5 倍）。派给 Haiku 的资料必须先压缩，上下文控制在 10 万 token 以内。
- 它是所有主模型的默认侦察兵：Agent 子任务凡是"查完只回结论"的，一律用 Haiku + 只读工具权限。
- agent 任务 80% 的 token 花在翻资料上——把翻资料全压给 Haiku 是最大的省钱杠杆。

## 已知坑（子代理开工前必读）

1. **Chaquopy 集合代理**：Java 集合（ArrayList 等）跨边界传给 Python 只是代理对象，不可迭代。传参一律用 `String[]`/数组；Python 侧 `_as_dirs()` 已有归一化兜底。教训见 `android/README-Android.md`。
2. **构建沙箱**：`GRADLE_USER_HOME`/`ANDROID_USER_HOME` 必须指向 `.android-build/` 内；不能同时设 `ANDROID_SDK_HOME`；`-Djava.io.tmpdir` 不能用 `JAVA_TOOL_OPTIONS` 传；工程路径含空格，须由 Node 直调 GradleMain。
3. **修复后的 0.1beta APK 未经真机复测**：任何涉及安卓壳的改动，交付时必须附「真机复测清单」（安装→首次启动→设置页填档案→测试连接→四任务→报告页），由用户在真我 GT Neo5 上人工验证后才算完成。

## 安全红线（对所有模型生效）

- `data/config.json` 含明文 LLM API Key，`android/keystore.properties` 与 `.android-build/keystore/*.jks` 含明文签名口令：**禁止**将其内容输出到任何回复、日志或外部服务；禁止提交到公开仓库。
- 丢失 keystore 将无法覆盖升级，构建相关操作不得删除或重建 keystore。
- 后端只监听 127.0.0.1:8787 回环，任何改动不得对外网开放端口。

## 标准工作流（一次功能迭代）

1. Sonnet 5.5 主会话：理解需求 → 按路由表拆分子任务 → 为每个子任务写验收标准。
2. 需要背景资料时 → 派 Haiku 5.5 侦察子代理（只读，回摘要 ≤500 字）。
3. 子任务分发：后端/测试/构建 → GLM 5.3；前端/视觉迭代 → Kimi K3。
4. 各执行模型完成后跑 `python -m unittest tests.test_e2e`，24 项必须全绿。
5. 改过后端/前端 → `python .android-build\sync_app.py` → `node .android-build\build_apk.js assembleRelease` → `python .android-build\finalize_apk.py`。
6. Sonnet 5.5 统一审查合并 diff。
7. 输出真机复测清单，等待用户人工验证结果。
