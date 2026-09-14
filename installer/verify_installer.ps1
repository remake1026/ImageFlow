param([string]$Installer = (Join-Path $PSScriptRoot '..\releases\ImageFlow-1.1.0-Win10-11-Setup.exe'))
$ErrorActionPreference = 'Stop'
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$repoRoot = Split-Path $PSScriptRoot -Parent
$testRoot = Join-Path $repoRoot ('installer_staging\verification-' + [guid]::NewGuid().ToString('N'))
$installDir = Join-Path $testRoot '中文路径 with spaces\ImageFlow'
$registryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ImageFlow'
$desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ImageFlow.lnk'
$menuDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'ImageFlow'
if (Test-Path -LiteralPath $registryPath) { throw 'Existing ImageFlow install detected; use a clean test account.' }
if (Test-Path -LiteralPath $menuDir) { throw 'Existing ImageFlow Start menu folder detected; use a clean test account.' }
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$backupLink = Join-Path $testRoot 'original-desktop.lnk'
if (Test-Path -LiteralPath $desktopLink) { Copy-Item -LiteralPath $desktopLink -Destination $backupLink }
$results = [System.Collections.Generic.List[string]]::new()
function Assert-Check([bool]$Condition, [string]$Name) {
    if (-not $Condition) { throw "FAIL: $Name" }
    $results.Add($Name)
    Write-Output "PASS: $Name"
}
function Invoke-Setup([string]$Arguments, [int]$Expected = 0) {
    $process = Start-Process -FilePath $Installer -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) { Stop-Process -Id $process.Id; throw 'Installer timed out' }
    Assert-Check ($process.ExitCode -eq $Expected) "Installer exit $Expected [$Arguments]"
}
function Invoke-Uninstall {
    $uninstaller = Join-Path $installDir 'Uninstall.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        # _?= keeps the uninstaller in its directory and makes the wait deterministic.
        $process = Start-Process -FilePath $uninstaller -ArgumentList "/S _?=$installDir" -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit(60000)) { Stop-Process -Id $process.Id; throw 'Uninstaller timed out' }
        Assert-Check ($process.ExitCode -eq 0) 'Uninstaller exit 0'
    }
}
$appProcess = $null
try {
    Invoke-Setup "/S /DESKTOP=0 /STARTMENU=0 /D=$installDir"
    Assert-Check (Test-Path -LiteralPath "$installDir\ImageFlow.exe") 'Install into Chinese and space-containing path'
    if (Test-Path -LiteralPath $backupLink) {
        Assert-Check ((Get-FileHash -LiteralPath $desktopLink).Hash -eq (Get-FileHash -LiteralPath $backupLink).Hash) 'Unchecked desktop option preserves existing shortcut'
    } else { Assert-Check (-not (Test-Path -LiteralPath $desktopLink)) 'Unchecked desktop option creates no shortcut' }
    Assert-Check (-not (Test-Path -LiteralPath $menuDir)) 'Unchecked Start menu option creates no folder'
    $entry = Get-ItemProperty -LiteralPath $registryPath
    Assert-Check ($entry.InstallLocation -eq $installDir -and $entry.DisplayVersion -eq '1.1.0') 'Windows uninstall registration and version'
    Assert-Check ($entry.UninstallString -eq ('"' + $installDir + '\Uninstall.exe"')) 'Quoted uninstall path'
    $appProcess = Start-Process -FilePath "$installDir\ImageFlow.exe" -WorkingDirectory $installDir -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 5
    $appProcess.Refresh()
    Assert-Check (-not $appProcess.HasExited -and $appProcess.MainWindowTitle -match 'ImageFlow') 'Installed application opens its main window'
    Invoke-Setup "/S /D=$installDir" 3
    Stop-Process -Id $appProcess.Id
    $appProcess.WaitForExit()
    $appProcess = $null
    [IO.File]::WriteAllText("$installDir\my-photo.txt", 'user file must survive')
    [IO.File]::WriteAllText("$installDir\products.csv", "Product,Colors`nCustom,Red")
    Invoke-Setup '/S /DESKTOP=1 /STARTMENU=1'
    Assert-Check ((Get-ItemProperty -LiteralPath $registryPath).InstallLocation -eq $installDir) 'Update remembers previous custom directory without /D'
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($desktopLink)
    Assert-Check ($link.TargetPath -eq "$installDir\ImageFlow.exe" -and $link.WorkingDirectory -eq $installDir) 'Desktop shortcut target and working directory'
    Assert-Check (Test-Path -LiteralPath "$menuDir\ImageFlow.lnk") 'Start menu application shortcut'
    Assert-Check (Test-Path -LiteralPath "$menuDir\卸载 ImageFlow.lnk") 'Start menu uninstaller shortcut'
    Invoke-Setup '/S /DESKTOP=0 /STARTMENU=0'
    Assert-Check (-not (Test-Path -LiteralPath $desktopLink) -and -not (Test-Path -LiteralPath $menuDir)) 'Update can remove previously selected shortcuts'
    Assert-Check ((Get-Content -LiteralPath "$installDir\products.csv" -Raw) -match 'Custom') 'Update preserves legacy user catalog'
    Invoke-Setup '/S /DESKTOP=1 /STARTMENU=1'
    Invoke-Uninstall
    Assert-Check (-not (Test-Path -LiteralPath "$installDir\ImageFlow.exe")) 'Uninstall removes application'
    Assert-Check (-not (Test-Path -LiteralPath $registryPath)) 'Uninstall removes registration'
    Assert-Check (-not (Test-Path -LiteralPath $desktopLink) -and -not (Test-Path -LiteralPath $menuDir)) 'Uninstall removes owned shortcuts'
    Assert-Check ((Get-Content -LiteralPath "$installDir\my-photo.txt" -Raw) -eq 'user file must survive') 'Uninstall preserves user-added files'
    Assert-Check ((Get-Content -LiteralPath "$installDir\products.csv" -Raw) -match 'Custom') 'Uninstall preserves legacy user catalog'
    $occupied = Join-Path $testRoot 'unrelated-folder'
    New-Item -ItemType Directory -Path $occupied | Out-Null
    [IO.File]::WriteAllText("$occupied\keep.txt", 'unchanged')
    Invoke-Setup "/S /D=$occupied" 2
    Assert-Check (-not (Test-Path -LiteralPath "$occupied\ImageFlow.exe")) 'Refuse unrelated occupied directory'
    $results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testRoot 'results.json') -Encoding utf8
    Write-Output "Verification report: $testRoot\results.json"
} finally {
    if ($appProcess -and -not $appProcess.HasExited) { Stop-Process -Id $appProcess.Id }
    Invoke-Uninstall
    if (Test-Path -LiteralPath $backupLink) { Copy-Item -LiteralPath $backupLink -Destination $desktopLink -Force }
}
