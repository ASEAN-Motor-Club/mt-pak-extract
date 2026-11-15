$pk='D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks'
$keep='zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_AMC_C1EmisMaskedTest_P.pak'
$full='zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_AMC_C1EmissiveFull_P.pak'
Copy-Item ("C:\Users\freeman\" + $keep) ($pk + "\" + $keep) -Force
if (Test-Path ($pk + "\" + $keep)) { "COPIED " + $keep } else { "COPY_FAILED " + $keep }
Get-ChildItem $pk -Filter '*Emis*' | ForEach-Object {
  if (($_.Name -ne $keep) -and ($_.Name -ne $full)) { Remove-Item $_.FullName -Force; "DELETED " + $_.Name } else { "KEPT " + $_.Name }
}
$P = $pk.Replace('\','/') + '/'
$list = @('MotorTown-Windows.pak','Schedule_I_0.7.19.pak','zzz_AMC_C1Base_v3_P.pak','zzz_AMC_HamsEngines_Test_v0.6.4_0.7.19_P.pak','zzz_ASEAN_MuhanDiffLock_v0.1.0_0.7.19.pak','zzzz_AMC_C1Full_Roads_P.pak','zzzzz_AMC_C1Mesh_v15_P.pak','zzzzzz_AMC_C1Map_v11_P.pak','zzzzzzzzz_AMC_Shuto_Lights_v13_P.pak', $full, $keep)
$ini='C:\Users\freeman\AppData\Local\MotorTown\Saved\Config\Windows\CustomPak.ini'
Copy-Item $ini "$ini.bak_wl" -Force
$out = @(';METADATA=(Diff=true, UseCommands=true)','[CustomPakAccepted]',('Count=' + $list.Count))
for ($i=0; $i -lt $list.Count; $i++) { $out += ('Pak' + $i + '=' + $P + $list[$i]) }
$out += ''; $out += '[CustomPakBootSentinel]'; $out += 'Count=0'
for ($i=0; $i -lt $list.Count; $i++) { $out += ('Pak' + $i + '=' + $P + $list[$i]) }
Set-Content -Path $ini -Value ($out -join "`r`n")
Select-String -Path $ini -Pattern 'Count=|Pak9=' | Select-Object -First 2 | ForEach-Object { $_.Line }
