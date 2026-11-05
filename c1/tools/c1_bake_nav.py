"""Bake MotorTownNavigation.GraphData from the C1 road splines.

Why: shipped maps carry a serialised FMTRoadGraphData; BuildNavigation() never rebuilds it
at runtime (verified in game: Jeju 17,619 nodes before and after the call). Our map has 0.

Editor-only: builds MTRoadGraphNode structs in Python and assigns them to the nav actor's
`graph_data` property, then saves the level so UE serialises it itself. No byte work.

Node conventions copied from a live Jeju graph (D:/c1_nodes.json):
  * SpeedLimit is cm/s, not kph  (1111.111 = 40 km/h, 1666.667 = 60 km/h)
  * Lane is signed: forward lanes 1..N, oncoming -1..-N
  * LateralDistance is the signed lane-centre offset in cm (+ right of travel)
  * AutoConnectDistance / RightSideClearance use -1 as "unset"
  * CrossroadId -1 when not at a junction

    D:\\C1Mirror\\run_py.bat D:/UEProjects/C1/Scripts/c1_bake_nav.py
"""
import json
import math
import os
import traceback

import unreal

# Paths are overridable so the same script works for any level without editing it.
CONFIG = os.environ.get('C1_BAKE_CONFIG', 'D:/UEProjects/C1/Scripts/nav_bake_config.json')
OUT_LEVEL = os.environ.get('C1_LEVEL', '/Game/Mods/C1/Maps/C1Roads')
REPORT = os.environ.get('C1_BAKE_REPORT', 'D:/UEProjects/C1/Scripts/c1_nav_bake_report.json')

CM_PER_KMH = 1000.0 / 36.0     # 27.7778 cm/s per km/h
DEFAULTS = {
    'limit_roads': 0,
    'step_cm': 1000.0,
    'connect_cm': 2500.0,
    # 0.85 = 31.8 deg. The old 0.55 allowed a 56 deg cut, and the graph used the whole
    # allowance: AI turned across a merge instead of following it ("turns into
    # perpendicular traffic").
    'forward_dot': 0.85,
    # Belt-and-braces on the lateral frame. On planar roads it tracks forward_dot, so it
    # costs nothing today; it catches a crest or curved merge where the tangents agree
    # but the frames twist.
    'normal_dot': 0.85,
    # Stacked decks: two corridors 10-12 m apart horizontally but metres apart in Z look
    # like a legal successor at 4 m link range and the AI drives into the barrier
    # between them.
    'deck_dz_cm': 150.0,
    'deck_dist_cm': 1200.0,
    # and the long shallow version of the same defect
    'grade_max': 0.5,
}


def log(m):
    unreal.log('[C1BAKE] ' + str(m))


def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.load(open(CONFIG)))
    except Exception as e:
        log('config_default (%s)' % e)
    return cfg


def get_spline(road):
    for name in ('Spline', 'spline'):
        try:
            s = road.get_editor_property(name)
            if s is not None:
                return s
        except Exception:
            pass
    return None


def vec(v):
    return (float(v.x), float(v.y), float(v.z))


def main():
    cfg = load_config()
    step = float(cfg['step_cm'])
    log('config %s' % cfg)

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(OUT_LEVEL)

    nav = None
    roads = []
    for a in eas.get_all_level_actors():
        cname = a.get_class().get_name()
        if cname == 'MotorTownNavigation' and nav is None:
            nav = a
        elif cname == 'MotorTownRoad':
            try:
                if a.get_actor_label().startswith('C1_Rd'):
                    roads.append(a)
            except Exception:
                pass
    if nav is None:
        raise RuntimeError('no MotorTownNavigation actor')
    roads.sort(key=lambda a: a.get_actor_label())
    limit = int(cfg['limit_roads'])
    if limit:
        roads = roads[:limit]
    log('nav=%s roads=%d step=%.0fcm' % (nav.get_actor_label(), len(roads), step))

    # ---- 1. sample nodes -----------------------------------------------------------
    nodes = []          # plain dicts first; unreal structs come later
    for road in roads:
        spl = get_spline(road)
        if spl is None:
            log('NO_SPLINE %s' % road.get_actor_label())
            continue
        try:
            length = float(spl.get_spline_length())
            nf = int(road.get_editor_property('num_forward_lanes'))
            nb = int(road.get_editor_property('num_backward_lanes'))
            width = float(road.get_editor_property('lane_width'))
            kmh = float(road.get_editor_property('speed_limit_kph'))
        except Exception as e:
            log('PROP_FAIL %s %s' % (road.get_actor_label(), e))
            continue
        if length <= 1.0 or (nf + nb) <= 0:
            continue

        lanes = [l for l in range(1, nf + 1)] + [-l for l in range(1, nb + 1)]
        # Lanes TILE the carriageway: lane_width * (nf + nb) equals the decal width on every
        # C1 road, so lane centres are measured from the road EDGES, not stacked outward from
        # the spline. Stacking put lane 2 of a 2-lane road at 5.25 m on a road 3.5 m from the
        # centreline -- off the surface, which is why AI vehicles hit barriers and columns.
        total_w = width * float(nf + nb)
        count = max(2, int(math.ceil(length / step)) + 1)
        first_index = len(nodes)

        for lane in lanes:
            # C1 is a LEFT-hand-traffic map while MotorTown's AI keeps right. Numbering the
            # lanes from the LEFT edge makes the lane the AI prefers (+1) the LHT slow lane,
            # instead of the overtaking lane next to the oncoming carriageway.
            if lane > 0:
                lateral = -total_w / 2.0 + (lane - 0.5) * width   # +1 = leftmost (LHT slow)
            else:
                lateral = total_w / 2.0 - (abs(lane) - 0.5) * width   # -1 = rightmost
            for k in range(count):
                s = min(length, k * step)
                loc = spl.get_location_at_distance_along_spline(s, unreal.SplineCoordinateSpace.WORLD)
                tan = spl.get_direction_at_distance_along_spline(s, unreal.SplineCoordinateSpace.WORLD)
                rgt = spl.get_right_vector_at_distance_along_spline(s, unreal.SplineCoordinateSpace.WORLD)
                lx, ly, lz = vec(loc)
                rx, ry, rz = vec(rgt)
                # Oncoming lanes travel AGAINST the spline tangent. Keeping the raw tangent
                # made oncoming nodes point the same way as forward traffic, so cars on the
                # wrong side drove head-on ("traffic coming the wrong way"). Reverse both the
                # travel direction and the right vector (right of travel) for lane < 0.
                tx, ty, tz = vec(tan)
                # position stays on the spline's own lateral axis: only the TRAVEL frame flips
                px = lx + rx * lateral
                py = ly + ry * lateral
                pz = lz + rz * lateral
                if lane < 0:
                    tx, ty, tz = -tx, -ty, -tz
                    rx, ry, rz = -rx, -ry, -rz
                nodes.append({
                    'road': road, 'lane': lane, 'side': 1 if lane > 0 else -1,
                    's': s, 'loc': (px, py, pz),
                    'dir': (tx, ty, tz), 'right': (rx, ry, rz),
                    'lateral': lateral, 'kmh': kmh,
                    'road_start': first_index, 'k': k, 'count': count,
                })

    log('sampled nodes=%d' % len(nodes))
    if not nodes:
        raise RuntimeError('no nodes sampled')

    # ---- 2. edges: along each lane, plus nearest neighbours at road ends ------------
    connect = float(cfg['connect_cm'])
    fdot = float(cfg['forward_dot'])
    by_road = {}
    for idx, n in enumerate(nodes):
        by_road.setdefault((id(n['road']), n['lane']), []).append(idx)

    edges = [dict() for _ in nodes]     # target -> (cost, distance)
    for key, idxs in by_road.items():
        for a, b in zip(idxs, idxs[1:]):
            d = math.dist(nodes[a]['loc'], nodes[b]['loc'])
            if d > 0.1:
                edges[a][b] = (0.0, d)   # cost 0.0 like Jeju; distance = spacing

    # ---- 2b. connectivity: any node may connect to the nearest node of ANOTHER road -------
    # Endpoint-only linking leaves mid-road merges and on-ramps disconnected, which shows up
    # in game as "the car drives a hundred metres then stops". Search from every node.
    connect_any = float(cfg.get('connect_any_cm', 4000.0))
    # Two roads can be separate actors yet occupy the same corridor (C1 has 11 pairs under a
    # metre apart). Linking those fuses the two lane chains edge-to-edge, so the AI can hop
    # between them. Skip links to a node that is both near and travelling the same way --
    # at a real junction the tangents are perpendicular, so legit links are unaffected.
    parallel_dot = float(cfg.get('parallel_dot', 0.90))
    parallel_skip = float(cfg.get('parallel_skip_cm', 400.0))
    normal_dot = float(cfg.get('normal_dot', 0.85))
    deck_dz = float(cfg.get('deck_dz_cm', 150.0))
    deck_dist = float(cfg.get('deck_dist_cm', 1200.0))
    grade_max = float(cfg.get('grade_max', 0.5))
    cell2 = 2000.0

    def cellkey2(p):
        return (int(p[0] // cell2), int(p[1] // cell2))

    grid_all = {}
    for idx, n in enumerate(nodes):
        grid_all.setdefault(cellkey2(n['loc']), []).append(idx)

    linked = 0
    skipped_parallel = 0
    skipped_normal = 0
    skipped_deck = 0
    skipped_grade = 0
    for idx, n in enumerate(nodes):
        cx, cy = int(n['loc'][0] // cell2), int(n['loc'][1] // cell2)
        best = None
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for j in grid_all.get((gx, gy), ()):
                    if j == idx:
                        continue
                    m = nodes[j]
                    if id(m['road']) == id(n['road']):
                        continue
                    if m['lane'] != n['lane']:
                        continue
                    d = math.dist(n['loc'], m['loc'])
                    if d > connect_any:
                        continue
                    dot = (n['dir'][0] * m['dir'][0] + n['dir'][1] * m['dir'][1]
                           + n['dir'][2] * m['dir'][2])
                    if dot < fdot:
                        continue
                    if dot > parallel_dot and d < parallel_skip:
                        skipped_parallel += 1
                        continue
                    # lateral frame must agree: a link that mirrors the right vector is a
                    # hop to the far side of the carriageway, not a merge
                    rdot = (n['right'][0] * m['right'][0] + n['right'][1] * m['right'][1]
                            + n['right'][2] * m['right'][2])
                    if rdot < normal_dot:
                        skipped_normal += 1
                        continue
                    # stacked decks: near in plan, metres apart in Z. Nothing in the graph
                    # format marks "this is a bridge above that road", so the only signal
                    # is the height difference itself.
                    dz = m['loc'][2] - n['loc'][2]
                    if abs(dz) > deck_dz and d < deck_dist:
                        skipped_deck += 1
                        continue
                    horiz = math.hypot(m['loc'][0] - n['loc'][0], m['loc'][1] - n['loc'][1])
                    if abs(dz) / max(horiz, 1.0) > grade_max:
                        skipped_grade += 1
                        continue
                    if best is None or d < best[0]:
                        best = (d, j)
        if best is not None and best[1] not in edges[idx]:
            edges[idx][best[1]] = (0.0, best[0])
            linked += 1
    log('cross-road links=%d (skipped_parallel=%d normal=%d deck=%d grade=%d)'
        % (linked, skipped_parallel, skipped_normal, skipped_deck, skipped_grade))

    # ---- 2c. lane-change edges: same spline point, adjacent lane, non-zero cost ------------
    lateral_cost = float(cfg.get('lateral_cost', 30.0))
    by_point = {}
    for idx, n in enumerate(nodes):
        by_point.setdefault((id(n['road']), n['k']), []).append(idx)
    lat = 0
    for key, idxs in by_point.items():
        for a in idxs:
            for b in idxs:
                if a == b:
                    continue
                if abs(nodes[a]['lane'] - nodes[b]['lane']) != 1:
                    continue
                if nodes[a]['lane'] * nodes[b]['lane'] <= 0:
                    continue
                d = math.dist(nodes[a]['loc'], nodes[b]['loc'])
                if d > 1.0:
                    edges[a][b] = (lateral_cost, d)
                    lat += 1
    log('lane-change edges=%d' % lat)

    dead_ends = sum(1 for e in edges if not e)
    log('dead_ends=%d' % dead_ends)

    # ---- 3. build the unreal structs ----------------------------------------------
    node_array = []
    for i, n in enumerate(nodes):
        nd = unreal.MTRoadGraphNode()
        nd.set_editor_property('node_index', i)
        nd.set_editor_property('road', n['road'])
        nd.set_editor_property('spline_distance', float(n['s']))
        nd.set_editor_property('absolute_location', unreal.Vector(*n['loc']))
        nd.set_editor_property('direction', unreal.Vector(*n['dir']))
        nd.set_editor_property('right_vector', unreal.Vector(*n['right']))
        nd.set_editor_property('lane', int(n['lane']))
        nd.set_editor_property('spline_point_index', -1)
        nd.set_editor_property('lateral_distance', float(n['lateral']))
        nd.set_editor_property('lateral_offset', 0.0)
        nd.set_editor_property('flags', 0)  # 0 is the most common value in Jeju (6,352 of 17,619)
        nd.set_editor_property('auto_connect_distance', -1.0)
        nd.set_editor_property('speed_limit', float(n['kmh']) * CM_PER_KMH)
        nd.set_editor_property('island_id', 0)
        nd.set_editor_property('crossroad_id', -1)
        nd.set_editor_property('right_side_clearance', -1.0)

        earr = []
        for tgt, (cost, dist) in sorted(edges[i].items()):
            e = unreal.MTRoadGraphNodeEdge()
            e.set_editor_property('node_index', int(tgt))
            e.set_editor_property('cost', float(cost))
            e.set_editor_property('distance', float(dist))
            e.set_editor_property('flags', 0)
            earr.append(e)
        nd.set_editor_property('edges', earr)
        node_array.append(nd)

    data = unreal.MTRoadGraphData()
    data.set_editor_property('nodes', node_array)
    xs = [n['loc'][0] for n in nodes]
    ys = [n['loc'][1] for n in nodes]
    zs = [n['loc'][2] for n in nodes]
    data.set_editor_property('bounds', unreal.Box(
        unreal.Vector(min(xs), min(ys), min(zs)),
        unreal.Vector(max(xs), max(ys), max(zs))))
    nav.set_editor_property('graph_data', data)

    # ---- 4. read back + save -------------------------------------------------------
    back = nav.get_editor_property('graph_data')
    n_back = -1
    try:
        n_back = back.nodes.GetArrayNum() if hasattr(back.nodes, 'GetArrayNum') else len(back.nodes)
    except Exception as e:
        log('readback_fail %s' % e)
    log('readback_nodes=%d' % n_back)

    les.save_current_level()
    log('saved %s' % OUT_LEVEL)

    report = {'roads': len(roads), 'nodes': len(nodes), 'step_cm': step,
              'readback_nodes': n_back, 'cross_links': linked, 'lane_change': lat, 'dead_ends': dead_ends,
              'skipped_parallel': skipped_parallel, 'skipped_normal': skipped_normal,
              'skipped_deck': skipped_deck, 'skipped_grade': skipped_grade,
              'bounds': [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]}
    with open(REPORT, 'w') as f:
        json.dump(report, f, indent=1)
    log('C1BAKE_DONE %s' % json.dumps(report))


try:
    main()
except Exception:
    log('FATAL ' + traceback.format_exc())
    raise
