@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  set "PYTHON_CMD=python"
) else (
  set "PYTHON_CMD=py -3"
)
%PYTHON_CMD% installer\build_windows.py
if errorlevel 1 (
  echo 打包失败，请查看上方错误信息。需要 64 位 Python 3.11+ 和 NSIS 3。
  pause
  exit /b 1
)
echo.
echo 打包完成：releases\ImageFlow-1.2.0-Windows-x86-x64-Setup.exe
pause
