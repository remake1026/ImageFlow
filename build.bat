@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.11 -m pip install -r requirements.txt
if errorlevel 1 (
  echo 依赖安装失败，无法打包。
  pause
  exit /b 1
)
py -3.11 -m PyInstaller --noconfirm --clean --windowed --add-data "resources;resources" --add-data "products.csv;." --name "NuPhy图片交付助手" main.py
if errorlevel 1 (
  echo 打包失败，请查看上方错误信息。
  pause
  exit /b 1
)
copy /Y "products.csv" "dist\NuPhy图片交付助手\products.csv" >nul
echo.
echo 打包完成：dist\NuPhy图片交付助手\NuPhy图片交付助手.exe
pause
