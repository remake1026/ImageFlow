ImageFlow 1.1.0 安装说明

系统要求：Windows 10 1809（内部版本 17763）及以上 / Windows 11，64 位。
安装包自带 Python、Qt 和图片处理运行库，无需另行安装依赖。

1. 双击 ImageFlow-1.1.0-Win10-11-Setup.exe。
2. 点击“下一步”，选择完整安装目录，例如 D:\软件\ImageFlow。
3. 选择桌面和开始菜单快捷方式，首次安装均默认勾选，可取消。
4. 安装结束后，可勾选“运行 ImageFlow”，再点击“完成”。

默认安装到当前用户，无需管理员权限；请选择有写入权限的目录。
更新：先退出 ImageFlow，再运行安装包。新版安装会记住上次路径和选项。
旧 ZIP 版升级：选中原来包含 ImageFlow.exe 的目录，不要选它的父目录。
卸载：Windows 设置 → 应用 → ImageFlow → 卸载，或运行 Uninstall.exe。
卸载保留用户预设、SKU 数据、原图、项目及安装目录内用户自行添加的文件。

静默安装（/D 必须放最后，路径不加引号）：
ImageFlow-1.1.0-Win10-11-Setup.exe /S /DESKTOP=1 /STARTMENU=1 /D=D:\软件\ImageFlow
将 1 改为 0 可取消相应快捷方式。静默安装不会自动启动软件。

源码与安装包：https://github.com/remake1026/ImageFlow
文件校验值：releases/SHA256SUMS.txt
