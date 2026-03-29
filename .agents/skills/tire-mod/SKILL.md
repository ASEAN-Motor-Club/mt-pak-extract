---
name: tire-mod-creation
description: Create MotorTown tire mods — new tire types with custom physics, friction values, and VehicleParts DataTable registration
---

# Tire Mod Creation

Create mod PAKs that add new tire types to MotorTown with custom friction and physics parameters. This skill covers the full pipeline from JSON config to working `.pak` file.

## Quick Start

```bash
nix develop --command bash -c '
python3 scripts/create_tirepack.py \
  --config tire_entries.json \
  --output AMCBetterTires_P.pak
'
```

## Pipeline Overview

| Step | Tool | Input | Output |
|------|------|-------|--------|
| 1. Patch tire physics | C# `--patch-tire` | `tire_entries.json` + `BasicTire_45.uasset` | New tire `.uasset/.uexp` |
| 2a. Add to VehicleParts | C# `--add-tire-parts` | `tire_entries.json` + `VehicleParts.uasset` | Modified `VehicleParts.uasset` |
| 2b. Add to VehicleParts0 | C# `--add-tire-parts` | `tire_entries.json` + `VehicleParts0.uasset` | Modified `VehicleParts0.uasset` |
| 3. Assemble PAK dir | Python | All outputs | Directory structure |
| 4. Build PAK | Rust `mod_pack` | Directory | `.pak` file |

## Configuration

### `tire_entries.json`

```json
{
  "tire_physics": {
    "name": "APF_77_Tire",
    "template": "BasicTire_45",
    "static_mu": 1.5,
    "sliding_mu": 1.3,
    "offroad_friction": 1.8
  },
  "tire_part": {
    "row_name": "APF_77",
    "display_name": ["AMC Police 77"],
    "cost": 2000,
    "mass_kg": 10,
    "vehicle_types": ["Small"],
    "tire_asset_path": "/Game/Cars/Parts/Tire/APF_77_Tire/APF_77_Tire"
  }
}
```

#### Tire Physics Fields

| Field | Description |
|-------|-------------|
| `name` | Internal asset name (becomes the `.uasset` filename) |
| `template` | Base game tire to clone from (filename without extension in `out/`) |
| `static_mu` | Static friction coefficient (grip at rest / low speed) |
| `sliding_mu` | Sliding friction coefficient (grip while skidding) |
| `offroad_friction` | Off-road friction multiplier. Only set if you want offroad capability. Omit to inherit template default. |

#### Tire Part Fields

| Field | Description |
|-------|-------------|
| `row_name` | DataTable row name (visible as internal ID) |
| `display_name` | Array of strings for in-game display (set via `Name2.Texts`) |
| `cost` | In-game purchase price |
| `mass_kg` | Tire mass in kilograms |
| `vehicle_types` | Array: `Small`, `Medium`, `Large`, `HeavyMachine`, `MotorCycle` |
| `tire_asset_path` | UE package path: `/Game/Cars/Parts/Tire/{Name}/{Name}` |

## Base Game Tire Physics Reference

| Tire | StaticMu | SlidingMu | OffroadFriction |
|------|----------|-----------|-----------------|
| BasicTire_45 (standard) | 1.1 | 1.0 | — |
| BasicTire_65 (wider) | 1.1 | 1.0 | — |
| PerformanceTire | — | ~1.0 | — |
| DriftTire | — | 0.85 | — |
| OffroadTire | 0.95 | 0.9 | 1.4 |
| HeavyDutyFront/Rear | — | 0.9 | — |
| HeavyDuty_Load1 | 0.97 | 0.87 | — |
| HeavyMachine_20Ton | 0.95 | 0.88 | 1.2 |

### Recommended Value Ranges

| Feel | StaticMu | SlidingMu | OffroadFriction |
|------|----------|-----------|-----------------|
| Stock-like | 1.0–1.1 | 0.85–1.0 | — |
| Grippy (natural) | 1.3–1.5 | 1.1–1.3 | 1.6–1.8 |
| Racing slick | 1.5–1.7 | 1.3–1.5 | — |
| Unrealistic max grip | 2.0+ | 2.0+ | 2.0+ |

> [!TIP]
> Real-world tire Mu values: road tires ~0.7–1.0, performance ~1.0–1.3, racing slicks ~1.4–1.7. Values above 2.0 feel "glued to the road" and unnatural.

## Critical Rules (Gotchas)

### 1. PAK Path — FLAT, No Subfolder

> [!CAUTION]
> Tire physics assets MUST be placed directly in `Cars/Parts/Tire/`, **not** in a subfolder.

The VehicleParts import uses package path `/Game/Cars/Parts/Tire/{Name}`, which the engine maps to **`Content/Cars/Parts/Tire/{Name}.uasset`**.

```
✅ Tire/APF_77_Tire.uasset               ← engine finds it
❌ Tire/APF_77_Tire/APF_77_Tire.uasset   ← engine CAN'T find it
```

The base game stores all tire assets flat (confirmed by PAK listing). The `tire_asset_path` in config uses `/Game/Cars/Parts/Tire/{Name}/{Name}` format because that's how UE import references work: `{PackagePath}/{ObjectName}`. The first `{Name}` is the package, the second is the object within it. The **file** path uses only the package portion.

**This was the #1 bug that caused friction values to not load — the game silently fell back to default physics.**

### 2. NameMap[0] — Self-Package Reference Must Be Renamed

> [!CAUTION]
> When cloning a tire asset, `NameMap[0]` contains the **old package path** (e.g., `/Game/Cars/Parts/Tire/BasicTire`). This MUST be updated to match the new asset's identity.

Failing to rename this causes the game to misidentify the loaded asset, resulting in default physics values being used (friction shows as blank in the shop UI).

```csharp
// Detect old package path from NameMap[0]
var oldPackagePath = asset.GetNameReference(0)?.Value;

// After renaming exports, update the self-package reference
asset.SetNameReference(0, FString.FromString(newAssetPath));
```

> [!IMPORTANT]
> This is specific to **tire physics assets** (which are standalone DataAssets). For cargo blueprints, NameMap stale entries ARE harmless because blueprints reference their class via imports. Tire physics assets use NameMap[0] as the self-package identifier.

### 3. FName Number Suffix — BasicTire_45 Trap

> [!CAUTION]
> UE's FName system parses trailing `_NN` as an instance Number: `BasicTire_45` is stored as FName(`"BasicTire"`, Number=46). When cloning, the export inherits Number=46, causing the new tire to appear as `APF_77_Tire_45`.

Always use the **direct FName constructor** with explicit Number=0:

```csharp
// ✅ Correct — Number=0, name is exactly "APF_77_Tire"
export.ObjectName = new FName(asset, tireName, 0);

// ❌ Wrong — FName.FromString may parse _77 as Number=78
export.ObjectName = FName.FromString(asset, tireName);
```

This also applies to DataTable row names:
```csharp
// ✅ "APF_77" as literal row name
newRow.Name = new FName(asset, rowName, 0);

// ❌ Parsed as "APF" + Number=78 → displays as "APF_77" but has wrong identity
newRow.Name = FName.FromString(asset, rowName);
```

### 4. VehicleParts0 Override — Must Patch Both DataTables

> [!IMPORTANT]
> The game loads **two** VehicleParts DataTables:
> - `VehicleParts.uasset` (713 rows — full parts catalog)
> - `VehicleParts0.uasset` (50 rows — override/addon table)
>
> `VehicleParts0` **supersedes** `VehicleParts` for tire categories. If your new tire is only in `VehicleParts` but `VehicleParts0` contains all 12 base tires, the game's merged tire list won't include your tire.

**Fix:** Add the tire to BOTH DataTables. The build script runs `--add-tire-parts` twice.

### 5. Template Row Selection — Use Offroad, Not MotorCycleTire

> [!WARNING]
> When cloning a VehicleParts DataTable row as a template, use the **last** tire row (`Offroad`), not the first (`MotorCycleTire_01`).

`MotorCycleTire_01` has motorcycle-specific properties:
- `VehicleTypes = [MotorCycle]` — won't appear for cars
- `TirePhysicsDataAsset_BikeRear` — references a bike-only asset

The `Offroad` row has car-appropriate defaults (`VehicleTypes = [Small, Medium, Large]`, null `BikeRear`).

The code uses "last tire row found" strategy:
```csharp
// Iterate all rows — keep overwriting templateRow for each tire
// Last match = Offroad
templateRow = spd;
```

### 6. Display Name — Name2.Texts Array

> [!IMPORTANT]
> The in-game display name comes from the `Name2` struct's `Texts` array, NOT from `Name` or `Desciption`.

- `Name` — localization hash (GUID). Generate a random one for uniqueness.
- `Name2.Texts` — **actual display strings** shown in the shop UI. Set via `TextPropertyData` with `HistoryType.None`.
- `Desciption` — fallback display / localization key. Set to the display name text.

If `Name2.Texts` is empty and `Desciption` still has the template's hash, the tire displays the template's name (e.g., "Offroad").

### 7. Rename Order Matters

> [!WARNING]
> When patching tire assets, rename in this order:
> 1. **Exports first** (set new FName with Number=0)
> 2. **Imports** (update any references to old name)
> 3. **NameMap last** (clean up stale package path)
>
> If you rename NameMap entries BEFORE exports, the export's old FName (which references the NameMap by index) silently changes to the new string but retains the old Number suffix.

### 8. C# Output Filename — Preserve Template Name

The `--add-tire-parts` command uses `Path.GetFileNameWithoutExtension(templatePath)` for the output filename. This ensures:
- Input `VehicleParts.uasset` → output `VehicleParts.uasset`
- Input `VehicleParts0.uasset` → output `VehicleParts0.uasset`

## Verifying a Built PAK

```bash
# 1. List PAK contents — check flat tire path, both VehicleParts tables present
cargo run --release --bin mod_explore --quiet -- MyTires_P.pak --list

# 2. Dump tire asset internals — verify NameMap, export name, no stale references
cd csharp/CargoExtractor
dotnet run --configuration Release --verbosity quiet -- \
  --dump /path/to/APF_77_Tire.uasset

# Expected output:
#   FolderName: /Game/Cars/Parts/Tire/APF_77_Tire
#   Name[0]: '/Game/Cars/Parts/Tire/APF_77_Tire'     ← NOT BasicTire
#   Export[0]: Name=APF_77_Tire                        ← NOT APF_77_Tire_45

# 3. Binary scan for stale template references
python3 -c "
import re
with open('APF_77_Tire.uasset', 'rb') as f:
    data = f.read()
for m in re.finditer(rb'BasicTire', data):
    print(f'  WARNING: stale BasicTire ref at offset {m.start()}')
"
```

## Diagnostic Checklist

If the tire doesn't appear in-game:
1. **Not in tire list?** → Missing from `VehicleParts0.uasset` (Gotcha #4)
2. **Shows wrong template name?** → `Name2.Texts` not set (Gotcha #6)
3. **Shows but no friction values?** → Asset not loading:
   - File in subfolder instead of flat (Gotcha #1)
   - NameMap[0] still has old package path (Gotcha #2)
   - Export name has `_45` suffix from FName Number (Gotcha #3)
4. **Shows as motorcycle tire only?** → Cloned from MotorCycleTire_01 (Gotcha #5)

## Key Files

| File | Purpose |
|------|---------|
| `scripts/create_tirepack.py` | Orchestrates the full tire mod build pipeline |
| `csharp/CargoExtractor/Program.cs` | C# tool: `--patch-tire`, `--add-tire-parts`, `--dump` |
| `tire_entries.json` | Tire physics + VehicleParts config |
| `out/BasicTire_45.uasset` | Default tire physics template |
| `out/VehicleParts.uasset` | Base game VehicleParts DataTable (713 rows) |
| `out/VehicleParts0.uasset` | Override VehicleParts DataTable (50 rows) |
