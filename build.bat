@echo off
REM =============================================================================
REM HYDRA-UMC-OS - Validate and test the read-only platform agent
REM Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
REM GPL-3.0-or-later - see LICENSE
REM =============================================================================
setlocal
echo ===============================================================
echo  HYDRA-UMC-OS - build.bat
echo  Validates and tests the read-only platform agent.
echo  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)
echo  ^<electrohobby3d@gmail.com^> ^| GPL-3.0-or-later - see LICENSE
echo ===============================================================
cd /d "%~dp0"
set "PYTHONPATH=%CD%\agent\src"
echo === HYDRA-UMC-OS build / test ===
python bump_version.py
if errorlevel 1 ( echo NATIVE VERSION BUMP FAILED. & pause & exit /b 1 )
python "%~dp0bump_manifest_version.py" --sync
if errorlevel 1 ( echo VERSION SYNCHRONIZATION FAILED. & pause & exit /b 1 )
if errorlevel 1 ( echo VERSION BUMP FAILED. & pause & exit /b 1 )
python -m unittest discover -s agent\tests -v
if errorlevel 1 ( echo BUILD FAILED. & pause & exit /b 1 )
echo Build OK: agent tests passed.
pause
