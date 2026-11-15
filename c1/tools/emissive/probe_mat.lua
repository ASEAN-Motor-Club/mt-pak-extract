local paths = {
  "/Game/Mods/C1Full/Materials/MI_C1_mat_mat_window3_glass_sh.MI_C1_mat_mat_window3_glass_sh",
  "/Game/Mods/C1/Materials/MI_C1_mat_mat_window3_glass_sh.MI_C1_mat_mat_window3_glass_sh",
}
for _, p in ipairs(paths) do
  local o = StaticFindObject(p)
  if o then
    local par = nil
    pcall(function() par = o.Parent end)
    local pn = "nil"
    if par then pcall(function() pn = par:GetFullName() end) end
    print("FOUND " .. p)
    print("  PARENT " .. tostring(pn))
  else
    print("MISSING " .. p)
  end
end
print("PROBE_DONE")
