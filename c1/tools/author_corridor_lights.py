"""Port ALL 2,169 corridor lamps as NATIVE light actors with per-lamp values from the BeamNG source.

Why native actors and not BP_C1_Lamp instances: a blueprint's light component is a class default
(CDO) shared by every instance, so per-lamp intensity/range/cone cannot be expressed without one
BP per value. Native SpotLight/PointLight actors carry their own component values, which is also
the only path that has behaved reliably in this project (the P0 ladder).

Per-lamp mapping from the source record (canonical units, see
c1/docs/MAP_PORTING_GUIDE.md section 7 and c1/GOTCHAS.md section 32):
  intensity          = brightness * 5000 cd  (spot -> CANDELAS units)
                       brightness * 62832 lm (sign lights -> LUMENS units)
                       records without brightness get 1.0
  attenuation_radius = range_m * 100 cm      (range only clamps the inverse-square falloff)
  inner/outer cone   = source inner/outer degrees (both engines agree; no clamping)
  colour             = source linear RGBA converted to sRGB, NOT linear*255
  pitch              = -90 (straight down)

NOTE: the /lamps runtime probe counts BP_C1_Lamp actors and reports 0 once these native
actors replace them. Actor labels are editor-only and are stripped by the cook, so the
pak cannot be audited by grepping for "C1Port_" either — audit via the umap export-table
size (v5 4 lights = 56,021 B, v6 2,169 lights = 630,770 B).

Idempotent: destroys C1Lamp_/C1Ladder_/C1NativeLight_/C1Port_ actors before spawning.
"""
import json
import os
import traceback

import unreal

LEVEL = "/Game/Mods/C1Full/Maps/C1Full_Roads"
ROWS = os.environ.get("C1_LAMP_ROWS", r"D:/C1FullMirror/Scripts/corridor_rows.json")
REPORT = os.environ.get("C1_LAMP_REPORT", r"D:/C1FullMirror/Scripts/author_corridor.json")
PREFIXES = ("C1Lamp_", "C1Ladder_", "C1NativeLight_", "C1Port_")

# BeamNG (documentation.beamng.com/modding/lighting/pbl):
#   SpotLight intensity is CANDELAS, PointLight is LUMENS; legacy `brightness` fallback is
#   1 brightness ~= 5000 cd (spot) and ~= 62832 lm (point); range/radius only clamp the
#   inverse-square falloff. Official street-lamp guidance: 10000-50000 cd, range 25-60 m.
CD_PER_BRIGHTNESS = 5000.0
LM_PER_BRIGHTNESS = 62832.0
DEFAULT_BRIGHTNESS = 1.0
CD_SCALE = float(os.environ.get("C1_CD_SCALE", "1.0"))    # street/tunnel eyeball knob
# Sign lights are POINT lights at the canonical default (62832 lm) — correct as a source value, but
# inside a small sign box it blows out the sign face and reads as a hotspot in reflections. Scaled
# down; the sign emissive material already provides the visible glow.
SIGN_LM_SCALE = float(os.environ.get("C1_SIGN_LM_SCALE", "0.15"))
SIGN_DEFAULT_LM = float(os.environ.get("C1_SIGN_DEFAULT_LM", "800"))   # lumen value for value-less signs

rows = json.load(open(ROWS))
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

out = {"placed": 0, "failed": 0, "deleted": 0, "errors": [], "by_group": {},
       "intensity_hist": {}, "radius_hist": {}}

les.load_level(LEVEL)
unreal.log("[C1PORT] level %s rows %d" % (LEVEL, len(rows)))

for a in eas.get_all_level_actors():
    try:
        if a.get_actor_label().startswith(PREFIXES):
            eas.destroy_actor(a)
            out["deleted"] += 1
    except Exception:
        pass

skipped = []
for r in rows:
    # A row with no photometric value is a placeholder, not a lamp. The 356 sign_lights in this
    # source level carry only position + texSize: no brightness, range, colour or angles, and every
    # one is isEnabled=false. Lighting them with the class default produced white blobs at 62,832 lm.
    if all(r.get(k) is None for k in ("brightness", "src_range_m", "src_color", "inner_deg", "outer_deg")):
        skipped.append(r.get("name"))
        continue
    try:
        x, y, z = r["ue_cm"]
        cls = unreal.PointLight if r.get("group") == "sign_lights" else unreal.SpotLight
        actor = eas.spawn_actor_from_class(cls, unreal.Vector(x, y, z),
                                           unreal.Rotator(roll=0.0, pitch=-90.0, yaw=0.0))
        actor.set_actor_label("C1Port_" + r["name"])

        brightness = r.get("brightness")
        b = float(brightness) if isinstance(brightness, (int, float)) and brightness > 0 else DEFAULT_BRIGHTNESS
        is_point = (r.get("group") == "sign_lights")
        if is_point:
            # Value-less sign lamps get the documented small-point-light default, not the legacy
            # brightness default (which is ~60x brighter and clips to white against MT exposure).
            inten = SIGN_DEFAULT_LM if r.get("sign_default") else b * LM_PER_BRIGHTNESS * SIGN_LM_SCALE
            units = unreal.LightUnits.LUMENS
        else:
            inten = b * CD_PER_BRIGHTNESS * CD_SCALE
            units = unreal.LightUnits.CANDELAS

        rng = float(r.get("src_range_m") or 25.0)
        radius = rng * 100.0                     # metres -> cm; range only clamps falloff

        inner = float(r.get("inner_deg") or 25.0)
        outer = float(r.get("outer_deg") or 170.0)
        if inner >= outer:
            inner = outer * 0.5

        # source colour is LINEAR RGBA; UE FColor is sRGB, so convert properly
        def lin_to_srgb(x):
            x = max(0.0, min(1.0, float(x)))
            v = 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1 / 2.4)) - 0.055
            return int(round(v * 255))
        src = r.get("src_color") or [1.0, 1.0, 1.0, 1.0]
        color = unreal.Color(r=lin_to_srgb(src[0]), g=lin_to_srgb(src[1]), b=lin_to_srgb(src[2]), a=255)

        c = actor.light_component
        c.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        c.set_editor_property("intensity_units", units)
        c.set_editor_property("intensity", inten)
        c.set_editor_property("attenuation_radius", radius)
        c.set_editor_property("cast_shadows", False)
        c.set_editor_property("light_color", color)
        if cls is unreal.PointLight:
            pass
        else:
            c.set_editor_property("inner_cone_angle", inner)
            c.set_editor_property("outer_cone_angle", outer)

        out["placed"] += 1
        g = r.get("group", "?")
        out["by_group"][g] = out["by_group"].get(g, 0) + 1
        ik = "%d" % inten
        out["intensity_hist"][ik] = out["intensity_hist"].get(ik, 0) + 1
        rk = "%d" % radius
        out["radius_hist"][rk] = out["radius_hist"].get(rk, 0) + 1
    except Exception:
        out["failed"] += 1
        if len(out["errors"]) < 5:
            out["errors"].append(traceback.format_exc().splitlines()[-1])

les.save_current_level()
out["skipped_placeholders"] = len(skipped)
out["summary"] = "CORRIDOR placed=%d failed=%d deleted=%d skipped_placeholder=%d" % (
    out["placed"], out["failed"], out["deleted"], len(skipped))
json.dump(out, open(REPORT, "w"), indent=1)
print(out["summary"], json.dumps(out["by_group"]))
print("intensity", json.dumps(out["intensity_hist"]), "radius", json.dumps(out["radius_hist"]))
