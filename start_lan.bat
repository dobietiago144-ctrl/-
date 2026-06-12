@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 政策文件审查 — 局域网模式
set POLICY_REVIEWER_MODE=lan

:: ---- 环境检查 ----
echo [检查] 正在检测 Python 环境...
where python >nul 2>&1 || (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause & exit /b 1
)

echo [检查] 正在检测依赖包...
python -c "import streamlit" >nul 2>&1 || (
    echo [提示] 依赖未安装，请先运行 install.bat
    pause & exit /b 1
)

:: ---- 检测局域网 IP（只运行一次）----
echo [检查] 正在检测局域网 IP 地址...
python detect_ip.py
if %errorlevel% neq 0 (
    echo [警告] IP 检测未完全成功，继续启动...
)

:: 从临时文件读取 LAN_IPS
set "POLICY_REVIEWER_LAN_IPS="
if exist "%TEMP%\lan_ip_display.txt" (
    for /f "usebackq tokens=1* delims==" %%a in (`findstr /b "LAN_IPS=" "%TEMP%\lan_ip_display.txt" 2^>nul`) do (
        set "POLICY_REVIEWER_LAN_IPS=%%b"
    )
)

:: ---- 启动信息 ----
echo.
echo =======================================================
echo     政策文件依据有效性审查程序 — 局域网共享模式
echo =======================================================
echo.
echo   本机访问：http://127.0.0.1:8501
echo.
echo   局域网访问地址：
echo   ------------------------------------------------
if exist "%TEMP%\lan_ip_display.txt" (
    type "%TEMP%\lan_ip_display.txt" 2>nul | findstr /v "LAN_IPS="
) else (
    echo   （未能检测到局域网 IP）
)
echo   ------------------------------------------------
echo.
echo =======================================================
echo   [安全提醒]
echo   当前为局域网共享模式，请仅在可信内网环境使用。
echo   请勿将端口暴露到公网。
echo =======================================================
echo.
echo [启动] 正在启动 Streamlit 服务...

streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless false

if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序启动失败，请检查上方错误信息。
)
pause
