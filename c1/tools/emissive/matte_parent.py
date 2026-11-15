import unreal
AT=unreal.AssetToolsHelpers.get_asset_tools(); EAL=unreal.EditorAssetLibrary; MEL=unreal.MaterialEditingLibrary
base=unreal.load_asset('/Game/Env/Materials/Master/M_PolygonMaster')
p='/Game/Env/Materials/Color/MI_MatteBlue_01_E'
if EAL.does_asset_exist(p): EAL.delete_asset(p)
par=AT.create_asset('MI_MatteBlue_01_E','/Game/Env/Materials/Color',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
MEL.set_material_instance_parent(par,base)
EAL.save_asset(p, only_if_is_dirty=False)
print('DUMMY_MATTE_SAVED')
ip='/Game/Mods/C1Full/Materials/MI_C1_mat_mat_window3_glass_sh'
if EAL.does_asset_exist(ip): EAL.delete_asset(ip)
mi=AT.create_asset('MI_C1_mat_mat_window3_glass_sh','/Game/Mods/C1Full/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
MEL.set_material_instance_parent(mi,par)
for key,path in [('BaseColor','/Game/Mods/C1/Textures/glass/area_zz_01_gtf_tex_273_a'),('Emissive','/Game/Mods/C1/Textures/glass/area_zz_01_gtf_tex_273_aem_color')]:
    t=unreal.load_asset(path)
    if t: MEL.set_material_instance_texture_parameter_value(mi,key,t)
MEL.set_material_instance_scalar_parameter_value(mi,'EmissiveIntensity',5.0)
white=unreal.LinearColor(1.0,1.0,1.0,1.0)
for v in ('BaseColor_Tint','Emissive_Tint'):
    try:
        MEL.set_material_instance_vector_parameter_value(mi,v,white); print('TINT_SET',v)
    except Exception as e: print('TINT_FAIL',v,e)
EAL.save_asset(ip, only_if_is_dirty=False)
print('MATTE_MI_SAVED')
