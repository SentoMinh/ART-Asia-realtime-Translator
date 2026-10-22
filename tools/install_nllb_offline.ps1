param([string]$PackageRoot = $PSScriptRoot, [string]$CacheRoot = '')

$ErrorActionPreference = 'Stop'
if (-not $CacheRoot) {
    if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is unavailable. Specify -CacheRoot.' }
    $CacheRoot = Join-Path $env:LOCALAPPDATA 'VRChat-Translator\local-model'
}
$CacheRoot = [IO.Path]::GetFullPath($CacheRoot)
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$expectedNames = @('config.json', 'shared_vocabulary.json', 'tokenizer.json', 'model.bin')
$manifest = Get-Content -LiteralPath (Join-Path $PackageRoot 'model-files.json') -Raw | ConvertFrom-Json
if ($manifest.Count -ne $expectedNames.Count) { throw 'Invalid model file list.' }
$names = @($manifest | ForEach-Object { $_.name })
if (Compare-Object ($names | Sort-Object) ($expectedNames | Sort-Object)) { throw 'Invalid model filenames.' }

function Test-ModelFile($Path, $Part) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ((Get-Item -LiteralPath $Path).Length -ne $Part.size) { return $false }
    $hasher = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {
        $digest = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '')
        return $digest -eq $Part.sha256
    } finally {
        $stream.Dispose()
        $hasher.Dispose()
    }
}

# Check the entire package before touching an existing installation.
foreach ($part in $manifest) {
    if ($part.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or $part.size -le 0) { throw 'Invalid model checksum or size.' }
    if (-not (Test-ModelFile (Join-Path $PackageRoot ('nllb\' + $part.name)) $part)) {
        throw "Damaged or missing file: $($part.name). Extract the complete ZIP again."
    }
}
$target = Join-Path $CacheRoot 'nllb'
$installed = $true
foreach ($part in $manifest) {
    if (-not (Test-ModelFile (Join-Path $target $part.name) $part)) { $installed = $false }
}
if ($installed) {
    Write-Output 'NLLB is already installed and verified. Open ART and select Local Model for Translating.'
    return
}

$suffix = [Guid]::NewGuid().ToString('N')
$staging = Join-Path $CacheRoot ('nllb-install-' + $suffix)
$backup = Join-Path $CacheRoot ('nllb-backup-' + $suffix)
$prefix = $CacheRoot.TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
foreach ($path in @($target, $staging, $backup)) {
    if (-not [IO.Path]::GetFullPath($path).StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Installation path is outside the model cache.'
    }
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Expected an ordinary model folder: $path"
        }
    }
}
New-Item -ItemType Directory -Path $staging -Force | Out-Null
foreach ($part in $manifest) {
    $destination = Join-Path $staging $part.name
    Copy-Item -LiteralPath (Join-Path $PackageRoot ('nllb\' + $part.name)) -Destination $destination
    if (-not (Test-ModelFile $destination $part)) { throw "Copy verification failed: $($part.name)" }
}

# Folder renames keep the old model intact if installation cannot finish.
$movedOld = $false
if (Test-Path -LiteralPath $target) {
    Move-Item -LiteralPath $target -Destination $backup
    $movedOld = $true
}
try {
    Move-Item -LiteralPath $staging -Destination $target
} catch {
    if ($movedOld -and -not (Test-Path -LiteralPath $target)) {
        Move-Item -LiteralPath $backup -Destination $target
    }
    throw
}
Write-Output "NLLB installed and verified: $target"
Write-Output 'Open ART > Settings > Models. Select Local Model for Translating, then Use model for NLLB.'
if ($movedOld) { Write-Output "Previous files were preserved in: $backup" }
