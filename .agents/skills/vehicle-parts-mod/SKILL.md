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
| `max_weight_kg` | inherited (700) | Max load capacity in kg |
| `wear_rate` | inherited | Tire wear rate — lower = slower wear (PerformanceTire: 1.3) |
| `smoke_rate` | inherited | Smoke intensity — only works with `DriftTire` template |
| `patch_length_coefficient` | inherited (100000) | Patch behavior coefficient |
| `rolling_resistance_coeff` | inherited | Rolling resistance (PerformanceTire: 0.009) |

> [!NOTE]
> `WearRate` and `RollingResistanceCoeff` exist on `PerformanceTire_45` but NOT on `BasicTire_45`. When cloning from BasicTire_45, these are added via `set_or_add_float`. The `PerformanceTire_45` asset must be extracted separately if you want to use it as a template (it's not in `assets.json` — use `--search PerformanceTire` to find its PAK path).

#### Tire Part Fields

| Field | Default | Description |
|-------|---------|-------------|
| `row_name` | required | DataTable row name |
| `display_name` | required | Array for in-game display (`Name2.Texts`) |
| `cost` | required | Purchase price |
| `mass_kg` | `10` | Tire mass |
| `vehicle_types` | required | `Small`, `Medium`, `Large`, `HeavyMachine`, `MotorCycle`, `Pickup`, `Bus`, `Truck`, `SemiTractor`, `SemiTrailer`, `Motorhome` |
| `vehicle_keys` | cleared | Restrict to specific vehicles. Auto-cleared when cloning from compat templates (see `general-modding` → Row Cloning Behavior) |
| `level_requirement` | cleared | Career level gate. Auto-cleared when cloning from compat templates |
| `truck_classes` | not set | `HeavyDuty`, `MediumDuty` — only needed for truck/bus tires |
| `bIsDualRearWheel` | `false` | Set `true` for DRW (dual rear wheel) truck tires |
| `tire_asset_path` | required | UE path: `/Game/Cars/Parts/Tire/{Name}/{Name}` |

### Base Game Tire Physics Reference

| Tire | StaticMu | SlidingMu | OffroadFriction | WearRate | MaxWeightKg |
|------|----------|-----------|-----------------|----------|-------------|
| BasicTire_45 (standard) | 1.1 | 1.0 | — | — | 700 |
| PerformanceTire_45 | 1.15 | 1.0 | — | 1.3 | 700 |
| BasicTire_65 (wider) | 1.1 | 1.0 | — | — | — |
| DriftTire | — | 0.85 | — | — | — |
| OffroadTire | 0.95 | 0.9 | 1.4 | — | — |
| HeavyDutyFront/Rear | — | 0.9 | — | — | — |
| HeavyDuty_Load1 | 0.97 | 0.87 | — | — | — |
| HeavyMachine_20Ton | 0.95 | 0.88 | 1.2 | — | — |

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

### Bike Tires — Dual Physics Assets

Unlike car tires which use a **single** physics asset, bike tires reference **two separate assets** — one for the front wheel and one for the rear:

| Property | Car Tire | Bike Tire |
|----------|----------|-----------|
| `Tire.TirePhysicsDataAsset` | Front + Rear (same) | **Front only** |
| `Tire.TirePhysicsDataAsset_BikeRear` | `null` (unused) | **Rear only** |
| Asset count per tire | 1 | 2 |

Stock bike (`MotorCycleTire_01`) references:
- Front: `Motorcycle_Front` — SpringX=25000, SpringY=2500, DampingY=40, MaxWeightKg=200
- Rear: `Motorcycle_Rear` — SpringY=3000, DampingY=50, MaxWeightKg=300

The rear is slightly stiffer and supports more weight. When creating custom bike tires, you MUST clone and patch **both** assets.

**Builder support:** The `create_tirepack.py` script auto-detects bike mode when `tire_physics` has `front` and `rear` sub-dicts. It automatically sets both import references and nulls out the car-only rear ref for non-bike tires.

```json
{
  "tire_physics": {
    "front": {"name": "APF_Cruiser_78_Front", "template": "Motorcycle_Front", ...},
    "rear":  {"name": "APF_Cruiser_78_Rear",  "template": "Motorcycle_Rear",  ...}
  }
}
```

### Tire Gotchas

1. **PAK Path — FLAT, No Subfolder:** Tire physics assets MUST be in `Cars/Parts/Tire/` directly, not in a subfolder. The engine maps `/Game/Cars/Parts/Tire/{Name}` to `Content/Cars/Parts/Tire/{Name}.uasset`.

2. **NameMap[0] — Must Rename:** When cloning a tire, `NameMap[0]` has the old package path. Must update it or the game uses default physics. For cooked assets, `--clone-asset` MUST have `patch_namemap_0: true`.

3. **FName Number Suffix:** `BasicTire_45` is stored as FName(`"BasicTire"`, Number=46). Always use `new FName(asset, name, 0)` to avoid stale Number suffixes.

4. **VehicleParts0 Override:** Game loads both `VehicleParts` (713 rows) and `VehicleParts0` (50 rows). VehicleParts0 supersedes for shared categories. Add tire to BOTH.

5. **Template Row Selection:** Use the last tire row (`Offroad`), not `MotorCycleTire_01` which has bike-only properties.

6. **Display Name:** In-game name comes from `Name2.Texts`, NOT `Name` or `Desciption`.

7. **Rename Order:** Exports → Imports → NameMap. Renaming NameMap first causes silent corruption.

8. **Pure Digit Row Names:** `APF_78` gets parsed as FName(`"APF"`, Number=79), causing save/load mismatches and disappearing tires. Append a letter: `APF_78A`.

9. **Combining mods manually requires merging all assets:** The tire pack builder only stages its own assets. If combining PD Parts (which has 6 car tire physics assets) with bike tires, you must extract BOTH PAKs, merge directories (so all tire physics assets are present), patch VehicleParts0 for any cross-mod changes, then repack. See `general-modding` skill for the manual merge workflow.

10. **Inherited properties from compat templates:** When using `--compat-mod`, the template row's `VehicleKeys` and `LevelRequirementToBuy` carry over. The builder auto-clears these when not in config. See `general-modding` skill → "Row Cloning Behavior" for the full pattern.

11. **Truck/bus vehicle types:** Use `Bus`, `Truck`, `SemiTractor`, `SemiTrailer`, `Motorhome` for truck parts. Also set `truck_classes` to `HeavyDuty` and/or `MediumDuty`. `vehicle_types` controls which vehicle categories can equip the part; `truck_classes` filters within truck-type vehicles.

12. **DRW tires:** Set `bIsDualRearWheel: true` on the tire part to render two wheels on the rear axle. `BasicHeavyDutyRearTire` is the best template for DRW truck tires.

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

5. **VehicleKeys Must Include All Target Vehicles:** If an intake row has `VehicleKeys: ["Elisa_Police", "Muhan_Police"]`, ONLY those vehicles can equip it. Adding a new vehicle (e.g., `Gunthoo_Police`) requires patching the row to include it. Use `--patch-rows` with `set_name_array` to update the whitelist.

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

> [!WARNING]
> **Always use the ORIGINAL mod PAK as the compat base, NOT a previous version's compat PAK.** Using a compat PAK as base (e.g., `v0.3.0_MoreTuningCompat_P.pak`) causes duplicate entries — the old rows from v0.3.0 appear twice (once from the compat base, once from the new build). Instead, use the original upstream PAK (e.g., `qxZap_MoreTuning_P.pak`) and let the build script add ALL your tires fresh.

### Combining Two VehiclePart Mods Into One PAK

When two mods both override `VehicleParts0`, only one loads (alphabetically last wins). To combine them into a single PAK:

```bash
# 1. Build the "base" mod standalone first
python3 scripts/mods.py build police-tyres

# 2. Build the "add-on" mod with --compat-mod pointing to the base PAK
python3 scripts/create_tirepack.py \
  --config mods/amc-tyres/tire_entries.json \
  --compat-mod mods/police-tyres/builds/zzz_ASEAN_PoliceTyres_v0.2.0_P.pak \
  --output mods/amc-tyres/builds/zzz_ASEAN_MCTyres_Combined_P.pak
```

The `--compat-mod` PAK's `VehicleParts0` is extracted and used as the template. New rows are appended on top of existing rows from the compat mod. The combined PAK contains all add-on physics assets plus the merged `VehicleParts0`.

**Important:** The combined PAK only contains the add-on mod's physics assets. The base mod's assets must also be present — either manually merged into the PAK or as a separate PAK the user installs alongside.

> [!WARNING]
> **Inherited properties carry over from compat template.** See `general-modding` skill → "Row Cloning Behavior" for which properties to clear and how.

> [!WARNING]
> **When building a compat PAK for a mod update (e.g., v0.5.0), always use the ORIGINAL upstream PAK as the base, NOT the previous version's compat PAK.** Example: To build `zzz_AMCTires_v0.5.0_MoreTuningCompat_P.pak`, use `qxZap_MoreTuning_P.pak` as `--compat-mod`, NOT `zzz_AMCTires_v0.3.0_MoreTuningCompat_P.pak`. The old compat PAK already contains your previous rows — using it as base duplicates them.

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
| Tire has no friction values | Asset in subfolder, NameMap[0] stale, `_NN` suffix, or **physics asset missing from PAK** |
| Intake doesn't feel different | Dot-path not patched correctly |
| Only on wrong vehicles | `VehicleTypes`/`VehicleKeys` mismatch |
| Conflicting with another mod | Rebuild with `--compat-mod` |
| Tire disappears on restart | Pure digit row name (use `APF_78A` not `APF_78`) |
| Bike tire has no grip | Only front OR rear physics asset present — bike tires need BOTH |
| Combined mod loses car tire grip | Other mod's tire physics assets not merged — use manual merge, not just `--compat-mod` |

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
