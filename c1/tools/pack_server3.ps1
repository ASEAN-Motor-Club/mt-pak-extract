$ErrorActionPreference = 'Stop'
# Build the C1 dedicated-server pak from the CLIENT pak's record list.
#
# SAFETY CONTRACT — this script is read-only with respect to the original pak:
#   writes : stage_server_<HHmmss>\ , paklist_server.txt , pak_server.log ,
#            builds\zzz_AMC_C1_Server_P.pak
#   read   : game Paks\zzz_AMC_C1_P.pak (hash only), Saved\Cooked\WindowsServer\** ,
#            maps_client\** (falls back to maps_in\**)
# NEVER RUN from a staging path or a name that could collide with the client pak: the guards
# below abort first. Do not adapt this script into mvp_deploy.ps1 / pack_only.ps1 /
# install_paks.ps1 / dsrun.ps1 — those write the game install and rebuild the client pak.
$proj    = 'D:\UEProjects\C1'
$cooked  = "$proj\Saved\Cooked\WindowsServer\C1\Content\Mods\C1"
$listSrc = "$proj\server_pak_list_v2.txt"
$stage   = "$proj\stage_server_$([DateTime]::Now.ToString('HHmmss'))"
$modDst  = "$stage\MotorTown\Content\Mods\C1"
$pakOut  = "$proj\builds\zzz_AMC_C1_Server_P.pak"

$clientPak  = "$proj\builds\zzz_AMC_C1_v2_P.pak"
$clientCook = "$proj\Saved\Cooked\Windows"
$pinnedSha  = '96A2BABA031FF0839225EF741DC3B43C4D3E73B85F76A3C4A08F65427514B988'

# ---------- guard 1: output name / location ----------
if ($pakOut -notlike '*_Server_P.pak')            { Write-Output ('ABORT output name is not *_Server_P.pak: ' + $pakOut); exit 10 }
if ((Split-Path $pakOut -Leaf) -eq 'zzz_AMC_C1_P.pak') { Write-Output 'ABORT output name equals the client pak'; exit 10 }
if ((Split-Path $pakOut -Parent) -like '*Content\Paks*') { Write-Output 'ABORT output dir is a game Paks dir'; exit 10 }
if ($pakOut -eq $clientPak)                        { Write-Output 'ABORT output path is the installed client pak'; exit 10 }
Write-Output ('guard_output_ok=' + $pakOut)

# ---------- guard 2: pre-flight state of the originals ----------
if (-not (Test-Path $clientPak)) { Write-Output 'ABORT client pak not found'; exit 11 }
$preSha = (Get-FileHash $clientPak -Algorithm SHA256).Hash
Write-Output ('client_pak_pre_sha=' + $preSha)
if ($preSha -ne $pinnedSha) { Write-Output 'ABORT client pak hash is not the pinned value - regenerate the record list and re-pin before building'; exit 11 }
$preCook = Get-ChildItem $clientCook -Recurse -File -ErrorAction SilentlyContinue
$preCookBytes = ($preCook | Measure-Object Length -Sum).Sum
Write-Output ('client_cook_pre files=' + $preCook.Count + ' bytes=' + $preCookBytes)

if (-not (Test-Path $cooked))  { Write-Output 'ABORT no WindowsServer cook'; exit 3 }
if (-not (Test-Path $listSrc)) { Write-Output 'ABORT no server_pak_list.txt'; exit 3 }

# ---------- stage exactly the client pak's records (minus .ubulk) ----------
$paths = Get-Content $listSrc | Where-Object { $_.Trim().Length -gt 0 }
Write-Output ('requested=' + $paths.Count)

$missing = New-Object System.Collections.Generic.List[string]
$staged = 0
foreach ($rel in $paths) {
  $rel = $rel.Trim()
  $src = if ($rel -like 'Maps/*') {
    $mf = Join-Path "$proj\maps_client" ($rel.Substring(5))
    if (Test-Path $mf) { $mf } else { Join-Path "$proj\maps_in" ($rel.Substring(5)) }
  } else { Join-Path $cooked ($rel -replace '/', '\') }
  if (-not (Test-Path $src)) {
    $alt = Join-Path $cooked ($rel -replace '/', '\')
    if (Test-Path $alt) { $src = $alt } else { $missing.Add($rel); continue }
  }
  $dst = Join-Path $modDst ($rel -replace '/', '\')
  $dir = Split-Path $dst -Parent
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  Copy-Item $src $dst -Force
  $staged++
}
Write-Output ('staged=' + $staged + ' missing=' + $missing.Count)
if ($missing.Count -gt 0) { $missing | Select-Object -First 15 | ForEach-Object { Write-Output ('  MISSING ' + $_) } }

$lines = New-Object System.Collections.Generic.List[string]
Get-ChildItem -Recurse -File $stage | ForEach-Object {
  $rel = $_.FullName.Substring($stage.Length + 1).Replace('\', '/')
  $lines.Add('"' + $_.FullName + '" "../../../' + $rel + '"')
}
$listOut = "$proj\paklist_server.txt"
Set-Content -Path $listOut -Value $lines -Encoding ascii

New-Item -ItemType Directory -Force -Path "$proj\builds" | Out-Null
& 'D:\UE_5.5\Engine\Binaries\Win64\UnrealPak.exe' $pakOut "-create=$listOut" -compress *> "$proj\pak_server.log"
Write-Output ('entries=' + $lines.Count)
Write-Output ('pak_bytes=' + (Get-Item $pakOut).Length)
Write-Output ('pak_sha256=' + (Get-FileHash $pakOut -Algorithm SHA256).Hash)
Write-Output ('pak=' + $pakOut)

# ---------- guard 3: post-flight proof that the originals are untouched ----------
$postSha = (Get-FileHash $clientPak -Algorithm SHA256).Hash
$postCook = Get-ChildItem $clientCook -Recurse -File -ErrorAction SilentlyContinue
$postCookBytes = ($postCook | Measure-Object Length -Sum).Sum
Write-Output ('client_pak_post_sha=' + $postSha)
Write-Output ('CLIENT_PAK_UNCHANGED=' + ($postSha -eq $pinnedSha))
Write-Output ('CLIENT_COOK_UNCHANGED=' + (($postCook.Count -eq $preCook.Count) -and ($postCookBytes -eq $preCookBytes)))
if ($postSha -ne $pinnedSha) { Write-Output 'STOP original client pak changed'; exit 12 }
Write-Output 'PACK_SERVER2_END'
