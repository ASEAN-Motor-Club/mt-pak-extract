"""Set the C1Full map's world start time by adding MT's own AMTTimeOfDayConfig actor.

Why not the SunSky: the parent map serialises NOTHING about time. `TimeOfDay` appears zero times
in C1Full.umap, and BP_C1_Sky's ChildActorComponent carries only `ChildActorClass= MTSunSky_C` —
no SolarTime/Latitude overrides. AMTSunSky recomputes from the world clock every frame
(UpdateLighting + ReceiveTimeOfDayChanged), so editing the sky actor's properties in the map is a
no-op: there is nothing stored to edit.

AMTTimeOfDayConfig is a plain native actor (safe to place, unlike game BP instances) whose
`TimeOfDayConfig` struct is {Speed, Start}. Start is hours (0-24); 22.0 = 22:00.

Reports the pre-existing state so we can see whether the game already spawns one.
"""
import json
import traceback

import unreal

LEVEL = "/Game/Mods/C1Full/Maps/C1Full"
REPORT = "D:/C1FullMirror/Scripts/author_timeofday.json"
START_HOUR = 22.0
SPEED = 1.0

out = {"steps": [], "pre": {}, "post": {}, "errors": []}


def log(m):
    unreal.log("[C1TIME] " + str(m))


def step(name, fn):
    try:
        r = fn()
        out["steps"].append({"step": name, "ok": True, "result": str(r)})
        log(name + " -> " + str(r))
        return r
    except Exception:
        out["steps"].append({"step": name, "ok": False, "error": traceback.format_exc()})
        log(name + " FAILED")
        return None


les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

les.load_level(LEVEL)
log("loaded " + LEVEL)

cls = getattr(unreal, "MTTimeOfDayConfig", None)
out["class_available"] = str(cls)


def report_existing():
    found = []
    for actor in eas.get_all_level_actors():
        try:
            n = actor.get_class().get_name()
        except Exception:
            continue
        if "TimeOfDay" in n:
            entry = {"class": n, "label": str(actor.get_actor_label())}
            try:
                cfg = actor.get_editor_property("TimeOfDayConfig")
                entry["TimeOfDayConfig"] = str(cfg)
            except Exception as e:
                entry["TimeOfDayConfig"] = "unreadable: %r" % (e,)
            found.append(entry)
    out["pre"]["actors"] = found
    return "existing=%d" % len(found)


step("report existing time config actors", report_existing)


def make_config():
    if cls is None:
        raise RuntimeError("unreal.MTTimeOfDayConfig not bound")
    # idempotent: drop ours/any previous one before spawning
    removed = 0
    for actor in eas.get_all_level_actors():
        if actor.get_class().get_name().startswith("MTTimeOfDayConfig"):
            eas.destroy_actor(actor)
            removed += 1
    actor = eas.spawn_actor_from_class(cls, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0.0, 0.0, 0.0))
    if actor is None:
        raise RuntimeError("spawn returned None")
    actor.set_actor_label("C1TimeOfDay")
    cfg = actor.get_editor_property("TimeOfDayConfig")
    # the struct is {Speed, Start}; set through the struct and write it back
    try:
        cfg.set_editor_property("Speed", float(SPEED))
        cfg.set_editor_property("Start", float(START_HOUR))
        actor.set_editor_property("TimeOfDayConfig", cfg)
    except Exception:
        cfg = unreal.MTTimeOfDayConfigParams()
        cfg.set_editor_property("Speed", float(SPEED))
        cfg.set_editor_property("Start", float(START_HOUR))
        actor.set_editor_property("TimeOfDayConfig", cfg)
    got = actor.get_editor_property("TimeOfDayConfig")
    out["post"] = {"removed": removed, "TimeOfDayConfig": str(got),
                   "start": str(got.get_editor_property("Start")),
                   "speed": str(got.get_editor_property("Speed"))}
    return "spawned start=%s speed=%s removed=%d" % (
        out["post"]["start"], out["post"]["speed"], removed)


step("spawn MTTimeOfDayConfig with Start=22", make_config)
step("save level", lambda: les.save_current_level())

bad = [s for s in out["steps"] if not s["ok"]]
out["summary"] = "TIMEOFDAY ok=%d failed=%d" % (len(out["steps"]) - len(bad), len(bad))
with open(REPORT, "w") as f:
    json.dump(out, f, indent=1)
print(out["summary"])
