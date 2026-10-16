@echo off
chcp 65001 >nul
title m4s2mp42
cd /d "%~dp0"

where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0m4s2mp42.py"
    exit /b 0
)

where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0m4s2mp42.py"
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0m4s2mp42.py"
    if errorlevel 1 pause
    exit /b %errorlevel%
)

echo 未找到 Python 3，请先从 https://www.python.org/ 安装。
pause
exit /b 1
