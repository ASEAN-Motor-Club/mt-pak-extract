"""Create the C1 master materials and 1,609 material instances from the manifest.

Three masters, because one cannot be both opaque and masked and scalar-roughness and
texture-roughness at the same time without branch nodes that make the graph unreadable:
  M_C1_Surface         opaque, scalar roughness/metallic
  M_C1_Surface_Tex     opaque, roughness/metallic/AO maps
  M_C1_Surface_Masked  masked (glass, fence mesh), opacity map
All three expose: BaseColor, Normal, EmissiveStrength, Specular, AmbientOcclusion.

Run:  UnrealEditor-Cmd <uproject> -run=pythonscript -script=.../make_materials.py
      with C1_REBUILD_MASTERS=1 to rebuild the master graphs (the only way to add parameters).

Everything is logged to LOG_PATH. unreal.log() alone is not enough: a PythonScriptCommandlet
prints "Python script executed successfully" even when the script dies at import time, and its
unreal.log output never reaches the commandlet log. The first version of this script ran 19
seconds, created nothing, and reported success -- twice.
"""
import json
import os
import traceback

import unreal

MAT_PATH = '/Game/Mods/C1/Materials'
LOG_PATH = r'D:\make_materials.log'

tools = None
mel = None
MANIFEST = None
REBUILD_MASTERS = False


def log(m):
    line = str(m)
    try:
        with open(LOG_PATH, 'a') as f:
            f.write(line + '\n')
    except Exception:
        pass
    try:
        unreal.log('C1MAT ' + line)
    except Exception:
        pass


def init():
    """Resolve paths and library handles. Deliberately not at import time: anything that raises
    here has to be reported, and an import-time failure is swallowed by the commandlet."""
    global tools, mel, MANIFEST, REBUILD_MASTERS
    proj = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    v2 = os.path.join(proj, 'materials_ue_v2.json')
    # materials_ue_v2.json comes from c1/tools/mat_values.py: per-material roughness/metallic
    # from the source where the source has a factor, else the class table, plus Specular. The v1
    # manifest's hardcoded 0.65/0.0 is what made real-metal materials render as plastic.
    MANIFEST = v2 if os.path.exists(v2) else os.path.join(proj, 'materials_ue.json')
    REBUILD_MASTERS = os.environ.get('C1_REBUILD_MASTERS') == '1'
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mel = unreal.MaterialEditingLibrary
    log('init manifest=%s exists=%s rebuild_masters=%s'
        % (MANIFEST, os.path.exists(MANIFEST), REBUILD_MASTERS))


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
        # Parameters cannot be added to an existing graph; MIs parented to the old asset are
        # reparented to the rebuilt one below.
        unreal.EditorAssetLibrary.delete_asset('%s/%s' % (MAT_PATH, name))
    mat = tools.create_asset(name, MAT_PATH, unreal.Material, unreal.MaterialFactoryNew())

    base = tex_param(mat, 'BaseColor', -800, -200, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    nrm = tex_param(mat, 'Normal', -800, 100, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    emis_t = tex_param(mat, 'EmissiveTex', -800, 500, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    emis_s = scalar_param(mat, 'EmissiveStrength', 0.0, -800, 700)
    # The source carries no specular data at all (0 of 1,609 definitions have a specular field),
    # so a per-class Specular is the only way to stop painted metal, concrete and markings all
    # sharing the dielectric default F0.
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

    # AO is a contrast lever, not a brightness one - and it was never wired: 160 MIs carry an AO
    # slot in the manifest and the old slot_param had no 'ao' entry, so those maps were dropped
    # before the master was even considered.
    ao = tex_param(mat, 'AmbientOcclusion', -1100, 100,
                   unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    mel.connect_material_property(ao, 'R', unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)

    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat, False)
    log('master %s textured=%s masked=%s' % (name, textured, masked))
    return mat


def main():
    init()
    data = json.load(open(MANIFEST))
    log('entries=%d' % len(data['materials']))

    masters = {
        'M_C1_Surface': build_master('M_C1_Surface', False, False),
        'M_C1_Surface_Tex': build_master('M_C1_Surface_Tex', True, False),
        'M_C1_Surface_Masked': build_master('M_C1_Surface_Masked', False, True),
    }

    ok = fail = 0
    failed = []
    # manifest slot key -> master material parameter name. Binding by raw slot key silently does
    # nothing, which looks like "material created but grey".
    slot_param = {
        'basecolor': 'BaseColor',
        'normal': 'Normal',
        'roughness': 'RoughnessTex',
        'metallic': 'MetallicTex',
        'opacity': 'OpacityTex',
        'emissive': 'EmissiveTex',
        'ao': 'AmbientOcclusion',
        # NOTE: no 'detail' binding. The masters have no DetailTex parameter, and binding to a
        # parameter that does not exist silently does nothing. 4 materials ship a detailMap;
        # that is a deliberate omission, not an oversight.
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
                    continue
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
        if i % 100 == 0:
            log('progress %d/%d ok=%d fail=%d' % (i + 1, len(data['materials']), ok, fail))

    log('DONE ok=%d fail=%d' % (ok, fail))
    if failed:
        log('FAILED %s' % ' | '.join(failed[:10]))
    return ok, fail, failed


try:
    open(LOG_PATH, 'w').close()
    main()
    log('exit ok')
except Exception:
    log('SCRIPT_FAILED >>> ' + traceback.format_exc().replace('\n', ' | '))
    raise
