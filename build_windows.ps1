$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildRoot = Join-Path $projectRoot ".build"
$pythonRoot = Join-Path $buildRoot "python-3.13"
$pythonArchive = Join-Path $buildRoot "python-3.13.17-embed-amd64.zip"
$pipWheel = Join-Path $buildRoot "pip-wheel.whl"
$pipArchive = Join-Path $buildRoot "pip-wheel.zip"
$pythonExe = Join-Path $pythonRoot "python.exe"
$pythonUrl = "https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip"

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $pythonExe)) {
    if (-not (Test-Path -LiteralPath $pythonArchive)) {
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonArchive
    }
    New-Item -ItemType Directory -Path $pythonRoot -Force | Out-Null
    Expand-Archive -LiteralPath $pythonArchive -DestinationPath $pythonRoot -Force
    @("python313.zip", ".", "Lib\site-packages", "import site") |
        Set-Content -LiteralPath (Join-Path $pythonRoot "python313._pth") -Encoding Ascii
    New-Item -ItemType Directory -Path (Join-Path $pythonRoot "Lib\site-packages") -Force | Out-Null
    $pipMetadata = Invoke-RestMethod -Uri "https://pypi.org/pypi/pip/json"
    $pipPackage = $pipMetadata.urls | Where-Object { $_.filename -match '^pip-.*-py3-none-any\.whl$' } | Select-Object -First 1
    if (-not $pipPackage) { throw "Could not find the pip wheel for bootstrapping." }
    Invoke-WebRequest -Uri $pipPackage.url -OutFile $pipWheel
    Copy-Item -LiteralPath $pipWheel -Destination $pipArchive -Force
    Expand-Archive -LiteralPath $pipArchive -DestinationPath (Join-Path $pythonRoot "Lib\site-packages") -Force
}

& $pythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $pythonExe -m pip install setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Build tooling installation failed." }
& $pythonExe -m pip install --no-build-isolation --cache-dir (Join-Path $buildRoot "pip-cache") `
    -r (Join-Path $projectRoot "requirements-desktop.txt") -r (Join-Path $projectRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& $pythonExe (Join-Path $projectRoot "assets\render_icon.py")
if ($LASTEXITCODE -ne 0) { throw "Application icon generation failed." }

$distRoot = Join-Path $projectRoot "dist"
$workRoot = Join-Path $buildRoot "pyinstaller"
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
foreach ($old in @("Chaoxing", "Chaoxing-Windows", "学习通PLUS", "chaoxing-worker.exe", "Chaoxing-Windows.zip", "学习通PLUS-Windows.zip", "学习通PLUS-Setup-*.exe", "XueXiTong-Plus-*")) {
    Remove-Item -Path (Join-Path $distRoot $old) -Recurse -Force -ErrorAction SilentlyContinue  # -Path: entries may be wildcards
}
Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue

# GUI and worker are built together (packaging\app.spec) into one folder that shares a
# single _internal directory; packaging\prune.py drops Qt modules, models and DLLs we never load.
& $pythonExe -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath $workRoot `
    (Join-Path $projectRoot "packaging\app.spec")
if ($LASTEXITCODE -ne 0) { throw "Application build failed." }

$releaseDir = Join-Path $distRoot "学习通PLUS"
Copy-Item -LiteralPath (Join-Path $projectRoot "README_DESKTOP.md") -Destination (Join-Path $releaseDir "README.txt") -Force
$releaseAssets = Join-Path $releaseDir "assets"
New-Item -ItemType Directory -Path $releaseAssets -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "assets\learning_plus.ico") -Destination $releaseAssets -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "assets\learning_plus.png") -Destination $releaseAssets -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "assets\chaoxing_official.jpg") -Destination $releaseAssets -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination (Join-Path $releaseDir "LICENSE.txt") -Force
# The uninstaller in the install folder: a copy of the launcher (same _internal) that starts in
# uninstall mode because of its name (ui\winsetup.UNINSTALL_EXE).
Copy-Item -LiteralPath (Join-Path $releaseDir "学习通PLUS.exe") -Destination (Join-Path $releaseDir "卸载学习通PLUS.exe") -Force
# Qt ships build leftovers (objects-*\*.obj) inside its qml folder. They are never loaded and
# their deep paths can exceed MAX_PATH when installed, so drop them from the release.
Get-ChildItem -LiteralPath (Join-Path $releaseDir "_internal") -Directory -Recurse -Filter "objects-*" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
# Release file names are ASCII: GitHub strips non-ASCII characters from release asset names.
$versionMatch = Select-String -LiteralPath (Join-Path $projectRoot "ui\controller.py") -Pattern '^APP_VERSION = "([^"]+)"' | Select-Object -First 1
$appVersion = if ($versionMatch) { $versionMatch.Matches[0].Groups[1].Value } else { "0.0.0" }
$releaseZip = Join-Path $distRoot "XueXiTong-Plus-Windows-$appVersion.zip"
Compress-Archive -LiteralPath $releaseDir -DestinationPath $releaseZip -CompressionLevel Optimal -Force
# The installer carries the same files as an LZMA zip: about a quarter smaller than Deflate.
# (The no-install zip above stays Deflate so Windows Explorer can open it.)
$payloadZip = Join-Path $buildRoot "setup-payload.zip"
& $pythonExe (Join-Path $projectRoot "packaging\make_payload.py") $releaseDir $payloadZip
if ($LASTEXITCODE -ne 0) { throw "Installer payload build failed." }

# Installer: our own Qt Quick setup program (installer\setup.py) with the release zip
# appended to the end of the exe. zipfile finds the archive from the file's end.
$setupWork = Join-Path $buildRoot "pyinstaller-setup"
$setupDist = Join-Path $buildRoot "setup-dist"
Remove-Item -LiteralPath $setupWork, $setupDist -Recurse -Force -ErrorAction SilentlyContinue
& $pythonExe -m PyInstaller --noconfirm --clean --distpath $setupDist --workpath $setupWork `
    (Join-Path $projectRoot "packaging\setup.spec")
if ($LASTEXITCODE -ne 0) { throw "Setup program build failed." }
Get-ChildItem -LiteralPath $distRoot -Filter "XueXiTong-Plus-Setup-*.exe" -ErrorAction SilentlyContinue | Remove-Item -Force
$installer = Join-Path $distRoot "XueXiTong-Plus-Setup-$appVersion.exe"
$out = [IO.File]::Open($installer, [IO.FileMode]::Create)
try {
    foreach ($part in @((Join-Path $setupDist "setup-stub.exe"), $payloadZip)) {
        $in = [IO.File]::OpenRead($part)
        try { $in.CopyTo($out) } finally { $in.Dispose() }
    }
} finally { $out.Dispose() }

Write-Host "Build complete: $(Join-Path $releaseDir '学习通PLUS.exe')"
Write-Host "Worker component: $(Join-Path $releaseDir 'chaoxing-worker.exe')"
Write-Host "Release archive: $releaseZip"
Write-Host "Installer: $installer"
