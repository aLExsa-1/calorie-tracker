# AGC「方式二」上传签名密钥（pepk）操作指引

> 目标任务：按 AGC 文档《方式二：AppGallery Connect 仅管理开发者上传的签名密钥》，
> 把 calorie-tracker 现有的 release 签名密钥打包成 `sign.zip` 上传，
> 之后 AGC 用**同一把密钥**为分发到用户设备的应用签名。

## 一、当前状态（本机实测，2026 会话）

| 项 | 值 |
|---|---|
| 包名 | `com.calorietracker.app` |
| 版本 | versionName `0.4.0` / versionCode `7` |
| 待上架包 | `release/CalorieTracker-0.4.0-arm64.apk`（仅 arm64-v8a，已签名，v2+v3） |
| 签名密钥库 | `.android-build/keystore/calorietracker-release.jks` |
| 该 APK 证书 SHA-256 | `6dbfb59428c29b9108a1cf74f1735a3546e19bcb014d09180e5d862bce5b0ab6` |
| 证书 DN | `CN=Calorie Tracker, OU=Personal, O=CalorieTracker, L=Local, ST=Local, C=CN` |
| 可用 JDK | `.android-build/tools/jdk-17/bin/java.exe`（Temurin 17.0.20.1） |
| **pepk.jar** | **已就绪**：`.android-build/agc/pepk.jar`（本地源码编译 + 往返自测通过） |
| 别名与口令 | `android/keystore.properties`（**红线：不读取、不输出、不提交**） |

官方 pepk 下载地址已失效，本仓库改为**用公开源码自建**并保留可审计性，
细节（来源、4 处本地改动、自测方法、重建命令）见 `.android-build/agc/README.md`。
脚本会打印所用 jar 的 sha256，本次构建为
`408ed288f046cecdf07fc0cf328d075cfc20c691476779de97ee77847ae42871`。

## 二、操作步骤

### 步骤 A：确认 pepk.jar 就位

`.android-build/agc/pepk.jar` 已存在即无需任何下载动作。若将来丢失，按
`.android-build/agc/README.md` 第四节重建（无需联网也能从 `pepk-src/` 编译）。

### 步骤 B：取 encryptionkey（**必须来自你自己应用的 AGC 页面**）

在 AGC：「我的应用」→ 选中 Calorie Tracker（`com.calorietracker.app`）→「应用签名」→ 方式二 →
步骤 c 的命令里，`--encryptionkey=` 后面那一串就是。

它必须是 **136 个十六进制字符**（= 4 字节 keyId + 64 字节 P-256 点，工具里写死的长度）。

文档示例里那串（你第一次粘贴的）是 **137 个字符**，多了一个 `F`：

- 原文：`...A0F43461F9FE140F278A5D...`
- 修正：`...A0F43461F9E140F278A5D...`（`F9FE140` 里多了一个 `F`，应为 `F9E140`）

判定依据：把 137 个字符的所有单字符删/改/插变体（约 4500 个）逐个做 P-256 曲线检验，
**只有"删掉索引 106 的 F"这一个**满足曲线方程——随机字节落在 P-256 上的概率约 2⁻²⁵⁶，
所以这几乎可以确定就是原值被多复制了一个字符。修正后应为：

```
034200041E224EE22B45D19B23DB91BA9F52DE0A06513E03A5821409B34976FDEED6E0A47DBA48CC249DD93734A6C5D9A0F43461F9E140F278A5D2860846C2CF5D2C3C02
```

该串是**公钥**（非机密）。仍建议以你页面上复制的为准；两者应完全一致。

### 步骤 C：打包加密

双击仓库根目录的 `agc-upload-signing-key.cmd`，按提示操作：

1. 提示 `encryptionkey（粘贴后按回车）` 时，**整行粘贴** AGC 那条 `java -jar pepk.jar ...` 命令
   也行（脚本会自动截出 `--encryptionkey=` 后面的十六进制并做校验），只粘贴密钥本身也行；
2. 脚本会先校验公钥（长度 136 + P-256 曲线），通过后才调用 pepk；
3. pepk 询问两次口令：先 keystore 口令、后该别名口令，输入不回显，相同就输同一个。

输出：`.android-build/keystore/agc-sign.zip`。

### 步骤 D：上传

回到 AGC「方式二」页面，在"上传步骤 c 生成的 zip 包"处点【浏览】选中 `agc-sign.zip`。

### 步骤 E：第 2 条（可选）留空

"（可选）上传不同于签名密钥的上传密钥"**不要填**——不填即用步骤 1 的签名密钥同时作为上传密钥，
签名密钥 / 上传密钥 / AGC 签名密钥三者同一把，已安装用户与后续升级都不会出现签名不一致。

### 步骤 F：核对指纹（验收）

AGC 显示的签名密钥指纹（SHA-256）应等于：

```
6dbfb59428c29b9108a1cf74f1735a3546e19bcb014d09180e5d862bce5b0ab6
```

本地可用自带 keytool 复核（会要求输入 keystore 口令，顺便确认 `Keystore type`）：

```cmd
"D:\deepseek workspace\calorie-tracker\.android-build\tools\jdk-17\bin\keytool.exe" -list -v -keystore "D:\deepseek workspace\calorie-tracker\.android-build\keystore\calorietracker-release.jks"
```

## 三、已经踩过并排掉的坑（2026 会话记录）

| 症状 | 根因 | 现状 |
|---|---|---|
| 官方 pepk.jar 下载 404 | Google 已下架该静态地址 | 改为源码自建 `pepk.jar`，见 `.android-build/agc/README.md` |
| `Invalid argument: -jar` | 脚本只想要密钥，却把整行命令粘了进去，`java -jar ...` 全变成了参数 | 脚本现在会从整行文本里自动截出 `--encryptionkey=` 的值 |
| `密钥长度 = 137` | 复制的密钥多了一个字符 | 脚本现在先校验长度，并给出上面那段修正值 |
| 报错信息里 `sha256 : CertUtil:` | `for /f` 里用 `%VAR%` 判断会被提前展开，导致每轮都覆盖 | 改成 `if not defined`，已显示正确哈希 |
| 公钥校验通过却仍报"没通过校验" | 在 `if (...)` 块里 `echo` 含括号的变量，括号提前闭合了块 | 改为 `goto` 分支，已验证 |

## 四、常见报错对照

| 现象 | 原因 | 处理 |
|---|---|---|
| `Unrecognized keystore format` / `别名不存在` | 文件不是 JKS/PKCS12，或 alias 写错 | 用上面 keytool 命令确认 `Keystore type` 与别名 |
| `KeyCheck` 报 `BAD ... bytes` | 密钥长度不对 | 回到 AGC 页面重新复制 |
| `BAD point is not on the curve` | 密钥被复制坏了 | 重新复制；必要时按第二节的变体搜索法定位 |
| `No console available` | 在无控制台环境运行（IDE 内、被重定向） | 用 `cmd.exe` 运行或直接双击 .cmd |
| 打包成功但 AGC 上传解析失败 | zip 不完整，或公钥与页面不一致 | 删除 zip 重新生成，确认公钥来源 |
| 上传后提示签名与已上架版本不一致 | 历史上用过另一把密钥签过包 | 先查 AGC 已登记指纹，不要盲目重建密钥 |

## 五、安全红线与善后

- **`agc-sign.zip` 里是加密私钥，而 encryptionkey 是公开的**：上传完成后**立刻删除**该 zip，
  不要放进 `release/`、不要发给任何人或 AI 会话。
- **不得删除或重建** `.android-build/keystore/calorietracker-release.jks`：丢失即无法覆盖升级。
  建议离线备份 jks 与口令（U 盘/密码管理器），口令只输入到你自己的终端，不要粘贴进聊天窗口。
- 不要运行来路不明的 `pepk.jar`：它经手你的签名私钥。优先用 `.android-build/agc/pepk.jar`。
- 启用 AGC 应用签名后，后续每个版本仍用同一把密钥签名（现有
  `python .android-build/sync_app.py` → `node .android-build/build_apk.js assembleRelease` →
  `python .android-build/finalize_apk.py` 流程不变）。

## 六、脚本维护说明

仓库根目录的 `agc-upload-signing-key.cmd` 是 **GBK(936) + CRLF** 编码——
cmd.exe 在中文 Windows 上按 GBK 读批处理，UTF-8 会显示成乱码。

- 母本（UTF-8）：`.android-build/agc/agc-upload-signing-key.utf8.cmd`
- 生成：`powershell -NoProfile -ExecutionPolicy Bypass -File .android-build\agc\mk-cmd.ps1`
  （本机 PowerShell 执行策略为 Restricted，**必须**加 `-ExecutionPolicy Bypass`）
- 改脚本请改母本再生成，不要直接编辑根目录那份。

## 七、结果摘要（执行完成后填写，≤300 字）

- 待填：上传时间、AGC 显示的密钥指纹、上传结果、`agc-sign.zip` 是否已删除。
