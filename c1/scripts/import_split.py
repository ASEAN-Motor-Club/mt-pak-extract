"""A3 dry run: import three split cells and their no-collision meshes, then read everything back.

Structural cells go to /Game/Mods/C1Full/Meshes under their own names (delete-before-import, so the
LOD chain is rebuilt rather than patched), get CTF_UseComplexAsSimple, and then get their shipped
StaticMaterials array restored from slotmap.json.

The paint and foliage meshes go to their own folders and are deliberately left without collision:
the flag stays at the default and the body setup carries no simple shapes, so nothing in them can
push the car.

Every claim is read back from the asset after saving, in the same process but after a reload, and
written to D:/a3_report.json.
"""
import json
import os

import unreal

DEST_STRUCT = "/Game/Mods/C1Full/Meshes"
DEST_PAINT = "/Game/Mods/C1Full/Meshes"
DEST_FOLIAGE = "/Game/Mods/C1Full/Meshes_NoCollision"
# The structural cells come from meshes_local, the tile set the working port was built from.
# nc_out/cells_v2 is the no-collision RE-EXPORT and is lossy: c2_9 alone drops 113 -> 100 material
# sections and 72,465 -> 67,613 faces, and the importer then keeps only 76% of what is left. Feeding
# that set in is what shredded the map in game while the editor still reported sane bounds.
SRC_STRUCT = r"D:\C1FullMirror\meshes_local"
SRC_FOLIAGE = r"D:\C1FullMirror\nc_out\foliage"
SRC_PAINT = r"D:\C1FullMirror\nc_out\paint\C1_NoCollision_Paint.obj"
SLOTMAP = r"D:\slotmap.json"
MAT_DIR = "/Game/Mods/C1Full/Materials"
REPORT = r"D:\a3_report.json"
LOG = r"D:\a3.log"
SCALE = 100.0
FLAG = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
NON_CELL = {"uvquad"}   # 1-triangle UV helper shipped next to the cells, not a cell
ELEM_TYPES = ("sphere_elems", "box_elems", "convex_elems", "sphyl_elems", "tapered_capsule_elems")
CFG = r"D:\import_split_cfg.json"
CELLS = ["c-14_-31", "c-1_-3", "c0_-6"]


def log(m):
    unreal.log("A3 " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


def import_obj(path, dest, name):
    task = unreal.AssetImportTask()
    task.filename = path
    task.destination_path = dest
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
    for holder in ("static_mesh_import_data", "mesh_import_data"):
        data = getattr(opt, holder, None)
        if data is not None and hasattr(data, "import_uniform_scale"):
            data.import_uniform_scale = SCALE
            break
    task.options = opt
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])


def empty_source(path):
    """True when the OBJ carries no triangle at all.

    Six sources are placeholders: three vertices and one face, and that face is the malformed
    `f 0 1/1/1 2/2/2` line the split writes into every file. Strip that line and there is nothing
    left to import, so the importer fails and the previous build's asset stays behind -- which is
    how a sliver survived here long after the split stopped producing geometry for these cells.
    """
    try:
        if os.path.getsize(path) > 8192:
            return False
        with open(path, "r", errors="ignore") as f:
            for line in f:
                if line.startswith("f ") and len(line.split()) >= 4:
                    return False
    except OSError:
        return False
    return True


def drop(pkg):
    if unreal.EditorAssetLibrary.does_asset_exist(pkg):
        if not unreal.EditorAssetLibrary.delete_asset(pkg):
            raise RuntimeError("could not delete %s" % pkg)
        return True
    return False


def collision_state(sm):
    body = sm.get_editor_property("body_setup")
    if body is None:
        return {"flag": None, "simple": None}
    flag = body.get_editor_property("collision_trace_flag")
    counts = {}
    try:
        agg = body.get_editor_property("agg_geom")
        for key in ELEM_TYPES:
            try:
                counts[key] = len(agg.get_editor_property(key))
            except Exception as e:
                counts[key] = "err:%s" % e
    except Exception as e:
        counts = "err:%s" % e
    return {"flag": str(flag), "elems": counts,
            "simple_total": sum(v for v in counts.values() if isinstance(v, int))
            if isinstance(counts, dict) else None}


def clear_simple_collision(sm):
    """Drop the convex hull the OBJ importer adds for every static mesh.

    The importer creates one convex element per mesh. With the trace flag left at the default,
    that hull is what physics uses, so a "no collision" mesh has to have no geometry at all.
    """
    body = sm.get_editor_property("body_setup")
    if body is None:
        return "no_body"
    agg = body.get_editor_property("agg_geom")
    for key in ELEM_TYPES:
        try:
            agg.set_editor_property(key, [])
        except Exception as e:
            return "clear_failed:%s:%s" % (key, e)
    body.set_editor_property("agg_geom", agg)
    sm.set_editor_property("body_setup", body)
    unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)
    return None


def apply_slots(sm, rec):
    """Attach the shipped material instances to the slots the importer created.

    The array itself is left alone: the importer built it from the OBJ's `usemtl` groups, and its
    order is what the face sections reference. Rewriting the array wholesale would shift every
    face onto a different material. `imported_material_slot_name` is read-only in 5.5, so the
    mapping is name -> shipped instance.
    """
    name_to_mi = {}
    null_names = set()
    for slot in rec["slots"]:
        key = slot.get("imported") or slot.get("slot")
        if key:
            name_to_mi[key] = slot["mi"]
            if not slot["mi"]:
                null_names.add(key)
    got = sm.get_editor_property("static_materials")
    unmatched, bound = [], 0
    for entry in got:
        name = str(entry.get_editor_property("imported_material_slot_name"))
        if name not in name_to_mi:
            # the shipped mesh has no slot for this name (its source export predates the material
            # or the face came from paint/foliage), but the packaged instance set covers it: the
            # build names every instance MI_C1_<material>
            guess = "%s/MI_C1_%s" % (MAT_DIR, name)
            if unreal.EditorAssetLibrary.does_asset_exist(guess):
                name_to_mi[name] = guess
            else:
                unmatched.append(name)
                continue
        mi_path = name_to_mi[name]
        mi = None
        if mi_path:
            mi = unreal.EditorAssetLibrary.load_asset(mi_path)
            if mi is None:
                return "mi_missing:%s" % mi_path
            bound += 1
        entry.set_editor_property("material_interface", mi)
    sm.set_editor_property("static_materials", got)
    unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)
    return None if not unmatched else "unmatched:%s" % unmatched[:5]


def obj_material_names(path):
    """Materials that actually carry a face, in file order.

    Counting `usemtl` lines is wrong: the split ends every file with an extra `usemtl` block whose
    only face is the malformed `f 0 ...` line, so once that line is stripped the material has no
    geometry and the importer -- correctly -- creates no slot for it. The gate then reports a
    mismatch that is only a count of a slot nobody can see.
    """
    names = []
    seen = set()
    current = None
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("usemtl "):
                current = line.split(None, 1)[1].strip()
            elif line.startswith("f ") and current is not None:
                if current not in seen:
                    seen.add(current)
                    names.append(current)
    return names


def slots_state(sm):
    got = sm.get_editor_property("static_materials")
    nonnull = sum(1 for g in got if g.get_editor_property("material_interface") is not None)
    return len(got), nonnull


def load_cells():
    """Cell list from the config file; "all" means every structural OBJ the split produced."""
    global REPORT, LOG
    if not os.path.exists(CFG):
        return list(CELLS)
    cfg = json.load(open(CFG))
    # Every path in this script is overridable from the config. That matters: a rebuild from a
    # corrected source tree is only honest if the import really reads that tree, and a config key
    # that is silently ignored looks exactly like a successful rebuild.
    for key in ("report", "log", "src_struct", "src_foliage", "src_paint", "slotmap"):
        if cfg.get(key):
            globals()[key.upper()] = cfg[key]
    cells = cfg.get("cells", list(CELLS))
    if cells == "all":
        # a union: c0_-21 is foliage-only, so listing structural OBJs alone would skip its foliage
        names = set()
        for d in (SRC_STRUCT, SRC_FOLIAGE):
            names.update(os.path.splitext(f)[0] for f in os.listdir(d) if f.lower().endswith(".obj"))
        cells = sorted(names)
    return cells


def main():
    cells = load_cells()   # must run first: the config can redirect the report and log paths
    open(LOG, "w").close()
    sm_map = json.load(open(SLOTMAP))
    log("cells=%d" % len(cells))
    report = {"cells": {}, "paint": {}, "foliage": {}, "ok": False, "cell_count": len(cells)}
    done = 0

    for cell in cells:
        obj = os.path.join(SRC_STRUCT, cell + ".obj")
        pkg = "%s/%s" % (DEST_STRUCT, cell)
        if not os.path.exists(obj):
            # c0_-21 is foliage-only: the split produced no structural geometry for it, so there
            # is nothing to import here and its foliage is handled in the loop below
            report["cells"][cell] = {"foliage_only": True}
            continue
        if empty_source(obj):
            deleted = drop(pkg)
            report["cells"][cell] = {"empty_source": True, "deleted_first": deleted}
            log("cell %s -> empty_source" % cell)
            continue
        deleted = drop(pkg)
        import_obj(obj, DEST_STRUCT, cell)
        sm = unreal.EditorAssetLibrary.load_asset(pkg)
        if sm is None:
            report["cells"][cell] = {"error": "import_failed"}
            continue
        body = sm.get_editor_property("body_setup")
        if body is not None:
            body.set_editor_property("collision_trace_flag", FLAG)
            unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)
        if cell in NON_CELL:
            slot_err = "skipped:non_cell"
        elif cell in sm_map:
            slot_err = apply_slots(sm, sm_map[cell])
        else:
            slot_err = "no_slotmap"
        # read back from a freshly loaded asset
        sm = unreal.EditorAssetLibrary.load_asset(pkg)
        slots, nonnull = slots_state(sm)
        want = sm_map.get(cell, {})
        obj_mtls = obj_material_names(obj)
        names = [str(e.get_editor_property("imported_material_slot_name"))
                 for e in sm.get_editor_property("static_materials")]
        report["cells"][cell] = {
            "deleted_first": deleted,
            "lods": int(sm.get_num_lods()),
            "collision": collision_state(sm),
            "slots": slots,
            "obj_mtls": len(obj_mtls),
            "slot_names_match_obj": sorted(names) == sorted(obj_mtls),
            "unbound": [n for n, e in zip(names, sm.get_editor_property("static_materials"))
                        if e.get_editor_property("material_interface") is None],
            "expected_null": sorted({(s0.get("imported") or s0.get("slot"))
                                     for s0 in (want.get("slots") or []) if not s0.get("mi")}),
            "nonnull": nonnull,
            "want_slots": want.get("want_slots"),
            "want_nonnull": want.get("want_nonnull"),
            "slot_err": slot_err,
        }
        done += 1
        if done % 25 == 0:
            log("progress %d/%d last=%s" % (done, len(cells), cell))
        elif done <= 3:
            log("cell %s -> %s" % (cell, report["cells"][cell]))

    # paint: one mesh, no collision
    pkg = "%s/C1_NoCollision_Paint" % DEST_PAINT
    drop(pkg)
    import_obj(SRC_PAINT, DEST_PAINT, "C1_NoCollision_Paint")
    sm = unreal.EditorAssetLibrary.load_asset(pkg)
    if sm is None:
        report["paint"] = {"error": "import_failed"}
    else:
        clear_err = clear_simple_collision(sm)
        slot_err = apply_slots(sm, {"slots": []})
        sm = unreal.EditorAssetLibrary.load_asset(pkg)
        slots, nonnull = slots_state(sm)
        report["paint"] = {"lods": int(sm.get_num_lods()), "collision": collision_state(sm),
                           "slots": slots, "bound": nonnull, "clear_err": clear_err,
                           "slot_err": slot_err}
        log("paint -> %s" % report["paint"])

    # foliage for the same cells, only where the cell has foliage
    for cell in cells:
        obj = os.path.join(SRC_FOLIAGE, cell + ".obj")
        if not os.path.exists(obj):
            report["foliage"][cell] = {"skipped": "no foliage"}
            continue
        pkg = "%s/%s" % (DEST_FOLIAGE, cell)
        if empty_source(obj):
            drop(pkg)
            report["foliage"][cell] = {"skipped": "empty_source"}
            continue
        drop(pkg)
        import_obj(obj, DEST_FOLIAGE, cell)
        sm = unreal.EditorAssetLibrary.load_asset(pkg)
        if sm is None:
            report["foliage"][cell] = {"error": "import_failed"}
        else:
            clear_err = clear_simple_collision(sm)
            slot_err = apply_slots(sm, {"slots": []})
            sm = unreal.EditorAssetLibrary.load_asset(pkg)
            slots, nonnull = slots_state(sm)
            report["foliage"][cell] = {"lods": int(sm.get_num_lods()),
                                       "collision": collision_state(sm),
                                       "slots": slots, "bound": nonnull,
                                       "clear_err": clear_err, "slot_err": slot_err}
        log("foliage %s -> %s" % (cell, report["foliage"][cell]))

    struct_ok = all(
        isinstance(v, dict) and (v.get("foliage_only") or v.get("empty_source") or
                                 (v.get("lods") == 1
        and v.get("slot_names_match_obj") is True
        and v.get("slot_err") in (None, "skipped:non_cell")
        and set(v.get("unbound") or []) <= set(v.get("expected_null") or [])
        and v.get("collision", {}).get("flag") == str(FLAG)))
        for v in report["cells"].values())
    def nc(r):
        return (isinstance(r, dict) and "lods" in r and r.get("lods") == 1
                and r.get("collision", {}).get("flag") != str(FLAG)
                and r.get("collision", {}).get("simple_total") == 0
                and r.get("clear_err") is None and r.get("slot_err") is None
                and r.get("bound") == r.get("slots"))

    foliage_checked = [v for v in report["foliage"].values() if isinstance(v, dict) and "lods" in v]
    foliage_ok = all(nc(v) for v in foliage_checked) and not any(
        isinstance(v, dict) and "error" in v for v in report["foliage"].values())
    report["ok"] = bool(struct_ok and nc(report["paint"]) and foliage_ok)
    json.dump(report, open(REPORT, "w"), indent=1)
    log("A4_GATE_%s cells=%d paint_slots=%d foliage=%d"
        % ("OK" if report["ok"] else "FAIL", len(report["cells"]),
           report["paint"].get("slots"), len([v for v in report["foliage"].values()
                                              if isinstance(v, dict) and "lods" in v])))


main()
