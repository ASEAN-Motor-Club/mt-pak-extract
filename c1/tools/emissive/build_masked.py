r"""Masked (alpha-cutout) emissive materials — own master + instances.

No vanilla master is both BLEND_Masked and emissive-capable (M_PlantMaster is masked
but has no emissive), so we author one. Ships the master AND the instances; the master
lives under /Game/Mods so it overwrites nothing vanilla.
"""
import unreal, json

AT = unreal.AssetToolsHelpers.get_asset_tools()
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
MASTER = '/Game/Mods/C1/Materials/M_C1_MaskedEmissive'
ENTRIES = json.load(open(r'C:\Users\freeman\masked_entries.json'))


def build_master():
    if EAL.does_asset_exist(MASTER):
        EAL.delete_asset(MASTER)
    m = AT.create_asset('M_C1_MaskedEmissive', '/Game/Mods/C1/Materials',
                        unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    bc = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0)
    bc.set_editor_property('parameter_name', 'BaseColor')
    MEL.connect_material_property(bc, '', unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(bc, 'A', unreal.MaterialProperty.MP_OPACITY_MASK)
    em = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -700, 400)
    em.set_editor_property('parameter_name', 'Emissive')
    inten = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -700, 650)
    inten.set_editor_property('parameter_name', 'EmissiveIntensity')
    inten.set_editor_property('default_value', 5.0)
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, 400)
    MEL.connect_material_expressions(em, '', mul, 'A')
    MEL.connect_material_expressions(inten, '', mul, 'B')
    MEL.connect_material_property(mul, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    EAL.save_asset(MASTER, only_if_is_dirty=False)
    print('MASKED_MASTER_SAVED', flush=True)
    return m


def main():
    master = build_master()
    ok = fail = 0
    for e in ENTRIES:
        path = e['instance']
        name = path.rsplit('/', 1)[-1]
        folder = path.rsplit('/', 1)[0]
        if EAL.does_asset_exist(path):
            EAL.delete_asset(path)
        mi = AT.create_asset(name, folder, unreal.MaterialInstanceConstant,
                             unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, master)
        for key, tp in (('BaseColor', e['base']), ('Emissive', e['emissive'])):
            tex = unreal.load_asset(tp)
            if tex is None:
                print('MISSING_TEXTURE', path, key, tp, flush=True)
                continue
            MEL.set_material_instance_texture_parameter_value(mi, key, tex)
        MEL.set_material_instance_scalar_parameter_value(mi, 'EmissiveIntensity', e['intensity'])
        if EAL.save_asset(path, only_if_is_dirty=False):
            ok += 1
        else:
            print('SAVE_FAILED', path, flush=True)
            fail += 1
    print('MASKED_DONE ok=%d fail=%d' % (ok, fail), flush=True)


main()
