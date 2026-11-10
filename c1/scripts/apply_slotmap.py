"""Rebuild each cell's StaticMaterials array from slotmap.json.

Runs in the editor AFTER import_local.py has delete-imported the cells: the delete takes
the slot array with it, and the OBJ importer can only offer what the OBJ's `usemtl` lines
say. This restores the shipped array exactly — order, names, and the EMPTY slots that
carry no material — then re-reads it and refuses to pass unless what is in the asset
matches what the dump said.

Order and gaps are load-bearing: dropping an empty slot shifts every later slot, and the
mesh then draws the wrong material on its faces while the non-null count still matches.

Usage: run inside the editor (Scripts/apply_slotmap.py); reads D:\\slotmap.json.
"""
import json

import unreal

SLOTMAP = r"D:\slotmap.json"
DEST = "/Game/Mods/C1Full/Meshes"
PROGRESS = r"D:\apply_slotmap.log"


def log(m):
    unreal.log("SLOTMAP " + str(m))
    with open(PROGRESS, "a") as f:
        f.write(str(m) + "\n")


def apply_cell(cell, rec):
    path = "%s/%s" % (DEST, cell)
    sm = unreal.EditorAssetLibrary.load_asset(path)
    if sm is None:
        return "load"
    arr = []
    for s in rec["slots"]:
        entry = unreal.StaticMaterial()
        mi = None
        if s["mi"]:
            mi = unreal.EditorAssetLibrary.load_asset(s["mi"])
            if mi is None:
                return "mi_missing:%s" % s["mi"]
        entry.set_editor_property("material_interface", mi)
        entry.set_editor_property("material_slot_name", s["slot"] or "None")
        # ImportedMaterialSlotName is read-only on UE 5.5 StaticMaterial; the import already wrote
        # it, and raising here aborts the whole run on the first cell. Write it only if allowed.
        try:
            entry.set_editor_property("imported_material_slot_name", s["imported"] or "None")
        except Exception:
            pass
        arr.append(entry)
    sm.set_editor_property("static_materials", arr)
    unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)
    return None


def verify_cell(cell, rec):
    path = "%s/%s" % (DEST, cell)
    sm = unreal.EditorAssetLibrary.load_asset(path)
    if sm is None:
        return ["load"]
    got = sm.get_editor_property("static_materials")
    errs = []
    if len(got) != rec["want_slots"]:
        errs.append("slots %d != %d" % (len(got), rec["want_slots"]))
    nonnull = 0
    for i, g in enumerate(got):
        want = rec["slots"][i] if i < len(rec["slots"]) else None
        mi = g.get_editor_property("material_interface")
        if mi is not None:
            nonnull += 1
        if want is None:
            continue
        gs = g.get_editor_property("material_slot_name")
        ws = want["slot"] or "None"
        if str(gs) != ws:
            errs.append("slot[%d] name %r != %r" % (i, str(gs), ws))
        # get_path_name() returns the full object path ("/Game/…/MI_X.MI_X"); slotmap stores the
        # package path. Strip the object suffix before comparing or every cell "fails" on cosmetics.
        gm = mi.get_path_name() if mi is not None else None
        if gm is not None:
            gm = gm.split(".")[0]
        wm = want["mi"]
        if (gm or None) != (wm or None):
            errs.append("slot[%d] mi %r != %r" % (i, gm, wm))
    if nonnull != rec["want_nonnull"]:
        errs.append("nonnull %d != %d" % (nonnull, rec["want_nonnull"]))
    return errs


def main():
    open(PROGRESS, "w").close()
    data = json.load(open(SLOTMAP))
    log("cells=%d" % len(data))
    applied, failed = 0, []
    for cell, rec in data.items():
        err = apply_cell(cell, rec)
        if err:
            failed.append([cell, err])
            continue
        errs = verify_cell(cell, rec)
        if errs:
            failed.append([cell, errs[:3]])
            continue
        applied += 1
        if applied % 25 == 0:
            log("applied %d" % applied)
    log("APPLY_SLOTMAP_%s applied=%d failed=%d"
        % ("OK" if not failed and applied == len(data) else "FAIL", applied, len(failed)))
    for item in failed[:10]:
        log("fail: %s" % (item,))


main()
