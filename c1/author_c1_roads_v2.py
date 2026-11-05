"""Author C1 roads natively in D:\\C1Mirror (the MotorTown project, real engine classes).

    UnrealEditor-Cmd.exe D:\C1Mirror\MotorTown.uproject -run=pythonscript \
        -script="D:/UEProjects/C1/Scripts/author_c1_roads.py" -unattended

Frame: source -> UE is a pure Y mirror (see to_ue). Units already centimetres.
Builds /Game/Mods/C1/Maps/C1Roads with:
  C1_SegNN_*   28 one-way lane segments (lanes/width from the BeamNG DecalRoad data)
  C1_Course    one Track_Course spline for the race (lanes irrelevant)
  40 gates     MotorTownRaceSection, CourseName=C1Shuto
  MotorTownNavigation with BuildNavigation() baked
"""
import json
import traceback

import unreal

SPEC = 'D:/UEProjects/C1/Scripts/road_specs_v2.json'
OUT_LEVEL = '/Game/Mods/C1/Maps/C1Roads'
COURSE_KEY = 'C1Shuto'


def log(msg):
    unreal.log('[C1ROADS] ' + str(msg))


def to_ue(p):
    """Source frame -> UE map frame: pure Y mirror, no offset. Measured, not assumed:
    geometry Y -1,052,240..-493,825 vs source +569,452..+998,116; traces peak at zero shift."""
    return (float(p[0]), -float(p[1]), float(p[2]))


def ue_yaw(deg):
    return -float(deg)


def enum_member(enum_name, value_name):
    """UE exposes UENUM entries with their C++ names; accept either casing."""
    cls = getattr(unreal, enum_name, None)
    if cls is None:
        # the UENUM is bound under its reflected name (MTRoadType here), not the header name
        for attr in dir(unreal):
            if attr.lower() == enum_name.lower().lstrip('e') or attr.lower().endswith(enum_name.lower()):
                cls = getattr(unreal, attr)
                break
    if cls is None:
        for attr in dir(unreal):
            if 'roadtype' in attr.lower():
                cls = getattr(unreal, attr)
                break
    if cls is None:
        raise RuntimeError('no enum bound for %s' % enum_name)
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


def make_spline(road, points, closed):
    spline = get_spline(road)
    if spline is None:
        raise RuntimeError('road has no accessible Spline component')
    spline.clear_spline_points(update_spline=False)
    for i, p in enumerate(points):
        # AddSplinePoint(Index, Position, UpdateSpline) - takes a Vector, not a SplinePoint.
        # Python binding is AddSplinePoint(Position, bUpdateSpline) - it appends; no index.
        spline.add_spline_point(
            unreal.Vector(float(p[0]), float(p[1]), float(p[2])),
            unreal.SplineCoordinateSpace.WORLD, update_spline=False)

    if closed:
        try:
            spline.set_closed_loop(True)
        except Exception as e:
            log('closed_loop_failed %s' % e)
    spline.update_spline()
    return spline.get_number_of_spline_points()


def set_props(obj, pairs, label):
    for key, value in pairs:
        try:
            obj.set_editor_property(key, value)
        except Exception as e:
            log('SET_FAIL %s.%s : %s' % (label, key, e))


def author_road(eas, spec_road, points, closed, extra_props=()):
    road = eas.spawn_actor_from_class(unreal.MotorTownRoad, unreal.Vector(0.0, 0.0, 0.0))
    n = make_spline(road, points, closed)
    props = [('road_type', enum_member('MTRoadType', spec_road['road_type'])),
             ('lane_width', float(spec_road['lane_width'])),
             ('num_forward_lanes', int(spec_road['forward_lanes'])),
             ('num_backward_lanes', int(spec_road['backward_lanes'])),
             ('speed_limit_kph', float(spec_road['speed_kph'])),
             ('road_flags', int(spec_road['flags']))]
    props.extend(extra_props)
    set_props(road, props, spec_road['name'])
    road.set_actor_label(spec_road['name'])
    lanes = spec_road['forward_lanes'] + spec_road['backward_lanes']
    log('ROAD %s pts=%d lanes=%d lane_width=%.0f speed=%.0f' %
        (spec_road['name'], n, lanes, spec_road['lane_width'], spec_road['speed_kph']))
    return road


def author_gate(eas, g):
    x, y, z = to_ue(g['pos'])
    loc = unreal.Vector(x, y, z)
    rot = unreal.Rotator(0.0, ue_yaw(g['yaw']), 0.0)
    gate = eas.spawn_actor_from_class(unreal.MotorTownRaceSection, loc, rot)
    set_props(gate, [('course_name', COURSE_KEY)], 'gate%d' % g['index'])
    comp = None
    for name in ('RootComponent', 'root_component'):
        try:
            comp = gate.get_editor_property(name)
            if comp is not None:
                break
        except Exception:
            pass
    if comp is not None:
        for key in ('box_extent', 'BoxExtent'):
            try:
                comp.set_editor_property(key, unreal.Vector(200.0, 600.0, 1500.0))
                break
            except Exception:
                pass
    gate.set_actor_label('C1_gate_%02d' % g['index'])
    return gate


def main():
    spec = json.load(open(SPEC))
    raw = spec['points']
    points = [to_ue(p) for p in raw]
    ys = [p[1] for p in points]
    log('spec points=%d segments=%d gates=%d' % (len(points), len(spec['segments']), len(spec['gates'])))
    log('frame_check X %.0f..%.0f Y %.0f..%.0f (Y must be negative)' %
        (min(p[0] for p in points), max(p[0] for p in points), min(ys), max(ys)))
    if max(ys) > 0:
        raise RuntimeError('frame_check FAILED: Y is not mirrored')

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if unreal.EditorAssetLibrary.does_asset_exist(OUT_LEVEL):
        log('deleting existing %s' % OUT_LEVEL)
        unreal.EditorAssetLibrary.delete_asset(OUT_LEVEL)
    les.new_level(OUT_LEVEL)
    log('level_created=%s' % OUT_LEVEL)

    for seg in spec['segments']:
        a, b = seg['start'], seg['end']
        sub = points[a:b + 1]
        if len(sub) < 2:
            log('SKIP_SEG %s too few points' % seg['name'])
            continue
        author_road(eas, {'name': seg['name'], 'road_type': seg['road_type'],
                          'lane_width': seg['lane_width'],
                          'forward_lanes': seg['lanes'], 'backward_lanes': 0,
                          'speed_kph': seg['speed_kph'], 'flags': seg['flags']},
                    sub, False)

    course = spec['course']
    author_road(eas, course, points, True, extra_props=[('course_key', unreal.Name(COURSE_KEY))])

    gates = 0
    for g in spec['gates']:
        try:
            author_gate(eas, g)
            gates += 1
        except Exception as e:
            log('GATE_FAIL %s' % e)
    log('gates=%d' % gates)

    nav = eas.spawn_actor_from_class(unreal.MotorTownNavigation, unreal.Vector(0.0, 0.0, 0.0))
    try:
        nav.build_navigation()
        log('build_navigation=called')
    except Exception as e:
        log('build_navigation=ERR %s' % e)

    les.save_current_level()
    log('saved=%s' % OUT_LEVEL)
    log('C1ROADS_DONE')


try:
    main()
except Exception:
    unreal.log_error('[C1ROADS] FAILED\n' + traceback.format_exc())
    unreal.log_error('C1ROADS_FAILED')
