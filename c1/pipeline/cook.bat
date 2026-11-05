@echo off
REM Cook one map in the project that can see the game content.
REM Cooking in D:\C1Mirror strips every game-class reference.
set PROJ=D:\UEProjects\C1\C1.uproject
set MAP=/Game/Mods/C1/Maps/C1
set OUT=D:\UEProjects\C1\Saved\Cooked\Windows\C1\Content\Mods\C1\Maps

"D:\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "%PROJ%" -run=cook ^
  -TargetPlatform=Windows -map=%MAP% -unattended -nop4 -nosplash -stdout -log ^
  > D:\UEProjects\C1\cook.log 2>&1

echo COOK_RC=%ERRORLEVEL%
copy /Y "%OUT%\C1.umap" D:\C1Mirror\cook_out.umap >nul
copy /Y "%OUT%\C1.uexp" D:\C1Mirror\cook_out.uexp >nul
echo COOK_DONE
