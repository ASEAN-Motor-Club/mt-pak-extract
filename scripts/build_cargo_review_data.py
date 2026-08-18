#!/usr/bin/env python3
"""Parse cargo-improvement.md into structured data the wiki generator consumes.

The review document carries the exact Round-0 values inline. Parsing it directly
(and verifying counts) is more reliable than hand-keying 87 cargo tables.

Outputs: scripts/cargo_review_data.json
"""
import json
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else \
    "/opt/data/cache/documents/doc_fbfedf11d942_cargo-improvement.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else \
    "scripts/cargo_review_data.json"

text = open(SRC, encoding="utf-8").read()
lines = text.splitlines()


def section(start_marker, end_markers):
    si = None
    for i, ln in enumerate(lines):
        if ln.startswith(start_marker):
            si = i
            break
    if si is None:
        raise SystemExit(f"marker not found: {start_marker}")
    ei = len(lines)
    for i in range(si + 1, len(lines)):
        if any(lines[i].startswith(m) for m in end_markers):
            ei = i
            break
    return si, ei


# ---- Task 2: names (markdown table, 3 cols: slug | current | correct) ----
si, ei = section("## Task 2", ["## Task 3"])
names = {}
for ln in lines[si:ei]:
    if not ln.startswith("| "):
        continue
    cells = [c.strip() for c in ln.strip().strip("|").split("|")]
    if len(cells) < 3 or not cells[0] or set(cells[0]) <= {"-"}:
        continue
    if cells[1].startswith("Current") and cells[2].startswith("Correct"):
        continue
    names[cells[0]] = cells[2]
print(f"Task 2 names: {len(names)}")

# ---- Task 3: weights (md table, 3 cols: slug | current | correct range) ----
si, ei = section("## Task 3", ["## Task 4"])
weights = {}
for ln in lines[si:ei]:
    if not ln.startswith("| "):
        continue
    cells = [c.strip() for c in ln.strip().strip("|").split("|")]
    if len(cells) < 3 or not cells[0] or set(cells[0]) <= {"-"}:
        continue
    # data row: slug | mesh mass | weight range (or single value)
    if cells[2].endswith("kg"):
        weights[cells[0]] = cells[2]
print(f"Task 3 weights: {len(weights)}")

# ---- Task 5: cargo_space aggregates ----
si, ei = section("## Task 5", ["## Task 6"])
space_aggregates = {}
cur_type = None
for ln in lines[si:ei]:
    t = ln.strip()
    if t.startswith("### ") and not t.startswith("### N/A"):
        cur_type = t[4:].strip().rstrip(":").strip()
        space_aggregates[cur_type] = {"cargos": [], "vehicles": [], "parts": []}
        continue
    if cur_type is None:
        continue
    m = re.match(r"-\s*\*\*(Cargos|Vehicles|Parts)\*\*\s*\((\d+)\):\s*(.*)", t)
    if not m:
        continue
    key = m.group(1).lower()
    declared = int(m.group(2))
    body = m.group(3)
    if declared == 0 or body.strip() in ("—", "-"):
        continue
    if key == "cargos":
        # entries are "Name (slug), Name (slug)"
        pairs = re.findall(r"([^(),]+?)\s+\(([^()]+)\)", body)
        for name, slug in pairs:
            space_aggregates[cur_type][key].append(
                {"name": name.strip(), "slug": slug.strip()}
            )
    else:
        # entries are comma-separated names only
        for nm in [x.strip() for x in body.split(",") if x.strip()]:
            space_aggregates[cur_type][key].append({"name": nm})
    if declared != len(space_aggregates[cur_type][key]):
        print(f"  WARN {cur_type} {key}: declared {declared} got "
              f"{len(space_aggregates[cur_type][key])}")
print(f"Task 5 space types: {len(space_aggregates)}")

# ---- Task 8: production/dropoff per cargo ----
si, ei = section("## Task 8", ["## Task 9"])
production = {}
cur_slug = None
for ln in lines[si:ei]:
    t = ln.strip()
    m = re.match(r"### .+ \(([^)]+)\)$", t)
    if m:
        cur_slug = m.group(1).strip().strip("`")
        production[cur_slug] = {"produced": [], "dropoff": []}
        continue
    if cur_slug is None:
        continue
    pm = re.match(r"-\s*\*\*(Produced at|Dropoff at):\*\*\s*(.*)", t)
    if not pm:
        continue
    kind = "produced" if pm.group(1) == "Produced at" else "dropoff"
    body = pm.group(2).strip()
    if body in ("—", ""):
        continue
    for entry in body.split("; "):
        parts = [p.strip() for p in entry.split("|")]
        loc = parts[0]
        inputs = parts[1] if len(parts) > 1 else None
        time = parts[-1] if len(parts) > 1 else None
        production[cur_slug][kind].append({
            "loc": loc,
            "inputs": inputs if inputs not in ("—", "") else None,
            "time": time if time not in ("—", "") else None,
        })
print(f"Task 8 cargos: {len(production)}")

data = {
    "names": names,
    "weights": weights,
    "space_aggregates": space_aggregates,
    "production": production,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=1, ensure_ascii=False)
print(f"Wrote {OUT}")