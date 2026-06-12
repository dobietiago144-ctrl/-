@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 政策文件审查 — 单机模式
set POLICY_REVIEWER_MODE=local

:: ---- 环境检查 ----
where python >nul 2>&1 || (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause & exit /b 1
)
python -c "import streamlit" >nul 2>&1 || (
    echo [提示] 依赖未安装，请先运行 install.bat
    pause & exit /b 1
)

:: ---- 启动信息 ----
echo.
echo =======================================================
echo     政策文件依据有效性审查程序 — 单机模式
echo =======================================================
echo   仅限本机浏览器访问。
echo   访问地址：http://127.0.0.1:8501
echo =======================================================
echo.

start "" http://127.0.0.1:8501
streamlit run app.py --server.address 127.0.0.1 --server.port 8501

if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序启动失败，请检查上方错误信息。
)
pause
