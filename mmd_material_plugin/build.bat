@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo  MMD Material Plugin (.mll) Build Script
echo ===================================================

:: Devkit search paths
set "DEVKIT_2025="
set "DEVKIT_2026="

if exist "C:\Autodesk_devkit\devkitBase_2025" set "DEVKIT_2025=C:\Autodesk_devkit\devkitBase_2025"
if exist "C:\Autodesk_devkit\devkitBase_2026" set "DEVKIT_2026=C:\Autodesk_devkit\devkitBase_2026"
if exist "%USERPROFILE%\devkitBase" set "DEVKIT_2025=%USERPROFILE%\devkitBase"

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
if not exist "bin\2026" mkdir bin\2026

:: Build Maya 2026 if available
if not "%DEVKIT_2026%"=="" (
    echo.
    echo [INFO] Building for Maya 2026 (DEVKIT: %DEVKIT_2026%)...
    if not exist "build_2026" mkdir build_2026
    "%CMAKE_EXE%" -G "Visual Studio 17 2022" -A x64 -DDEVKIT_LOCATION="%DEVKIT_2026%" -B build_2026 -S .
    if not errorlevel 1 (
        "%CMAKE_EXE%" --build build_2026 --config Release
        if exist "build_2026\Release\mmd_material.mll" (
            copy /Y "build_2026\Release\mmd_material.mll" "bin\2026\mmd_material.mll" >nul
            copy /Y "build_2026\Release\mmd_material.mll" "bin\mmd_material.mll" >nul
            echo [SUCCESS] Maya 2026: bin\2026\mmd_material.mll
        )
    )
)

:: Build Maya 2025 if available
if not "%DEVKIT_2025%"=="" (
    echo.
    echo [INFO] Building for Maya 2025 (DEVKIT: %DEVKIT_2025%)...
    if not exist "build_2025" mkdir build_2025
    "%CMAKE_EXE%" -G "Visual Studio 17 2022" -A x64 -DDEVKIT_LOCATION="%DEVKIT_2025%" -B build_2025 -S .
    if not errorlevel 1 (
        "%CMAKE_EXE%" --build build_2025 --config Release
        if exist "build_2025\Release\mmd_material.mll" (
            copy /Y "build_2025\Release\mmd_material.mll" "bin\2025\mmd_material.mll" >nul
            echo [SUCCESS] Maya 2025: bin\2025\mmd_material.mll
        )
    )
)

echo.
echo ===================================================
echo  Build process finished.
echo ===================================================
cd /d "%SCRIPT_DIR%"
exit /b 0
