@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo  MMD Material Plugin (.mll) Build Script
echo ===================================================

:: Devkit path
if "%DEVKIT_LOCATION%"=="" (
    set "DEVKIT_LOCATION=%USERPROFILE%\devkitBase"
)
echo [INFO] DEVKIT_LOCATION: %DEVKIT_LOCATION%

:: Visual Studio 2022 setup
set "VS_VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
if not exist "%VS_VCVARS%" (
    set "VS_VCVARS=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat"
)

if not exist "%VS_VCVARS%" (
    echo [ERROR] Visual Studio vcvarsall.bat not found.
    exit /b 1
)

echo [INFO] Loading MSVC environment: %VS_VCVARS%
call "%VS_VCVARS%" x64 >nul

:: Navigate to script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist "build" mkdir build
if not exist "bin" mkdir bin

cd build

:: Run CMake configure
echo [INFO] Running CMake configure...
cmake -G "Visual Studio 17 2022" -A x64 -DDEVKIT_LOCATION="%DEVKIT_LOCATION%" ..
if errorlevel 1 (
    echo [ERROR] CMake configure failed.
    exit /b 1
)

:: Run CMake build
echo [INFO] Building Release configuration...
cmake --build . --config Release
if errorlevel 1 (
    echo [ERROR] Build failed.
    exit /b 1
)

:: Copy artifact
if exist "Release\mmd_material.mll" (
    copy /Y "Release\mmd_material.mll" "..\bin\mmd_material.mll" >nul
    echo [SUCCESS] mmd_material.mll built successfully: bin\mmd_material.mll
) else if exist "mmd_material.mll" (
    copy /Y "mmd_material.mll" "..\bin\mmd_material.mll" >nul
    echo [SUCCESS] mmd_material.mll built successfully: bin\mmd_material.mll
) else (
    echo [WARNING] mmd_material.mll not found in expected output directories.
)

cd /d "%SCRIPT_DIR%"
exit /b 0
