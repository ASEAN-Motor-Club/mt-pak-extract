"""Give every existing cell actor its real transform.

The meshes were re-imported with local vertices, so the geometry only lands in the
right place once each actor sits at its cell origin (origin_m * 100 = cm).

Deliberately does NOT destroy/spawn actors: tearing the whole level down and
rebuilding it in one session crashes the editor inside a road subsystem
(EXCEPTION_INT_DIVIDE_BY_ZERO on the empty-world frame).
"""
import json

import unreal

PROGRESS = r"D:\set_transforms.log"
ORIGINS = r"D:\C1FullMirror\cell_origins.json"
LEVEL = "/Game/Mods/C1Full/Maps/C1Full"
PREFIX = "C1_cell_"
SCALE = 100.0


def log(m):
    unreal.log("XF " + str(m))
    with open(PROGRESS, "a") as f:
        f.write(str(m) + "\n")


def main():
    open(PROGRESS, "w").close()
    origins = json.load(open(ORIGINS))

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(LEVEL)
    log("level=%s" % LEVEL)

    moved, no_origin, labels = 0, [], []
    for a in eas.get_all_level_actors():
        try:
            label = a.get_actor_label()
        except Exception:
            continue
        if not label.startswith(PREFIX):
            continue
        name = label[len(PREFIX):]
        org = origins.get(name)
        if org is None:
            no_origin.append(name)
            continue
        # MT is metres->cm with the OPPOSITE Y axis from BeamNG: the OBJ importer
        # already negates Y in the vertices, so the actor offset must negate too or
        # every tile lands at 2*origin - y instead of -y.
        loc = unreal.Vector(org[0] * SCALE, -org[1] * SCALE, 0.0)
        try:
            a.set_actor_location(loc, False, False)
            moved += 1
            if moved <= 3:
                labels.append("%s -> (%.0f,%.0f)" % (name, loc.x, loc.y))
        except Exception as exc:
            no_origin.append("%s:%s" % (name, exc))
        if moved % 100 == 0:
            log("moved %d" % moved)

    for l in labels:
        log("sample " + l)
    log("moved=%d problems=%d" % (moved, len(no_origin)))
    if no_origin:
        log("problems_sample=%s" % no_origin[:5])

    # ---- gate: measure the placed world, not the intent ----
    # Road splines span x ~ -1,104,777..611,734 cm and y ~ -1,002,062..1,658,899 cm.
    # A union of only a few km means the meshes stayed local and the actors never moved.
    mn = [1e18, 1e18]
    mx = [-1e18, -1e18]
    for a in eas.get_all_level_actors():
        try:
            if not a.get_actor_label().startswith(PREFIX):
                continue
            o, e = a.get_actor_bounds(False)
            mn[0] = min(mn[0], o.x - e.x); mx[0] = max(mx[0], o.x + e.x)
            mn[1] = min(mn[1], o.y - e.y); mx[1] = max(mx[1], o.y + e.y)
        except Exception:
            pass
    span_km = [(mx[i] - mn[i]) / 100000.0 for i in range(2)]
    ok = (abs(mn[0] / 100000.0 + 11.0) < 0.5 and abs(mx[1] / 100000.0 - 16.6) < 0.5)
    log("GATE x=%.2f..%.2f km y=%.2f..%.2f km span=%.2fx%.2f -> %s"
        % (mn[0] / 1e5, mx[0] / 1e5, mn[1] / 1e5, mx[1] / 1e5, span_km[0], span_km[1],
           "XF_GATE_OK" if ok else "XF_GATE_FAIL"))

    les.save_current_level()
    log("SAVED")
    log("XF_DONE")


main()
