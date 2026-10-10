# MMD Material Plugin (.mll) PowerShell Build Script
param(
    [string]$DevkitLocation = if ($env:USERPROFILE) { "$env:USERPROFILE\devkitBase" } else { "C:\Users\<ユーザー名>\devkitBase" },
    [string]$Config = "Release"
)

$ErrorActionPreference = "Stop"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " MMD Material Plugin (.mll) Build Script (PowerShell)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# 環境変数設定
$env:DEVKIT_LOCATION = $DevkitLocation

# CMakeの検索
$cmakeExe = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
if (-not (Test-Path -Path $cmakeExe)) {
    $found = Get-Command cmake -ErrorAction SilentlyContinue
    if ($found) {
        $cmakeExe = $found.Source
    } else {
        $foundInVs = Get-ChildItem -Path "C:\Program Files\Microsoft Visual Studio" -Filter "cmake.exe" -Recurse -Depth 8 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($foundInVs) {
            $cmakeExe = $foundInVs.FullName
        } else {
            Write-Error "cmake.exe could not be found."
            exit 1
        }
    }
}

Write-Host "[INFO] DEVKIT_LOCATION: $env:DEVKIT_LOCATION" -ForegroundColor Green
Write-Host "[INFO] CMake: $cmakeExe" -ForegroundColor Green

# ディレクトリ作成
if (-not (Test-Path "build")) { New-Item -ItemType Directory -Path "build" | Out-Null }
if (-not (Test-Path "bin")) { New-Item -ItemType Directory -Path "bin" | Out-Null }

Set-Location "build"

# CMake実行
Write-Host "[INFO] Running CMake configure..." -ForegroundColor Yellow
& "$cmakeExe" -G "Visual Studio 17 2022" -A x64 ..
if ($LASTEXITCODE -ne 0) {
    Write-Error "CMake configure failed."
    exit 1
}

Write-Host "[INFO] Building $Config configuration..." -ForegroundColor Yellow
& "$cmakeExe" --build . --config $Config
if ($LASTEXITCODE -ne 0) {
    Write-Error "CMake build failed."
    exit 1
}

# 成果物コピー
$builtMll = "Release\mmd_material.mll"
if (Test-Path $builtMll) {
    try {
        Copy-Item $builtMll -Destination "..\bin\mmd_material.mll" -Force
        Write-Host "[SUCCESS] mmd_material.mll built successfully -> bin\mmd_material.mll" -ForegroundColor Green
    } catch {
        Write-Warning "Mayaが起動中で mmd_material.mll をロックしています。"
        Write-Warning "Mayaを再起動するか、Maya内で cmds.unloadPlugin('mmd_material.mll') を実行してください。"
    }
} else {
    Write-Warning "mmd_material.mll not found in expected path: $builtMll"
}

Set-Location $scriptDir
