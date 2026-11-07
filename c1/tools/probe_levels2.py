"""Probe 2: exact Python signatures for the sublevel API, with C1Full actually loaded.

The first probe ran against /Temp/Untitled_0 because nothing had been loaded, so its level
list was meaningless. Load the persistent map first, then ask for real signatures -- a wrong
argument order here creates a stray streaming level or worse, silently does nothing.
"""
import json

import unreal

OUT = "D:/C1FullMirror/Scripts/probe_levels2.json"
PERSISTENT = "/Game/Mods/C1Full/Maps/C1Full"


def sig(fn):
    out = {}
    for attr in ("__doc__",):
        try:
            out[attr] = str(getattr(fn, attr))[:400]
        except Exception as e:
            out[attr] = "ERR " + str(e)[:80]
    return out


def main():
    r = {}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.load_level(PERSISTENT)

    world = unreal.EditorLevelLibrary.get_editor_world()
    r["world"] = world.get_path_name() if world else None
    r["current_level"] = str(les.get_current_level().get_path_name()) if les.get_current_level() else None

    levels = unreal.EditorLevelUtils.get_levels(world)
    r["level_count"] = len(levels)
    info = []
    for lv in levels:
        entry = {"class": lv.get_class().get_name()}
        for prop in ("b_always_loaded", "world_asset", "b_should_be_loaded", "b_should_be_visible", "level_colors"):
            try:
                v = lv.get_editor_property(prop)
                entry[prop] = v.get_path_name() if hasattr(v, "get_path_name") else str(v)
            except Exception:
                pass
        info.append(entry)
    r["levels"] = info

    r["sig_create_new_streaming_level"] = sig(unreal.EditorLevelUtils.create_new_streaming_level)
    r["sig_add_level_to_world"] = sig(unreal.EditorLevelUtils.add_level_to_world)
    r["sig_make_level_current"] = sig(unreal.EditorLevelUtils.make_level_current)
    r["sig_move_actors_to_level"] = sig(unreal.EditorLevelUtils.move_actors_to_level)
    r["sig_new_level"] = sig(les.new_level)
    r["sig_load_level"] = sig(les.load_level)
    r["sig_save_current_level"] = sig(les.save_current_level)

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    r["actors_in_world"] = len(eas.get_all_level_actors())

    with open(OUT, "w") as f:
        json.dump(r, f, indent=1)


main()
