@echo off
REM =============================================================================
REM HYDRA-UMC-OS - Run the read-only node diagnostics agent
REM Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
REM GPL-3.0-or-later - see LICENSE
REM =============================================================================
setlocal
echo ===============================================================
echo  HYDRA-UMC-OS - run.bat
echo  Runs the read-only node diagnostics agent.
echo  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)
echo  ^<electrohobby3d@gmail.com^> ^| GPL-3.0-or-later - see LICENSE
echo ===============================================================
cd /d "%~dp0"
set "PYTHONPATH=%CD%\agent\src"
python -m hydra_umc_os.agent --config config\hydra-umc-os.example.json health %*
pause
