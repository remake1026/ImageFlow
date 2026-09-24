# ImageFlow

ImageFlow 是一款 Windows 桌面应用，将多尺寸裁剪、构图微调、水印、文件命名和批量导出集中在一个工作区中。所有编辑均以参数方式保存，**不会重命名、覆盖或修改导入的原始照片**。

## 界面预览

<p align="center">
  <img src="docs/images/imageflow-overview.png" alt="ImageFlow 主界面：图片列表、裁剪画布、尺寸和水印设置" width="1000">
</p>

## 基本使用流程

1. 点击“导入照片”，选择需要交付的成片。
2. 在“尺寸设置”中勾选需要的比例，并从“尺寸预览”选择要编辑的尺寸。
3. 在画布中调整构图；在裁剪框内双击可查看裁剪后预览，再次双击或点击顶部“恢复默认构图预览”即可继续编辑。
4. 在“水印设置”“命名设置”“导出设置”中配置输出规则。
5. 点击“一键导出全部”，将所有已选尺寸批量导出。

## 核心功能

- 批量导入 JPG、PNG、WebP、TIFF、BMP 等常用图片格式。
- 内置原图比例、1:1、4:5、3:4、9:16、16:9 等尺寸，支持自定义尺寸。
- 每张图片、每个尺寸独立保存裁剪缩放与位置；支持方向键微调、滚轮缩放、自动居中和三分法辅助线。
- 支持透明 PNG 水印的位置、大小、透明度、旋转、边距与安全区设置；关闭水印后，预览和导出均不显示水印。
- 支持品牌、产品、颜色、日期、序号等命名规则，可选择保留原文件名或完全覆盖为规则名称。
- 支持 JPG / PNG / WebP 导出、质量设置、ICC/EXIF 选项、按尺寸建立子文件夹和同名保护。
- 支持保存与打开项目文件，保留导入路径和编辑参数；支持水印和命名预设。
- 顶部为单排深色自定义标题栏，Logo、ImageFlow、“管理后台”和窗口控制按钮位于同一排；支持窗口拖动、双击最大化/还原和边缘缩放。“管理后台”可查看并清除预览缓存，以及新增、删除产品和维护其可选颜色；产品表格支持双击单元格编辑，点击空白处自动保存并即时刷新命名下拉框。

## 安装教程

### 从源码运行

1. 安装 [Python 3.11 或更高版本](https://www.python.org/downloads/)。安装时请勾选 **Add Python to PATH**。
2. 下载本仓库的源码 ZIP，或执行：

   ```bat
   git clone https://github.com/remake1026/ImageFlow.git
   ```

3. 进入项目文件夹后，双击 `start.bat`。首次运行会自动安装所需依赖，随后启动 ImageFlow。

也可以使用命令行：

```bat
cd ImageFlow
py -3.11 -m pip install -r requirements.txt
py -3.11 main.py
```

## 开发与打包

项目使用 Python、PySide6、Pillow、PyInstaller 和 [NSIS 3](https://nsis.sourceforge.io/Download)。Windows x64 发行构建采用 Python 3.14，依赖固定在 `installer/requirements-build.txt`，Qt 限制在支持 Windows 10 的版本范围内。

```bat
build.bat
```

也可分步构建：

```bat
py -3.14 -m pip install -r installer/requirements-build.txt
py -3.14 -m PyInstaller --noconfirm --clean "ImageFlow.spec"
py -3.14 installer/build_installer.py
```

> `build*`、`dist*`、安装临时目录和 `releases/` 中的发行产物均可再生成，且不会提交到仓库。

构建产物会输出到 `releases/`。如 NSIS 不在 PATH，可给构建脚本传入 `--makensis C:\路径\makensis.exe`。静默安装参数见 [安装说明](installer/README.txt)。

## 项目结构

```text
main.py                    主窗口、界面交互与应用流程
app/                       裁剪画布、图像处理、导出与数据模型
resources/                 图标与深色主题样式
products.csv               产品/ 颜色下拉数据
installer/                 发行包安装脚本
docs/images/               README 配图
```

## 数据与隐私

ImageFlow 在本机处理图片。裁剪、水印和命名均作为编辑参数保存，原始照片不会被修改；导出时仅生成新的输出文件。
