"""Restore material interfaces by SLOT NAME, not by array position.

apply_slotmap.py rewrites StaticMaterials wholesale from the original dump. That
is only valid when the mesh's section->slot indices are unchanged. The no-rope
re-import dropped one material, so every section after it shifted by one and the
position-based restore painted wrong textures on the cells.

The importer already writes each slot's name from the OBJ `usemtl`, and section
indices point at that NEW array. So the correct repair is to keep the new array
order and only fill in the material each name refers to, using the original
slotmap as the name->instance lookup.
"""
import json

import unreal

SLOTMAP = r"D:\slotmap.json"
DEST = "/Game/Mods/C1Full/Meshes"
LOG = r"D:\remap_slots.log"


def log(m):
    unreal.log("REMAP " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


def main():
    open(LOG, "w").close()
    slotmap = json.load(open(SLOTMAP))
    done = 0
    skipped = 0
    problems = []

    for cell, rec in slotmap.items():
        path = "%s/%s" % (DEST, cell)
        sm = unreal.EditorAssetLibrary.load_asset(path)
        if sm is None:
            skipped += 1
            continue

        # name -> material instance path, from the original shipped asset
        by_name = {}
        for s in rec.get("slots", []):
            for key in (s.get("imported"), s.get("slot")):
                if key and key != "None":
                    by_name[key] = s.get("mi")

        arr = sm.get_editor_property("static_materials")
        new_arr = []
        changed = False
        missing = set()
        for entry in arr:
            name = str(entry.get_editor_property("material_slot_name"))
            mi_path = None
            if name in by_name:
                mi_path = by_name[name]
            else:
                candidate = "/Game/Mods/C1Full/Materials/MI_C1_" + name
                if unreal.EditorAssetLibrary.does_asset_exist(candidate):
                    mi_path = candidate
                else:
                    missing.add(name)

            # Iterating the array yields struct COPIES, so mutating `entry`
            # writes nothing back (this is why the first remap left every slot
            # on WorldGridMaterial). Build fresh StaticMaterial entries instead,
            # in the importer's own order.
            ne = unreal.StaticMaterial()
            ne.set_editor_property("material_slot_name", name)
            try:
                ne.set_editor_property("imported_material_slot_name", name)
            except Exception:
                pass
            mi = unreal.EditorAssetLibrary.load_asset(mi_path) if mi_path else None
            ne.set_editor_property("material_interface", mi)
            new_arr.append(ne)
            changed = True

        if missing:
            problems.append((cell, sorted(missing)[:3]))
        if changed:
            sm.set_editor_property("static_materials", new_arr)
            unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)
            done += 1

    log("REMAP_DONE cells=%d skipped=%d unmatched_names=%d" % (done, skipped, len(problems)))
    for cell, names in problems[:6]:
        log("unmatched %s: %s" % (cell, names))


main()
