# CLAUDE.md — calorie-tracker 协作规则（v2）

会话开始必须加载并遵守。价格、基准分数、详细理由见 `docs/model-routing-reference.md`（按需读取，不要常驻）。
适用模型：~anthropic/claude-sonnet-latest（主脑）/ ~anthropic/claude-haiku-latest / z-ai/glm-5.3，均经 OpenRouter 接入 
## 一、原则（先看这条）

1. **默认单模型**：一个任务若只涉及 1–2 个文件、改动小于约 50 行，就在当前会话直接做完，**不要分派**。分派要重新交代背景、丢失缓存、多一轮审查，小任务里这些开销比省下的差价还大。
2. **分派的触发条件**（满足任一才分派）：需要大量读代码/日志（→ Haiku 侦察）；多文件后端或构建改动（→ GLM）；需要看截图做视觉迭代（→ Sonnet）；跨层改动合并后需要审查（→ Sonnet）。
3. **能省 token 的第一杠杆是少读**：翻资料交给 Haiku，只回摘要。
4. **派活必须限定读取范围**：简报里列出要读的具体文件或目录，禁止让子代理"自行浏览整个仓库"。Haiku 单次输入必须控制在 10 万 token 以内（OpenRouter 日志显示，不加限制的侦察请求输入已达 8 万左右，接近断崖线）。默认排除目录见第二节。

## 二、项目导航

- `backend/` Python 标准库后端（server/engine/config/llm/search/prompts/schemas/store），无第三方依赖
- `frontend/` 纯静态前端（index.html / style.css / app.js），无构建
- `android/` 安卓壳：Chaquopy 17（CPython 3.14）+ WebView + `MainActivity.java` + `ctserver.py`
- `.android-build/` 离线构建工具链（约 2 GB，已被 .gitignore 排除）
- `tests/` `test_e2e.py` + `mock_llm.py`

**唯一源码在根目录 `backend/` 与 `frontend/`。** `android/app/src/main/python/{backend,frontend}/` 是 `sync_app.py` 生成的副本：**只改根目录，禁止直接改副本**，也不要读副本（重复内容白烧 token）。

**检索时默认排除**：`.android-build/`、`android/app/build/`、`android/.gradle/`、`_v1_local_rules/`（旧版本，README 称可删除）、`__pycache__/`、`*.apk`、`data/`。

## 三、路由表

| 任务 | 模型 | effort | 备注 |
|---|---|---|---|
| 理解需求、拆任务、写验收标准、最终审查 | ~anthropic/claude-sonnet-latest | — | 编排与审查，不逐行写功能 |
| 查代码/找定义/读日志/压缩长文档（只回摘要） | ~anthropic/claude-haiku-latest | — | 用只读子代理（Explore 类型）；单次提示词必须 ≤10 万 token，超过则价格×5 |
| lint/格式化/重命名/批量小改、commit message、README 同步 | ~anthropic/claude-haiku-latest | — | 改完必须过测试 |
| 后端改动、bug 修复、测试维护、构建脚本执行与排查 | z-ai/glm-5.3 | **默认 low**，复杂断言或 Gradle/JDK 排错用 high | 不要用默认的 max，会白烧推理 token |
| 跨模块重构方案设计 | z-ai/glm-5.3 | max | 仅限方案，不顺手实现；方案由 Sonnet 审后再分派 |
| 前端交互重构、UI 组件、对着截图/错误页/logcat 迭代 | ~anthropic/claude-sonnet-latest | — | 只派"少而重"的活，同一任务线保持上下文稳定以吃缓存 |
| 超大范围仓库调研（读多写少） | ~anthropic/claude-sonnet-latest | — | 先试 Haiku 侦察，不够再升级 |
| Chaquopy Java↔Python 边界 | z-ai/glm-5.3 | high | 先读「六、已知坑」 |
| WebView 真机疑难杂症 | ~anthropic/claude-sonnet-latest | — | 需要截图/logcat 才用 Sonnet；纯代码层面的原因归 GLM |

**归属冲突的裁决**：看产出物——改 Python/Java/构建脚本归 GLM，改 HTML/CSS/JS 或需要读图归 Sonnet。

## 四、如何分派（执行机制）

- **别名对照（已在 OpenRouter 日志中验证，2026-10-12）**：Agent 工具的 `model` 参数用的是别名，别名名字与实际模型**不对应**，不要按字面理解：

  | `model` 参数 | 实际执行模型 | 用途 |
  |---|---|---|
  | `haiku` | ~anthropic/claude-haiku-latest | 侦察、摘要、批量小改 |
  | `opus` | **~anthropic/claude-sonnet-latest**（不是 Claude Opus） | 前端、视觉迭代、大仓库调研 |
  | `fable` | **z-ai/glm-5.3**（不是 Fable） | 后端、测试、构建、Chaquopy 排错 |
  | `sonnet` | ~anthropic/claude-sonnet-latest | 编排、最终审查 |

- 派任务时只用上表别名，不要凭名字猜模型。子代理自报的身份**不可信**（测试中 `opus` 自报为 claude-opus-5-5、`fable` 自报为 claude-fable-5-1，均与实际不符），以 OpenRouter 日志为准。
- 映射依赖 Claude Desktop 的模型映射配置。若映射被修改或日志显示路由不对，停止分派，回到降级规则。
- 做不到时：由当前模型降级直接完成，并在回复里说明"未分派，原因：…"，不得假装已分派。
- 跨会话/跨模型交接一律写文件：把任务简报写到 `docs/tasks/<任务名>.md`（目标、涉及文件、验收标准、禁止事项），执行方完成后在同一文件末尾追加「结果摘要」（≤300 字）和改动文件清单。
- **升级规则**：低档模型同一问题两次失败 → 停止重试，升级一档（Haiku→GLM→Sonnet）并附上失败日志摘要；禁止原地反复重试。

## 五、验收与交付

1. 改动后运行 `python -m unittest tests.test_e2e`：**全部通过，且用例数不得减少**（当前 68 项，写测试后以实际数为准并更新此处）。
2. 改过 `backend/` 或 `frontend/` → `python .android-build/sync_app.py` → `node .android-build/build_apk.js assembleRelease` → `python .android-build/finalize_apk.py`。
3. 多文件改动合并后，Sonnet 审查 diff（只审不重写）。**本目录目前不是 git 仓库，没有 diff 可审也无法回滚**——先 `git init` 并做一次基线提交（见 `.gitignore` 说明），否则多模型并行改动无法追溯。
4. 涉及安卓壳的交付必须附「真机复测清单」：安装 → 首次启动 → 设置页填档案 → 测试连接 → 四类 AI 任务 → 报告页。在用户的真我 GT Neo5 上人工验证通过前，不得宣称完成。修复后的 0.1beta APK 至今未经真机复测。

## 六、已知坑

1. **Chaquopy 集合代理**：Java 集合（ArrayList 等）传到 Python 只是代理对象，不可迭代。传参用 `String[]`/数组；Python 侧 `_as_dirs()` 已有兜底。详见 `android/README-Android.md`。
2. **构建沙箱**：`GRADLE_USER_HOME`/`ANDROID_USER_HOME` 必须指向 `.android-build/` 内；不能同时设 `ANDROID_SDK_HOME`；`-Djava.io.tmpdir` 不能走 `JAVA_TOOL_OPTIONS`；工程路径含空格，须由 Node 直调 GradleMain。

## 七、安全红线（所有模型、所有子代理）

- **禁止读取（不只是禁止输出）**：`data/config.json`（明文 LLM API Key）、`android/keystore.properties`、`.android-build/keystore/*`（签名口令）。原因：模型读到的内容会作为请求上传给 OpenRouter 及其下游 provider，读了就等于外泄。需要核对配置结构时，只读 `backend/config.py` 与 README。
- 以上文件内容不得出现在任何回复、日志、任务简报或外部服务中；不得提交到公开仓库。
- `data/`（含 `config.json`、`ct.db`）**当前未被 .gitignore 排除**，`git init` 之前必须先补上 `data/`。
- 不得删除或重建 keystore（丢失后无法覆盖升级）。
- 后端只监听 127.0.0.1:8787 回环，任何改动不得对外开放端口。
- 建议在 `.claude/settings.json` 配置 deny 规则做硬拦截，见参考文档，提示词约束不如权限拦截可靠。
