r"""Batch-build C1 emissive instances from emissive_entries.json (see README.md).

Reuses each existing instance (they carry no static switches, so no permutation
resource is created), reparents to the emissive-enabled matte dummy, and binds
BaseColor + Emissive + intensity + white tints. Force-saves every asset.
"""
import unreal, json, os

AT = unreal.AssetToolsHelpers.get_asset_tools()
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
PARENT_PATH = '/Game/Env/Materials/Color/MI_MatteBlue_01_E'
BASE_PATH = '/Game/Env/Materials/Master/M_PolygonMaster'
ENTRIES = json.load(open(r'C:\Users\freeman\emissive_entries.json'))


def ensure_parent():
    if not EAL.does_asset_exist(BASE_PATH):
        AT.create_asset('M_PolygonMaster', '/Game/Env/Materials/Master',
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


def main():
    parent = ensure_parent()
    ok = fail = 0
    white = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)
    for e in ENTRIES:
        path = e['instance']
        mi = unreal.load_asset(path)
        if mi is None:
            name = path.rsplit('/', 1)[-1]
            folder = path.rsplit('/', 1)[0]
            mi = AT.create_asset(name, folder, unreal.MaterialInstanceConstant,
                                 unreal.MaterialInstanceConstantFactoryNew())
        if mi is None:
            print('CREATE_FAILED', path, flush=True)
            fail += 1
            continue
        MEL.set_material_instance_parent(mi, parent)
        for key, tp in (('BaseColor', e['base']), ('Emissive', e['emissive'])):
            tex = unreal.load_asset(tp)
            if tex is None:
                print('MISSING_TEXTURE', path, key, tp, flush=True)
                continue
            MEL.set_material_instance_texture_parameter_value(mi, key, tex)
        MEL.set_material_instance_scalar_parameter_value(mi, 'EmissiveIntensity', e['intensity'])
        for tint in ('BaseColor_Tint', 'Emissive_Tint'):
            MEL.set_material_instance_vector_parameter_value(mi, tint, white)
        if EAL.save_asset(path, only_if_is_dirty=False):
            ok += 1
        else:
            print('SAVE_FAILED', path, flush=True)
            fail += 1
        if ok % 25 == 0:
            print('PROGRESS', ok, flush=True)
    print('BATCH_DONE ok=%d fail=%d' % (ok, fail), flush=True)


main()
