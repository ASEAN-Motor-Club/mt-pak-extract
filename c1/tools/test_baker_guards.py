"""Offline test harness for c1_bake_nav.py's cross-road linker guards.

Runs the REAL baker file against a stub `unreal` module and synthetic roads, so the
shipped logic — not a reimplementation — is what gets asserted.

Scenarios (all lane 1, width 350, 120 kph):
  RdA  ground level, straight +X                    -> the reference road
  RdB  same plan line, 10 m higher (stacked deck)    -> must NOT link to A
  RdC  merges onto A at 20 deg, same height          -> must link to A
  RdD  crosses A at 50 deg, same height              -> must NOT link (over the cut)
  RdE  runs alongside A, same direction, mirrored
       right vector (far side of the carriageway)    -> must NOT link (normal guard)

    python3 test_baker_guards.py
"""
import json
import math
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BAKER = os.path.join(HERE, 'c1_bake_nav.py')
WORK = os.environ.get('C1_TEST_WORK') or tempfile.mkdtemp(prefix='c1baketest-')


# ---------------------------------------------------------------- stub unreal
class Vec:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __repr__(self):
        return 'Vec(%.0f, %.0f, %.0f)' % (self.x, self.y, self.z)


class Obj:
    """Property bag that mimics get/set_editor_property."""

    def __init__(self, **kw):
        self._p = dict(kw)

    def set_editor_property(self, k, v):
        self._p[k] = v

    def get_editor_property(self, k):
        if k not in self._p:
            raise KeyError(k)
        return self._p[k]


class NodeArr(list):
    def GetArrayNum(self):
        return len(self)


class Spline:
    """Polyline with arc-length parameterisation, constant direction per segment."""

    def __init__(self, pts):
        self.pts = [tuple(p) for p in pts]
        self.seg = []
        total = 0.0
        for a, b in zip(self.pts, self.pts[1:]):
            d = math.dist(a, b)
            self.seg.append((total, total + d, a, b))
            total += d
        self.length = total

    def get_spline_length(self):
        return self.length

    def _at(self, s):
        s = max(0.0, min(self.length, s))
        for s0, s1, a, b in self.seg:
            if s <= s1 or (s0, s1, a, b) is self.seg[-1]:
                t = 0.0 if s1 == s0 else (s - s0) / (s1 - s0)
                p = tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
                d = tuple((b[i] - a[i]) / (s1 - s0) for i in range(3)) if s1 > s0 else (1, 0, 0)
                n = math.sqrt(sum(c * c for c in d)) or 1.0
                d = tuple(c / n for c in d)
                return p, d
        return self.pts[0], (1, 0, 0)

    def get_location_at_distance_along_spline(self, s, space=None):
        return Vec(*self._at(s)[0])

    def get_direction_at_distance_along_spline(self, s, space=None):
        return Vec(*self._at(s)[1])

    def get_right_vector_at_distance_along_spline(self, s, space=None):
        d = self._at(s)[1]
        # UE Z-up: right of +X is +Y, i.e. forward rotated +90 deg about Z
        return Vec(-d[1], d[0], 0.0)


class SplineWithRight(Spline):
    def __init__(self, pts, right):
        super().__init__(pts)
        self._right = right

    def get_right_vector_at_distance_along_spline(self, s, space=None):
        return Vec(*self._right)


class Actor:
    def __init__(self, label, cls, **props):
        self._label = label
        self._cls = cls
        self._p = dict(props)

    def get_class(self):
        return types.SimpleNamespace(get_name=lambda: self._cls)

    def get_actor_label(self):
        return self._label

    def set_actor_label(self, v):
        self._label = v

    def get_name(self):
        return self._label

    def get_outermost(self):
        return self

    def get_editor_property(self, k):
        if k == 'Spline':
            return self._p['Spline']
        if k not in self._p:
            raise KeyError(k)
        return self._p[k]

    def set_editor_property(self, k, v):
        self._p[k] = v


ROAD_A = [(0, 0, 0), (6000, 0, 0)]
ROAD_B = [(500, 0, 1000), (6500, 0, 1000)]                      # deck 10 m up, 5 m staggered
ROAD_C = [(-500, -2000, 0), (6000, 366, 0)]                     # merges at 20 deg
ROAD_D = [(-1000, -3000, 0), (6000, 5345, 0)]                   # crosses at 50 deg
ROAD_G = [(0, 1800, 350), (6000, 1800, 350)]                          # 3.5 m up, 18 m aside: grade 19%
ROAD_E = [(0, 700, 0), (6000, 700, 0)]                          # alongside, mirrored right
ROAD_F = [(0, 0, 0), (0, 0, 0)]                                 # unused placeholder


def build_world():
    roads = [
        Actor('C1_RdA', 'MotorTownRoad', Spline=Spline(ROAD_A), num_forward_lanes=1,
              num_backward_lanes=0, lane_width=350.0, speed_limit_kph=120.0),
        Actor('C1_RdB', 'MotorTownRoad', Spline=Spline(ROAD_B), num_forward_lanes=1,
              num_backward_lanes=0, lane_width=350.0, speed_limit_kph=120.0),
        Actor('C1_RdC', 'MotorTownRoad', Spline=Spline(ROAD_C), num_forward_lanes=1,
              num_backward_lanes=0, lane_width=350.0, speed_limit_kph=120.0),
        Actor('C1_RdD', 'MotorTownRoad', Spline=Spline(ROAD_D), num_forward_lanes=1,
              num_backward_lanes=0, lane_width=350.0, speed_limit_kph=120.0),
        Actor('C1_RdG', 'MotorTownRoad', Spline=SplineWithRight(ROAD_G, (0, -1, 0)),
              num_forward_lanes=1, num_backward_lanes=0, lane_width=350.0,
              speed_limit_kph=120.0),
        Actor('C1_RdE', 'MotorTownRoad', Spline=SplineWithRight(ROAD_E, (0, -1, 0)),
              num_forward_lanes=1, num_backward_lanes=0, lane_width=350.0,
              speed_limit_kph=120.0),
        # 15 m above and 10 m across: outside the deck radius (d = 18 m), so only the
        # grade rule can reject it
        Actor('C1_RdF', 'MotorTownRoad', Spline=Spline([(1000, 0, 1500), (7000, 0, 1500)]),
              num_forward_lanes=1, num_backward_lanes=0, lane_width=350.0,
              speed_limit_kph=120.0),
    ]
    nav = Actor('MotorTownNavigation', 'MotorTownNavigation', graph_data=Obj())
    return roads, nav


def install_unreal(roads, nav):
    u = types.ModuleType('unreal')
    u.log = lambda m: None
    u.log_error = lambda m: print('LOGERR', m)
    u.log_warning = lambda m: None
    u.Vector = Vec
    u.Box = lambda mn, mx: Obj(min=mn, max=mx)
    u.SplineCoordinateSpace = types.SimpleNamespace(WORLD=0)
    u.MTRoadGraphNode = lambda: Obj(edges=[], node_index=-1)
    u.MTRoadGraphNodeEdge = lambda: Obj()
    u.MTRoadGraphData = lambda: Obj()
    u.LevelEditorSubsystem = 'les'
    u.EditorActorSubsystem = 'eas'

    class _LES:
        def load_level(self, p):
            pass

        def save_current_level(self):
            return True

    class _EAS:
        def get_all_level_actors(self):
            return roads + [nav]

    u.EditorAssetLibrary = types.SimpleNamespace(save_asset=lambda *a, **k: True)
    u.EditorLoadingAndSavingUtils = types.SimpleNamespace(save_dirty_packages=lambda *a, **k: True)
    u.get_editor_subsystem = lambda cls: _LES() if cls == 'les' else _EAS()
    sys.modules['unreal'] = u


def main():
    os.environ.setdefault('C1_BAKE_CONFIG', os.path.join(WORK, 'test_nav_bake_config.json'))
    os.environ.setdefault('C1_BAKE_REPORT', os.path.join(WORK, 'test_bake_report.json'))
    cfg = {'limit_roads': 0, 'step_cm': 1000.0, 'connect_cm': 2500.0, 'connect_any_cm': 4000.0,
           'forward_dot': 0.85, 'normal_dot': 0.85, 'deck_dz_cm': 150.0,
           'deck_dist_cm': 1200.0, 'grade_max': 0.25, 'deck_dz_abs_cm': 250.0, 'crossroad_min_nodes': 2, 'crossroad_pass': 1, 'parallel_dot': 0.9,
           'parallel_skip_cm': 400.0, 'lateral_cost': 30.0}
    json.dump(cfg, open(os.environ['C1_BAKE_CONFIG'], 'w'))

    roads, nav = build_world()
    install_unreal(roads, nav)

    src = open(BAKER).read()
    try:
        exec(compile(src, BAKER, 'exec'), {'__name__': '__main__'})
    except SystemExit:
        pass

    data = nav.get_editor_property('graph_data')
    nodes = data.get_editor_property('nodes')
    print('baked nodes:', len(nodes))

    # node -> road label
    roads_of = []
    for i in range(len(nodes)):
        nd = nodes[i]
        roads_of.append(nd.get_editor_property('road').get_actor_label())
    edges = []
    for i in range(len(nodes)):
        es = nodes[i].get_editor_property('edges')
        edges.append([(e.get_editor_property('node_index'), e.get_editor_property('cost'))
                      for e in es])

    def links(src_road, dst_road):
        out = []
        for i, es in enumerate(edges):
            if roads_of[i] != src_road:
                continue
            for tgt, cost in es:
                if cost == 0 and roads_of[tgt] == dst_road:
                    out.append((i, tgt))
        return out

    checks = []

    def check(name, ok, detail=''):
        checks.append((name, ok, detail))
        print(('PASS ' if ok else 'FAIL ') + name + ('  ' + detail if detail else ''))

    a_to_b = links('C1_RdA', 'C1_RdB') + links('C1_RdB', 'C1_RdA')
    check('stacked deck (10 m above) not linked', not a_to_b, '%d links' % len(a_to_b))

    c_to_a = links('C1_RdC', 'C1_RdA') + links('C1_RdA', 'C1_RdC')
    check('20 deg merge still linked', bool(c_to_a), '%d links' % len(c_to_a))

    d_to_a = links('C1_RdD', 'C1_RdA') + links('C1_RdA', 'C1_RdD')
    check('50 deg cut rejected', not d_to_a, '%d links' % len(d_to_a))

    e_to_a = links('C1_RdE', 'C1_RdA') + links('C1_RdA', 'C1_RdE')
    check('mirrored right vector rejected', not e_to_a, '%d links' % len(e_to_a))

    g_to_a = links('C1_RdG', 'C1_RdA') + links('C1_RdA', 'C1_RdG')
    check('height jump beyond the deck radius rejected', not g_to_a, '%d links' % len(g_to_a))

    f_to_a = links('C1_RdF', 'C1_RdA') + links('C1_RdA', 'C1_RdF')
    check('steep link outside deck radius rejected', not f_to_a, '%d links' % len(f_to_a))

    # sampling regression: 1 lane, 10 m spacing => 7 nodes for a 60 m road
    check('node count sane', len(nodes) >= 30, '%d nodes' % len(nodes))

    # --- RE pass: island / crossroad / flags consistency ---
    isl = [nodes[i].get_editor_property('island_id') for i in range(len(nodes))]
    xid = [nodes[i].get_editor_property('crossroad_id') for i in range(len(nodes))]
    flg = [nodes[i].get_editor_property('flags') for i in range(len(nodes))]

    check('island ids are per-component', len(set(isl)) >= 2,
          '%d islands' % len(set(isl)))
    check('flags bit 0x4 matches crossroad_id',
          all((f & 4 != 0) == (x != -1) for f, x in zip(flg, xid)),
          '%d junction nodes' % sum(1 for x in xid if x != -1))
    edge_ok = True
    for i in range(len(nodes)):
        for e in nodes[i].get_editor_property('edges'):
            ef = e.get_editor_property('flags')
            t = e.get_editor_property('node_index')
            if ef == 1 and not (xid[i] != -1 and xid[i] == xid[t]):
                edge_ok = False
    check('edge flags only inside one crossroad group', edge_ok)

    # --- shipped default: crossroad_pass off must leave -1 / 0 everywhere ---
    cfg0 = dict(cfg, crossroad_pass=0)
    json.dump(cfg0, open(os.environ['C1_BAKE_CONFIG'], 'w'))
    roads2, nav2 = build_world()
    install_unreal(roads2, nav2)
    try:
        exec(compile(src, BAKER, 'exec'), {'__name__': '__main__'})
    except SystemExit:
        pass
    n2 = nav2.get_editor_property('graph_data').get_editor_property('nodes')
    check('crossroad_pass=0 writes shipped defaults',
          all(n.get_editor_property('crossroad_id') == -1 and
              n.get_editor_property('flags') == 0 for n in n2),
          '%d nodes' % len(n2))
    check('crossroad_pass=0 still writes island ids',
          len({n.get_editor_property('island_id') for n in n2}) == len(set(isl)),
          '%d islands' % len({n.get_editor_property('island_id') for n in n2}))

    report = json.load(open(os.environ['C1_BAKE_REPORT']))
    print('\nreport:', {k: report[k] for k in
                        ('cross_links', 'skipped_parallel', 'skipped_normal',
                         'skipped_deck', 'skipped_grade', 'islands', 'crossroads',
                         'junction_merges') if k in report})

    bad = [c for c in checks if not c[1]]
    print('\n%d/%d checks passed' % (len(checks) - len(bad), len(checks)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
