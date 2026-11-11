"""Derive per-material roughness / metallic / specular values for the C1 surface MIs.

Why this exists: the importer never read the source's material factors. `make_materials.py`
hardcodes `Roughness 0.65` and `Metallic 0.0` for every scalar material, so 104 materials the
source declares `metallicFactor: 1.0` (real metal) render as plastic, and 24 materials with a
`roughnessFactor` (0.21-0.94) are flattened to 0.65. Both are recoverable from the source;
nothing has to be invented.

Precedence per parameter, highest first:
  1. the source's own `roughnessFactor` / `metallicFactor` (BeamNG Stages[0])
  2. the class default table below (for the 35.8% of mapped area whose source definition is
     colour-map only - the deck has no roughness, metallic, normal or AO anywhere in the source)

Specular has no source data at all: across 1,609 used definitions, zero carry a specular field.
It is therefore class-authored, and it only takes effect once the masters expose a `Specular`
scalar wired to MP_SPECULAR - a value written into an MI for a parameter its master does not
have is silently discarded.

Usage:
    mat_values.py --manifest materials_ue.json --source c1_src.zip \
                  [--out materials_ue_v2.json] [--report mat_values_report.json]
"""
import argparse
import json
import re
import zipfile

# name pattern -> (roughness, specular, metallic_hint, class label)
# Ordered: first match wins. Values follow docs/c1-shuto/SURFACE_RESPONSE_PLAN.md section 7.
CLASSES = [
    (r'(^|_)(line|stripe|paint|marking)', 0.60, 0.50, None, 'marking'),
    (r'asfa|(^|_)road(_|$)|road_0', 0.92, 0.30, None, 'asphalt'),
    (r'sitami|jimen|sidewalk|pavement|pave_', 0.84, 0.35, None, 'paved'),
    (r'guard_rail|(^|_)rail|handrail', 0.45, 0.60, None, 'guardrail'),
    (r'(^|_)metal|steel|iron|chrome', 0.40, 0.60, None, 'metal'),
    (r'glass|window', 0.08, 0.50, None, 'glass'),
    (r'tree|bush|grass|leaf|plant|veg|shrub|hedge', 0.95, 0.25, None, 'vegetation'),
    (r'concrete|(^|_)wall|tile|facade|building|kbs|kbj|kbm|kbk|kbi', 0.86, 0.40, None, 'concrete'),
]
DEFAULT = (0.75, 0.50, None, 'default')


def classify(name):
    low = name.lower()
    for pat, rough, spec, metal, label in CLASSES:
        if re.search(pat, low):
            return rough, spec, metal, label
    return DEFAULT


def load_source_factors(zip_path):
    """name -> {'roughnessFactor','metallicFactor','hasRoughnessMap','hasMetallicMap'}"""
    out = {}
    with zipfile.ZipFile(zip_path) as z:
        for entry in z.namelist():
            if not entry.endswith('materials.json'):
                continue
            try:
                data = json.loads(z.read(entry).decode('utf-8', 'ignore'))
            except Exception:
                continue
            for key, val in (data.items() if isinstance(data, dict) else []):
                if not isinstance(val, dict):
                    continue
                stages = val.get('Stages') or []
                st = stages[0] if stages and isinstance(stages[0], dict) else {}
                out[val.get('name') or key] = {
                    'roughnessFactor': st.get('roughnessFactor'),
                    'metallicFactor': st.get('metallicFactor'),
                    'hasRoughnessMap': 'roughnessMap' in st,
                    'hasMetallicMap': 'metallicMap' in st,
                    'hasAoMap': 'ambientOcclusionMap' in st,
                }
    return out


def master_can_bind(master):
    """Which texture parameters the master actually exposes.

    M_C1_Surface_Tex is the only one built with roughness/metallic maps. M_C1_Surface is scalar
    by design. M_C1_Surface_Masked was built with textured=False, so its 66 materials that ship a
    roughness map in the source silently lose it -- they must keep a scalar value until the master
    gains the parameters, and the count belongs in the report, not in a silent fallback.
    """
    return {
        'M_C1_Surface': set(),
        'M_C1_Surface_Tex': {'roughness', 'metallic'},
        'M_C1_Surface_Masked': set(),
    }.get(master, set())


def build(manifest, factors):
    changes = []
    stats = {'scalar_from_source': 0, 'scalar_from_class': 0,
             'map_bound': 0, 'map_unbindable': 0}
    for e in manifest['materials']:
        name = e['mi'][len('MI_C1_'):] if e['mi'].startswith('MI_C1_') else e['material']
        src = factors.get(name) or factors.get(e['material']) or {}
        rough_def, spec_def, _, label = classify(name)
        bindable = master_can_bind(e['master'])
        slots = e.get('slots') or {}

        scalars = dict(e.get('scalars') or {})
        old_r = scalars.get('Roughness')
        old_m = scalars.get('Metallic')

        entry = {'mi': e['mi'], 'class': label, 'master': e['master'],
                 'roughness': [old_r, old_r, 'unchanged'],
                 'metallic': [old_m, old_m, 'unchanged'],
                 'specular': spec_def, 'unbindable_maps': []}

        for key, factor_key, has_map_key, default in (
                ('roughness', 'roughnessFactor', 'hasRoughnessMap', rough_def),
                ('metallic', 'metallicFactor', 'hasMetallicMap', 0.0)):
            param = key if key != 'roughness' else 'roughness'
            if key in bindable and (key in slots or src.get(has_map_key)):
                scalars.pop(key.capitalize(), None)     # the map drives it; scalar is noise
                entry[key] = [None, None, 'map']
                stats['map_bound'] += 1
                continue
            if src.get(has_map_key) and key not in bindable:
                entry['unbindable_maps'].append(key)
                stats['map_unbindable'] += 1
            factor = src.get(factor_key)
            if factor is not None:
                new = round(float(factor), 3)
                stats['scalar_from_source'] += 1
                why = 'source'
            else:
                new = default
                stats['scalar_from_class'] += 1
                why = 'class'
            scalars[key.capitalize()] = new
            entry[key] = [old_r if key == 'roughness' else old_m, new, why]

        scalars.setdefault('Specular', spec_def)

        if entry['roughness'][2] != 'unchanged' or entry['metallic'][2] != 'unchanged' \
                or entry['unbindable_maps']:
            changes.append(entry)
        e['scalars'] = scalars
        e['value_class'] = label
        e['value_source'] = {'roughness': entry['roughness'][2],
                             'metallic': entry['metallic'][2]}
        if entry['unbindable_maps']:
            e['unbindable_maps'] = entry['unbindable_maps']
    return changes, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--source', required=True)
    ap.add_argument('--out')
    ap.add_argument('--report', default='mat_values_report.json')
    a = ap.parse_args()

    manifest = json.load(open(a.manifest))
    factors = load_source_factors(a.source)
    before = len(manifest['materials'])
    changes, stats = build(manifest, factors)
    after = len(manifest['materials'])
    assert before == after, 'entry count changed'

    by_class = {}
    for c in changes:
        by_class.setdefault(c['class'], 0)
        by_class[c['class']] += 1

    metals = sum(1 for c in changes
                 if c['metallic'][2] == 'source' and c['metallic'][1] and c['metallic'][1] > 0.5)
    report = {
        'entries': after,
        'changed': len(changes),
        'by_class': dict(sorted(by_class.items(), key=lambda kv: -kv[1])),
        'metallic_from_source_over_0.5': metals,
        'roughness_from_source': sum(1 for c in changes if c['roughness'][2] == 'source'),
        'stats': stats,
        'unbindable_maps': sorted((c['mi'], c['unbindable_maps']) for c in changes
                                  if c['unbindable_maps']),
        'changes': changes,
    }
    json.dump(report, open(a.report, 'w'), indent=1)
    if a.out:
        json.dump(manifest, open(a.out, 'w'), indent=1)

    print('MAT_VALUES entries=%d changed=%d metallic_source>0.5=%d roughness_source=%d'
          % (after, len(changes), metals, report['roughness_from_source']))
    print('MAT_VALUES classes %s' % report['by_class'])
    for c in changes[:6]:
        print('  %-34s %-10s rough %s->%s (%s) metal %s->%s (%s) spec %s'
              % (c['mi'][:34], c['class'], c['roughness'][0], c['roughness'][1], c['roughness'][2],
                 c['metallic'][0], c['metallic'][1], c['metallic'][2], c['specular']))


if __name__ == '__main__':
    main()
