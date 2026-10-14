@echo off
setlocal
title AGC 方式二 - 打包签名密钥 (pepk)

rem ============================================================
rem  AGC 方式二：把 release 签名密钥打包成 agc-sign.zip
rem  本脚本不包含任何口令；口令由 pepk 运行时向你询问。
rem  口令输入时不回显字符，属正常现象。
rem
rem  维护说明：这是 UTF-8 母本，仓库根目录的 .cmd 由 mk-cmd.ps1 转成
rem  GBK + CRLF（cmd 在中文 Windows 上才能正确显示中文）。改这里再生成。
rem ============================================================

set "ROOT=%~dp0"
set "JKS=%ROOT%.android-build\keystore\calorietracker-release.jks"
set "OUTZIP=%ROOT%.android-build\keystore\agc-sign.zip"
set "PEPK=%ROOT%.android-build\agc\pepk.jar"
set "PROPS=%ROOT%android\keystore.properties"
set "KOUT=%ROOT%.android-build\agc\keycheck.out"

echo ============================================================
echo   AGC 方式二：打包签名密钥（pepk）
echo ============================================================
echo.

rem ---------- 1) 定位 java ----------
set "JAVA="
if exist "%ROOT%.android-build\tools\jdk-17\bin\java.exe" set "JAVA=%ROOT%.android-build\tools\jdk-17\bin\java.exe"
if not defined JAVA if exist "C:\Program Files\Java\jdk\bin\java.exe" set "JAVA=C:\Program Files\Java\jdk\bin\java.exe"
if not defined JAVA for %%J in (java.exe) do set "JAVA=%%~$PATH:J"
if not defined JAVA (
  echo [错误] 找不到 java.exe，请安装 JDK 17 或以上后重试。
  goto :end
)
echo [1/4] Java      : %JAVA%

rem ---------- 2) 定位 pepk.jar ----------
if not exist "%PEPK%" if exist "%ROOT%.android-build\keystore\pepk.jar" set "PEPK=%ROOT%.android-build\keystore\pepk.jar"
if not exist "%PEPK%" if exist "%ROOT%pepk.jar" set "PEPK=%ROOT%pepk.jar"
if not exist "%PEPK%" (
  echo [错误] 找不到 pepk.jar。
  echo        请把 pepk.jar 放到下面这个位置，再重新运行本脚本：
  echo        %ROOT%.android-build\agc\pepk.jar
  goto :end
)
set "JARHASH="
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "%PEPK%" SHA256 2^>nul') do if not defined JARHASH set "JARHASH=%%H"
if not defined JARHASH set "JARHASH=?"
echo [2/4] pepk.jar  : %PEPK%
echo       sha256    : %JARHASH%

rem ---------- 3) 校验密钥库并读取别名 ----------
if not exist "%JKS%" (
  echo [错误] 找不到签名密钥库：
  echo        %JKS%
  goto :end
)
set "ALIAS="
if exist "%PROPS%" for /f "usebackq tokens=2 delims==" %%A in (`findstr /b /i "keyAlias" "%PROPS%"`) do set "ALIAS=%%A"
if defined ALIAS set "ALIAS=%ALIAS: =%"
if not defined ALIAS set /p "ALIAS=未能自动读取别名，请手动输入 keyAlias（在 android\keystore.properties 里）: "
if not defined ALIAS (
  echo [错误] 别名为空。
  goto :end
)
echo [3/4] 密钥库    : %JKS%
echo       别名 alias: %ALIAS%
echo       输出文件  : %OUTZIP%

rem ---------- 4) 取 encryptionkey 并校验 ----------
echo.
echo 请到 AGC 后台（我的应用 - 应用签名 - 方式二 - 步骤 c）复制 encryptionkey。
echo 可以【整行粘贴】那条 java -jar pepk.jar ... 命令，也可以只粘贴密钥本身，
echo 脚本都会自动截出 --encryptionkey= 后面的那串十六进制。
echo.
set "RAW="
set /p "RAW=encryptionkey（粘贴后按回车）: "
if not defined RAW (
  echo [错误] 没有输入任何内容。
  goto :end
)
set "RAW=%RAW:"=%"
set "TMP=%RAW:*--encryptionkey=%"
if not "%TMP%"=="%RAW%" set "RAW=%TMP%"
if "%RAW:~0,1%"=="=" set "RAW=%RAW:~1%"
set "KEY="
for /f "tokens=1 delims= " %%A in ("%RAW%") do set "KEY=%%A"
if not defined KEY (
  echo [错误] 没能从输入里截出密钥，请重新粘贴。
  goto :end
)

rem 危险字符守卫（截出的内容应当只有十六进制字符）
set "T=%KEY%"
if not "%T%"=="%T:&=%" goto :badkey
if not "%T%"=="%T:|=%" goto :badkey
if not "%T%"=="%T:>=%" goto :badkey
if not "%T%"=="%T:<=%" goto :badkey
if not "%T%"=="%T:^=%" goto :badkey

set "LEN=0"
set "S=%T%"
:strlen
if not defined S goto :strlen_done
set "S=%S:~1%"
set /a LEN+=1
goto :strlen
:strlen_done

if not "%LEN%"=="136" (
  echo.
  echo [错误] 密钥长度 = %LEN% 个十六进制字符，pepk 要求正好 136 个
  echo        （4 字节 keyId + 64 字节 P-256 点）。
  echo        常见原因：
  echo          1. 复制到的是文档里的示例值，不是你自己应用的密钥；
  echo          2. 复制时多带或少带了一个字符。
  echo        请回到 AGC 后台对应页面重新复制，整行命令粘贴也可以。
  goto :end
)

"%JAVA%" -cp "%PEPK%" com.google.security.keymaster.lite.KeyCheck %KEY% > "%KOUT%" 2>&1
set "KRC=%ERRORLEVEL%"
set "KLINE="
for /f "usebackq delims=" %%L in ("%KOUT%") do if not defined KLINE set "KLINE=%%L"
del "%KOUT%" >nul 2>nul
if "%KLINE:~0,2%"=="OK" goto :key_ok
if "%KLINE:~0,3%"=="BAD" goto :key_bad
echo [4/4] 公钥校验 : 当前 pepk.jar 不含内置校验，跳过（由 pepk 自行校验）
goto :run

:key_ok
echo [4/4] 公钥校验 : %KLINE%
goto :run

:key_bad
echo [4/4] 公钥校验 : %KLINE%
echo.
echo [错误] 这串公钥没通过校验，说明它被复制坏了或不是对应版本的密钥。
echo        请回到 AGC 后台重新复制，或把原文发给助手排查。
goto :end

:run
echo.
echo 开始打包。接下来 pepk 会询问两次口令：
echo   第一次是 keystore 口令，第二次是该别名的口令。
echo   输入时屏幕不显示任何字符，属正常现象；两个口令相同就两次输入同一个。
echo.
del "%OUTZIP%" >nul 2>nul
"%JAVA%" -jar "%PEPK%" --keystore "%JKS%" --alias "%ALIAS%" --output="%OUTZIP%" --encryptionkey=%KEY% --include-cert
set "RC=%ERRORLEVEL%"
echo.

if exist "%OUTZIP%" (
  echo [成功] 已生成加密的签名密钥包：
  for %%F in ("%OUTZIP%") do echo        %%~fF  ^(%%~zF 字节^)
  echo.
  echo 下一步：
  echo   1. 回到 AGC「方式二」页面，点【浏览】上传这个 zip 包；
  echo   2. 第 2 条「上传不同于签名密钥的上传密钥」留空不填；
  echo   3. 上传成功后立刻删除该 zip（里面是加密私钥，不要外发、不要提交）。
) else (
  echo [失败] 未生成 zip 包（pepk 退出码 %RC%）。
  echo        请把上面的报错原文发给助手排查，参考 docs\tasks\agc-signing-key-upload.md 第三节。
)
echo.
echo 本应用当前证书 SHA-256（用于与 AGC 后台显示的密钥指纹核对）：
echo   6dbfb59428c29b9108a1cf74f1735a3546e19bcb014d09180e5d862bce5b0ab6
goto :end

:badkey
echo.
echo [错误] 截出的密钥里有非法字符，请重新粘贴（只应是 0-9 a-f 这 16 个字符）。

:end
echo.
pause
endlocal
