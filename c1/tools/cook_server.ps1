$ErrorActionPreference = 'Stop'
# WindowsServer cook of the C1 mod project.
#
# SAFETY CONTRACT — verified by before/after measurement in this script:
#   writes : Saved\Cooked\WindowsServer\** , Saved\Logs\cook_server.log
#   read   : project Content, Saved\Cooked\Windows (client cook), DDC
# Never passes -Clean: that is the only cook flag that can prune another platform's
# cooked tree. If a clean cook is ever needed, use a throwaway -OutputDir instead.
$ue    = 'D:\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$proj  = 'D:\UEProjects\C1'
$up    = "$proj\C1.uproject"
$log   = "$proj\Saved\Logs\cook_server.log"
$clientCook = "$proj\Saved\Cooked\Windows"
$cookArgs = @('-run=cook','-TargetPlatform=WindowsServer','-CookAll','-unattended','-nop4','-nosplash','-stdout','-FullStdOutLogOutput')
if ($cookArgs -contains '-Clean') { Write-Output 'ABORT -Clean in cook args'; exit 5 }

function Measure-Tree($path) {
  $i = Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue
  $sz = ($i | Measure-Object Length -Sum).Sum
  $newest = ($i | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
  return [pscustomobject]@{ Count = $i.Count; Bytes = $sz; Newest = $newest }
}

$pre = Measure-Tree $clientCook
Write-Output ('client_cook_before files=' + $pre.Count + ' bytes=' + $pre.Bytes + ' newest=' + $pre.Newest)
Write-Output ('cook_start=' + (Get-Date -Format o))
& $ue $up $cookArgs *> $log
Write-Output ('cook_rc=' + $LASTEXITCODE)

$post = Measure-Tree $clientCook
$same = ($pre.Count -eq $post.Count) -and ($pre.Bytes -eq $post.Bytes) -and ($pre.Newest -eq $post.Newest)
Write-Output ('client_cook_after files=' + $post.Count + ' bytes=' + $post.Bytes + ' newest=' + $post.Newest)
Write-Output ('CLIENT_COOK_UNCHANGED=' + $same)
if (-not $same) { Write-Output 'STOP client cook tree changed during a server cook'; Write-Output 'COOK_SERVER_END'; exit 6 }

Get-Content $log -ErrorAction SilentlyContinue | Select-String -Pattern 'Cook.*(success|error|failed)|Error:' | Select-Object -Last 5 | ForEach-Object { Write-Output ('  ' + $_.Line) }

$cooked = "$proj\Saved\Cooked\WindowsServer\C1\Content\Mods\C1"
if (Test-Path $cooked) {
  foreach ($d in @('Meshes','Kit','Textures','Materials','Collision')) {
    $f = Join-Path $cooked $d
    if (Test-Path $f) {
      $items = Get-ChildItem $f -Recurse -File
      $ub = ($items | Where-Object { $_.Extension -eq '.ubulk' } | Measure-Object Length -Sum).Sum
      Write-Output ("$d files=" + $items.Count + " mb=" + [math]::Round((($items | Measure-Object Length -Sum).Sum)/1MB,1) + " ubulk_mb=" + [math]::Round($ub/1MB,1))
    } else { Write-Output "WARN missing $d" }
  }
  $all = Get-ChildItem "$proj\Saved\Cooked\WindowsServer" -Recurse -File
  Write-Output ('server_cook_files=' + $all.Count + ' mb=' + [math]::Round((($all | Measure-Object Length -Sum).Sum)/1MB,1))
} else { Write-Output 'SERVER_COOK_MISSING'; Write-Output 'COOK_SERVER_END'; exit 7 }
Write-Output 'COOK_SERVER_END'
