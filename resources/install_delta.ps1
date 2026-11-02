param([int]$AppPid, [string]$Plan, [string]$AppPath, [switch]$NoRestart, [switch]$QuietFailure)
$ErrorActionPreference = 'Stop'
$stage = Split-Path -Parent ([IO.Path]::GetFullPath($Plan))
$journal = [Collections.Generic.List[object]]::new()
$rollbackFailed = $false
$root = Split-Path -Parent ([IO.Path]::GetFullPath($AppPath))

function Safe-Path([string]$Base, [string]$Relative) {
    if ($Relative -ne 'ImageFlow.exe' -and -not $Relative.StartsWith('_internal/')) { throw 'Invalid application path.' }
    if ($Relative -match '[\\:<>"|?*\x00-\x1f]' -or $Relative -match '(^|/)(\.|\.\.|)(/|$)' -or $Relative -match '[. ](/|$)' -or $Relative -match '(?i)(^|/)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|/|$)' -or $Relative -match '(?i)(^|/)presets\.json$|\.(pem|key|imageflowproject)$') { throw 'Unsafe application path.' }
    $basePath = [IO.Path]::GetFullPath($Base).TrimEnd('\')
    $path = [IO.Path]::GetFullPath((Join-Path $basePath $Relative))
    if (-not $path.StartsWith($basePath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes application folder.' }
    $check = $path
    while ($check) {
        $item = Get-Item -LiteralPath $check -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Reparse points are not allowed.' }
        $parent = Split-Path -Parent $check
        if ($parent -eq $check) { break }
        $check = $parent
    }
    return $path
}
function Digest([string]$Path) {
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($hash.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hash.Dispose() }
}
function Matches([string]$Path, $Entry) {
    return ((Test-Path -LiteralPath $Path -PathType Leaf) -and (Get-Item -LiteralPath $Path).Length -eq $Entry.size -and (Digest $Path) -eq $Entry.sha256)
}
function Backup-File([string]$Relative, [string]$Destination) {
    $backup = Join-Path $stage ('backup/' + $Relative)
    $exists = Test-Path -LiteralPath $Destination -PathType Leaf
    if ($exists) {
        [IO.Directory]::CreateDirectory((Split-Path -Parent $backup)) | Out-Null
        Copy-Item -LiteralPath $Destination -Destination $backup
    }
    $record = [pscustomobject]@{ destination=$Destination; backup=$backup; existed=$exists }
    $journal.Add($record)
    ConvertTo-Json -InputObject @($journal.ToArray()) -Depth 5 | Set-Content -LiteralPath "$stage\rollback.json" -Encoding UTF8
}
function Rollback {
    for ($i=$journal.Count-1; $i -ge 0; $i--) {
        $record = $journal[$i]
        try {
            if ($record.existed) {
                # A locked write can fail without altering the original file.
                if (-not (Test-Path -LiteralPath $record.destination -PathType Leaf) -or (Digest $record.destination) -ne (Digest $record.backup)) {
                    Copy-Item -LiteralPath $record.backup -Destination $record.destination -Force
                }
            }
            elseif (Test-Path -LiteralPath $record.destination -PathType Leaf) { Remove-Item -LiteralPath $record.destination -Force }
        } catch { $script:rollbackFailed = $true }
    }
    if ($rollbackFailed) { throw "Some files could not be restored. Recovery files: $stage" }
}
function Full-Install($Full, [string]$Version) {
    $expected = "https://github.com/remake1026/ImageFlow/releases/download/v$Version/ImageFlow-$Version-Windows-x86-x64-Setup.exe"
    if ($Full.url -cne $expected -or $Full.sha256 -notmatch '^[a-f0-9]{64}$' -or $Full.size -le 0 -or $Full.size -gt 1GB) { throw 'Invalid fallback installer metadata.' }
    $installer = Join-Path $stage 'full.exe'
    if (-not (Matches $installer $Full)) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Add-Type -AssemblyName System.Windows.Forms
        $form = New-Object Windows.Forms.Form
        $form.Text = 'ImageFlow 更新'
        $form.Width = 440; $form.Height = 130
        $label = New-Object Windows.Forms.Label
        $label.Dock = 'Fill'; $label.TextAlign = 'MiddleCenter'
        $label.Text = '增量安装未完成，正在下载完整安装包，请稍候……'
        $form.Controls.Add($label); $form.Show()
        $client = New-Object Net.WebClient
        $client.Headers['User-Agent'] = 'ImageFlow-Updater'
        try {
            $task = $client.DownloadFileTaskAsync([Uri]$Full.url, $installer)
            while (-not $task.IsCompleted) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 100 }
            $task.GetAwaiter().GetResult()
        } finally { $client.Dispose(); $form.Dispose() }
    }
    if (-not (Matches $installer $Full)) { throw 'Fallback installer checksum mismatch.' }
    $setup = Start-Process -FilePath $installer -ArgumentList "/S /D=$root" -WindowStyle Hidden -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "Fallback installer returned $($setup.ExitCode)." }
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
}

try {
    $planData = Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($planData.schema -ne 1 -or $planData.version -notmatch '^\d+\.\d+\.\d+$' -or [IO.Path]::GetFullPath($planData.install_dir) -ne $root -or (Split-Path -Leaf $AppPath) -ne 'ImageFlow.exe') { throw 'Invalid update plan.' }
    Safe-Path $root 'ImageFlow.exe' | Out-Null
    if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) { throw 'Installed application is missing.' }
    $process = Get-Process -Id $AppPid -ErrorAction SilentlyContinue
    if ($process -and -not $process.WaitForExit(60000)) { throw 'Application is still running.' }
    try {
        $manifestPath = Join-Path $stage 'update-manifest.json'
        if ((Digest $manifestPath) -ne $planData.manifest_sha256) { throw 'Manifest changed after download.' }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.schema -ne 1 -or $manifest.version -ne $planData.version -or $manifest.files.Count -gt 5000) { throw 'Invalid target manifest.' }
        $entries = @{}
        foreach ($entry in $manifest.files) {
            Safe-Path $root $entry.path | Out-Null
            if ($entries.ContainsKey($entry.path) -or $entry.sha256 -notmatch '^[a-f0-9]{64}$' -or $entry.size -lt 0 -or $entry.size -gt 1GB) { throw 'Invalid manifest file.' }
            $entries[$entry.path] = $entry
        }
        if (-not $entries.ContainsKey('ImageFlow.exe')) { throw 'Missing main executable.' }
        $changed = @{}
        foreach ($entry in $planData.changed) {
            if ($changed.ContainsKey($entry.path) -or -not $entries.ContainsKey($entry.path)) { throw 'Invalid changed file.' }
            $changed[$entry.path] = $true
        }
        # Recheck every file after the application has exited, before any mutation.
        foreach ($entry in $manifest.files) {
            $base = if ($changed.ContainsKey($entry.path)) { Join-Path $stage 'files' } else { $root }
            if (-not (Matches (Safe-Path $base $entry.path) $entry)) { throw 'Staged or unchanged file checksum mismatch.' }
        }
        foreach ($entry in $planData.removed) {
            if ($entries.ContainsKey($entry.path)) { throw 'Removed file is still required.' }
            $destination = Safe-Path $root $entry.path
            if (Test-Path -LiteralPath $destination) {
                if (-not (Matches $destination $entry)) { throw 'Obsolete file changed after staging.' }
            }
        }
        foreach ($entry in $planData.changed) {
            $destination = Safe-Path $root $entry.path
            Backup-File $entry.path $destination
            [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
            Copy-Item -LiteralPath (Safe-Path "$stage\files" $entry.path) -Destination $destination -Force
        }
        foreach ($entry in $planData.removed) {
            $destination = Safe-Path $root $entry.path
            if (Test-Path -LiteralPath $destination) { Backup-File $entry.path $destination; Remove-Item -LiteralPath $destination -Force }
        }
        foreach ($entry in $manifest.files) {
            if (-not (Matches (Safe-Path $root $entry.path) $entry)) { throw 'Installed file checksum mismatch.' }
        }
        # Commit ownership metadata last; keep a backup for any failure in this step.
        $installedManifest = Join-Path $root 'update-manifest.json'
        if ((Test-Path -LiteralPath $installedManifest) -and ((Get-Item -LiteralPath $installedManifest -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Manifest is a reparse point.' }
        Backup-File 'update-manifest.json' $installedManifest
        Copy-Item -LiteralPath $manifestPath -Destination $installedManifest -Force
    } catch {
        $_ | Out-String | Set-Content -LiteralPath "$stage\incremental-error.log" -Encoding UTF8
        Rollback
        Full-Install $planData.full $planData.version
        'full' | Set-Content -LiteralPath "$stage\result.txt"
    }
    # Change only a registration belonging to this exact installation.
    foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
        $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, $view)
        $key = $baseKey.OpenSubKey('Software\Microsoft\Windows\CurrentVersion\Uninstall\ImageFlow', $true)
        try { if ($key -and $key.GetValue('InstallLocation') -eq $root) { $key.SetValue('DisplayVersion', $planData.version) } }
        finally { if ($key) { $key.Dispose() }; $baseKey.Dispose() }
    }
    if (-not (Test-Path -LiteralPath "$stage\result.txt")) { 'delta' | Set-Content -LiteralPath "$stage\result.txt" }
    if (-not $NoRestart) { Start-Process -FilePath $AppPath }
    exit 0
} catch {
    $_ | Out-String | Set-Content -LiteralPath "$stage\error.log" -Encoding UTF8
    if (-not $QuietFailure) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show("更新未完成：$($_.Exception.Message)`n恢复文件和日志：$stage", 'ImageFlow 更新') | Out-Null
    }
    exit 1
}
