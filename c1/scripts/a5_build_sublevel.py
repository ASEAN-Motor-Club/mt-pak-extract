"""A5 step 1: build the C1Full_NoCollision sublevel and spawn its actors.

The sublevel holds everything that must not collide: the merged road-paint mesh (one actor at the
origin, world metres like the decal mesh it replaces) and one actor per foliage mesh, each sitting
on its cell's grid origin exactly like the cell actors do.

Nothing touches C1Full yet — attaching the sublevel is step 2, so a bad spawn is cheap to throw
away.
"""
import json
import os

import unreal

SUBLEVEL = "/Game/Mods/C1Full/Maps/C1Full_NoCollision"
MESH_DIR = "/Game/Mods/C1Full/Meshes"
FOLIAGE_DIR = "/Game/Mods/C1Full/Meshes_NoCollision"
PAINT_MESH = MESH_DIR + "/C1_NoCollision_Paint"
ORIGINS = r"D:\C1FullMirror\cell_origins_v2.json"
FOLIAGE_OBJS = r"D:\C1FullMirror\nc_out\foliage"
REPORT = r"D:\a5_step1.json"
LOG = r"D:\a5_step1.log"
PAINT_LABEL = "C1_NC_Paint"
CELL_LABEL = "C1_NC_%s"


def log(m):
    unreal.log("A5 " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


def spawn(label, mesh_path, loc):
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None:
        return {"label": label, "error": "mesh_missing:%s" % mesh_path}
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(loc[0], loc[1], loc[2]), unreal.Rotator(0, 0, 0))
    if actor is None:
        return {"label": label, "error": "spawn_failed"}
    actor.set_actor_label(label)
    comp = actor.static_mesh_component
    comp.set_editor_property("mobility", unreal.ComponentMobility.STATIC)
    comp.set_static_mesh(mesh)
    try:
        comp.set_collision_profile_name("NoCollision")
    except Exception as e:
        return {"label": label, "error": "collision_profile:%s" % e}
    real_loc = actor.get_actor_location()
    return {"label": label, "mesh": mesh_path.rsplit("/", 1)[-1],
            "loc": [round(real_loc.x, 2), round(real_loc.y, 2), round(real_loc.z, 2)],
            "profile": str(comp.get_collision_profile_name())}


def main():
    open(LOG, "w").close()
    report = {"actors": {}, "errors": [], "paint": None, "counts": {}}

    # start from the shipped level so the editor has a world, then make the new level current
    unreal.EditorLevelLibrary.load_level("/Game/Mods/C1Full/Maps/C1Full")
    log("loaded C1Full, creating %s" % SUBLEVEL)
    if not unreal.EditorLevelLibrary.new_level(SUBLEVEL):
        log("NEW_LEVEL_FAILED")
        json.dump(report, open(REPORT, "w"), indent=1)
        return
    log("new level created: %s" % SUBLEVEL)

    origins = json.load(open(ORIGINS))

    paint = spawn(PAINT_LABEL, PAINT_MESH, (0.0, 0.0, 0.0))
    report["paint"] = paint
    if paint.get("error"):
        report["errors"].append(paint)

    foliage_cells = sorted(os.path.splitext(f)[0] for f in os.listdir(FOLIAGE_OBJS)
                           if f.lower().endswith(".obj"))
    for cell in foliage_cells:
        if cell not in origins:
            report["errors"].append({"cell": cell, "error": "no_origin"})
            continue
        ox, oy = origins[cell]
        rec = spawn(CELL_LABEL % cell, "%s/%s" % (FOLIAGE_DIR, cell),
                    (ox * 100.0, -oy * 100.0, 0.0))
        report["actors"][cell] = rec
        if rec.get("error"):
            report["errors"].append(rec)

    unreal.EditorLevelLibrary.save_current_level()
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    report["counts"] = {"in_level": len(actors), "foliage_expected": len(foliage_cells),
                        "total_expected": 1 + len(foliage_cells)}
    report["ok"] = (not report["errors"] and len(actors) == 1 + len(foliage_cells))
    json.dump(report, open(REPORT, "w"), indent=1)
    log("A5_STEP1_%s actors=%d expected=%d errors=%d"
        % ("OK" if report["ok"] else "FAIL", len(actors), 1 + len(foliage_cells),
           len(report["errors"])))
    for e in report["errors"][:8]:
        log("err: %s" % e)


main()
