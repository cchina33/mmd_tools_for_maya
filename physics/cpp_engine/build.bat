@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo MMD XPBD Physics Engine - DLL Build Script (64-bit)
echo ===================================================

cd /d "%~dp0"

if not exist bin mkdir bin

:: Visual Studio 64bit 環境変数の検出
set VCVARS=
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
) else if exist "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" (
    set "VCVARS=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
) else if exist "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat" (
    set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"
) else if exist "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat" (
    set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
)

if "%VCVARS%"=="" (
    echo [エラー] vcvars64.bat が見つかりませんでした。
    exit /b 1
)

echo [情報] VC環境変数を読み込み中: %VCVARS%
call "%VCVARS%" >nul 2>&1

echo [情報] コンパイルおよびDLLリンクを開始します...
cl.exe /O2 /LD /std:c++17 /EHsc /W3 /I include src\xpbd_engine.cpp src\xpbd_c_api.cpp /Fe:bin\mmd_xpbd.dll

if %ERRORLEVEL% equ 0 (
    echo ===================================================
    echo [成功] bin\mmd_xpbd.dll のビルドに成功しました！
    echo ===================================================
    del *.obj >nul 2>&1
    del bin\*.exp >nul 2>&1
    del bin\*.lib >nul 2>&1
    exit /b 0
) else (
    echo ===================================================
    echo [失敗] ビルド中にエラーが発生しました。
    echo ===================================================
    exit /b %ERRORLEVEL%
)
