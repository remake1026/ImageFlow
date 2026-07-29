Add-Type -AssemblyName System.Windows.Forms

$ErrorActionPreference = 'Stop'
$appName = 'NuPhy 图片交付助手'
$sourceApp = Join-Path $PSScriptRoot 'app'

if (-not (Test-Path -LiteralPath $sourceApp)) {
    [System.Windows.Forms.MessageBox]::Show(
        '安装包内容不完整：未找到 app 文件夹。',
        $appName,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '请选择安装位置（可选择任意磁盘或文件夹）'
$dialog.ShowNewFolderButton = $true
$dialog.SelectedPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)

if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    exit 0
}

$installPath = Join-Path $dialog.SelectedPath $appName
if (Test-Path -LiteralPath $installPath) {
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "`"$installPath`" 已存在。是否使用本安装包更新其中的文件？",
        $appName,
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) {
        exit 0
    }
}

try {
    New-Item -ItemType Directory -Path $installPath -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceApp '*') -Destination $installPath -Recurse -Force

    $exe = Get-ChildItem -LiteralPath $installPath -Filter '*.exe' -File | Select-Object -First 1
    if (-not $exe) {
        throw '安装文件中未找到应用程序。'
    }

    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    $shortcutPath = Join-Path $desktop "$appName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $exe.FullName
    $shortcut.WorkingDirectory = $installPath
    $shortcut.IconLocation = "$($exe.FullName),0"
    $shortcut.Description = $appName
    $shortcut.Save()

    [System.Windows.Forms.MessageBox]::Show(
        "安装完成。`n`n安装位置：$installPath`n桌面快捷方式已创建。",
        $appName,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
    exit 0
}
catch {
    [System.Windows.Forms.MessageBox]::Show(
        "安装失败：$($_.Exception.Message)",
        $appName,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}
