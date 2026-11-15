local paths = {
 "/Game/Mods/C1/Textures/glass/area_zz_01_gtf_tex_273_a.area_zz_01_gtf_tex_273_a",
 "/Game/Mods/C1/Textures/glass/area_zz_01_gtf_tex_273_aem_color.area_zz_01_gtf_tex_273_aem_color",
}
for _,p in ipairs(paths) do
  local o=StaticFindObject(p)
  print((o and "TEX_OK " or "TEX_MISSING ")..p)
end
print("TEX_PROBE_DONE")
