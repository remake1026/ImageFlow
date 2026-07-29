@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.11 -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo 依赖安装失败。请确认已安装 Python 3.11，且安装时勾选了“Add Python to PATH”。
  pause
  exit /b 1
)
py -3.11 main.py
if errorlevel 1 pause
