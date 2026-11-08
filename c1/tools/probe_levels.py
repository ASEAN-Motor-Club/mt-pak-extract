"""Probe the level/sublevel API surface before creating C1Full_Lights.

Results go to a JSON file: this editor build's python log lines are NOT reliably
captured in the .log (C1PROBE lines vanish), and a probe that reports nothing is
worse than no probe. Same reason author_corridor_lights.py writes author_corridor.json.
"""
import json
import os

import unreal

OUT = "D:/C1FullMirror/Scripts/probe_levels.json"
PERSISTENT = "/Game/Mods/C1Full/Maps/C1Full"


def names(obj, needles=None):
    out = []
    for n in dir(obj):
        if n.startswith("_"):
            continue
        if needles is None or any(k in n.lower() for k in needles):
            out.append(n)
    return sorted(out)


def main():
    r = {"persistent": PERSISTENT}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    r["les_level_api"] = names(les, ["level", "sublevel", "stream"])
    r["level_utils_api"] = names(unreal.EditorLevelUtils)
    r["library_api"] = names(unreal.EditorLevelLibrary, ["level", "map", "world"])
    r["streaming_classes"] = sorted(c for c in dir(unreal) if "LevelStreaming" in c)
    r["actor_classes"] = sorted(c for c in dir(unreal) if c in ("SpotLight", "PointLight", "Light", "RectLight"))

    world = unreal.EditorLevelLibrary.get_editor_world()
    r["world"] = world.get_path_name() if world else None

    try:
        levels = unreal.EditorLevelUtils.get_levels(world)
        r["level_count"] = len(levels)
        info = []
        for lv in levels:
            entry = {}
            try:
                entry["pkg"] = lv.get_editor_property("world_asset").get_path_name()
            except Exception as e:
                entry["pkg_err"] = str(e)[:80]
            for prop in ("b_always_loaded", "streaming_volume", "b_should_be_loaded", "b_should_be_visible"):
                try:
                    entry[prop] = str(lv.get_editor_property(prop))
                except Exception:
                    pass
            info.append(entry)
        r["levels"] = info
    except Exception as e:
        r["levels_err"] = str(e)[:200]

    r["editor_level_utils_has_create"] = [n for n in r["level_utils_api"] if "create" in n.lower() or "add" in n.lower()]
    r["lights_exist"] = unreal.EditorAssetLibrary.does_asset_exist("/Game/Mods/C1Full/Maps/C1Full_Lights")
    r["roads_exists"] = unreal.EditorAssetLibrary.does_asset_exist("/Game/Mods/C1Full/Maps/C1Full_Roads")
    try:
        r["actors_in_world"] = len(eas.get_all_level_actors())
    except Exception as e:
        r["actors_err"] = str(e)[:120]

    with open(OUT, "w") as f:
        json.dump(r, f, indent=1)


main()
