#!/bin/bash
# Run on the Mac architecture targeted by this build (arm64 or x86_64).
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
  echo '请在 macOS 上运行此脚本。' >&2
  exit 1
fi
arch="$(uname -m)"
case "$arch" in arm64|x86_64) ;; *) echo "不支持的处理器: $arch" >&2; exit 1 ;; esac
python_cmd="${PYTHON:-python3}"
"$python_cmd" -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11 或更新版本"'
venv="installer_staging/venv-mac-$arch"
"$python_cmd" -m venv "$venv"
python="$venv/bin/python"
python_arch="$("$python" -c 'import platform; print(platform.machine())')"
if [[ "$python_arch" != "$arch" ]]; then
  echo "Python 架构 $python_arch 与目标 Mac 架构 $arch 不一致。请安装对应架构的 Python。" >&2
  exit 1
fi
"$python" -m pip install -r installer/requirements-build.txt
QT_QPA_PLATFORM=offscreen "$python" -m unittest discover -s tests -v
"$python" -m PyInstaller --noconfirm --clean --distpath "dist/mac-$arch" --workpath "build/mac-$arch" ImageFlow-mac.spec
mkdir -p releases installer_staging
stage="$(mktemp -d "$(pwd)/installer_staging/mac-dmg.XXXXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
cp -R "dist/mac-$arch/ImageFlow.app" "$stage/"
ln -s /Applications "$stage/Applications"
output="$(pwd)/releases/ImageFlow-1.2.0-macOS-$arch.dmg"
if [[ -e "$output" ]]; then
  echo "输出文件已存在：$output；请先移走旧文件。" >&2
  exit 1
fi
hdiutil create -volname ImageFlow -srcfolder "$stage" -format UDZO "$output"
echo "生成完成：$output"
echo '此构建未使用 Apple Developer ID 签名或公证，分发前请在 Mac 上测试。'
