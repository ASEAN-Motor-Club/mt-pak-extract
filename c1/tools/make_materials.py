"""Create the C1 master materials and 568 material instances from the manifest.

Three masters, because one cannot be both opaque and masked and scalar-roughness and
texture-roughness at the same time without branch nodes that make the graph unreadable:
  M_C1_Surface         opaque, scalar roughness/metallic
  M_C1_Surface_Tex     opaque, roughness/metallic/AO maps
  M_C1_Surface_Masked  masked (glass, fence mesh), opacity map
All three expose: BaseColor, Normal, EmissiveStrength.
"""
import json
import os

import unreal

MAT_PATH = '/Game/Mods/C1/Materials'
_PROJ = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
# materials_ue_v2.json is the manifest produced by c1/tools/mat_values.py: per-material
# roughness/metallic from the source where the source has a factor, else the class table, plus a
# Specular value. The v1 manifest's hardcoded 0.65/0.0 is what made 17 real-metal materials
# render as plastic.
_V2 = os.path.join(_PROJ, 'materials_ue_v2.json')
MANIFEST = _V2 if os.path.exists(_V2) else os.path.join(_PROJ, 'materials_ue.json')
REBUILD_MASTERS = os.environ.get('C1_REBUILD_MASTERS') == '1'
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def existing(path, name):
    p = '%s/%s' % (path, name)
    return unreal.load_asset(p) if unreal.EditorAssetLibrary.does_asset_exist(p) else None


def tex_param(mat, name, x, y, sampler):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('sampler_type', sampler)
    return e


def scalar_param(mat, name, default, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', default)
    return e


def build_master(name, textured, masked):
    mat = existing(MAT_PATH, name)
    if mat and not REBUILD_MASTERS:
        return mat
    if mat:
        # Params can only be added by rebuilding the graph; MIs parented to it keep their
        # bindings and are reparented to the new asset below.
        unreal.EditorAssetLibrary.delete_asset('%s/%s' % (MAT_PATH, name))
    mat = tools.create_asset(name, MAT_PATH, unreal.Material, unreal.MaterialFactoryNew())

    base = tex_param(mat, 'BaseColor', -800, -200, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    nrm = tex_param(mat, 'Normal', -800, 100, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    emis_t = tex_param(mat, 'EmissiveTex', -800, 500, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    emis_s = scalar_param(mat, 'EmissiveStrength', 0.0, -800, 700)
    # Specular control: the source has no specular data at all (0 of 1,609 definitions), so this
    # is the only way to stop painted metal, concrete and markings sharing F0 0.04.
    spec = scalar_param(mat, 'Specular', 0.5, -800, 900)

    mel.connect_material_property(base, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(nrm, 'RGB', unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(spec, '', unreal.MaterialProperty.MP_SPECULAR)

    # Emissive = EmissiveTex * EmissiveStrength, so a material with no emissive map binds its
    # base colour here and simply keeps strength at 0 - no branch nodes needed.
    emis = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -400, 500)
    mel.connect_material_expressions(emis_t, 'RGB', emis, 'A')
    mel.connect_material_expressions(emis_s, '', emis, 'B')
    mel.connect_material_property(emis, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    if textured:
        rgh = tex_param(mat, 'RoughnessTex', -500, -100,
                        unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        met = tex_param(mat, 'MetallicTex', -500, 200,
                        unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        mel.connect_material_property(rgh, 'R', unreal.MaterialProperty.MP_ROUGHNESS)
        mel.connect_material_property(met, 'R', unreal.MaterialProperty.MP_METALLIC)
    else:
        rgh = scalar_param(mat, 'Roughness', 0.65, -500, -100)
        met = scalar_param(mat, 'Metallic', 0.0, -500, 200)
        mel.connect_material_property(rgh, '', unreal.MaterialProperty.MP_ROUGHNESS)
        mel.connect_material_property(met, '', unreal.MaterialProperty.MP_METALLIC)

    if masked:
        opa = tex_param(mat, 'OpacityTex', -500, 500,
                        unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        mel.connect_material_property(opa, 'R', unreal.MaterialProperty.MP_OPACITY_MASK)
        mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
        mat.set_editor_property('two_sided', True)

    # AO is a contrast lever, not a brightness one, and it was never wired: 160 MIs carry an AO
    # slot in the manifest and the old slot_param had no 'ao' entry, so those maps were dropped
    # silently before the master was even considered.
    ao = tex_param(mat, 'AmbientOcclusion', -1100, 100,
                   unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    mel.connect_material_property(ao, 'R', unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)

    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat, False)
    unreal.log('C1MAT master %s textured=%s masked=%s' % (name, textured, masked))
    return mat


def main():
    data = json.load(open(MANIFEST))

    masters = {
        'M_C1_Surface': build_master('M_C1_Surface', False, False),
        'M_C1_Surface_Tex': build_master('M_C1_Surface_Tex', True, False),
        'M_C1_Surface_Masked': build_master('M_C1_Surface_Masked', False, True),
    }

    ok = fail = 0
    failed = []
    # manifest slot key -> master material parameter name. Binding by raw slot key silently
    # does nothing, which looks like "material created but grey".
    slot_param = {
        'basecolor': 'BaseColor',
        'normal': 'Normal',
        'roughness': 'RoughnessTex',
        'metallic': 'MetallicTex',
        'opacity': 'OpacityTex',
        'emissive': 'EmissiveTex',
        'ao': 'AmbientOcclusion',
        # NOTE: no 'detail' binding yet. The masters have no DetailTex parameter, and binding to a
        # parameter that does not exist silently does nothing -- it would look done and change
        # nothing. 4 materials ship a detailMap; that is a deliberate omission, not an oversight.
    }

    for i, e in enumerate(data['materials']):
        try:
            mi = existing(MAT_PATH, e['mi'])
            if not mi:
                mi = tools.create_asset(e['mi'], MAT_PATH, unreal.MaterialInstanceConstant,
                                        unreal.MaterialInstanceConstantFactoryNew())
            mel.set_material_instance_parent(mi, masters[e['master']])
            for slot, tex_path in e['slots'].items():
                param = slot_param.get(slot)
                if not param:
                    continue  # ao/detail not exposed by v1 masters
                tex = unreal.load_asset(tex_path)
                if tex:
                    mel.set_material_instance_texture_parameter_value(mi, param, tex)
            # materials without an emissive map still need the parameter bound, or the
            # unset texture samples black and the expression is invalid
            if 'emissive' not in e['slots'] and 'basecolor' in e['slots']:
                tex = unreal.load_asset(e['slots']['basecolor'])
                if tex:
                    mel.set_material_instance_texture_parameter_value(mi, 'EmissiveTex', tex)
            for k, v in e['scalars'].items():
                mel.set_material_instance_scalar_parameter_value(mi, k, v)
            mel.update_material_instance(mi)
            unreal.EditorAssetLibrary.save_loaded_asset(mi, False)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            failed.append('%s: %s' % (e['mi'], exc))
        if i % 50 == 0:
            unreal.log('C1MAT progress %d/%d ok=%d fail=%d' % (i + 1, len(data['materials']), ok, fail))

    unreal.log('C1MAT_DONE ok=%d fail=%d' % (ok, fail))
    if failed:
        unreal.log('C1MAT_FAILED %s' % ' | '.join(failed[:10]))


main()
