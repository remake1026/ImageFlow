param([int]$AppPid, [string]$Installer, [string]$AppPath)
$ErrorActionPreference = 'Stop'
try {
    $process = Get-Process -Id $AppPid -ErrorAction SilentlyContinue
    if ($process) { $process.WaitForExit(60000) | Out-Null }
    if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) { throw 'ImageFlow 未能正常退出，请关闭后重试。' }
    $installDir = Split-Path -Parent $AppPath
    $result = Start-Process -FilePath $Installer -ArgumentList "/S /D=$installDir" -Wait -PassThru
    if ($result.ExitCode -ne 0) { throw "安装程序返回错误代码 $($result.ExitCode)，请检查软件是否已关闭以及安装目录的权限。" }
    Remove-Item -LiteralPath $Installer -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath $AppPath
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("更新失败：$($_.Exception.Message)`n安装包保存在：$Installer", 'ImageFlow 更新') | Out-Null
}
