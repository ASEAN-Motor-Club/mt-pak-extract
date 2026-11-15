"""Create placeholder MaterialInstanceConstants for every material slotmap.json names.

apply_slotmap.py refuses a cell when a referenced instance is absent, and this
project only carries the emissive subset — the rest of the C1 material set was
built elsewhere. The shipped pak contains ONLY the meshes, so the instance
contents here never reach the game: at runtime /Game/Mods/C1Full/Materials/MI_C1_*
resolves from the already-installed material paks. All the editor needs is an
asset at the right path so the slot reference can be written.
"""
import json

import unreal

SLOTMAP = r"D:\slotmap.json"
PARENT_CANDIDATES = [
    "/Game/Env/Materials/Color/MI_MatteBlue_01_E",
    "/Game/Mods/C1/Materials/M_C1_Emissive",
]
LOG = r"D:\material_dummies.log"


def log(m):
    unreal.log("DUMMY " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


def main():
    open(LOG, "w").close()
    slotmap = json.load(open(SLOTMAP))
    paths = set()
    for rec in slotmap.values():
        for s in rec.get("slots", []):
            mi = s.get("mi")
            if mi:
                paths.add(mi)

    parent = None
    for cand in PARENT_CANDIDATES:
        parent = unreal.EditorAssetLibrary.load_asset(cand)
        if parent is not None:
            break
    if parent is None:
        log("NO_PARENT")
        return

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    created = 0
    skipped = 0
    failed = []
    for path in sorted(paths):
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            skipped += 1
            continue
        package, _, name = path.rpartition("/")
        asset = tools.create_asset(name, package, unreal.MaterialInstanceConstant,
                                   unreal.MaterialInstanceConstantFactoryNew())
        if asset is None:
            failed.append(path)
            continue
        asset.set_editor_property("parent", parent)
        unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)
        created += 1

    log("DUMMY_DONE created=%d already=%d failed=%d" % (created, skipped, len(failed)))
    for p in failed[:5]:
        log("failed: " + p)


main()
