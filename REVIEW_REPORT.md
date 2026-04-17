# MoneyRun Mod & UAssetAPI Fixes — Review Report

**Date**: 2026-04-12  
**Author**: Agent session  
**Target**: MotorTown v0.7.18  
**Output**: `MoneyRun_v0.7.18_P.pak` (73,368 bytes, V11 PAK, 10 files)

---

## 1. Objective

Build a MotorTown v0.7.18 mod (`MoneyRun_v0.7.18_P.pak`) that adds:
- **Money Stack** and **Money Pallet** cargo types
- **Harbor_Export** as a source (produces both cargos)
- **Factory_Toy** as a sink (consumes both cargos)

---

## 2. UAssetAPI Bug Fixes (Critical — review carefully)

Three bugs were discovered and fixed in UAssetAPI's unversioned property serialization. All fixes are in the `csharp/UAssetAPI/` submodule (fork: `ASEAN-Motor-Club/UAssetAPI`).

### 2.1 BoolProperty: 0-byte encoding at CDO top level

**Root cause**: In UE5 unversioned format, BoolProperty values at CDO top-level are encoded entirely in the `FUnversionedHeader.ZeroMask` with **0 bytes** written to the data stream. `IsZero=true` → Value=false, `IsZero=false` → Value=true. UAssetAPI incorrectly read 1 byte for ALL unversioned BoolProperty values, causing stream misalignment.

**Context matters**: BoolProperty inside structs/arrays/maps (non-top-level) still reads 1 byte from the stream. The 0-byte encoding only applies at CDO top level.

**Files modified**:
- `UAssetAPI/PropertyTypes/Objects/BoolPropertyData.cs` — Read: 0 bytes for `CdoTopLevel` (`Value = !IsZero`), 1 byte otherwise. Write: same context-aware behavior.
- `UAssetAPI/PropertyTypes/Objects/PropertyData.cs` — Added `CdoTopLevel` to `PropertySerializationContext` enum.

**Review concern**: Is the 0-byte vs 1-byte distinction correct for ALL UE5 versions? The fix assumes CDO top-level unversioned BoolProperty is always 0 bytes. This was verified against v0.7.18 assets (Harbor_Export, Factory_Toy) but should be tested against other UE5 games.

### 2.2 IsTopLevel: must be CDO-only

**Root cause**: `FUnversionedHeader.IsTopLevel` must only be `true` for exports with `RF_ClassDefaultObject` flag. Setting it for ALL NormalExports caused non-CDO exports (like `MotorTownInteractable_GEN_VARIABLE`) to use `CdoTopLevel` context, reading BoolProperty with 0 bytes when it should read 1 byte, causing cascading stream misalignment.

**Files modified**:
- `UAssetAPI/Unversioned/FUnversionedHeader.cs` — Added `public bool IsTopLevel = false;` field.
- `UAssetAPI/ExportTypes/NormalExport.cs` — Read: sets `IsTopLevel` based on `RF_ClassDefaultObject` flag. Write: passes `CdoTopLevel` context only for CDO exports.
- `UAssetAPI/MainSerializer.cs` — Read: computes `propContext = CdoTopLevel` when `header.IsTopLevel` is true. Write: accepts and passes `propContext` parameter.

**Review concern**: The `IsTopLevel` flag is set AFTER reading the unversioned header but BEFORE reading properties. Verify the timing is correct — does UE5 engine code set this flag before or after header parsing?

### 2.3 EnumProperty: context check must include CdoTopLevel

**Root cause**: `EnumPropertyData.Read/Write` checked `serializationContext == Normal` before using unversioned enum index encoding. When CDO top-level properties pass `CdoTopLevel` context, this check failed and the code fell through to `ReadFName()` / `Write(FName)`, which is wrong for unversioned format.

**File modified**:
- `UAssetAPI/PropertyTypes/Objects/EnumPropertyData.cs` — Changed context check from `== Normal` to `Normal || CdoTopLevel`.

**Review concern**: Minimal and correct. Both `Normal` and `CdoTopLevel` should use the unversioned enum index encoding. Only `Array`, `Map`, and `StructFallback` should use the FName-based path.

---

## 3. Uncommitted / In-Progress Code (needs cleanup)

### 3.1 UAssetAPI — debug/instrumentation code remaining

These items are in the local working tree but NOT yet committed or pushed to the `fix/unversioned-header-serialization` branch:

| File | Issue | Line |
|------|-------|------|
| `MainSerializer.cs:411` | Unused `schemaDebug` variable | `string schemaDebug = relevantSchema?.Name ?? "null";` |
| `MainSerializer.cs:427` | Duplicate `if` statement (looks like a merge artifact) | Two identical `if (relevantSchema == null) throw...` lines |
| `MainSerializer.cs:444-445` | Blank lines (minor) | Extra blank lines after ZeroMask block |
| `UAsset.cs:991-1002` | `[SCHEMA DBG]` debug output for Harbor_Export/Factory_Toy | Conditional debug prints that should be removed or gated behind `#if DEBUG` |
| `UAsset.cs:1043` | Improved error message in `#if DEBUGVERBOSE` block | Good change, but review message format |

### 3.2 UAssetTool — Program.cs uncommitted changes

The `--dump` mode was enhanced with:
- `HasUnversioned` flag in header output
- `SerialOffset`/`SerialSize` per export
- StructExport/ClassExport detail (LoadedProperties, FProperty details with PropertyFlags)
- CDO-specific raw hex dump (first 256 bytes for RawExport, property list for NormalExport)
- Non-CDO NormalExport property listing

**Review concern**: The dump enhancements are useful for debugging but the CDO hex dump is verbose. Consider gating behind a `--verbose` flag.

### 3.3 MapPropertyData — validation guard

A bounds check was added for `numKeysToRemove`:
```csharp
if (numKeysToRemove < 0 || numKeysToRemove > 1000000)
    throw new FormatException(...);
```

This is a defensive guard, not a bug fix. The magic number `1000000` should be reviewed — is there a better upper bound?

---

## 4. Mod Build Pipeline

### 4.1 Architecture

The mod is built by `scripts/create_cargopack.py` (subclass of `scripts/modbase.py::ModBuilder`):

```
Stage 1: transform_assets  — Clone SmallBox.uasset → Money, MoneyPallet blueprints
Stage 2: register_in_tables — Add rows to Cargos.uasset, patch delivery point CDOs
Stage 3: assemble_pak       — Stage files into PAK directory layout
Stage 4: build_pak          — Run mod_pack binary
Stage 5: verify_pak          — Run mod_explore to list contents
```

### 4.2 Config Files

| File | Purpose |
|------|---------|
| `cargo_entries.json` | Cargo definitions: Money Stack, Money Pallet (display name, cargo_type "None", weight, payment, mesh, blueprint) |
| `recipe_entries.json` | Delivery routes: Harbor_Export (source, `replace_production_configs: true`), Factory_Toy (sink, append mode) |

### 4.3 Key Design Decisions

1. **`cargo_type: "None"`** for modded cargo — prevents wildcard demand matching. `SmallPackage` would cause cargo to appear at Supermarkets/Warehouses.

2. **Harbor_Export uses cloned Factory_Toy template** — The original Harbor_Export has a `Supplies` map (not `ProductionConfigs`). The mod needs `ProductionConfigs` for recipe-based production, so Factory_Toy is cloned and renamed to Harbor_Export. This means the mod's Harbor_Export behaves differently from the base game version.

3. **`replace_production_configs: true`** for Harbor_Export — Since Harbor_Export originally has `Supplies` (not `ProductionConfigs`), the cloned Factory_Toy template already has 2 toy-related production configs. These are replaced entirely with Money + MoneyPallet recipes.

4. **Factory_Toy uses append mode** — The original Factory_Toy keeps its 2 toy-related production configs; the 2 Money recipes are appended, totaling 4 entries.

### 4.4 PAK Contents (10 files)

```
MotorTown/Content/DataAsset/Cargos.uasset + .uexp        (93 rows = 91 original + 2 mod)
MotorTown/Content/Objects/Mission/Delivery/DeliveryPoint/Factory_Toy.uasset + .uexp  (4 ProductionConfigs)
MotorTown/Content/Objects/Mission/Delivery/DeliveryPoint/Harbor_Export.uasset + .uexp  (2 ProductionConfigs)
MotorTown/Content/Objects/Mission/Delivery/Money.uasset + .uexp
MotorTown/Content/Objects/Mission/Delivery/MoneyPallet.uasset + .uexp
```

---

## 5. Known Issues / Warnings

| Issue | Severity | Details |
|-------|----------|---------|
| `Property 'bCanPickup' not found for 'set'` | Low | MoneyPallet blueprint doesn't have this property; patch silently skipped |
| `Property 'TimeSinceLastProduction' not found for 'set'` | Low | Exists in MTDeliveryPoint schema but not in ProductionConfigs struct; harmless |
| `Property 'ProductionFlags' not found for 'set'` | Low | Same as above; patches skipped |
| UAssetAPI debug code not cleaned up | Medium | See §3.1 above — schema debug output, unused variable, duplicate if-statement |
| No in-game testing | High | Mod has not been tested in MotorTown v0.7.18; roundtrip verification only |

---

## 6. Mappings.usmap Analysis

The current `Mappings.usmap` (2.2MB, usmap v4, 21,884 schemas) was compared with the UE4SS usmap dumper implementation:

- **No package versioning**: UE4SS hardcodes `bHasVersionInfo = false`, so FileVersionUE4/FileVersionUE5/custom versions/NetCL are never written. This matches our file.
- **Extensions present**: PPTH (object paths, 52KB) and EATR (property flags, 429KB) are included and read by UAssetAPI.
- **EATR PropertyFlags unused**: UAssetAPI reads `PropertyFlags` from EATR into `UsmapPropertyData.PropertyFlags` but the unversioned serializer never references them during Read/Write. They could potentially be used to make smarter serialization decisions (e.g., checking `CPF_Edit` to determine if a property is serialized).
- **`PatchMappingsForVersion()`** in UAssetTool `Program.cs` patches `MTVehicleColor` PropCount from 1→9 at runtime. This compensates for the usmap lacking versioning info that would tell UAssetAPI which engine version's property layout to use.

---

## 7. Review Checklist

### Critical — UAssetAPI correctness
- [ ] BoolProperty 0-byte CDO top-level: verify against UE5 C++ source or other UE5 games
- [ ] IsTopLevel flag timing: verify set before property read begins
- [ ] EnumProperty CdoTopLevel context: verify unversioned enum index encoding applies
- [ ] Clean up debug code before pushing to `fix/unversioned-header-serialization` branch

### Important — Mod functionality
- [ ] In-game test: load mod PAK, verify Harbor_Export produces Money/MoneyPallet, Factory_Toy consumes them
- [ ] Harbor_Export clone: verify the game doesn't crash when a Supplies-based delivery point is replaced with ProductionConfigs
- [ ] Cargos 93 rows: verify no row corruption in composite DataTable (91 base + 2 mod)

### Nice-to-have — Code quality
- [ ] Remove `schemaDebug` variable from `MainSerializer.cs:411`
- [ ] Remove duplicate `if` statement from `MainSerializer.cs:427`
- [ ] Gate `[SCHEMA DBG]` output behind `#if DEBUG` or remove
- [ ] Add `--verbose` flag to `--dump` mode for CDO hex output
- [ ] Review `numKeysToRemove` magic number in `MapPropertyData.cs`
- [ ] Consider using EATR PropertyFlags for smarter unversioned serialization decisions

---

## 8. File Map

### UAssetAPI (submodule, uncommitted vs `fix/unversioned-header-serialization` branch)
```
UAssetAPI/Unversioned/FUnversionedHeader.cs      — +1 line (IsTopLevel field)
UAssetAPI/ExportTypes/NormalExport.cs             — +9/-2 (IsTopLevel set, CdoTopLevel write context)
UAssetAPI/MainSerializer.cs                       — +23/-6 (propContext plumbing, debug artifacts)
UAssetAPI/PropertyTypes/Objects/BoolPropertyData.cs — +26/-2 (0-byte CdoTopLevel encoding)
UAssetAPI/PropertyTypes/Objects/EnumPropertyData.cs — +4/-2 (CdoTopLevel in context check)
UAssetAPI/PropertyTypes/Objects/MapPropertyData.cs   — +5 (numKeysToRemove validation)
UAssetAPI/PropertyTypes/Objects/PropertyData.cs     — +3/-1 (CdoTopLevel enum value)
UAssetAPI/UAsset.cs                                  — +14/-1 (schema debug, error message)
```

### UAssetTool (uncommitted vs HEAD `d99d325`)
```
csharp/UAssetTool/Program.cs  — +45/-16 (enhanced --dump, removed MTDeliveryPoint debug print)
```

### Mod configs (committed)
```
cargo_entries.json   — Money + MoneyPallet cargo definitions
recipe_entries.json  — Harbor_Export source, Factory_Toy sink
```

### Python build scripts (committed)
```
scripts/create_cargopack.py — Cargo mod builder (447 lines)
scripts/modbase.py          — Base ModBuilder class (341 lines)
```

### Output
```
MoneyRun_v0.7.18_P.pak — 73,368 bytes, V11 PAK, 10 files
```
