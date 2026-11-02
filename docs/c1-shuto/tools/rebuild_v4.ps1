$ErrorActionPreference = 'Continue'
$ue    = 'D:\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$proj  = 'D:\UEProjects\C1\C1.uproject'
$mesh  = 'D:\UEProjects\C1\meshes'
$sdir  = 'D:\UEProjects\C1\Scripts'

Write-Output '=== stage 1: extract translated cells (offset baked into vertices) ==='
if (Test-Path D:\cells_v3.tgz) {
    tar -xzf D:\cells_v3.tgz -C $mesh
    Write-Output ('extract_ok rc=' + $LASTEXITCODE)
} else {
    Write-Output 'ABORT no tarball'
    exit 1
}
Write-Output ('obj_count=' + (Get-ChildItem "$mesh\*.obj").Count)

function Run-Ue($script, $log, $marker) {
    & $ue $proj -run=pythonscript -script="$script" -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput *> $log
    Write-Output ("$marker rc=" + $LASTEXITCODE)
    Get-Content $log -ErrorAction SilentlyContinue |
        Select-String -Pattern 'C1_IMPORT_DONE|C1_IMPORT_FAIL|C1MAT|C1COL|Error:' |
        Select-Object -Last 8 | ForEach-Object { Write-Output ('  ' + $_.Line) }
}

Write-Output '=== stage 2: import ==='
Run-Ue 'D:/UEProjects/C1/Scripts/import_win.py' 'D:\UEProjects\C1\Saved\Logs\import_cells.log' 'import'

Write-Output '=== stage 3: materials ==='
Run-Ue 'D:/UEProjects/C1/Scripts/assign_materials.py' 'D:\UEProjects\C1\Saved\Logs\assign_materials.log' 'materials'

Write-Output '=== stage 4: collision ==='
Run-Ue 'D:/UEProjects/C1/Scripts/set_collision.py' 'D:\UEProjects\C1\Saved\Logs\set_collision.log' 'collision'

Write-Output '=== stage 5: cook + pack ==='
& powershell -NoProfile -ExecutionPolicy Bypass -File "$sdir\cook_pack.ps1"
Write-Output 'REBUILD_V4_DONE'
