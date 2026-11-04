"""Author the full C1 road network from the BeamNG DecalRoad AI paths.

Replaces the 27 racing-line slices with one MotorTownRoad per decal (155), keeping both
carriageways, ramps and stacked sections. `C1_Course` (Track_Course, C1Shuto) and the 40
race gates are left alone.

Editor-only: spawns actors, builds splines, sets reflected properties. No byte work.

    D:\\C1Mirror\\run_py.bat D:/UEProjects/C1/Scripts/author_decal_roads.py
"""
import json
import os
import traceback

import unreal

SPEC = os.environ.get('C1_SPEC', 'D:/UEProjects/C1/Scripts/c1_decal_roads.json')
OUT_LEVEL = os.environ.get('C1_LEVEL', '/Game/Mods/C1/Maps/C1Roads')
REPORT = os.environ.get('C1_AUTHOR_REPORT', 'D:/UEProjects/C1/Scripts/c1_decal_author_report.json')
DROP_PREFIXES = ('C1_Seg', 'C1_Rd')   # old racing-line slices + our own roads (idempotent)


def log(m):
    unreal.log('[C1DECAL] ' + str(m))


def enum_member(enum_name, value_name):
    cls = getattr(unreal, enum_name, None)
    if cls is None:
        for attr in dir(unreal):
            if attr.lower().endswith(enum_name.lower()) or attr.lower() == enum_name.lower():
                cls = getattr(unreal, attr)
                break
    if cls is None:
        for attr in dir(unreal):
            if 'roadtype' in attr.lower():
                cls = getattr(unreal, attr)
                break
    if cls is None:
        raise RuntimeError('no enum bound for ' + enum_name)
    for cand in (value_name, value_name.upper(), value_name.lower()):
        if hasattr(cls, cand):
            return getattr(cls, cand)
    for attr in dir(cls):
        if attr.upper() == value_name.upper():
            return getattr(cls, attr)
    raise RuntimeError('%s has no member %s' % (enum_name, value_name))


def get_spline(road):
    for name in ('Spline', 'spline'):
        try:
            s = road.get_editor_property(name)
            if s is not None:
                return s
        except Exception:
            pass
    return None


def make_spline(road, points):
    spline = get_spline(road)
    if spline is None:
        raise RuntimeError('road has no accessible Spline component')
    spline.clear_spline_points(update_spline=False)
    for p in points:
        spline.add_spline_point(unreal.Vector(float(p[0]), float(p[1]), float(p[2])),
                                unreal.SplineCoordinateSpace.WORLD, update_spline=False)
    spline.update_spline()
    return spline.get_number_of_spline_points()


def set_props(obj, pairs, label):
    failed = []
    for key, value in pairs:
        try:
            obj.set_editor_property(key, value)
        except Exception as e:
            failed.append((key, str(e)))
            log('SET_FAIL %s.%s : %s' % (label, key, e))
    return failed


def main():
    spec = json.load(open(SPEC))
    roads = spec['roads']
    log('spec roads=%d points=%d' % (len(roads), sum(len(r['points']) for r in roads)))

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(OUT_LEVEL)

    # 1. drop the old racing-line slices, keep course / gates / nav
    dropped = 0
    for a in eas.get_all_level_actors():
        try:
            label = a.get_actor_label()
        except Exception:
            continue
        if label.startswith(DROP_PREFIXES):
            eas.destroy_actor(a)
            dropped += 1
    log('dropped old segments=%d' % dropped)

    # 2. author one road per decal
    road_enum = enum_member('MTRoadType', 'Road')
    authored = []
    failures = []
    for r in roads:
        try:
            road = eas.spawn_actor_from_class(unreal.MotorTownRoad, unreal.Vector(0.0, 0.0, 0.0))
            n = make_spline(road, r['points'])
            failed = set_props(road, [
                ('road_type', road_enum),
                ('lane_width', float(r['lane_width'])),
                ('num_forward_lanes', int(r['forward_lanes'])),
                ('num_backward_lanes', int(r['backward_lanes'])),
                ('speed_limit_kph', float(r['speed_kph'])),
                ('road_flags', int(r['flags'])),
            ], r['name'])
            road.set_actor_label(r['name'])
            authored.append({'name': r['name'], 'points': n,
                             'lane_width': float(r['lane_width']),
                             'f': int(r['forward_lanes']), 'b': int(r['backward_lanes']),
                             'len_m': r['length_m'], 'set_failures': [k for k, _ in failed]})
            if len(authored) % 25 == 0:
                log('progress authored=%d' % len(authored))
        except Exception as e:
            failures.append({'name': r['name'], 'error': str(e)})
            log('AUTHOR_FAIL %s : %s' % (r['name'], e))

    # 3. read back a sample straight from the actors, then save
    verify = []
    for a in eas.get_all_level_actors():
        try:
            label = a.get_actor_label()
        except Exception:
            continue
        if not label.startswith('C1_Rd'):
            continue
        try:
            verify.append({
                'name': label,
                'type': str(a.get_editor_property('road_type')),
                'kmh': float(a.get_editor_property('speed_limit_kph')),
                'f': int(a.get_editor_property('num_forward_lanes')),
                'b': int(a.get_editor_property('num_backward_lanes')),
            })
        except Exception as e:
            verify.append({'name': label, 'error': str(e)})

    les.save_current_level()
    log('saved %s' % OUT_LEVEL)

    speeds = sorted({v['kmh'] for v in verify if 'kmh' in v})
    types = sorted({v['type'] for v in verify if 'type' in v})
    report = {'authored': len(authored), 'dropped_old': dropped,
              'failures': failures, 'verify_count': len(verify),
              'verify_speeds': speeds, 'verify_types': types,
              'roads': authored}
    with open(REPORT, 'w') as f:
        json.dump(report, f, indent=1)
    log('AUTHORED=%d FAILED=%d VERIFIED=%d speeds=%s types=%s' %
        (len(authored), len(failures), len(verify), speeds, types))
    log('C1DECAL_WROTE ' + REPORT)


try:
    main()
except Exception:
    log('FATAL ' + traceback.format_exc())
    raise
