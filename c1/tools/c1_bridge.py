"""Bridge the 10 m seams between C1 road segments and set the speed limit to 120 kph.

Editor-only: moves existing spline points and sets one property per actor. No byte edits.

Run in the MIRROR project (only project with the MotorTown classes):
    D:\\C1Mirror\\run_py.bat D:/UEProjects/C1/Scripts/c1_bridge.py
"""
import json
import traceback

import unreal

LEVEL = '/Game/Mods/C1/Maps/C1Roads'
OUT = 'D:/UEProjects/C1/Scripts/c1_bridge_report.json'
SPEED = 120.0
MAX_SHIFT = 1500.0   # cm - refuse to move an endpoint further than this
MIN_ROOM = 300.0     # cm - keep at least this much before the next spline point


def log(m):
    unreal.log('[C1BRIDGE] ' + str(m))


def get_spline(actor):
    for n in ('Spline', 'spline', 'RootComponent', 'root_component'):
        try:
            c = actor.get_editor_property(n)
            if c is not None:
                return c
        except Exception:
            pass
    return None


def pt(spline, i):
    v = spline.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD)
    return [float(v.x), float(v.y), float(v.z)]


def dist(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(LEVEL)
    actors = eas.get_all_level_actors()

    segs = []
    for a in actors:
        if a.get_class().get_name() == 'MotorTownRoad' and a.get_actor_label().startswith('C1_Seg'):
            segs.append(a)
    segs.sort(key=lambda a: a.get_actor_label())
    log('segments=%d' % len(segs))
    if not segs:
        raise RuntimeError('no C1_Seg actors found')

    splines = {}
    for a in segs:
        s = get_spline(a)
        if s is None:
            raise RuntimeError('no spline on ' + a.get_actor_label())
        splines[a.get_actor_label()] = s

    # ---- 1. measure the gaps as they are now -------------------------------------
    before = []
    for i in range(len(segs) - 1):
        la, lb = segs[i].get_actor_label(), segs[i + 1].get_actor_label()
        sa, sb = splines[la], splines[lb]
        end = pt(sa, sa.get_number_of_spline_points() - 1)
        start = pt(sb, 0)
        before.append((la, lb, round(dist(end, start), 2)))

    # ---- 2. close every gap at its midpoint --------------------------------------
    moved = []
    skipped = []
    for i in range(len(segs) - 1):
        la, lb = segs[i].get_actor_label(), segs[i + 1].get_actor_label()
        sa, sb = splines[la], splines[lb]
        na, nb = sa.get_number_of_spline_points(), sb.get_number_of_spline_points()
        end = pt(sa, na - 1)
        start = pt(sb, 0)
        gap = dist(end, start)
        if gap < 0.5:
            continue
        if gap > MAX_SHIFT:
            skipped.append((la, lb, round(gap, 1), 'gap_too_large'))
            continue
        # keep the point spacing sane: the neighbour point must stay MIN_ROOM away
        if na > 1 and dist(end, pt(sa, na - 2)) < MIN_ROOM:
            skipped.append((la, lb, round(gap, 1), 'no_room_before_end'))
            continue
        if nb > 1 and dist(start, pt(sb, 1)) < MIN_ROOM:
            skipped.append((la, lb, round(gap, 1), 'no_room_after_start'))
            continue
        mid = [(end[k] + start[k]) * 0.5 for k in range(3)]
        sa.set_location_at_spline_point(na - 1, unreal.Vector(*mid),
                                        unreal.SplineCoordinateSpace.WORLD, update_spline=False)
        sb.set_location_at_spline_point(0, unreal.Vector(*mid),
                                        unreal.SplineCoordinateSpace.WORLD, update_spline=False)
        moved.append((la, lb, round(gap, 2)))

    for lab, s in splines.items():
        s.update_spline()

    # ---- 3. speed limit -----------------------------------------------------------
    speeds = {}
    for a in segs:
        try:
            a.set_editor_property('speed_limit_kph', SPEED)
            speeds[a.get_actor_label()] = float(a.get_editor_property('speed_limit_kph'))
        except Exception as e:
            speeds[a.get_actor_label()] = 'FAIL %s' % e

    les.save_current_level()
    log('saved=%s' % LEVEL)

    # ---- 4. read back -------------------------------------------------------------
    after = []
    for i in range(len(segs) - 1):
        la, lb = segs[i].get_actor_label(), segs[i + 1].get_actor_label()
        sa, sb = splines[la], splines[lb]
        end = pt(sa, sa.get_number_of_spline_points() - 1)
        start = pt(sb, 0)
        after.append((la, lb, round(dist(end, start), 3)))

    report = {'level': LEVEL, 'segments': len(segs),
              'gaps_before': before, 'closed': moved, 'skipped': skipped,
              'gaps_after': after, 'speeds': speeds}
    with open(OUT, 'w') as f:
        json.dump(report, f, indent=1)

    worst = max([g[2] for g in after]) if after else 0
    bad_speeds = [k for k, v in speeds.items() if not isinstance(v, float) or abs(v - SPEED) > 0.01]
    log('closed=%d skipped=%d worst_gap_after=%.3f bad_speeds=%d' %
        (len(moved), len(skipped), worst, len(bad_speeds)))
    for s in skipped:
        log('SKIP %s' % (s,))
    log('C1BRIDGE_WROTE ' + OUT)


try:
    main()
except Exception:
    log('FATAL ' + traceback.format_exc())
    raise
