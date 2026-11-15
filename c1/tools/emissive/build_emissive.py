r"""Build C1 emissive material instances — the verified recipe (see README.md).

Run inside UnrealEditor-Cmd Python, e.g.:
  UnrealEditor-Cmd.exe D:\UEProjects\C1\C1.uproject -run=pythonscript -script=... -unattended

Add one entry per material that has an `…_aem_color` texture companion.
The parent dummy is created once and reused; it is NEVER shipped.
"""
import unreal

AT = unreal.AssetToolsHelpers.get_asset_tools()
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary

PARENT_PATH = '/Game/Env/Materials/Color/MI_MatteBlue_01_E'
BASE_PATH = '/Game/Env/Materials/Master/M_PolygonMaster'
EMISSIVE_INTENSITY = 5.0

# instance path -> (BaseColor texture, Emissive texture)
MATERIALS = {
    '/Game/Mods/C1Full/Materials/MI_C1_mat_mat_window3_glass_sh': (
        '/Game/Mods/C1/Textures/glass/area_zz_01_gtf_tex_273_a',
        '/Game/Mods/C1/Textures/glass/area_zz_01_gtf_tex_273_aem_color',
    ),
}


def ensure_dummy_parent():
    if not EAL.does_asset_exist(BASE_PATH):
        base = AT.create_asset('M_PolygonMaster', '/Game/Env/Materials/Master',
                               unreal.Material, unreal.MaterialFactoryNew())
        EAL.save_asset(BASE_PATH, only_if_is_dirty=False)
    if EAL.does_asset_exist(PARENT_PATH):
        EAL.delete_asset(PARENT_PATH)
    par = AT.create_asset('MI_MatteBlue_01_E', '/Game/Env/Materials/Color',
                          unreal.MaterialInstanceConstant,
                          unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(par, unreal.load_asset(BASE_PATH))
    EAL.save_asset(PARENT_PATH, only_if_is_dirty=False)
    print('DUMMY_PARENT_SAVED', flush=True)
    return par


def build_instance(path, base_tex, emis_tex, parent):
    name = path.rsplit('/', 1)[-1]
    folder = path.rsplit('/', 1)[0]
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)  # fresh: never inherit old static switches
    mi = AT.create_asset(name, folder, unreal.MaterialInstanceConstant,
                         unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, parent)
    for key, tex_path in (('BaseColor', base_tex), ('Emissive', emis_tex)):
        tex = unreal.load_asset(tex_path)
        if tex is None:
            print('MISSING_TEXTURE', key, tex_path, flush=True)
            return False
        MEL.set_material_instance_texture_parameter_value(mi, key, tex)
    MEL.set_material_instance_scalar_parameter_value(mi, 'EmissiveIntensity', EMISSIVE_INTENSITY)
    white = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)
    for tint in ('BaseColor_Tint', 'Emissive_Tint'):
        MEL.set_material_instance_vector_parameter_value(mi, tint, white)
    ok = EAL.save_asset(path, only_if_is_dirty=False)  # forced: setters don't dirty
    print('INSTANCE_SAVED', path, ok, flush=True)
    return bool(ok)


def main():
    parent = ensure_dummy_parent()
    for path, (base_tex, emis_tex) in MATERIALS.items():
        build_instance(path, base_tex, emis_tex, parent)
    print('EMISSIVE_BUILD_DONE', flush=True)


main()
