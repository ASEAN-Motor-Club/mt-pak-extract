@echo off
REM Launcher for python scripts inside D:\C1Mirror (the project that owns MotorTown classes).
REM Plugin folders are renamed *_off, so their DLLs are never on the DLL search path and the
REM editor dies with GetLastError=126. Putting every plugin Binaries\Win64 on PATH fixes it.
REM Never copy those DLLs into Binaries\Win64 - two copies means duplicate UClass registration.
setlocal
set "PLUGINS=D:\C1Mirror\Plugins"
set "PATH=%PATH%;%PLUGINS%\AsyncLoadingScreen_off\Binaries\Win64"
set "PATH=%PATH%;%PLUGINS%\ColorWheelPlugin_off\Binaries\Win64"
set "PATH=%PATH%;%PLUGINS%\JSONQuery_off\Binaries\Win64"
set "PATH=%PATH%;%PLUGINS%\KantanCharts_off\Binaries\Win64"
set "PATH=%PATH%;%PLUGINS%\Prefabricator_off\Binaries\Win64"
set "PATH=%PATH%;%PLUGINS%\SimpleController_off\Binaries\Win64"
set "PATH=%PATH%;%PLUGINS%\SimpleUPNP_off\Binaries\Win64"
set "PATH=%PATH%;%PLUGINS%\TrackIR_off\Binaries\Win64"
set "PATH=%PATH%;D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Binaries\Win64"
set "LOG=%~2"
if "%LOG%"=="" set "LOG=D:\C1Mirror\Saved\Logs\run_py.log"
"D:\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "D:\C1Mirror\MotorTown.uproject" ^
  -run=pythonscript -script="%~1" -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput > "%LOG%" 2>&1
echo RC=%ERRORLEVEL%
