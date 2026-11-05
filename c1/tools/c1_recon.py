"""Read-only recon of the C1 road network. Writes D:/UEProjects/C1/Scripts/c1_recon.json.

Run against the MotorTown project (real engine classes):
    UnrealEditor-Cmd.exe D:\\C1Mirror\\MotorTown.uproject -run=pythonscript \
        -script="D:/UEProjects/C1/Scripts/c1_recon.py" -unattended
"""
import json
import traceback

import unreal

LEVEL_CANDIDATES = ['/Game/Mods/C1/Maps/C1_Roads', '/Game/Mods/C1/Maps/C1Roads',
                    '/Game/Mods/C1/Maps/C1']
OUT = 'D:/UEProjects/C1/Scripts/c1_recon.json'


def log(m):
    unreal.log('[C1RECON] ' + str(m))


def prop(obj, names, default=None):
    if isinstance(names, str):
        names = (names,)
    for n in names:
        try:
            v = obj.get_editor_property(n)
            if v is not None:
                return v
        except Exception:
            pass
    return default


def enum_name(v):
    try:
        return str(v).split('.')[-1]
    except Exception:
        return str(v)


def spline_of(actor):
    for n in ('Spline', 'spline', 'RootComponent', 'root_component'):
        try:
            c = actor.get_editor_property(n)
            if c is not None:
                return c
        except Exception:
            pass
    return None


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    assets = unreal.EditorAssetLibrary.list_assets('/Game/Mods/C1/Maps', recursive=True, include_folder=False)
    levels = [a for a in assets if a.endswith('.umap') or ('.umap.' not in a and a.split('/')[-1].lower() not in ())]
    levels = [a for a in levels if not a.endswith('_P')]
    # list_assets returns object paths (/Game/X/Y.Y); load_level wants the package path
    levels = [a.split('.')[0] for a in levels]
    log('level_assets=%s' % json.dumps(levels))

    log('has_MotorTownRoad=%s has_MotorTownNavigation=%s' % (
        hasattr(unreal, 'MotorTownRoad'), hasattr(unreal, 'MotorTownNavigation')))
    try:
        cls = unreal.load_class(None, '/Script/MotorTown.MotorTownRoad')
        log('load_class MotorTownRoad -> %s' % cls)
    except Exception as e:
        log('load_class_fail %s' % e)

    scan = {}
    chosen = None
    for cand in levels:
        loaded = False
        try:
            loaded = unreal.EditorLoadingAndSavingUtils.load_map(cand)
        except Exception as e:
            log('load_map_fail %s %s' % (cand, e))
        if not loaded:
            try:
                loaded = les.load_level(cand)
            except Exception as e:
                log('load_level_fail %s %s' % (cand, e))
        log('LOAD %s -> %s' % (cand, loaded))
        actors = eas.get_all_level_actors()
        counts = {}
        for a in actors:
            c = a.get_class().get_name()
            counts[c] = counts.get(c, 0) + 1
        scan[cand] = {'actors': len(actors), 'classes': counts}
        log('SCAN %s actors=%d roads=%d' % (cand, len(actors), counts.get('MotorTownRoad', 0)))
        if counts.get('MotorTownRoad', 0) and chosen is None:
            chosen = cand

    if chosen is None:
        out = {'scan': scan, 'error': 'no level contains MotorTownRoad'}
        with open(OUT, 'w') as f:
            json.dump(out, f, indent=1)
        log('NO_ROADS ' + json.dumps(scan))
        return

    LEVEL = chosen
    les.load_level(LEVEL)
    actors = eas.get_all_level_actors()
    log('chosen=%s actors=%d' % (LEVEL, len(actors)))

    roads = []
    others = {}
    for a in actors:
        cls = a.get_class().get_name()
        if cls == 'MotorTownRoad':
            sp = spline_of(a)
            npts = 0
            first = last = None
            closed = None
            if sp is not None:
                try:
                    npts = sp.get_number_of_spline_points()
                except Exception as e:
                    log('npts_fail %s' % e)
                try:
                    closed = sp.is_closed_loop()
                except Exception:
                    pass
                try:
                    if npts:
                        first = sp.get_location_at_spline_point(0, unreal.SplineCoordinateSpace.WORLD)
                        last = sp.get_location_at_spline_point(npts - 1, unreal.SplineCoordinateSpace.WORLD)
                except Exception:
                    pass

            def vec(v):
                return [round(float(v.x), 2), round(float(v.y), 2), round(float(v.z), 2)] if v else None

            roads.append({
                'label': a.get_actor_label(),
                'name': a.get_name(),
                'road_type': enum_name(prop(a, 'road_type', '?')),
                'course_key': str(prop(a, 'course_key', '')),
                'lane_width': prop(a, 'lane_width'),
                'forward_lanes': prop(a, 'num_forward_lanes'),
                'backward_lanes': prop(a, 'num_backward_lanes'),
                'speed_kph': prop(a, 'speed_limit_kph'),
                'flags': prop(a, 'road_flags'),
                'points': npts,
                'closed': closed,
                'start': vec(first),
                'end': vec(last),
            })
        else:
            others[cls] = others.get(cls, 0) + 1

    navs = []
    for a in actors:
        if a.get_class().get_name() == 'MotorTownNavigation':
            gd = prop(a, 'graph_data')
            nodes = 0
            if gd is not None:
                try:
                    nodes = len(gd.get_editor_property('nodes'))
                except Exception:
                    try:
                        nodes = len(gd.nodes)
                    except Exception:
                        nodes = -1
            navs.append({'label': a.get_actor_label(), 'nodes': nodes})

    def dist(p, q):
        if not p or not q:
            return None
        return round(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2) ** 0.5, 2)

    for i, r in enumerate(roads):
        best = None
        best_to = None
        for j, s2 in enumerate(roads):
            if i == j:
                continue
            for key in ('start', 'end'):
                d = dist(r['end'], s2[key])
                if d is not None and (best is None or d < best):
                    best, best_to = d, s2['label'] + ' ' + key
            d0 = dist(r['start'], s2['start'])
            if d0 is not None and (best is None or d0 < best):
                best, best_to = d0, s2['label'] + ' start'
        r['seam_gap'] = best
        r['seam_to'] = best_to

    out = {'level': LEVEL, 'scan': scan, 'road_count': len(roads), 'roads': roads,
           'nav': navs, 'other_classes': others}
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1)

    for r in roads:
        log('ROAD %-18s type=%-13s lanes=%s/%s w=%s spd=%s pts=%s gap=%s' % (
            r['label'], r['road_type'], r['forward_lanes'], r['backward_lanes'],
            r['lane_width'], r['speed_kph'], r['points'], r['seam_gap']))
    log('nav=%s others=%s' % (json.dumps(navs), json.dumps(others)))
    log('C1RECON_WROTE ' + OUT)


try:
    main()
except Exception:
    log('FATAL ' + traceback.format_exc())
    raise
