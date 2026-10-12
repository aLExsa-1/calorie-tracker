# 热量管理 —— Android 版（0.2.1）

把 `calorie-tracker` 的 Python 后端与静态前端打包成一个**独立的安卓应用**：
APK 内部自带 Python 运行时（Chaquopy 17.0 / CPython 3.14），启动时在手机本机
（127.0.0.1:8787）拉起 `backend.server`，界面用 WebView 加载同一份 `frontend/`。

## 产物

| 项目 | 值 |
|---|---|
| 文件 | `android/CalorieTracker-0.2.1-arm64.apk`（当前版本） |
| 包名 | `com.calorietracker.app` |
| 版本 | versionName `0.2.1`，versionCode `4`（见 `app/build.gradle.kts`） |
| 大小 | 约 22.1 MB |
| CPU | 仅 `arm64-v8a`（现代真机；装不进 x86 模拟器） |
| 系统要求 | Android 7.0（API 24）及以上，targetSdk 35 |
| 签名 | release 签名（APK Signature Scheme v2），自建 keystore |

`android/` 下另保留了历史 APK（`0.1beta`、`0.2`、`0.2.0`），仅供回溯，新安装请使用 0.2.1。

## 安装

1. 把 `CalorieTracker-0.2.1-arm64.apk` 传到手机（微信/QQ/数据线/网盘均可）。
2. 在手机上点击安装；系统会提示「未知来源应用」，按提示允许该来源安装。
3. 桌面出现「热量管理」图标，打开即可。

> 首次启动需要初始化 Python 运行时，会有几秒到十几秒的「正在启动内置服务…」，
> 之后启动会快很多。全程不需要电脑。
>
> 若系统提示与旧版冲突，请先卸载旧包再安装（同一 keystore 签名的新版本一般可直接覆盖）。

## 首次配置（必须做一次）

应用界面和电脑版完全一致，但 LLM 的 API Key 不会随 APK 一起打包，需要在手机上填一次：

1. 进入底部「设置」页 → **LLM 档案** → 新建：
   - 协议：`openai`（DeepSeek、OpenAI、通义、Kimi 等兼容接口）或 `anthropic`
   - 地址：例如 `https://api.deepseek.com/v1`
   - 模型：例如 `deepseek-chat`
   - API Key：粘贴你的 Key
2. 保存后点「设为默认」，再点「测试连接」确认可用。
3. 如需联网搜索，在「联网搜索」里选 SearXNG / Tavily / Brave 并填好参数。

**所有数据（`ct.db`、`config.json` 含明文 Key）都保存在应用私有目录**
`/data/data/com.calorietracker.app/files/data/`，其他应用无法读取；卸载应用会一并删除。

## 与电脑版的差异

| 方面 | 说明 |
|---|---|
| 后端位置 | 从「电脑上单独运行」改为「APK 内嵌，随应用启动」 |
| 访问地址 | 固定 `127.0.0.1:8787`，只监听本机回环，不对外网开放 |
| 数据目录 | 应用私有目录 `files/data/`（电脑版是项目下的 `data/`） |
| 后端地址 | 位于「设置」页底部「高级：后端地址」折叠区。留空即可（同源）；若填了地址会连到别的后端 |
| 图片选择 | 通过 Activity 的 `WebChromeClient` 调起系统相册（见 0.2.1 修复记录） |
| 后端代码 | 未做任何改动，直接打包 `backend/`（编译为 `.pyc`） |
| 前端代码 | 未做任何改动，直接打包 `frontend/` 原始文件 |

## 版本记录与真机反馈

### 0.2.1（当前版本，真机运行成功）

应用内改动（与电脑版一致）：
- 饮食记录支持上传食物图片，由 AI 识别后估算热量（最多 4 张，每张 ≤ 5 MB）；
- 设置页新增语言切换：简体中文（默认）与 English，四个提示词模板名称已补英文；
- 更新日志弹窗按版本列出历史（v0.2.1、v0.2.0），英文界面显示英文条目。

安卓壳修复：

- **「添加食物图片」点击无反应**。原因：`MainActivity` 没有设置 `WebChromeClient`，
  WebView 收到 `<input type="file">` 时不会弹出文件选择器。修复：新增
  `onShowFileChooser`（调起系统选择器，按 `<input>` 是否带 `multiple` 决定是否多选）
  与 `onActivityResult`（把选中的图片 URI 回传给网页）。

> 真机反馈：0.2.1 在真机上运行成功，暂未发现 bug（具体复测项未逐条记录）。

### 0.2.0

- 界面：手机窄屏表格改为卡片，底部标签栏导航，极简风格，「后端地址」收入「高级」折叠区；
- 修复凌晨 0–8 点默认日期显示为前一天的问题；
- 首次使用或升级后自动弹出更新日志。

### 0.1beta（首次真机安装）

真机：**真我 GT Neo5（RMX3706，realme UI 7.0 / Android 16，第一代骁龙 8+，arm64-v8a）**。
安装正常，首次启动弹出错误页：

```
com.chaquopy.python.PyException: TypeError: 'ArrayList' object is not iterable
```

**原因**：`MainActivity` 把 Java 的 `ArrayList<String>` 直接传给 Python 的
`ctserver.start(data_dir, port, extra_dirs)`。Chaquopy 对 `java.util.ArrayList`
只做**代理包装**，Python 侧 `for item in extra_dirs` 无法迭代，于是后端在
「定位前端目录」这一步就抛异常，服务没起来。

**修复**（两层，任一层都足以解决）：

1. Java 侧改传 `String[]`（数组会被 Chaquopy 转成原生 Python `list`），
   不再传 `ArrayList`；
2. Python 侧新增 `_as_dirs()` 归一化函数：识别原生容器，遇到 Java 集合代理则
   依次尝试 `toArray()` → `iterator()/hasNext()/next()` 取出元素；
3. 额外加固：`find_web_dir()` 还会遍历 `sys.path`（Chaquopy 会把应用内容的
   解压目录加进去）做有限深度搜索，因此**即使 Java 侧什么都不传，Python 侧也能
   自己定位到 `frontend/`**。

对应的本机回归测试：`.android-build/repro_java_list.py`（用一个「可调用 `toArray()`
但不可迭代」的对象模拟 Chaquopy 的 ArrayList 代理，修复前报同样的 TypeError，
修复后正常返回前端目录）。

> 教训：Chaquopy 的 Java↔Python 边界只对**数组和基础类型**做原生转换，
> 传集合类会变成代理对象。跨边界优先用数组或字符串。

该修复随 0.2.1 一起在真机上运行成功（见上文 0.2.1 的真机反馈）。

## 目录结构

```
android/
  CalorieTracker-0.2.1-arm64.apk     当前安装包
  CalorieTracker-0.2.0-arm64.apk     历史版本（回溯用）
  CalorieTracker-0.2-arm64.apk       历史版本（回溯用）
  CalorieTracker-0.1beta-arm64.apk   历史版本（回溯用）
  settings.gradle.kts                工程配置
  build.gradle.kts                   AGP 8.7.3 + Chaquopy 17.0.0
  gradle.properties                  Gradle 参数（状态目录指向工程内）
  local.properties                   SDK 路径（本机专用，勿提交）
  keystore.properties                release 签名口令（勿公开）
  app/
    build.gradle.kts                 模块配置：versionName/versionCode/ABI/签名/Chaquopy
    src/main/AndroidManifest.xml     权限、Activity、允许明文回环流量
    src/main/java/com/calorietracker/app/MainActivity.java
                                     启动 Python、轮询健康检查、加载 WebView、文件选择器
    src/main/python/ctserver.py      Android 端引导：定数据目录、找前端、起服务
    src/main/python/backend/         由 sync_app.py 从 ../../backend 同步
    src/main/python/frontend/        由 sync_app.py 从 ../../frontend 同步
    src/main/res/                    图标、主题、文案
.android-build/                      构建工具链与脚本（体积大，可随时删除重建）
```

## 重新构建

`.android-build/` 里已备好整套工具链（JDK 17、Gradle 8.11.1、Android SDK 35、
keystore）与脚本，**不需要联网、不需要 Android Studio**：

```powershell
cd "D:\deepseek workspace\calorie-tracker"

# 1) 若改过后端/前端，先同步到 Android 工程
python .android-build\sync_app.py

# 2) 构建 release APK
node .android-build\build_apk.js assembleRelease

# 3) 整理出分发用的文件名并做校验
python .android-build\finalize_apk.py
```

发布新版本时，需要同时更新：`app/build.gradle.kts` 的 `versionName` 与 `versionCode`
（每次发布必须递增）、`frontend/changelog.json`，以及本文件的「当前版本」描述。

常用变体：

```powershell
node .android-build\build_apk.js assembleDebug        # 调试版（包名带 .debug 后缀）
node .android-build\build_apk.js assembleRelease --clean
python .android-build\smoke_test.py                   # 本机冒烟测试后端与前端
python .android-build\inspect_apk.py <apk 路径>        # 查看 APK 内容
```

若 `.android-build/` 被删除，按以下顺序重建工具链（需要联网，约 2 GB）：

```powershell
python .android-build\download_tools.py     # 下载 JDK / Gradle / cmdline-tools / 仓库清单
python .android-build\setup_tools.py        # 解压并解析 SDK 组件直链
python .android-build\install_sdk.py        # 下载并安装 platform-tools / android-35 / build-tools 35
python .android-build\accept_licenses.py    # 写入 SDK 许可文件
python .android-build\make_keystore.py      # 生成 release keystore（已有则跳过）
python .android-build\make_icons.py         # 重新生成启动图标
```

## 构建环境的几点说明

本机沙箱不允许写入用户主目录（`C:\Users\...\.gradle`、`.android`、`.android\analytics.settings`），
因此构建脚本做了这些处理，换机器时可能不再需要：

- `GRADLE_USER_HOME`、`ANDROID_USER_HOME` 指向 `.android-build/` 内；
- JVM 增加 `-Duser.home=<工程内目录>`，绕开 AGP 对 `~/.android` 的强制访问；
- 只设置 `ANDROID_USER_HOME`，**不能**同时设置 `ANDROID_SDK_HOME`（AGP 会报路径冲突）；
- 临时目录通过 `-Djava.io.tmpdir` 传入；**不能**用 `JAVA_TOOL_OPTIONS`，
  因为 `gradle.bat` 会按空格重新拆分其中的参数；
- 因为工程路径含空格且 `gradle.bat` 不保留引号，改由 Node 以参数数组直接调用
  Gradle 的 `org.gradle.launcher.GradleMain`；
- `org.gradle.vfs.watch=false`：沙箱内文件监视器初始化会失败；
- 显式 `buildToolsVersion = "35.0.0"`，避免 AGP 去要它默认的 34.0.0；
- 强制 Kotlin stdlib 统一为 1.8.22，消除 `Duplicate class kotlin.*`。

## 已验证 / 未验证

**0.2.1 已在本机完成**：

- `sync_app.py` 同步 `backend/` 与 `frontend/` 成功；
- `assembleRelease` 构建成功（BUILD SUCCESSFUL，退出码 0）；
- `finalize_apk.py` 通过（退出码 0），生成 `CalorieTracker-0.2.1-arm64.apk`；
- 电脑端 `python -m unittest tests.test_e2e` 34 项全部通过。

**0.1beta 时已在本机验证（0.2.1 未重新跑 badging / 签名校验，如需确认请运行 `inspect_apk.py` 与 `apksigner verify`）**：

- APK badging：包名、`minSdk=24`、`targetSdk=35`、`native-code=arm64-v8a`、应用名「热量管理」；
- `apksigner verify --print-certs` 通过（v2 签名，RSA 2048）；
- 包内 arm64-v8a 原生库（含 `libpython3.14.so`）与 `assets/chaquopy/app.imy`；
- `app.imy` 内含 `backend/*.pyc`、`ctserver.pyc` 与 `frontend/` 原始文件；
- `smoke_test.py`：按 `ctserver.start()` 的真实路径在本机启动后端，主要接口与静态文件均返回 200。

**真机验证（真我 GT Neo5 / Android 16）**：

- 0.2.1 已在真机上运行成功，暂未发现 bug（用户反馈）；
- 以下环节尚未逐项记录，仍需确认：
  1. Chaquopy 启动 Python 3.14 运行时的耗时与日志；
  2. `ctserver.find_web_dir()` 在设备上实际命中的目录；
  3. WebView 对 `http://127.0.0.1:8787` 的加载与 localStorage 行为；
  4. 「添加食物图片」能否弹出相册并回传图片（0.2.1 新修复）；
  5. 使用真实 API Key 调用 LLM 的完整流程。

**真机复测清单（交付前逐项勾选）**：

1. 安装 0.2.1 → 首次启动，确认无错误页；
2. 设置页填写 LLM 档案 → 「测试连接」成功；
3. 切换为 English，检查页面文字与四个提示词模板名称已翻译；
4. 记录页点「添加食物图片」，选 1–2 张，确认缩略图出现；
5. 四类 AI 任务各跑一次（饮食估算、运动估算、基础代谢估算、周期报告分析）；
6. 报告页生成周报/月报；
7. 更新日志弹窗显示 v0.2.1 与 v0.2.0 两个版本。

如果安装后启动失败，应用会显示明确的错误页；也可用数据线抓日志：

```powershell
$adb = ".android-build\tools\sdk\platform-tools\adb.exe"
& $adb logcat -s CalorieTracker python.stdout python.stderr
```

## 安全提示

- `keystore.properties` 与 `.android-build/keystore/*.jks` 含**明文签名口令**，
  请勿提交到公开仓库或分享；丢失 keystore 后无法对同一应用做覆盖升级。
- `config.json` 里的 LLM API Key 为明文，仅保存在应用私有目录；
  换手机或重置应用后需要重新填写。
- 该 APK 是自签名应用，不是应用商店版本，安装时需允许「未知来源」。
