"""Import all C1 corridor cell OBJs into the Motor Town cook project (Win64 host).

The cell OBJs are authored in METRES (a 500 m tile spans ~520 units). Unreal
imports OBJ with 1 unit = 1 cm, so an unscaled import yields a tile 520 cm
across - 100x too small, which is why the corridor never appeared under the
player. IMPORT_SCALE=100 bakes metres->centimetres at import time.
"""
import glob
import json
import os

import unreal

BASE = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
MESH_DIR = os.path.join(BASE, 'meshes')
DEST = '/Game/Mods/C1/Meshes'
IMPORT_SCALE = 100.0


def import_obj(path, name):
    task = unreal.AssetImportTask()
    task.filename = path
    task.destination_path = DEST
    task.destination_name = name
    task.replace_existing = True
    task.automated = True
    task.save = True
    opt = unreal.FbxImportUI()
    opt.import_mesh = True
    opt.import_materials = False
    opt.import_textures = False
    opt.automated_import_should_detect_type = True
    opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    # metres -> centimetres; try both locations the property can live on
    applied = False
    for holder in ('static_mesh_import_data', 'mesh_import_data'):
        try:
            data = getattr(opt, holder, None)
            if data is not None and hasattr(data, 'import_uniform_scale'):
                data.import_uniform_scale = IMPORT_SCALE
                applied = True
                break
        except Exception as exc:
            unreal.log_warning('scale set failed on %s: %s' % (holder, exc))
    if not applied and hasattr(opt, 'import_uniform_scale'):
        opt.import_uniform_scale = IMPORT_SCALE
        applied = True
    task.options = opt
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    if not applied:
        unreal.log_warning('C1_SCALE_NOT_APPLIED %s' % name)
    return unreal.EditorAssetLibrary.does_asset_exist('%s/%s' % (DEST, name))


def bounds_of(mesh):
    try:
        box = mesh.get_bounding_box()
        ext = box.max - box.min
        return [round(ext.x, 1), round(ext.y, 1), round(ext.z, 1)]
    except Exception:
        return None


def main():
    files = sorted(glob.glob(os.path.join(MESH_DIR, '*.obj')))
    ok = fail = 0
    tris = 0
    failed = []
    sample = None
    for i, path in enumerate(files):
        name = os.path.splitext(os.path.basename(path))[0]
        if import_obj(path, name):
            ok += 1
            mesh = unreal.load_asset('%s/%s' % (DEST, name))
            if mesh and hasattr(mesh, 'get_num_triangles'):
                tris += mesh.get_num_triangles(0)
            if sample is None and mesh is not None:
                sample = {'name': name, 'bounds_cm': bounds_of(mesh)}
        else:
            fail += 1
            failed.append(name)
    result = {'files': len(files), 'ok': ok, 'fail': fail, 'tris': tris,
              'scale': IMPORT_SCALE, 'sample': sample, 'failed': failed}
    with open(os.path.join(BASE, 'import_result.json'), 'w') as fh:
        json.dump(result, fh, indent=1)
    unreal.log('C1_IMPORT_DONE %s' % json.dumps(result))


main()
