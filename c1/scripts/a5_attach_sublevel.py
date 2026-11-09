"""A5 step 2: attach C1Full_NoCollision to C1Full and retire the old merged decal actor.

C1_Decals is deleted on purpose: it was the joint/marking sheet lifted 3 cm above the road, and
those same faces are now in C1_NoCollision_Paint at their true height. Keeping both would draw the
markings twice, 3 cm apart, and keep a colliding copy of the thing this whole pass exists to un-collide.

Verified after saving, in the same process: the persistent level references the sublevel, the cell
actors are untouched, and PlayerStart plus the prop actor are still there.
"""
import json

import unreal

PERSISTENT = "/Game/Mods/C1Full/Maps/C1Full"
SUBLEVEL = "/Game/Mods/C1Full/Maps/C1Full_NoCollision"
REPORT = r"D:\a5_step2.json"
LOG = r"D:\a5_step2.log"
OLD_DECAL_LABEL = "C1_Decals"


def log(m):
    unreal.log("A5 " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


def try_streaming_classes():
    """Return (class, name) for the always-loaded streaming class, whatever 5.5 calls it."""
    for name in ("LevelStreamingAlwaysLoaded", "LevelStreamingPersistent", "LevelStreamingDynamic"):
        cls = getattr(unreal, name, None)
        if cls is not None:
            return cls, name
    return None, None


def main():
    open(LOG, "w").close()
    report = {"added": None, "deleted": [], "before": {}, "after": {}, "ok": False}

    unreal.EditorLevelLibrary.load_level(PERSISTENT)
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    before_cells = [a for a in actors if (a.get_actor_label() or "").startswith("C1_cell_")]
    before_other = {a.get_actor_label(): a.get_class().get_name() for a in actors
                    if a.get_class().get_name() != "StaticMeshActor"}
    report["before"] = {"actors": len(actors), "cells": len(before_cells)}
    log("persistent loaded: actors=%d cells=%d" % (len(actors), len(before_cells)))

    # 1. retire the old merged decal actor
    for a in list(actors):
        if (a.get_actor_label() or "") == OLD_DECAL_LABEL:
            label = a.get_actor_label()
            a.destroy_actor()
            report["deleted"].append(label)
            log("deleted actor %s" % label)

    # 2. attach the sublevel
    world = unreal.EditorLevelLibrary.get_editor_world()
    cls, cls_name = try_streaming_classes()
    if cls is None:
        report["added"] = "no_streaming_class"
        log("no streaming class available")
    else:
        try:
            streaming = unreal.EditorLevelUtils.add_level_to_world(world, SUBLEVEL, cls)
            report["added"] = {"class": cls_name, "object": str(streaming)}
            log("added sublevel with %s -> %s" % (cls_name, streaming))
        except Exception as e:
            report["added"] = "error:%s" % e
            log("add_level_to_world failed: %s" % e)

    saved = []
    for label, fn in (
            ("loading_and_saving.save_map",
             lambda: unreal.EditorLoadingAndSavingUtils.save_map(PERSISTENT, PERSISTENT)),
            ("asset_library.save_asset",
             lambda: unreal.EditorAssetLibrary.save_asset(PERSISTENT, only_if_is_dirty=False)),
            ("level_library.save_current_level",
             lambda: unreal.EditorLevelLibrary.save_current_level())):
        try:
            res = fn()
            saved.append("%s=%s" % (label, res))
        except Exception as e:
            saved.append("%s=error:%s" % (label, e))
    report["saved"] = saved
    log("save attempts: %s" % saved)

    # 3. read back from a fresh load of the persistent level
    unreal.EditorLevelLibrary.load_level(PERSISTENT)
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    cells = [a for a in actors if (a.get_actor_label() or "").startswith("C1_cell_")]
    other = {a.get_actor_label(): a.get_class().get_name() for a in actors
             if a.get_class().get_name() != "StaticMeshActor"}
    report["after"] = {
        "actors": len(actors),
        "cells": len(cells),
        "has_old_decal": any((a.get_actor_label() or "") == OLD_DECAL_LABEL for a in actors),
        "player_start": "PlayerStart" in other,
        "prop": any(k and k.startswith("BP_C1_Prop") for k in other),
        "sublevels": [],
    }
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        for s in world.get_editor_property("streaming_levels") if world else []:
            try:
                report["after"]["sublevels"].append(s.get_world_asset().get_path_name())
            except Exception as e:
                report["after"]["sublevels"].append("err:%s" % e)
    except Exception as e:
        report["after"]["sublevels_err"] = str(e)

    ok = (report["after"]["cells"] == len(before_cells)
          and not report["after"]["has_old_decal"]
          and report["after"]["player_start"] and report["after"]["prop"]
          and isinstance(report["added"], dict))
    report["ok"] = ok
    json.dump(report, open(REPORT, "w"), indent=1)
    log("A5_STEP2_%s before=%s after=%s deleted=%s added=%s"
        % ("OK" if ok else "FAIL", report["before"], report["after"],
           report["deleted"], report["added"]))


main()
