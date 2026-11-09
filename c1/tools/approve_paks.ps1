# approve_paks.ps1 -- pre-seed Motor Town's custom-pak allowlist so the "new pak detected"
# prompt does not fire for paks we installed ourselves.
#
# The registry is %LOCALAPPDATA%\MotorTown\Saved\Config\Windows\CustomPak.ini,
# section [CustomPakAccepted], keyed by FULL FILE PATH with forward slashes (not by hash,
# not by bare filename -- stale entries for deleted paks stay forever, which is the proof).
#
#   approve_paks.ps1                       # approve every AMC pak currently in Content\Paks
#   approve_paks.ps1 -Paths a.pak,b.pak    # approve specific paths
#   approve_paks.ps1 -DryRun               # show what would change
param(
  [string[]]$Paths,
  [switch]$DryRun
)

$ini = "$env:LOCALAPPDATA\MotorTown\Saved\Config\Windows\CustomPak.ini"
$pakDir = 'D:/SteamLibrary/steamapps/common/Motor Town/MotorTown/Content/Paks'
if (-not (Test-Path $ini)) { Write-Output "FAIL no registry at $ini"; exit 2 }

if (-not $Paths -or $Paths.Count -eq 0) {
  $Paths = Get-ChildItem 'D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks' -Filter *.pak |
    Where-Object { $_.Name -match '^(zz+_)?AMC_|AMC_' } |
    ForEach-Object { "$pakDir/$($_.Name)" }
}
$Paths = $Paths | ForEach-Object { ($_ -replace '\\', '/') } | Select-Object -Unique
if ($Paths.Count -eq 0) { Write-Output 'nothing to approve'; exit 0 }

$raw = [IO.File]::ReadAllText($ini)
$lines = $raw -split "`r?`n"

# locate the accepted section and its extent
$secStart = -1; $secEnd = $lines.Length
for ($i = 0; $i -lt $lines.Length; $i++) {
  if ($lines[$i] -eq '[CustomPakAccepted]') { $secStart = $i }
  elseif ($secStart -ge 0 -and $lines[$i] -match '^\[') { $secEnd = $i; break }
}
if ($secStart -lt 0) { Write-Output 'FAIL [CustomPakAccepted] not found'; exit 3 }

$existing = New-Object System.Collections.Generic.List[string]
for ($i = $secStart + 1; $i -lt $secEnd; $i++) {
  if ($lines[$i] -match '^Pak\d+=(.+)$') { $existing.Add($matches[1].Trim()) }
}
$seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($e in $existing) { [void]$seen.Add($e) }

$added = @()
foreach ($p in $Paths) {
  if (-not $seen.Contains($p)) { $added += $p; [void]$seen.Add($p) }
}
Write-Output ("registry entries before={0} requested={1} to_add={2}" -f $existing.Count, $Paths.Count, $added.Count)
foreach ($a in $added) { Write-Output "  + $a" }
if ($DryRun -or $added.Count -eq 0) { Write-Output 'no write (dry-run or nothing to add)'; exit 0 }

$all = @($existing) + $added
$newSec = @('[CustomPakAccepted]', ('Count=' + $all.Count))
for ($i = 0; $i -lt $all.Count; $i++) { $newSec += ('Pak' + $i + '=' + $all[$i]) }

$before = @()
if ($secStart -gt 0) { $before = $lines[0..($secStart-1)] }
$after = @()
if ($secEnd -lt $lines.Length) { $after = $lines[$secEnd..($lines.Length-1)] }
$out = (@($before) + $newSec + @($after)) -join "`r`n"

$bak = $ini + '.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
Copy-Item $ini $bak -Force
[IO.File]::WriteAllText($ini, $out)

# verify by re-reading
$check = [IO.File]::ReadAllText($ini)
$n = ([regex]::Matches($check, '(?m)^Pak\d+=')).Count
$cnt = [regex]::Match($check, '(?m)^Count=(\d+)').Groups[1].Value
$missing = $Paths | Where-Object { $check -notmatch [regex]::Escape($_) }
Write-Output ("written entries={0} count={1} requested_missing={2} backup={3}" -f $n, $cnt, ($missing | Measure-Object).Count, (Split-Path $bak -Leaf))
if ($missing) { $missing | ForEach-Object { Write-Output "  MISSING $_" }; exit 4 }
Write-Output 'APPROVE_OK'
