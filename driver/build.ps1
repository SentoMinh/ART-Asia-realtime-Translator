param(
    [Parameter(Mandatory=$true)][string]$PreparedSource,
    [ValidateSet('Debug','Release')][string]$Configuration = 'Debug',
    [ValidatePattern('^10\.0\.\d+\.0$')][string]$WdkVersion = '10.0.26100.0'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PreparedSource).Path
$driverRoot = Join-Path $root 'audio\sysvad'
if (!(Test-Path -LiteralPath (Join-Path $root 'vrct-prepared.json'))) {
    throw 'Run driver/prepare.py first; this is not a prepared driver tree.'
}
$kit = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
$infverif = Join-Path $kit "Tools\$WdkVersion\x64\InfVerif.exe"
$inf2cat = Join-Path $kit "bin\$WdkVersion\x86\Inf2Cat.exe"
foreach ($tool in @($infverif, $inf2cat)) {
    if (!(Test-Path -LiteralPath $tool)) { throw "Missing WDK tool: $tool" }
}
$msbuild = $null
if (!$msbuild) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $found = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'MSBuild\**\Bin\amd64\MSBuild.exe'
        if ($found) { $msbuild = Get-Command ($found | Select-Object -First 1) }
    }
}
if (!$msbuild) {
    throw 'Windows driver build tools are missing. Open a Visual Studio Developer PowerShell with C++ tools, matching Windows SDK and WDK installed.'
}
foreach ($project in @('EndpointsCommon\EndpointsCommon.vcxproj', 'TabletAudioSample\TabletAudioSample.vcxproj')) {
    $extra = @()
    if ($project -like 'TabletAudioSample*') { $extra += '/p:TargetName=VrctAudio' }
    & $msbuild.Source (Join-Path $driverRoot $project) /m /t:Build "/p:Configuration=$Configuration" "/p:WindowsTargetPlatformVersion=$WdkVersion" /p:Platform=x64 /p:SignMode=Off /p:KMDF_VERSION_MAJOR=1 /p:KMDF_VERSION_MINOR=15 /p:TargetVersion=Windows10 /p:_NT_TARGET_VERSION=0xA000008 @extra
    if ($LASTEXITCODE -ne 0) { throw "Driver compilation failed: $project" }
}
$output = Join-Path $driverRoot "TabletAudioSample\x64\$Configuration"
# Fresh package directory prevents a failed rebuild leaving an old catalog in place.
$package = Join-Path $root ("package-" + $Configuration + "-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $package | Out-Null
foreach ($file in @('VrctAudio.sys', 'VrctAudio.inf')) {
    Copy-Item -LiteralPath (Join-Path $output $file) -Destination $package
}
Copy-Item -LiteralPath (Join-Path $root 'MICROSOFT-LICENSE') -Destination $package
& $infverif /u (Join-Path $package 'VrctAudio.inf')
if ($LASTEXITCODE -ne 0) { throw 'INF verification failed.' }
& $inf2cat "/driver:$package" /os:10_VB_X64,10_CO_X64,10_NI_X64,10_GE_X64
if ($LASTEXITCODE -ne 0) { throw 'Catalog creation failed.' }
if (!(Test-Path -LiteralPath (Join-Path $package 'VrctAudio.cat'))) { throw 'Catalog was not generated.' }
Write-Host "Unsigned development package: $package"
Write-Host 'Compilation and INF/catalog checks passed. This is NOT signed or runtime-tested.'
Write-Host 'Complete audio/Driver Verifier tests and Microsoft driver signing before distribution.'
