@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  set "PYTHON_CMD=python"
) else (
  set "PYTHON_CMD=py -3"
)
%PYTHON_CMD% -m pip install -r installer\requirements-build.txt
if errorlevel 1 (
  echo 依赖安装失败，无法打包。
  pause
  exit /b 1
)
%PYTHON_CMD% -m PyInstaller --noconfirm --clean "ImageFlow.spec"
if errorlevel 1 (
  echo 打包失败，请查看上方错误信息。
  pause
  exit /b 1
)
%PYTHON_CMD% installer\build_installer.py
if errorlevel 1 (
  echo 安装包生成失败，请确认已安装 NSIS 3。
  pause
  exit /b 1
)
echo.
echo 打包完成：releases\ImageFlow-1.1.0-Win10-11-Setup.exe
pause
