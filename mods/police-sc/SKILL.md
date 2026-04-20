---
name: intake-mod-creation
description: Create MotorTown intake mods — custom Intake-type parts with tuned Slope, BaseRPMRatio, and IntakeSpeedEfficencyMultiplier. Simulates superchargers or custom air intake systems.
---

# Intake Mod Creation

Create mod PAKs that add custom Intake-type parts to MotorTown. Unlike tire mods, intake mods have **no separate physics DataAsset** — all tuning values are inline in the VehicleParts row. This makes intake mods simpler to build but requires understanding how the Intake sub-struct affects engine behavior.

## Quick Start

```bash
# Standalone
nix develop --command bash -c '
python3 scripts/mods.py build police-sc
'

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

## Pipeline Overview

| Step | Tool | Input | Output |
|------|------|-------|--------|
| 0. Extract compat base | Rust `mod_explore` | `--compat-mod` PAK | VehicleParts0 template |
| 1. Add rows to VehicleParts0 | C# `--add-rows` | `intake_entries.json` + `VehicleParts0.uasset` | Modified `VehicleParts0.uasset` |
| 2. Assemble PAK dir | Python | DataTable output | Directory structure |
| 3. Build PAK | Rust `mod_pack` | Directory | `.pak` file |

> No `transform_assets()` step — intake parts don't need separate physics assets like tires do.

## How Intake Parts Work

### The Intake Sub-Struct

Every VehicleParts row contains ALL part sub-structs (Tire, Turbocharger, Intake, Suspension, etc.), with `PartType` determining which the engine reads. An Intake row has 3 tunable fields:

| Field | Type | Effect |
|-------|------|--------|
| `Slope` | Float | Torque curve slope — higher = more torque bias at peak RPM |
| `BaseRPMRatio` | Float | RPM ratio where the intake effect kicks in — lower = earlier power delivery |
| `IntakeSpeedEfficencyMultiplier` | Float | Overall efficiency multiplier — higher = more horsepower |

### Supercharger Simulation

Intake parts can simulate superchargers by tuning for instant response and high top-end power:

| Characteristic | Supercharger tuning | Turbocharger comparison |
|---------------|--------------------|-----------------------|
| Response | Low `BaseRPMRatio` (0.1–0.3) = instant boost | Turbo has lag (spool time via `TurbineWeight`) |
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
> Negative `Slope` values (like vanilla Row 202) shift the power curve to favor low-end torque over high-end HP. For a "strongest" supercharger, use **positive** Slope with high EfficiencyMult — this gives both torque AND horsepower.

## Configuration

### `mods/police-sc/intake_entries.json`

```json
{
  "intakes": [
    {
      "row_name": "PD_SC_Standard",
      "display_name": ["PD SC Standard"],
      "cost": 5000,
      "mass_kg": 5.0,
      "vehicle_types": ["Small"],
      "vehicle_keys": [
        "Elisa_Police", "Muhan_Police", "Zydro_Police",
        "Nuke_Police", "Police_01", "PoliceInterceptor_01"
      ],
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

### Intake Entry Fields

| Field | Default | Description |
|-------|---------|-------------|
| `row_name` | required | DataTable row name (internal ID) |
| `display_name` | required | Array of strings for in-game display |
| `cost` | required | In-game purchase price |
| `mass_kg` | `5.0` | Part mass in kilograms |
| `vehicle_types` | required | Array: `Small`, `Medium`, `Large`, `HeavyMachine`, `MotorCycle` |
| `vehicle_keys` | `[]` (all) | Restrict to specific vehicles |
| `level_requirement` | `{}` (none) | Career level gate |
| `intake.Slope` | inherited | Torque curve slope |
| `intake.BaseRPMRatio` | inherited | RPM ratio where effect begins |
| `intake.IntakeSpeedEfficencyMultiplier` | inherited | Overall efficiency multiplier |

## How It Works Internally

### Dot-Path Resolution for Sub-Struct Fields

The C# `--add-rows` command uses `ResolvePropertyWithContainer` to resolve dot-path notation through `StructPropertyData` containers:

```
"Intake.Slope" → finds "Intake" StructPropertyData → traverses into it → finds "Slope" FloatPropertyData
```

This means `set_or_add_float` with path `Intake.Slope` correctly patches the nested float inside the Intake sub-struct — no C# changes were needed.

### Template Row Matching

The script uses `template_row_match: {"PartType": "*Intake*"}` to find an existing Intake row as the clone template. The `*` wildcard does a substring match on the enum value.

> [!IMPORTANT]
> If no Intake row matches, the C# tool falls back to the **last row** in the DataTable, which may be a completely different part type. Always verify the template row name in the build output.

### Row Chaining

Like tire mods, intake rows are added **sequentially** — each new row is appended to the output of the previous step. This ensures the DataTable grows correctly:

```
VehicleParts0 (45 rows) → +PD_SC_Standard → (46 rows) → +PD_SC_MkII → (47 rows) → +PD_SC_Pursuit → (48 rows)
```

## Compat-Mod Support

Intake mods fully support `--compat-mod` for building on top of other mods' VehicleParts0:

```bash
# Build with AMC Tires + MoreTuning compat
python3 scripts/create_intakepack.py \
  --config mods/police-sc/intake_entries.json \
  --output zzz_AMC_PDParts_MoreTuningCompat_P.pak \
  --compat-mod uploads/zzz_ASEAN_PoliceTyres_v0.2.0_MoreTuningCompat_P.pak
```

### Chaining Multiple Mods

Since the AMC Tires MoreTuningCompat PAK already includes both MoreTuning's rows AND AMC Tires' rows in its VehicleParts0, using it as a single `--compat-mod` produces a PAK that includes all three mods' rows:

```
AMC Tires MoreTuningCompat (VehicleParts0 with ~320 rows)
  → + PD SC Standard, Mk II, Pursuit
  → Final PAK with all rows from all mods
```

> [!CAUTION]
> Users must install **only one variant** of the mod. Using both standalone and compat PAKs causes a double-override conflict on VehicleParts0.

## Critical Rules

### 1. No Separate Physics Asset

Unlike tires (which need a `MTTirePhysicsDataAsset`), intake parts have **all tuning inline** in the VehicleParts row. There is no `transform_assets()` step — only `register_in_tables()`.

This means the PAK only contains `VehicleParts0.uasset` + `.uexp` — no extra asset files.

### 2. PartType Must Be Intake

The `template_row_match` ensures the cloned row has `PartType = EMTPartType::Intake`. If the template is wrong, the game will interpret the row as a different part type (e.g., Tire, Turbocharger) and ignore the Intake sub-struct fields.

### 3. Positive Slope = Stronger

Higher positive `Slope` values give more torque at peak RPM. Negative `Slope` (like vanilla Row 202 with -0.1) actually reduces torque at high RPM. For "strongest" superchargers, use **positive** Slope with high EfficiencyMult.

### 4. BaseRPMRatio Below 0.5 = Instant Response

The vanilla Intake rows have `BaseRPMRatio` of 0.7–0.8 (boost kicks in at 70–80% RPM). For supercharger feel, use 0.1–0.3 (boost from 10–30% RPM — essentially instant).

## Verifying a Built PAK

```bash
# List PAK contents — should only have VehicleParts0
cargo run --release --bin mod_explore --quiet -- AMC_PDParts_P.pak --list

# Expected:
#   MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset
#   MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uexp
```

For deeper verification, extract and dump the DataTable to check row count and values.

## Diagnostic Checklist

If the intake part doesn't appear in-game:
1. **Not in parts list?** → Missing from VehicleParts0 or PartType is wrong
2. **Shows wrong name?** → `Name2.Texts` / display_name not set
3. **Doesn't feel different?** → Intake sub-struct values may not have patched (check dot-path)
4. **Only appears on wrong vehicles?** → Check `VehicleTypes` and `VehicleKeys`
5. **Conflicting with another mod?** → Rebuild with `--compat-mod`

## Key Files

| File | Purpose |
|------|---------|
| `scripts/create_intakepack.py` | Intake mod build script (subclasses ModBuilder) |
| `mods/police-sc/intake_entries.json` | Supercharger entries config |
| `mods/police-sc/mod.json` | AMC PD Parts mod definition |
| `out/VehicleParts0.uasset` | Base game VehicleParts0 DataTable template |
| `csharp/UAssetTool/Program.cs` | C# tool: `--add-rows` with dot-path patching |
