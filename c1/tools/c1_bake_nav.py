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
    'deck_dz_abs_cm': 250.0,
    'deck_dist_cm': 1200.0,
    # and the long shallow version of the same defect
    'grade_max': 0.25,
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
    lanes_from_width = int(cfg.get('lanes_from_width', 1)) == 1
    rebalanced = 0
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

        # Lanes TILE the carriageway: lane_width * (nf + nb) equals the decal width on every
        # C1 road, so lane centres are measured from the road EDGES, not stacked outward from
        # the spline. Stacking put lane 2 of a 2-lane road at 5.25 m on a road 3.5 m from the
        # centreline -- off the surface, which is why AI vehicles hit barriers and columns.
        total_w = width * float(nf + nb)
        # Lane COUNT from the painted width, which is what BeamNG itself does:
        #   numOfLanesFromRadius(rad1, rad2) = max(1, floor(min(rad1,rad2)*2/3.61 + 0.5))
        # i.e. round(width / 3.61) with a floor of one lane (lua/ge/map.lua). The mod's
        # `lanesLeft: 2` is only read when `autoLanes == false`, so for a default decal the
        # game never used it -- a 4 m decal is ONE lane, not two 2 m lanes. Applying the
        # source rule here keeps the authors' intent and removes the 1.5 m and 7.5 m lanes.
        if lanes_from_width:
            n_canon = int(math.floor(total_w / 361.0 + 0.5))
            n_canon = max(1, min(4, n_canon))
            if n_canon != (nf + nb):
                rebalanced += 1
            nf, nb = n_canon, 0
            width = total_w / float(n_canon)

        lanes = [l for l in range(1, nf + 1)] + [-l for l in range(1, nb + 1)]
        # Sample at multiples of step, then close the chain on the real end. The old
        # `min(length, k*step)` loop emitted a second node a few CENTIMETRES past the last
        # one whenever length was not a multiple of step (94 of 313 chains ended with a
        # 10-27 cm "edge"), which reads as a duplicate waypoint and upsets speed lookahead.
        s_list = []
        k = 0
        while k * step < length - 0.25 * step:
            s_list.append(k * step)
            k += 1
        if not s_list or (length - s_list[-1]) >= 0.25 * step:
            s_list.append(length)
        count = len(s_list)
        first_index = len(nodes)

        for lane in lanes:
            # C1 is a LEFT-hand-traffic map while MotorTown's AI keeps right. Numbering the
            # lanes from the LEFT edge makes the lane the AI prefers (+1) the LHT slow lane,
            # instead of the overtaking lane next to the oncoming carriageway.
            if lane > 0:
                lateral = -total_w / 2.0 + (lane - 0.5) * width   # +1 = leftmost (LHT slow)
            else:
                lateral = total_w / 2.0 - (abs(lane) - 0.5) * width   # -1 = rightmost
            for k, s in enumerate(s_list):
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
                    'lateral': lateral, 'kmh': kmh, 'width': total_w,
                    'road_start': first_index, 'k': k, 'count': count,
                })

    log('sampled nodes=%d' % len(nodes))
    if not nodes:
        raise RuntimeError('no nodes sampled')

    # ---- 1b. travel direction from the chain geometry, not the spline tangent -----------
    # get_direction_at_distance_along_spline returns a NEGATED tangent at isolated samples
    # (24 samples on C1Full). The position is fine, but the node then points back down the
    # road it just came from, which bakes a legal U-turn between two consecutive nodes.
    # Derive the direction from the chord to the next sample of the same lane instead; the
    # last node inherits the previous direction.
    chains = {}
    for idx, n in enumerate(nodes):
        chains.setdefault((id(n['road']), n['lane']), []).append(idx)
    fixed_dirs = 0
    for key, idxs in chains.items():
        for k in range(len(idxs) - 1):
            i, j = idxs[k], idxs[k + 1]
            dx = nodes[j]['loc'][0] - nodes[i]['loc'][0]
            dy = nodes[j]['loc'][1] - nodes[i]['loc'][1]
            dz = nodes[j]['loc'][2] - nodes[i]['loc'][2]
            L = math.sqrt(dx * dx + dy * dy + dz * dz)
            if L < 1.0:
                continue
            nd = (dx / L, dy / L, dz / L)
            if nodes[i]['lane'] < 0:      # oncoming lanes travel against the spline
                nd = (-nd[0], -nd[1], -nd[2])
            cur = nodes[i]['dir']
            if cur[0] * nd[0] + cur[1] * nd[1] + cur[2] * nd[2] < 0.9:
                nodes[i]['dir'] = nd
                fixed_dirs += 1
        if len(idxs) >= 2:
            nodes[idxs[-1]]['dir'] = nodes[idxs[-2]]['dir']
    # keep the stored right vector consistent with the (corrected) travel direction:
    # right-of-travel for Z-up is up x dir
    for n in nodes:
        dx, dy, _dz = n['dir']
        L = math.hypot(dx, dy) or 1.0
        n['right'] = (-dy / L, dx / L, 0.0)
    log('direction fixed from chords: %d nodes' % fixed_dirs)

    # ---- 2. edges: along each lane, plus nearest neighbours at road ends ------------
    connect = float(cfg['connect_cm'])
    fdot = float(cfg['forward_dot'])
    back_cos = float(cfg.get('back_cos', 0.2))
    by_road = {}
    for idx, n in enumerate(nodes):
        by_road.setdefault((id(n['road']), n['lane']), []).append(idx)

    edges = [dict() for _ in nodes]     # target -> (cost, distance)
    u_turn_blocked = 0
    for key, idxs in by_road.items():
        for a, b in zip(idxs, idxs[1:]):
            d = math.dist(nodes[a]['loc'], nodes[b]['loc'])
            if d <= 0.1:
                continue
            # A lane edge is what the pathfinder drives along. If the two sampled positions
            # disagree with the travel frame (dot < 0) the spline doubles back there, and the
            # edge is a legal U-turn in the middle of a highway. Never bake one: the car then
            # has to take the real road (or stop) instead of turning around.
            da, db = nodes[a]['dir'], nodes[b]['dir']
            if sum(x * y for x, y in zip(da, db)) < 0.0:
                u_turn_blocked += 1
                continue
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
    deck_abs = float(cfg.get('deck_dz_abs_cm', 250.0))
    deck_dist = float(cfg.get('deck_dist_cm', 1200.0))
    grade_max = float(cfg.get('grade_max', 0.25))
    # Continuity gate: how far sideways a link may move the car. BeamNG's own lane
    # spacing is width/(2*lanes), so two roads that genuinely continue one lane differ
    # by well under this; anything larger is a jump across open ground or a median.
    max_lateral = float(cfg.get('max_lateral_cm', 190.0))
    cell2 = 2000.0

    def cellkey2(p):
        return (int(p[0] // cell2), int(p[1] // cell2))

    grid_all = {}
    for idx, n in enumerate(nodes):
        grid_all.setdefault(cellkey2(n['loc']), []).append(idx)

    linked = 0
    skipped_parallel = 0
    skipped_normal = 0
    skipped_backward = 0
    skipped_deck = 0
    skipped_grade = 0
    skipped_lateral = 0
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
                    d = math.dist(n['loc'], m['loc'])
                    if d > connect_any:
                        continue
                    dot = (n['dir'][0] * m['dir'][0] + n['dir'][1] * m['dir'][1]
                           + n['dir'][2] * m['dir'][2])
                    if dot < fdot:
                        continue
                    # Headings agreeing is not enough: at a junction where two roads end facing
                    # each other, the reverse of every forward link passes the heading test while
                    # pointing BACKWARDS along the road (179 deg). A vehicle that obeys one halts
                    # and reverses. Require the hop itself to make forward progress.
                    fwd = ((m['loc'][0] - n['loc'][0]) * n['dir'][0]
                         + (m['loc'][1] - n['loc'][1]) * n['dir'][1]
                         + (m['loc'][2] - n['loc'][2]) * n['dir'][2]) / max(d, 1.0)
                    if fwd < back_cos:
                        skipped_backward += 1
                        continue
                    # Continuity: a link must continue the lane the car is in, so the target
                    # has to sit on the source's own heading line. Lane numbers are NOT
                    # comparable across roads once lane counts come from painted width --
                    # lane 1 of a 6 m decal is 1.5 m off centre, lane 1 of a 10 m decal is
                    # 2.5 m off -- so the test is the sideways offset itself, and the lane
                    # index is ignored. Every link older builds made across 5-20 m of open
                    # ground fails here by construction.
                    lat = (m['loc'][0] - n['loc'][0]) * n['right'][0] \
                        + (m['loc'][1] - n['loc'][1]) * n['right'][1] \
                        + (m['loc'][2] - n['loc'][2]) * n['right'][2]
                    if abs(lat) > max_lateral:
                        skipped_lateral += 1
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
                    # A junction is never metres apart in height, and the radius test above
                    # only covers short hops. Long links used to slip through on the grade
                    # test alone (17 m drop over 39 m = 44%, under the old 50% limit), which
                    # is exactly "the car noses off the deck onto the one below".
                    if abs(dz) > deck_abs:
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
    log('u-turn edges blocked=%d' % u_turn_blocked)
    log('lanes rebalanced from painted width=%d' % rebalanced)
    log('cross-road links=%d (skipped_parallel=%d normal=%d deck=%d grade=%d lateral=%d backward=%d)'
        % (linked, skipped_parallel, skipped_normal, skipped_deck, skipped_grade, skipped_lateral,
           skipped_backward))

    # ---- 2c. lane-change edges: diagonal, two stations ahead ------------------------------
    # The old edges joined the same station on the adjacent lane: 3.4 m sideways with zero
    # forward progress, i.e. a 90 deg corner at a 10 m station grid. The AI has to slow to
    # walking pace to obey one, which is the "crawls while changing lanes" report. Pointing
    # the same edge at the neighbouring lane two stations ahead (20 m) makes it a 9.5 deg
    # diagonal: identical lane change, executable at speed. One station ahead is the fallback
    # near a chain end (19 deg), still far from perpendicular.
    lateral_cost = float(cfg.get('lateral_cost', 30.0))
    lane_step = int(cfg.get('lane_change_step', 2))
    idx_of = {}
    for idx, nd in enumerate(nodes):
        idx_of[(id(nd['road']), nd['k'], nd['lane'])] = idx
    lat = 0
    lat_flat = 0
    for idx, nd in enumerate(nodes):
        for dl in (-1, 1):
            nl = nd['lane'] + dl
            if nd['lane'] * nl <= 0:
                continue
            # step 2 first (9.5 deg), then 1 (19 deg), then 0 -- same station, i.e. the old
            # perpendicular hop. Step 0 only ever fires at a chain end, where there is no
            # station ahead to aim at; without it a lane that also failed its cross-road
            # link ends with NO outgoing edge and AI vehicles halt there forever.
            for st in range(lane_step, -1, -1):
                j = idx_of.get((id(nd['road']), nd['k'] + st, nl))
                if j is None:
                    continue
                d = math.dist(nd['loc'], nodes[j]['loc'])
                if d > 1.0:
                    edges[idx][j] = (lateral_cost, d)
                    lat += 1
                    if st == 0:
                        lat_flat += 1
                break
    # rescue: nothing may end with zero outgoing edges. A truly isolated node makes the AI
    # stop the vehicle, so link it to the nearest node on the same road that faces roughly
    # the same way.
    rescued = 0
    for idx, nd in enumerate(nodes):
        if edges[idx]:
            continue
        best = None
        for j in range(len(nodes)):
            if j == idx or nodes[j]['road'] is not nd['road']:
                continue
            dv = math.dist(nd['loc'], nodes[j]['loc'])
            if dv > 3000.0:
                continue
            if sum(nd['dir'][q] * nodes[j]['dir'][q] for q in range(3)) < 0.5:
                continue
            if best is None or dv < best[1]:
                best = (j, dv)
        if best:
            edges[idx][best[0]] = (lateral_cost, best[1])
            rescued += 1
    log('lane-change edges=%d (step=%d stations, %d flat at a chain end, %d rescued)'
        % (lat, lane_step, lat_flat, rescued))

    # ---- 2d. island + crossroad ids -------------------------------------------------
    # Mirrors the two graph passes reconstructed from BuildNavigation (RE notes:
    # mt-sdk-2026-11-04/ROADGRAPH-SYMBOLS.md - FUN_14572e820 labels islands over the
    # edge graph, FUN_14572e030 clusters junction nodes at max(5 m, carriageway width)).
    # IslandId is a connected-component index; CrossroadId is -1 unless the node sits on
    # a link between two different roads and lands inside another road's junction
    # radius; Flags bit 0x4 marks those nodes and edge bit 0 marks merge-eligible edges.
    # The shipping AI may only read Edges - the RE does not prove otherwise - so this is
    # metadata that makes the graph self-consistent, not a claim that it fixes anything.
    def make_uf(n):
        p = list(range(n))

        def find(a):
            while p[a] != a:
                p[a] = p[p[a]]
                a = p[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                p[rb] = ra
        return find, union

    find, union = make_uf(len(nodes))
    for i, es in enumerate(edges):
        for j in es:
            union(i, j)
    remap = {}
    island = [0] * len(nodes)
    for i in range(len(nodes)):
        r = find(i)
        if r not in remap:
            remap[r] = len(remap)
        island[i] = remap[r]

    cand = set()
    for i, es in enumerate(edges):
        for j in es:
            if id(nodes[i]['road']) != id(nodes[j]['road']):
                cand.add(i)
                cand.add(j)

    find2, union2 = make_uf(len(nodes))
    merges = 0
    for i in cand:
        wi = float(nodes[i].get('width', 0.0))
        radius_sq = max(250000.0, wi * wi)      # max(5 m, carriageway width), in cm^2
        for j in edges[i]:
            if j not in cand or id(nodes[i]['road']) == id(nodes[j]['road']):
                continue
            dx = nodes[i]['loc'][0] - nodes[j]['loc'][0]
            dy = nodes[i]['loc'][1] - nodes[j]['loc'][1]
            dz = nodes[i]['loc'][2] - nodes[j]['loc'][2]
            if dx * dx + dy * dy + dz * dz < radius_sq:
                union2(i, j)
                merges += 1
    gmap = {}
    cross = [-1] * len(nodes)
    for i in cand:
        r = find2(i)
        if r not in gmap:
            gmap[r] = len(gmap)
        cross[i] = gmap[r]
    # A junction group of one node is not a junction: it just means "this node links to
    # another road but no other node is inside the merge radius". Keep those nodes at
    # CrossroadId -1 (same as the game's "not at a junction" value) instead of handing
    # the AI thousands of single-node crossroads.
    min_nodes = int(cfg.get('crossroad_min_nodes', 2))
    # Shipped Jeju_World keeps 2,908 nodes at Flags=4 but 6,244 at CrossroadId != -1, so the
    # game's own ids are NOT one-per-candidate-node: a group id there spans nodes we never
    # mark. Our clustering reproduces the union rule the RE recovered but not that spread, so
    # the ids are off by default until the shipped shape is measured properly.
    crossroad_pass = int(cfg.get('crossroad_pass', 0)) != 0
    sizes = {}
    for i in cand:
        if cross[i] != -1:
            sizes[cross[i]] = sizes.get(cross[i], 0) + 1
    kept_groups = {g for g, k in sizes.items() if k >= min_nodes}
    dropped = 0
    for i in cand:
        if cross[i] != -1 and cross[i] not in kept_groups:
            cross[i] = -1
            dropped += 1
    if not crossroad_pass:
        cross = [-1] * len(nodes)
        dropped = 0
    final_groups = {}
    for i in cand:
        if cross[i] != -1:
            final_groups.setdefault(cross[i], len(final_groups))
    for i in cand:
        if cross[i] != -1:
            cross[i] = final_groups[cross[i]]
    log('islands=%d crossroads=%d (singletons dropped=%d nodes, groups with >=%d nodes=%d)'
        % (len(remap), len(final_groups), dropped, min_nodes, len(final_groups)))

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
        nd.set_editor_property('flags', 4 if cross[i] != -1 else 0)
        nd.set_editor_property('auto_connect_distance', -1.0)
        nd.set_editor_property('speed_limit', float(n['kmh']) * CM_PER_KMH)
        nd.set_editor_property('island_id', int(island[i]))
        nd.set_editor_property('crossroad_id', int(cross[i]))
        nd.set_editor_property('right_side_clearance', -1.0)

        earr = []
        for tgt, (cost, dist) in sorted(edges[i].items()):
            e = unreal.MTRoadGraphNodeEdge()
            e.set_editor_property('node_index', int(tgt))
            e.set_editor_property('cost', float(cost))
            e.set_editor_property('distance', float(dist))
            e.set_editor_property('flags', 1 if cross[i] != -1 and cross[tgt] == cross[i] else 0)
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

    # Saving: the nav actor may live in a STREAMED SUBLEVEL (C1Full has it in
    # C1Full_Roads), and save_current_level() only writes the level that is current -
    # the parent. That silently discards the whole bake on the full map. Save the
    # package that owns the actor explicitly, then sweep any other dirty package.
    saved = []
    pkg = ''
    try:
        pkg = str(nav.get_outermost().get_name())
    except Exception as e:
        log('pkg_lookup_fail %s' % e)
    if pkg:
        try:
            unreal.EditorAssetLibrary.save_asset(pkg, only_if_is_dirty=False)
            saved.append(pkg)
        except Exception as e:
            log('save_asset_fail %s' % e)
    try:
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
        saved.append('dirty_packages')
    except Exception as e:
        log('save_dirty_fail %s' % e)
    try:
        les.save_current_level()
        saved.append(OUT_LEVEL)
    except Exception as e:
        log('save_level_fail %s' % e)
    log('saved %s' % (', '.join(saved) or 'NOTHING'))

    report = {'roads': len(roads), 'nodes': len(nodes), 'step_cm': step,
              'readback_nodes': n_back, 'cross_links': linked, 'lane_change': lat, 'dead_ends': dead_ends,
              'u_turn_blocked': u_turn_blocked,
              'skipped_parallel': skipped_parallel, 'skipped_normal': skipped_normal,
              'skipped_backward': skipped_backward,
              'skipped_deck': skipped_deck, 'skipped_grade': skipped_grade,
              'islands': len(remap), 'crossroads': len(final_groups),
              'crossroad_nodes': len(nodes) - sum(1 for x in cross if x == -1),
              'junction_merges': merges,
              'bounds': [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]}
    with open(REPORT, 'w') as f:
        json.dump(report, f, indent=1)
    log('C1BAKE_DONE %s' % json.dumps(report))


try:
    main()
except Exception:
    log('FATAL ' + traceback.format_exc())
    raise
