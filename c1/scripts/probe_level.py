"""Probe the shipped C1Full level: sublevels, actor census, and the transform/collision convention.

Nothing here writes. It answers the two questions A5 depends on:
  * how a cell actor is placed (transform, mobility, collision profile, mesh path)
  * how the existing decal/paint mesh actor is placed, so the merged paint mesh can match it
"""
import json

import unreal

LEVEL = "/Game/Mods/C1Full/Maps/C1Full"
OUT = r"D:\a5_probe.json"
LOG = r"D:\a5_probe.log"


def log(m):
    unreal.log("A5P " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


def actor_rec(a):
    rec = {"label": a.get_actor_label(), "class": a.get_class().get_name()}
    try:
        loc = a.get_actor_location()
        rot = a.get_actor_rotation()
        scale = a.get_actor_scale3d()
        rec["loc"] = [round(loc.x, 2), round(loc.y, 2), round(loc.z, 2)]
        rec["rot"] = [round(rot.pitch, 3), round(rot.yaw, 3), round(rot.roll, 3)]
        rec["scale"] = [round(scale.x, 3), round(scale.y, 3), round(scale.z, 3)]
    except Exception as e:
        rec["xform_err"] = str(e)
    try:
        comp = a.get_component_by_class(unreal.StaticMeshComponent)
        if comp:
            rec["profile"] = str(comp.get_editor_property("collision_profile_name"))
            rec["mobility"] = str(comp.get_editor_property("mobility"))
            sm = comp.get_editor_property("static_mesh")
            rec["mesh"] = sm.get_path_name() if sm else None
            lods = int(sm.get_num_lods()) if sm else None
            rec["lods"] = lods
    except Exception as e:
        rec["comp_err"] = str(e)
    return rec


def main():
    open(LOG, "w").close()
    unreal.EditorLevelLibrary.load_level(LEVEL)
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    census = {}
    for a in actors:
        c = a.get_class().get_name()
        census[c] = census.get(c, 0) + 1

    out = {"total": len(actors), "census": dict(sorted(census.items(), key=lambda kv: -kv[1]))}

    # sublevels, if the subsystem is reachable
    try:
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        out["sublevels"] = [str(p) for p in les.get_levels()]
    except Exception as e:
        out["sublevels_err"] = str(e)

    sma = [a for a in actors if a.get_class().get_name() == "StaticMeshActor"]
    out["static_mesh_actors"] = len(sma)
    out["samples"] = [actor_rec(a) for a in sma[:3]]
    decal = [a for a in sma if "decal" in (a.get_actor_label() or "").lower()
             or "paint" in (a.get_actor_label() or "").lower()]
    out["decal_like"] = [actor_rec(a) for a in decal[:5]]
    # any actor whose mesh is not one of the cells
    odd = []
    for a in sma:
        r = actor_rec(a)
        m = (r.get("mesh") or "")
        name = m.rsplit(".", 1)[-1] if m else ""
        if not name.startswith("c") and name not in ("", "None"):
            odd.append(r)
    out["non_cell_meshes"] = odd[:10]
    centers = [a for a in actors if a.get_class().get_name() != "StaticMeshActor"]
    out["non_static_samples"] = [{"label": a.get_actor_label(),
                                  "class": a.get_class().get_name()} for a in centers[:12]]
    json.dump(out, open(OUT, "w"), indent=1)
    log("total=%d sma=%d census=%s" % (len(actors), len(sma), out["census"]))
    log("A5P_DONE")


main()
