"""Port EVERY light in the source map into its own always-loaded sublevel.

Why a sublevel: the lights and the nav bake both live in C1Full_Roads, so each cook of one
feature shipped its own copy of that sublevel and evicted the other (pak mount is
last-alphabetical-wins, one pak per asset). Moving the lights to C1Full_Lights makes the two
features claim different assets, so neither can shadow the other again.

Always-loaded, NOT distance-streamed: corridor lights have to be present continuously at night.
Streaming them would pop them in and out while driving. (BeamNG's own 384 m partition manager is
a runtime toggle inside an always-loaded level, which is a different mechanism -- and a separate,
still-open perf question.)

Units are identical to author_corridor_lights.py (c1/docs/MAP_PORTING_GUIDE.md section 7,
c1/GOTCHAS.md section 32): the mapping is the port contract, not a per-run choice.
Report goes to JSON -- this editor build's python print/log lines are not captured in the .log.
"""
import collections
import json
import os
import traceback

import unreal

PERSISTENT = "/Game/Mods/C1Full/Maps/C1Full"
SUBLEVEL = "/Game/Mods/C1Full/Maps/C1Full_Lights"
ROWS = os.environ.get("C1_MAP_ROWS", r"D:/C1FullMirror/Scripts/map_rows.json")
REPORT = os.environ.get("C1_MAP_REPORT", r"D:/C1FullMirror/Scripts/author_all_lights.json")
PREFIXES = ("C1Port_", "C1MapLight_", "C1Lamp_", "C1NativeLight_")

CD_PER_BRIGHTNESS = 5000.0     # BeamNG spot: 1 brightness ~= 5,000 cd
DEFAULT_BRIGHTNESS = 1.0       # source class default when the record declares none
POINT_LM_DEFAULT = 800.0       # documented small-point-light default (400-1,000 lm @ 5-12 m)

rows = json.load(open(ROWS))
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

out = {"placed": 0, "failed": 0, "deleted": 0, "errors": [], "by_group": {},
       "intensity_hist": {}, "radius_hist": {}, "sublevel": SUBLEVEL}


def lin_to_srgb(v):
    v = max(0.0, min(1.0, float(v)))
    return int(round((12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055) * 255))


def main():
    les.load_level(PERSISTENT)
    world = unreal.EditorLevelLibrary.get_editor_world()
    out["world"] = world.get_path_name()
    out["actors_before"] = len(eas.get_all_level_actors())

    # (Re)attach the sublevel. add_level_to_world is a no-op if it is already in the world, so
    # this is safe to re-run; create_new_streaming_level is only for the first time.
    if unreal.EditorAssetLibrary.does_asset_exist(SUBLEVEL):
        sl = unreal.EditorLevelUtils.add_level_to_world(world, SUBLEVEL, unreal.LevelStreamingAlwaysLoaded)
        out["sublevel_added"] = "existing"
    else:
        sl = unreal.EditorLevelUtils.create_new_streaming_level(
            unreal.LevelStreamingAlwaysLoaded, SUBLEVEL, False)
        out["sublevel_added"] = "created"
    out["streaming_level"] = sl.get_name() if sl else None
    if sl is None:
        raise RuntimeError("could not attach %s to %s" % (SUBLEVEL, PERSISTENT))

    try:
        out["always_loaded"] = str(sl.get_editor_property("b_always_loaded"))
    except Exception as e:
        out["always_loaded_err"] = str(e)[:100]

    unreal.EditorLevelUtils.make_level_current(sl)
    cur = les.get_current_level()
    out["current_level"] = cur.get_path_name() if cur else None

    # Idempotency: clear previously spawned port lights before respawning.
    for a in eas.get_all_level_actors():
        try:
            if a.get_actor_label().startswith(PREFIXES):
                eas.destroy_actor(a)
                out["deleted"] += 1
        except Exception:
            pass

    for r in rows:
        try:
            x, y, z = r["ue_cm"]
            is_point = bool(r.get("sign_default"))
            cls = unreal.PointLight if is_point else unreal.SpotLight
            actor = eas.spawn_actor_from_class(cls, unreal.Vector(x, y, z),
                                               unreal.Rotator(roll=0.0, pitch=-90.0, yaw=0.0))
            actor.set_actor_label("C1Port_" + r["name"])

            b = r.get("brightness")
            b = float(b) if isinstance(b, (int, float)) and b > 0 else DEFAULT_BRIGHTNESS
            if is_point:
                inten = POINT_LM_DEFAULT
                units = unreal.LightUnits.LUMENS
            else:
                inten = b * CD_PER_BRIGHTNESS
                units = unreal.LightUnits.CANDELAS

            radius = float(r["src_range_m"]) * 100.0        # metres -> cm
            inner = float(r.get("inner_deg") or 25.0)
            outer = float(r.get("outer_deg") or 170.0)
            if inner >= outer:
                inner = outer * 0.5

            src = r.get("src_color") or [1.0, 0.94, 0.86, 1.0]
            color = unreal.Color(r=lin_to_srgb(src[0]), g=lin_to_srgb(src[1]),
                                 b=lin_to_srgb(src[2]), a=255)

            c = actor.light_component
            c.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
            c.set_editor_property("intensity_units", units)
            c.set_editor_property("intensity", inten)
            c.set_editor_property("attenuation_radius", radius)
            # Shadows off: 10,474 shadow-casting dynamic lights is not affordable, and the
            # source lamps do not cast directional shadows either (shadow_softness is a texel
            # blur, not a shadow map).
            c.set_editor_property("cast_shadows", False)
            c.set_editor_property("light_color", color)
            if not is_point:
                c.set_editor_property("inner_cone_angle", inner)
                c.set_editor_property("outer_cone_angle", outer)

            out["placed"] += 1
            g = r.get("group", "?")
            out["by_group"][g] = out["by_group"].get(g, 0) + 1
            out["intensity_hist"]["%d" % inten] = out["intensity_hist"].get("%d" % inten, 0) + 1
            out["radius_hist"]["%d" % radius] = out["radius_hist"].get("%d" % radius, 0) + 1
        except Exception:
            out["failed"] += 1
            if len(out["errors"]) < 5:
                out["errors"].append(traceback.format_exc().splitlines()[-1])

    out["actors_after"] = len(eas.get_all_level_actors())
    out["save_sublevel"] = bool(les.save_current_level())
    # The persistent level has to be saved too: it is what stores the reference to this sublevel.
    try:
        out["save_dirty"] = bool(les.save_all_dirty_levels())
    except Exception as e:
        out["save_dirty_err"] = str(e)[:120]

    out["summary"] = "MAPLIGHTS placed=%d failed=%d deleted=%d world=%d->%d" % (
        out["placed"], out["failed"], out["deleted"], out["actors_before"], out["actors_after"])
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=1)


main()
