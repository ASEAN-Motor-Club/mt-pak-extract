"""A5 verification: read the whole assembled map back and check it, without writing anything."""
import json

import unreal

PERSISTENT = "/Game/Mods/C1Full/Maps/C1Full"
SUBLEVEL = "/Game/Mods/C1Full/Maps/C1Full_NoCollision"
ORIGINS = r"D:\C1FullMirror\cell_origins_v2.json"
REPORT = r"D:\a5_verify.json"
LOG = r"D:\a5_verify.log"


def log(m):
    unreal.log("A5V " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")


def profile_of(a):
    try:
        return str(a.static_mesh_component.get_collision_profile_name())
    except Exception as e:
        return "err:%s" % e


def main():
    open(LOG, "w").close()
    origins = json.load(open(ORIGINS))
    unreal.EditorLevelLibrary.load_level(PERSISTENT)
    actors = unreal.EditorLevelLibrary.get_all_level_actors()

    census = {}
    for a in actors:
        c = a.get_class().get_name()
        census[c] = census.get(c, 0) + 1

    sma = [a for a in actors if a.get_class().get_name() == "StaticMeshActor"]
    cells = [a for a in sma if (a.get_actor_label() or "").startswith("C1_cell_")]
    nc = [a for a in sma if (a.get_actor_label() or "").startswith("C1_NC_")]

    # cell actors must sit exactly on their grid origin: loc = (ox*100, -oy*100, 0)
    drift = []
    for a in cells:
        cell = a.get_actor_label()[len("C1_cell_"):]
        if cell not in origins:
            drift.append([cell, "no_origin"])
            continue
        ox, oy = origins[cell]
        loc = a.get_actor_location()
        want = (ox * 100.0, -oy * 100.0, 0.0)
        if (round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)) != (round(want[0], 1),
                                                                  round(want[1], 1), 0.0):
            drift.append([cell, [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)], want])

    nc_bad = [[a.get_actor_label(), profile_of(a)] for a in nc if profile_of(a) != "NoCollision"]
    cell_profiles = {}
    for a in cells:
        p = profile_of(a)
        cell_profiles[p] = cell_profiles.get(p, 0) + 1

    paint = [a for a in nc if a.get_actor_label() == "C1_NC_Paint"]
    report = {
        "total_actors": len(actors),
        "census": dict(sorted(census.items(), key=lambda kv: -kv[1])),
        "static_mesh": len(sma),
        "cells": len(cells),
        "nc_actors": len(nc),
        "cell_profile_histogram": cell_profiles,
        "cell_transform_drift": drift[:10],
        "cell_transform_drift_count": len(drift),
        "nc_bad_profiles": nc_bad[:10],
        "nc_bad_profile_count": len(nc_bad),
        "paint_present": len(paint),
        "has_old_decal": any((a.get_actor_label() or "") == "C1_Decals" for a in actors),
    }
    report["ok"] = (len(cells) == 554 and len(nc) == 238 and len(paint) == 1
                    and not drift and not nc_bad and not report["has_old_decal"])
    json.dump(report, open(REPORT, "w"), indent=1)
    log("A5V_%s %s" % ("OK" if report["ok"] else "FAIL", json.dumps(report["census"])))
    log("cells=%d nc=%d paint=%d drift=%d nc_bad=%d old_decal=%s"
        % (len(cells), len(nc), len(paint), len(drift), len(nc_bad),
           report["has_old_decal"]))


main()
