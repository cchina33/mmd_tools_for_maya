@echo off
chcp 65001 > nul
pushd "%~dp0"

echo ====================================================================
echo  MMD Tools for Maya - Release Package Builder
echo ====================================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH.
    echo Please ensure Python is installed and added to your PATH environment variable.
    echo.
    pause
    popd
    exit /b 1
)

python package_release.py
set BUILD_STATUS=%errorlevel%

echo.
if %BUILD_STATUS% equ 0 (
    echo [SUCCESS] Release package created successfully.
) else (
    echo [ERROR] Build failed with exit code: %BUILD_STATUS%
)

echo.
pause
popd
exit /b %BUILD_STATUS%
