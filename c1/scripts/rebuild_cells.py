"""Delete-then-import the cell meshes so the result is a SINGLE-LOD asset.

PREREQUISITE: meshes_local/<cell>.obj must be the REBASED OBJ (origin subtracted, V mirrored --
see rebase_obj.py). Importing the absolute OBJ moves the cell by its own origin because every
actor already sits at origin*100 with Y negated.

Why deletion first: `replace_existing=True` on a multi-LOD asset rewrites LOD0 only and
keeps the stale levels (MAP_PORTING_GUIDE.md, LODs section). Those stale LODs keep the
old section/material tables -- after dropping the `dum` slot they point past the end of
the slot array, and the tile stops drawing entirely. Deleting the asset forces the
importer to build the whole mesh from the OBJ: one LOD, one consistent slot table.

Material assignment comes from slotmap.json, which was read out of the *shipped* assets,
so slot names and MI paths match what the map already expects.
"""
import json
import unreal

MAP = json.load(open(r"D:\slotmap.json"))  # built by make_slotmap.py from the SHIPPED assets
DEST = "/Game/Mods/C1Full/Meshes"
SRC = r"D:\C1FullMirror\meshes_local"
SCALE = 100.0
LOG = r"D:\rebuild_cells.log"


def log(m):
    unreal.log("REBUILD " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


open(LOG, "w").close()
for NAME, wants in MAP.items():
    path = "%s/%s" % (DEST, NAME)
    obj = SRC + "\\" + NAME + ".obj"

    # 1. Remove the old asset so the import cannot merge into its LOD chain.
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        ok = unreal.EditorAssetLibrary.delete_asset(path)
        log("%s delete_asset=%s" % (NAME, ok))
        if not ok:
            log("%s ABORT: could not delete" % NAME)
            continue

    # 2. Import fresh -> single LOD.
    task = unreal.AssetImportTask()
    task.filename = obj
    task.destination_path = DEST
    task.destination_name = NAME
    task.replace_existing = True
    task.automated = True
    task.save = True
    opt = unreal.FbxImportUI()
    opt.import_mesh = True
    opt.import_materials = False
    opt.import_textures = False
    opt.automated_import_should_detect_type = True
    opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    data = getattr(opt, "static_mesh_import_data", None)
    if data is not None:
        data.import_uniform_scale = SCALE
        for flag in ("generate_lightmap_u_vs", "import_mesh_lo_ds"):
            try:
                setattr(data, flag, False)
            except Exception as e:
                log("%s option %s failed: %s" % (NAME, flag, e))
    task.options = opt
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    sm = unreal.EditorAssetLibrary.load_asset(path)
    if sm is None:
        log("%s ABORT: not created" % NAME)
        continue
    lods = sm.get_num_lods()
    tris = [sm.get_num_triangles(i) for i in range(lods)]
    log("%s imported lods=%d tris=%s" % (NAME, lods, tris))

    # 3. Rebind the shipped material set, matched by slot name.
    by_name = {s: mi for s, mi in wants}

    def resolve(slot_name):
        """OBJ material names carry numeric suffixes the shipped slots drop
        (mat_botom_u_10 -> slot 'mat_botom_u'); match longest prefix either way."""
        if slot_name in by_name:
            return by_name[slot_name]
        cands = [k for k in by_name if slot_name.startswith(k)]
        if cands:
            return by_name[max(cands, key=len)]
        cands = [k for k in by_name if k.startswith(slot_name)]
        if cands:
            return by_name[max(cands, key=len)]
        return None

    have = [str(s.material_slot_name) for s in sm.get_editor_property("static_materials")]
    slots, missing, unbound = [], 0, []
    for slot_name in have:
        mi_path = resolve(slot_name)
        if mi_path is None:
            unbound.append(slot_name)
            continue
        mi = unreal.load_asset(mi_path.split(".")[0])
        if mi is None:
            missing += 1
            unbound.append(slot_name)
            continue
        slots.append(unreal.StaticMaterial(material_interface=mi, material_slot_name=unreal.Name(slot_name)))
    sm.set_editor_property("static_materials", slots)

    # 4. Complex-as-simple collision, matching the rest of the map.
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(sm, False)

    bb = sm.get_bounding_box()
    log("%s DONE lods=%d slots=%d missing_mi=%d unbound=%s bounds=(%.0f,%.0f,%.0f)..(%.0f,%.0f,%.0f)"
        % (NAME, sm.get_num_lods(), len(slots), missing, unbound[:4],
           bb.min.x, bb.min.y, bb.min.z, bb.max.x, bb.max.y, bb.max.z))
log("REBUILD_DONE")
