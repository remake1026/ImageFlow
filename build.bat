@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  set "PYTHON_CMD=python"
) else (
  set "PYTHON_CMD=py -3"
)
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
  echo 依赖安装失败，无法打包。
  pause
  exit /b 1
)
%PYTHON_CMD% -m PyInstaller --noconfirm --clean "NuPhy图片交付助手.spec"
if errorlevel 1 (
  echo 打包失败，请查看上方错误信息。
  pause
  exit /b 1
)
copy /Y "products.csv" "dist\NuPhy图片交付助手\products.csv" >nul
echo.
echo 打包完成：dist\NuPhy图片交付助手\NuPhy图片交付助手.exe
pause
