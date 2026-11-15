local p = "/Game/Mods/C1Full/Materials/MI_C1_mat_kb_light_a.MI_C1_mat_kb_light_a"
local ok, m = pcall(StaticFindObject, p)
if ok and m and m:IsValid() then
  local par = m.Parent
  print("MASKED_PARENT " .. (par and par:GetFullName() or "nil"))
else
  print("MASKED_NOT_LOADED")
end
