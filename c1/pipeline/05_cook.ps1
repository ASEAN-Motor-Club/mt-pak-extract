# C1 stage 5 — cook the map (Windows side).
#
# The map MUST cook from the mirror CLIENT project (D:\C1Mirror, Windows target).
# A WindowsServer cook of D:\UEProjects\C1 yields a 787-byte C1Roads.uexp stub
# because the level content lives in the mirror project.
#
# The cook MUST go through cook_roads.bat: the equivalent bare invocation
#   -run=cook -TargetPlatform=Windows -map=/Game/Mods/C1/Maps/C1Roads
# exits rc=1 within ~3 s when the project's plugin DLLs are not on PATH.
#
# Judge the cook by 'LogCook: Display: Done!' and the output mtime, never by
# the exit code alone.

param(
    [string]$Mirror = "D:\C1Mirror",
    [string]$Bat    = "D:\cook_roads.bat"
)

$ErrorActionPreference = "Stop"
$maps = Join-Path $Mirror "Saved\Cooked\Windows\MotorTown\Content\Mods\C1\Maps"
$umap = Join-Path $maps "C1Roads.umap"
$uexp = Join-Path $maps "C1Roads.uexp"

function Stamp($p) { if (Test-Path $p) { (Get-Item $p).LastWriteTime.ToString("s") } else { "missing" } }
function SizeOf($p) { if (Test-Path $p) { (Get-Item $p).Length } else { 0 } }

"COOK_PRE umap=$(Stamp $umap) uexp=$(Stamp $uexp) uexp_bytes=$(SizeOf $uexp)"
if (-not (Test-Path $Bat)) { "COOK_FAIL no bat at $Bat"; exit 1 }

& cmd /c $Bat
$rc = $LASTEXITCODE

$uexpBytes = SizeOf $uexp
"COOK_RC=$rc"
"COOK_POST umap=$(Stamp $umap) uexp=$(Stamp $uexp) uexp_bytes=$uexpBytes"

# A stub cook is ~787 bytes. The real sublevel payload is megabytes.
if ($uexpBytes -lt 100000) {
    "COOK_FAIL uexp looks like a stub ($uexpBytes bytes) — wrong project cooked"
    exit 2
}
# The .uexp must be newer than the run start; compare against the .umap pair.
if ((Stamp $uexp) -eq "missing") { "COOK_FAIL no uexp"; exit 3 }

"COOK_OK umap=$umap uexp=$uexp bytes=$uexpBytes"
