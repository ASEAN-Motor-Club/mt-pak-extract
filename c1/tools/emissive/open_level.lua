local ok, err = pcall(function()
  local pc = FindFirstOf("PlayerController")
  if not pc then print("NO_PC") return end
  local k = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
  if not k then print("NO_KISMET") return end
  k:ExecuteConsoleCommand(pc, "open /Game/Mods/C1Full/Maps/C1Full", nil)
  print("OPEN_ISSUED")
end)
if not ok then print("ERR " .. tostring(err)) end
