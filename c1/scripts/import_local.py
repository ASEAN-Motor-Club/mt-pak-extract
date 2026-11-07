"""Import the re-based tiles. Single responsibility: mesh asset creation.

Deterministic by construction:
  * state is keyed to a hash of the source OBJ set (names + sizes + mtimes), so any
    change to the geometry invalidates it and a full re-import happens instead of a
    half-applied mix;
  * every imported mesh gets CTF_UseComplexAsSimple in the same call that imports it,
    because the OBJ importer never creates collision;
  * the run ends with a gate that re-reads every mesh and fails loudly if any mesh is
    missing, unimported or left without collision.

Nothing here touches the level. Placement is an actor problem and lives in
set_transforms.py: loc = (origin_x * 100, -origin_y * 100, 0).
"""
import hashlib
import json
import os

import unreal

PROGRESS = r"D:\import_local.log"
SRC = r"D:\C1FullMirror\meshes_local"
DEST = "/Game/Mods/C1Full/Meshes"
SCALE = 100.0
STATE = r"D:\C1FullMirror\import_state.json"
FLAG = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE


def log(m):
    unreal.log("REBASE " + str(m))
    with open(PROGRESS, "a") as f:
        f.write(str(m) + "\n")


def source_signature(files):
    h = hashlib.sha256()
    for f in files:
        p = os.path.join(SRC, f)
        st = os.stat(p)
        h.update(("%s:%d:%.0f\n" % (f, st.st_size, st.st_mtime)).encode())
    return h.hexdigest()


def import_one(path, name):
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
    applied = False
    for holder in ("static_mesh_import_data", "mesh_import_data"):
        try:
            data = getattr(opt, holder, None)
            if data is not None and hasattr(data, "import_uniform_scale"):
                data.import_uniform_scale = SCALE
                applied = True
                break
        except Exception:
            pass
    if not applied and hasattr(opt, "import_uniform_scale"):
        opt.import_uniform_scale = SCALE
        applied = True
    task.options = opt
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return applied


def ensure_collision(name):
    sm = unreal.EditorAssetLibrary.load_asset("%s/%s" % (DEST, name))
    if sm is None:
        return "load"
    try:
        body = sm.get_editor_property("body_setup")
    except Exception as e:
        return "body:%s" % e
    if body is None:
        return "no_body"
    body.set_editor_property("collision_trace_flag", FLAG)
    unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)
    return None


def main():
    open(PROGRESS, "w").close()
    files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".obj"))
    sig = source_signature(files)
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    if st.get("signature") != sig:
        log("signature changed -> full import (%s)" % sig[:12])
        done = set()
    else:
        done = set(st.get("done", []))
    log("tiles=%d already_done=%d sig=%s" % (len(files), len(done), sig[:12]))

    imported, no_scale, col_fail = 0, 0, []
    for f in files:
        name = os.path.splitext(f)[0]
        if name in done:
            continue
        if not import_one(os.path.join(SRC, f), name):
            no_scale += 1
        err = ensure_collision(name)
        if err:
            col_fail.append([name, err])
        imported += 1
        done.add(name)
        if imported % 10 == 0:
            json.dump({"signature": sig, "done": sorted(done)}, open(STATE, "w"))
        if imported % 25 == 0:
            log("imported %d/%d this_run" % (imported, len(files)))
    json.dump({"signature": sig, "done": sorted(done)}, open(STATE, "w"))
    log("import_done=%d scale_failures=%d collision_failed=%d"
        % (imported, no_scale, len(col_fail)))

    # ---- gate: read every mesh back, not the counters above ----
    missing, no_col = [], []
    for f in files:
        name = os.path.splitext(f)[0]
        sm = unreal.EditorAssetLibrary.load_asset("%s/%s" % (DEST, name))
        if sm is None:
            missing.append(name)
            continue
        body = sm.get_editor_property("body_setup")
        flag = body.get_editor_property("collision_trace_flag") if body else None
        if flag != FLAG:
            ensure_collision(name)          # repair, then re-read
            sm = unreal.EditorAssetLibrary.load_asset("%s/%s" % (DEST, name))
            body = sm.get_editor_property("body_setup") if sm else None
            flag = body.get_editor_property("collision_trace_flag") if body else None
        if flag != FLAG:
            no_col.append(name)
    ok = not missing and not no_col
    log("GATE meshes=%d missing=%d no_collision=%d -> %s"
        % (len(files), len(missing), len(no_col), "IMPORT_GATE_OK" if ok else "IMPORT_GATE_FAIL"))
    if missing[:5]:
        log("missing sample: %s" % missing[:5])
    if no_col[:5]:
        log("no_collision sample: %s" % no_col[:5])


main()
