local names = {"MI_C1_building_window1", "MI_C1_building_black1", "MI_C1_sign_over19", "MI_C1_lamp1_tunnel"}
for _, n in ipairs(names) do
  local p = "/Game/Mods/C1Full/Materials/" .. n .. "." .. n
  local ok, m = pcall(StaticFindObject, p)
  if ok and m and m:IsValid() then
    local par = m.Parent
    print(n .. " PARENT " .. (par and par:GetFullName() or "nil"))
  else
    print(n .. " NOT_LOADED")
  end
end
