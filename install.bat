@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 政策文件审查 — 安装依赖

echo.
echo =======================================================
echo     正在安装依赖...
echo =======================================================
echo.

where python >nul 2>&1 || (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause & exit /b 1
)

pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo.
    echo =======================================================
    echo   依赖安装完成。请双击 start_local.bat 或 start_lan.bat
    echo =======================================================
) else (
    echo.
    echo [错误] 安装失败，请检查上方错误信息。
)
pause
