# -*- coding: utf-8 -*-
# XPBD DLL ビルドスクリプト (PowerShell版)

$ErrorActionPreference = "Stop"

$vsPaths = @(
    "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
)

$vcvars = $null
foreach ($p in $vsPaths) {
    if (Test-Path $p) {
        $vcvars = $p
        break
    }
}

if (-not $vcvars) {
    Write-Error "[エラー] vcvars64.bat が見つかりませんでした。"
    exit 1
}

Write-Host "[情報] VC環境変数を取得中: $vcvars"

# vcvars64.bat を実行して環境変数をインポート
cmd /c "`"$vcvars`" > nul && set" | Foreach-Object {
    if ($_ -match "^(.*?)=(.*)$") {
        Set-Item -Path "env:\$($matches[1])" -Value $matches[2]
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$binDir = Join-Path $scriptDir "bin"
if (-not (Test-Path $binDir)) {
    New-Item -ItemType Directory -Path $binDir | Out-Null
}

$includeDir = Join-Path $scriptDir "include"
$src1 = Join-Path $scriptDir "src\xpbd_engine.cpp"
$src2 = Join-Path $scriptDir "src\xpbd_c_api.cpp"
$outDll = Join-Path $binDir "mmd_xpbd.dll"

Write-Host "[情報] コンパイルおよびリンクを実行中..."
$clArgs = @(
    "/O2",
    "/LD",
    "/std:c++17",
    "/EHsc",
    "/W3",
    "/I", $includeDir,
    $src1,
    $src2,
    "/Fe:$outDll"
)

$proc = Start-Process -FilePath "cl.exe" -ArgumentList $clArgs -Wait -NoNewWindow -PassThru

if ($proc.ExitCode -eq 0) {
    Write-Host "===================================================" -ForegroundColor Green
    Write-Host "[成功] $outDll のビルドに成功しました！" -ForegroundColor Green
    Write-Host "===================================================" -ForegroundColor Green
    # 中間ファイルの整理
    Get-ChildItem -Path $scriptDir -Filter "*.obj" | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $binDir -Filter "*.exp" | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $binDir -Filter "*.lib" | Remove-Item -Force -ErrorAction SilentlyContinue
    exit 0
} else {
    Write-Error "[失敗] ビルドが終了コード $($proc.ExitCode) で失敗しました。"
    exit $proc.ExitCode
}
