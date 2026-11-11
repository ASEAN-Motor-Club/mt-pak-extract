"""Bind materials onto the NoCollision assets (paint + foliage).

Why this exists: the split moved road paint and foliage into their own meshes and
import_split.py then called

    apply_slots(sm, {"slots": []})

for both, i.e. it deliberately bound NOTHING. apply_slotmap.py only walks the 554
cell names in slotmap.json and only touches /Game/Mods/C1Full/Meshes, so it never
saw these either. Result: every NC asset ships with correctly named slots whose
MaterialInterface is WorldGridMaterial (import index -5), and the markings and
foliage are invisible in game.

The slot names on the imported asset are the OBJ `usemtl` names, which are exactly
what MI_C1_<name> is built from, so bind by name rather than by a shipped dump:

    1. exact        MI_C1_<slot>
    2. numeric      MI_C1_<slot>_<n>  (only when exactly one n exists)
    3. give up      leave the slot unbound and report the name

Unbound names are reported, never silently mapped to a neighbour: a wrong kanji
decal is worse than a missing one.

Usage: run inside the editor (paint + foliage only, no cells touched).
"""
import json

import unreal

PAINT = "/Game/Mods/C1Full/Meshes/C1_NoCollision_Paint"
FOLIAGE_DIR = "/Game/Mods/C1Full/Meshes_NoCollision"
MAT_DIR = "/Game/Mods/C1Full/Materials"
REPORT = r"D:\apply_nc_materials.json"
LOG = r"D:\apply_nc_materials.log"


def log(m):
    unreal.log("NCMAT " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


def build_index():
    """basename (without MI_C1_ prefix) -> full package path."""
    idx = {}
    for path in unreal.EditorAssetLibrary.list_assets(MAT_DIR, recursive=False,
                                                      include_folder=False):
        p = str(path).split(".")[0]
        base = p.rsplit("/", 1)[-1]
        if base.startswith("MI_C1_"):
            idx.setdefault(base[len("MI_C1_"):], p)
    log("material index entries=%d" % len(idx))
    return idx


def resolve(slot, idx):
    if not slot or slot == "None":
        return None
    if slot in idx:
        return idx[slot]
    # MI_C1_<slot>_<n>: accept only an unambiguous single match
    hits = [v for k, v in idx.items() if k.startswith(slot + "_") and
            k[len(slot) + 1:].isdigit()]
    if len(hits) == 1:
        return hits[0]
    return None


def bind(path, idx):
    sm = unreal.EditorAssetLibrary.load_asset(path)
    if sm is None:
        return {"error": "load"}
    current = sm.get_editor_property("static_materials")
    arr = []
    bound, unbound = 0, []
    for entry in current:
        name = str(entry.get_editor_property("material_slot_name"))
        mi_path = resolve(name, idx)
        mi = unreal.EditorAssetLibrary.load_asset(mi_path) if mi_path else None
        new = unreal.StaticMaterial()
        new.set_editor_property("material_interface", mi)
        new.set_editor_property("material_slot_name", name)
        try:
            new.set_editor_property(
                "imported_material_slot_name",
                str(entry.get_editor_property("imported_material_slot_name")))
        except Exception:
            pass
        if mi is not None:
            bound += 1
        else:
            unbound.append(name)
        arr.append(new)
    sm.set_editor_property("static_materials", arr)
    unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)

    # re-read: the write is what can silently not stick
    sm = unreal.EditorAssetLibrary.load_asset(path)
    check = [e.get_editor_property("material_interface")
             for e in sm.get_editor_property("static_materials")]
    return {"slots": len(check), "bound": sum(1 for m in check if m is not None),
            "unbound_names": unbound}


def main():
    open(LOG, "w").close()
    idx = build_index()
    report = {"paint": None, "foliage": {"assets": 0, "ok": 0, "failed": []}}

    report["paint"] = bind(PAINT, idx)
    log("paint -> %s" % (report["paint"],))

    for path in unreal.EditorAssetLibrary.list_assets(FOLIAGE_DIR, recursive=False,
                                                     include_folder=False):
        p = str(path).split(".")[0]
        r = bind(p, idx)
        report["foliage"]["assets"] += 1
        if r.get("error") or r.get("slots") != r.get("bound") + len(r.get("unbound_names", [])):
            report["foliage"]["failed"].append([p, r])
        else:
            report["foliage"]["ok"] += 1
        if report["foliage"]["assets"] % 40 == 0:
            log("foliage %d" % report["foliage"]["assets"])

    total_unbound = sorted({n for n in (report["paint"] or {}).get("unbound_names", [])})
    report["unbound_material_names"] = total_unbound
    report["summary"] = "paint_bound=%d/%d foliage=%d failed=%d unbound_names=%d" % (
        (report["paint"] or {}).get("bound", 0), (report["paint"] or {}).get("slots", 0),
        report["foliage"]["ok"], len(report["foliage"]["failed"]), len(total_unbound))
    json.dump(report, open(REPORT, "w"), indent=1)
    log("APPLY_NC_MATERIALS_DONE " + report["summary"])
    for n in total_unbound[:20]:
        log("  unbound %s" % n)


main()
