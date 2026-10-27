@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo  MMD Toon Shader Plugin (.mll) Build Script
echo ===================================================

:: Devkit search paths
set "DEVKIT_2025="
if exist "C:\Autodesk_devkit\devkitBase_2025" set "DEVKIT_2025=C:\Autodesk_devkit\devkitBase_2025"
if "%DEVKIT_2025%"=="" if exist "%USERPROFILE%\devkitBase" set "DEVKIT_2025=%USERPROFILE%\devkitBase"

if "%DEVKIT_2025%"=="" (
    echo [ERROR] Maya 2025 Devkit not found.
    exit /b 1
)

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

:: CMake path setup
set "CMAKE_EXE=cmake"
where cmake >nul 2>nul
if errorlevel 1 (
    set "CMAKE_EXE=C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
)

:: Navigate to script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist "bin" mkdir bin
if not exist "bin\2025" mkdir bin\2025

echo.
echo [INFO] Building for Maya 2025 (DEVKIT: %DEVKIT_2025%)...
if not exist "build_2025" mkdir build_2025
"%CMAKE_EXE%" -G "Visual Studio 17 2022" -A x64 -DDEVKIT_LOCATION="%DEVKIT_2025%" -B build_2025 -S .
if not errorlevel 1 (
    "%CMAKE_EXE%" --build build_2025 --config Release
    if exist "build_2025\Release\mmd_toon_shader.mll" (
        copy /Y "build_2025\Release\mmd_toon_shader.mll" "bin\2025\mmd_toon_shader.mll" >nul
        copy /Y "build_2025\Release\mmd_toon_shader.mll" "bin\mmd_toon_shader.mll" >nul
        echo [SUCCESS] Maya 2025: bin\2025\mmd_toon_shader.mll generated.
    ) else (
        echo [ERROR] Build output mmd_toon_shader.mll not found.
        exit /b 1
    )
) else (
    echo [ERROR] CMake configuration failed.
    exit /b 1
)

echo ===================================================
echo  Build process finished successfully.
echo ===================================================
