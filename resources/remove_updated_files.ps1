param([string]$InstallDir)
# The uninstaller also removes files introduced by later incremental updates.
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$manifest = Join-Path $root 'update-manifest.json'
if (-not (Test-Path -LiteralPath $manifest)) { exit 0 }
$data = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
if ($data.schema -ne 1 -or $data.files.Count -gt 5000) { exit 1 }
$paths = @()
foreach ($entry in $data.files) {
    $name = [string]$entry.path
    if ($name -ne 'ImageFlow.exe' -and -not $name.StartsWith('_internal/')) { exit 1 }
    if ($name -match '[\\:<>"|?*\x00-\x1f]' -or $name -match '(^|/)(\.|\.\.|)(/|$)' -or $name -match '[. ](/|$)' -or $name -match '(?i)(^|/)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|/|$)' -or $name -match '(?i)(^|/)presets\.json$|\.(pem|key|imageflowproject)$') { exit 1 }
    $path = [IO.Path]::GetFullPath((Join-Path $root $name))
    if (-not $path.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { exit 1 }
    $check = $path
    while ($check) {
        $item = Get-Item -LiteralPath $check -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { exit 1 }
        $parent = Split-Path -Parent $check
        if ($parent -eq $check) { break }
        $check = $parent
    }
    $paths += $path
}
foreach ($path in $paths) { if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path -Force } }
