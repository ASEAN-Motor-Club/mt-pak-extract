---
name: vehicle-parts-mod-creation
description: Create MotorTown vehicle part mods — tires (with custom physics DataAssets) and intakes (inline sub-struct tuning). Covers VehicleParts DataTable mechanics, PartType sub-structs, dot-path patching, and compat-mod support.
---

# Vehicle Parts Mod Creation

Create mod PAKs that add new vehicle parts to MotorTown. This skill covers **tire mods** (with separate physics DataAssets) and **intake mods** (with inline sub-struct tuning), plus the shared VehicleParts DataTable mechanics that apply to all part types.

## Part Types Overview

Every VehicleParts row contains ALL part sub-structs (Tire, Intake, Turbocharger, Suspension, etc.), with `PartType` determining which the engine reads:

```
PartType: Tire
├── Tire.TirePhysicsDataAsset → import reference to separate physics asset
├── VehicleTypes: [Small, Medium]
├── VehicleKeys: [Elisa_Police, ...]
├── LevelRequirementToBuy: {CL_Police: 10}
├── Cost, MassKg, Name2.Texts, etc.
└── ... (all other sub-structs present but inactive)

PartType: Intake
├── Intake.Slope → torque curve slope
├── Intake.BaseRPMRatio → RPM ratio where effect begins
├── Intake.IntakeSpeedEfficencyMultiplier → overall HP multiplier
├── Common fields (VehicleTypes, VehicleKeys, Cost, etc.)
└── ... (all other sub-structs present but inactive)

PartType: Turbocharger
├── Turbocharger.bIsValid → must be true
├── Turbocharger.TorqueMultiplier, BaseTorqueMultiplier
├── Turbocharger.TurbineWeight → spool time
├── Turbocharger.IntakePressureMultiplier, TurbineAspectRatio
├── Turbocharger.HeatingMultiplier, FuelConsumptionMultiplier
├── Common fields
└── ...
```

> [!IMPORTANT]
> Only patch `VehicleParts0` (50 rows), NOT `VehicleParts` (713 rows). This minimizes conflict surface with other mods. See `general-modding` skill for details.

---

## Tire Mods

### Quick Start

```bash
# Standalone
nix develop --command bash -c 'python3 scripts/mods.py build police-tyres'

# Or directly:
nix develop --command bash -c '
python3 scripts/create_tirepack.py \
  --config mods/police-tyres/tire_entries.json \
  --output ASEAN_PoliceTyres_P.pak
'

# Compatible with another mod
nix develop --command bash -c '
python3 scripts/create_tirepack.py \
  --config mods/police-tyres/tire_entries.json \
  --output ASEAN_PoliceTyres_MoreTuningCompat_P.pak \
  --compat-mod path/to/qxZap_MoreTuning_P.pak
'
```

### Pipeline

| Step | Tool | Input | Output |
|------|------|-------|--------|
| 0. Extract compat base | Rust `mod_explore` | `--compat-mod` PAK | VehicleParts0 template |
| 1. Patch tire physics | C# `--patch-tire` | `tire_entries.json` + `BasicTire_45.uasset` | New tire `.uasset/.uexp` |
| 2. Add to VehicleParts0 | C# `--add-tire-parts` | `tire_entries.json` + `VehicleParts0.uasset` | Modified `VehicleParts0.uasset` |
| 3. Assemble PAK dir | Python | All outputs | Directory structure |
| 4. Build PAK | Rust `mod_pack` | Directory | `.pak` file |

### Configuration (`tire_entries.json`)

```json
{
  "tires": [
    {
      "tire_physics": {
        "name": "APF_79_Tire",
        "template": "BasicTire_45",
        "static_mu": 1.6,
        "sliding_mu": 1.3,
        "offroad_friction": 1.4,
        "spring_x": 150000
      },
      "tire_part": {
        "row_name": "APF_79",
        "display_name": ["AMC Police 79"],
        "cost": 2000,
        "mass_kg": 10,
        "vehicle_types": ["Small"],
        "vehicle_keys": ["Elisa_Police", "Muhan_Police", "Zydro_Police"],
        "level_requirement": {"CL_Police": 10},
        "tire_asset_path": "/Game/Cars/Parts/Tire/APF_79_Tire/APF_79_Tire"
      }
    }
  ]
}
```

#### Tire Physics Fields

| Field | Default | Description |
|-------|---------|-------------|
| `name` | required | Internal asset name (becomes `.uasset` filename) |
| `template` | required | Base game tire to clone from (filename in `out/`) |
| `static_mu` | inherited | Static friction coefficient (grip at rest) |
| `sliding_mu` | inherited | Sliding friction coefficient |
| `offroad_friction` | inherited | Off-road friction multiplier |
| `spring_x` | inherited (180000) | Lateral stiffness — lower reduces rollover |
| `spring_y` | inherited | Longitudinal stiffness |
| `damping_x` | inherited | Lateral damping |
| `damping_y` | inherited | Longitudinal damping |

#### Tire Part Fields

| Field | Default | Description |
|-------|---------|-------------|
| `row_name` | required | DataTable row name |
| `display_name` | required | Array for in-game display (`Name2.Texts`) |
| `cost` | required | Purchase price |
| `mass_kg` | `10` | Tire mass |
| `vehicle_types` | required | `Small`, `Medium`, `Large`, `HeavyMachine`, `MotorCycle` |
| `vehicle_keys` | `[]` (all) | Restrict to specific vehicles |
| `level_requirement` | `{}` (none) | Career level gate |
| `tire_asset_path` | required | UE path: `/Game/Cars/Parts/Tire/{Name}/{Name}` |

### Base Game Tire Physics Reference

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

### Recommended Tire Value Ranges

| Feel | StaticMu | SlidingMu | OffroadFriction | SpringX |
|------|----------|-----------|-----------------|----------|
| Stock-like | 1.0–1.1 | 0.85–1.0 | — | 180000 |
| Cruiser (mild upgrade) | 1.3–1.4 | 1.1–1.2 | 1.3 | 180000 |
| Anti-rollover pursuit | 1.5–1.6 | 1.2–1.4 | 1.4 | 130000–150000 |
| High-grip pursuit | 1.6–1.8 | 1.4–1.6 | 1.6 | 180000 |
| Racing slick | 1.8–2.0 | 1.5–1.7 | — | 180000 |
| Unrealistic max grip | 2.0+ | 2.0+ | 2.0+ | 200000+ |

> [!WARNING]
> **Rollover risk:** High StaticMu (1.8+) on tall vehicles (SUVs, police cars) generates so much lateral G-force that the car rolls over instead of sliding. Fix: lower SpringX to ~150000, or reduce StaticMu to ~1.5.

### Tire Gotchas

1. **PAK Path — FLAT, No Subfolder:** Tire physics assets MUST be in `Cars/Parts/Tire/` directly, not in a subfolder. The engine maps `/Game/Cars/Parts/Tire/{Name}` to `Content/Cars/Parts/Tire/{Name}.uasset`.

2. **NameMap[0] — Must Rename:** When cloning a tire, `NameMap[0]` has the old package path. Must update it or the game uses default physics.

3. **FName Number Suffix:** `BasicTire_45` is stored as FName(`"BasicTire"`, Number=46). Always use `new FName(asset, name, 0)` to avoid stale Number suffixes.

4. **VehicleParts0 Override:** Game loads both `VehicleParts` (713 rows) and `VehicleParts0` (50 rows). VehicleParts0 supersedes for shared categories. Add tire to BOTH.

5. **Template Row Selection:** Use the last tire row (`Offroad`), not `MotorCycleTire_01` which has bike-only properties.

6. **Display Name:** In-game name comes from `Name2.Texts`, NOT `Name` or `Desciption`.

7. **Rename Order:** Exports → Imports → NameMap. Renaming NameMap first causes silent corruption.

8. **Pure Digit Row Names:** `APF_78` gets parsed as FName(`"APF"`, Number=79), causing save/load mismatches and disappearing tires. Append a letter: `APF_78A`.

---

## Intake Mods

### Quick Start

```bash
# Standalone
nix develop --command bash -c 'python3 scripts/mods.py build police-sc'

# Or directly:
nix develop --command bash -c '
python3 scripts/create_intakepack.py \
  --config mods/police-sc/intake_entries.json \
  --output AMC_PDParts_P.pak
'

# Compatible with other mods
nix develop --command bash -c '
python3 scripts/create_intakepack.py \
  --config mods/police-sc/intake_entries.json \
  --output AMC_PDParts_MoreTuningCompat_P.pak \
  --compat-mod path/to/qxZap_MoreTuning_P.pak
'
```

### Pipeline

| Step | Tool | Input | Output |
|------|------|-------|--------|
| 0. Extract compat base | Rust `mod_explore` | `--compat-mod` PAK | VehicleParts0 template |
| 1. Add rows to VehicleParts0 | C# `--add-rows` | `intake_entries.json` + `VehicleParts0.uasset` | Modified `VehicleParts0.uasset` |
| 2. Assemble PAK dir | Python | DataTable output | Directory structure |
| 3. Build PAK | Rust `mod_pack` | Directory | `.pak` file |

> No `transform_assets()` step — intake parts don't need separate physics assets like tires.

### How Intake Parts Work

An Intake row has 3 tunable fields in the `Intake` sub-struct:

| Field | Effect |
|-------|--------|
| `Slope` | Torque curve slope — higher positive = more torque bias at peak RPM |
| `BaseRPMRatio` | RPM ratio where effect kicks in — lower = earlier power delivery |
| `IntakeSpeedEfficencyMultiplier` | Overall efficiency multiplier — higher = more horsepower |

### Supercharger Simulation

Intake parts can simulate superchargers by tuning for instant response and high top-end power:

| Characteristic | Supercharger tuning | Turbocharger comparison |
|---------------|--------------------|-----------------------|
| Response | Low `BaseRPMRatio` (0.1–0.3) = instant boost | Turbo has lag (spool via `TurbineWeight`) |
| Torque | Moderate `Slope` (0.05–0.15) | Higher `TorqueMultiplier` (1.1–1.2) |
| Horsepower | High `EfficiencyMult` (2.0–2.5+) | High `IntakePressureMultiplier` (0.5–0.8) |

> [!TIP]
> A supercharger's defining characteristic is **immediate response** (low BaseRPMRatio) with **linear power delivery** (steady Slope). Turbos have delayed response (spool) but higher peak torque.

### Vanilla Game Values (v0.7.18+1)

**Intake rows:**

| Row | Slope | BaseRPMRatio | EfficiencyMult | Cost |
|-----|-------|-------------|----------------|------|
| Row 201 (GUID) | 0.1 | 0.7 | 1.5 | 300 |
| Row 202 (GUID) | -0.1 | 0.8 | 0.7 | 300 |

**Turbocharger rows (for comparison):**

| Row | TorqueMult | BaseTorqueMult | IntakePressMult | TurbineWeight | Cost |
|-----|-----------|---------------|----------------|--------------|------|
| Stock (Small) | 1.1 | 0.98 | 1.0 | 30 | 3,000 |
| Stage1 (Small) | 1.2 | 0.95 | 0.5/0.8 | 100 | 10,000 |
| Stock (HeavyDuty) | 1.1 | 0.98 | 1.0 | 30 | 10,000 |
| Stage1 (HeavyDuty) | 1.2 | 0.95 | 0.5/0.8 | 100 | 30,000 |
| Stock (HeavyMachine) | 1.1 | 0.98 | 1.0 | 30 | 50,000 |

### Recommended Intake Tuning Ranges

| Feel | Slope | BaseRPMRatio | EfficiencyMult |
|------|-------|-------------|----------------|
| Mild upgrade | 0.05 | 0.3 | 1.5–2.0 |
| Sport intake | 0.1 | 0.2 | 2.0–2.2 |
| Supercharger (street) | 0.1 | 0.1–0.15 | 2.0–2.3 |
| Supercharger (pursuit) | 0.15 | 0.1 | 2.3–2.5 |
| Extreme | 0.2+ | 0.05 | 2.5+ |

> [!WARNING]
> Negative `Slope` (like vanilla Row 202 with -0.1) reduces torque at high RPM. For "strongest" superchargers, use **positive** Slope with high EfficiencyMult — this gives both torque AND horsepower.

### Configuration (`intake_entries.json`)

```json
{
  "intakes": [
    {
      "row_name": "PD_SC_Standard",
      "display_name": ["PD SC Standard"],
      "cost": 5000,
      "mass_kg": 5.0,
      "vehicle_types": ["Small"],
      "vehicle_keys": ["Elisa_Police", "Muhan_Police"],
      "level_requirement": {"CL_Police": 10},
      "intake": {
        "Slope": 0.05,
        "BaseRPMRatio": 0.3,
        "IntakeSpeedEfficencyMultiplier": 2.0
      }
    }
  ]
}
```

#### Intake Entry Fields

| Field | Default | Description |
|-------|---------|-------------|
| `row_name` | required | DataTable row name |
| `display_name` | required | Array for in-game display |
| `cost` | required | Purchase price |
| `mass_kg` | `5.0` | Part mass |
| `vehicle_types` | required | Vehicle class filter |
| `vehicle_keys` | `[]` (all) | Restrict to specific vehicles |
| `level_requirement` | `{}` (none) | Career level gate |
| `intake.Slope` | inherited | Torque curve slope |
| `intake.BaseRPMRatio` | inherited | RPM ratio where effect begins |
| `intake.IntakeSpeedEfficencyMultiplier` | inherited | Overall HP multiplier |

### Intake Gotchas

1. **No Separate Physics Asset:** All tuning is inline in the VehicleParts row. PAK only contains `VehicleParts0.uasset` + `.uexp` — no extra files.

2. **PartType Must Be Intake:** The `template_row_match` ensures the cloned row has `PartType = Intake`. Wrong template = game ignores the Intake sub-struct.

3. **Positive Slope = Stronger:** Higher positive `Slope` = more torque at peak RPM. Negative `Slope` reduces high-end torque. For strongest superchargers, use positive Slope + high EfficiencyMult.

4. **BaseRPMRatio Below 0.5 = Instant Response:** Vanilla has 0.7–0.8 (boost at 70–80% RPM). Supercharger feel: 0.1–0.3 (boost from 10–30% RPM).

---

## Shared Mechanics

### Dot-Path Resolution Through Sub-Structs

The C# `--add-rows` command uses `ResolvePropertyWithContainer` to resolve dot-separated paths through `StructPropertyData` containers:

```
"Intake.Slope" → finds "Intake" StructPropertyData → traverses into it → finds "Slope" FloatPropertyData
```

Works with `set_or_add_float`, `set_or_create_name`, `set_or_create_int`, etc. Only ONE level of dot-path nesting is needed for VehicleParts sub-structs (e.g., `Intake.Slope`, `Turbocharger.bIsValid`).

### Template Row Matching

`--add-rows` uses `template_row_match` to find an existing row as the clone template. The `*` wildcard does a substring match on the field value:

```json
// For intakes
"template_row_match": {"PartType": "*Intake*"}

// For tires (handled internally by --add-tire-parts)
// Uses "last tire row found" strategy → Offroad
```

> [!IMPORTANT]
> If no row matches, the C# tool falls back to the **last row** in the DataTable, which may be a completely different part type. Always verify the template row in build output.

### Row Chaining

Rows are added **sequentially** — each new row is appended to the output of the previous step:

```
VehicleParts0 (45 rows) → +Row1 → (46) → +Row2 → (47) → +Row3 → (48)
```

### Compat-Mod Support

Both tire and intake mods support `--compat-mod` for building on top of other mods' VehicleParts0:

```bash
# Chain: AMC Tires MoreTuningCompat PAK already has both mods' rows
# → adding intakes on top produces PAK with all three mods
python3 scripts/create_intakepack.py \
  --config mods/police-sc/intake_entries.json \
  --output zzz_AMC_PDParts_MoreTuningCompat_P.pak \
  --compat-mod zzz_ASEAN_PoliceTyres_v0.2.0_MoreTuningCompat_P.pak
```

> [!CAUTION]
> Users must install **only one variant**. Both standalone + compat causes double-override on VehicleParts0.

### Display Name (`Name2.Texts`)

The in-game display name comes from the `Name2` struct's `Texts` array, NOT from `Name` or `Desciption`:

- `Name` — localization hash (GUID). Generate random for uniqueness.
- `Name2.Texts` — **actual display strings** shown in the shop UI.
- `Desciption` — fallback / localization key.

If `Name2.Texts` is empty and `Desciption` still has the template's hash, the part displays the template's name (e.g., "Offroad").

---

## Verifying a Built PAK

```bash
# List PAK contents
cargo run --release --bin mod_explore --quiet -- MyMod_P.pak --list

# Dump asset internals
cd csharp/UAssetTool
dotnet run --configuration Release --verbosity quiet -- \
  --dump /path/to/extracted/asset.uasset

# Binary scan for stale template references
python3 -c "
import re
with open('asset.uasset', 'rb') as f:
    data = f.read()
for m in re.finditer(rb'BasicTire|OldTemplate', data):
    print(f'Stale ref at offset {m.start()}: {m.group()}')
"
```

## Diagnostic Checklist

| Symptom | Likely Cause |
|---------|-------------|
| Part not in list | Missing from VehicleParts0, or wrong PartType |
| Shows wrong template name | `Name2.Texts` not set |
| Tire has no friction values | Asset in subfolder, NameMap[0] stale, or `_NN` suffix |
| Intake doesn't feel different | Dot-path not patched correctly |
| Only on wrong vehicles | `VehicleTypes`/`VehicleKeys` mismatch |
| Conflicting with another mod | Rebuild with `--compat-mod` |
| Tire disappears on restart | Pure digit row name (use `APF_78A` not `APF_78`) |

## Key Files

| File | Purpose |
|------|---------|
| `scripts/create_tirepack.py` | Tire mod build script |
| `scripts/create_intakepack.py` | Intake mod build script |
| `scripts/modbase.py` | Shared ModBuilder base class |
| `csharp/UAssetTool/Program.cs` | C# tool: `--add-rows`, `--patch-tire`, `--add-tire-parts`, `--dump` |
| `out/VehicleParts0.uasset` | Base game VehicleParts0 DataTable template |
| `out/VehicleParts.uasset` | Full VehicleParts DataTable (713 rows) |
| `mods/police-tyres/tire_entries.json` | Tire physics + part config |
| `mods/police-sc/intake_entries.json` | Intake tuning config |
