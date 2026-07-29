# ImageFlow

> 面向产品图片交付的本地批量裁剪、加水印、命名与导出工具。

ImageFlow 是一款基于 Windows 的桌面应用。它将多尺寸裁剪、构图微调、水印、文件命名和批量导出集中在一个工作区中；所有编辑均以参数方式保存，**不会重命名、覆盖或修改导入的原始照片**。

## 界面预览

<p align="center">
  <img src="docs/images/imageflow-overview.png" alt="ImageFlow 主界面：图片列表、裁剪画布、尺寸和水印设置" width="1000">
</p>

## 核心功能

- 导入 JPG、PNG、WebP、TIFF、BMP 等常用图片格式，支持批量处理。
- 内置原图比例、1:1、4:5、3:4、9:16、16:9 等尺寸；可新增、修改或删除自定义尺寸。
- 每张图片、每个尺寸独立保存裁剪缩放与位置；支持方向键微调、滚轮缩放、自动居中和三分法辅助线。
- 可切换“显示裁剪后预览”，快速查看最终构图而不影响裁剪参数。
- 支持透明 PNG 水印，提供定位、偏移、大小、透明度、旋转、边距与安全区设置。
- 关闭“启用水印”后，所有编辑预览与最终导出都会移除水印。
- 支持品牌、SKU、颜色、日期、序号等命名规则；可选择保留原始文件名或完全覆盖为规则名称。
- 支持 JPG / PNG / WebP 导出、质量设置、ICC/EXIF 选项、按尺寸建立子文件夹和同名保护。
- 支持保存与打开项目文件，保留导入路径和编辑参数；支持水印和命名预设。
- 右侧设置面板可独立展开多个设置项，并支持滚动浏览。

## 快速开始

### 从源码运行

环境要求：Windows、Python 3.11 或更高版本。

```bat
git clone https://github.com/remake1026/ImageFlow.git
cd ImageFlow
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

也可以直接双击 [start.bat](start.bat) 启动。

### 使用安装包

若获得发行版 ZIP，解压后双击 `Install.bat`。安装程序会显示目录选择框，可将软件安装到任意磁盘或文件夹，并自动创建桌面快捷方式。

## 基本工作流

1. 点击“导入照片”，选择需要交付的成片。
2. 在“尺寸设置”中勾选需要的比例，并从“尺寸预览”选择要编辑的尺寸。
3. 在画布中调整构图；需要时开启裁剪结果预览确认效果。
4. 在“水印设置”“命名设置”“导出设置”中配置输出规则。
5. 点击“一键导出全部”，将所有已选尺寸批量导出。

## 打包 Windows 应用

项目使用 PyInstaller 生成独立的 Windows 应用。安装依赖后可直接运行：

```bat
build.bat
```

或使用当前打包配置：

```bat
py -3.11 -m PyInstaller --noconfirm --clean "NuPhy图片交付助手.spec"
```

> PyInstaller 的 `build*` 与 `dist*` 目录属于可再生成产物，已由 `.gitignore` 排除。

## 项目结构

```text
main.py                    主窗口、界面交互与应用流程
app/crop_canvas.py         中央裁剪画布与结果预览
app/image_processor.py     图片方向修正、裁剪与水印渲染
app/exporter.py            后台批量导出
app/models.py              图片、尺寸、裁剪、水印和导出数据模型
app/project_io.py          项目文件读写
app/presets.py             本地预设存储
app/product_catalog.py     SKU 与颜色数据读取
products.csv               SKU / 颜色下拉数据
resources/                 图标与深色主题样式
installer/                 发行包安装脚本
```

## 技术栈

- Python
- PySide6
- Pillow
- PyInstaller

## 数据与隐私

ImageFlow 在本机处理图片。裁剪、水印和命名均作为编辑参数保存，原始照片不会被修改；导出时仅生成新的输出文件。
