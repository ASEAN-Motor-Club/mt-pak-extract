# C1 Shuto — restore emissive (night windows / signs / lamps) to the ported materials

**Goal:** 186 material instances in the shipped C1 pack currently carry **no emissive at all**. Restore the
emissive contract the BeamNG source declares, on a master that can actually express it, and ship it without
touching `CustomPak.ini`.

**Status:** plan only. Nothing below has been executed.

---

## 1. Measured context (all figures verified this session)

### 1.1 What the source declares — `c1/source/merged.materials.json` (1,605 materials)

| fact | value |
|---|---|
| materials with any emissive/glow data | **185** |
| `emissive: true` | 138 |
| dedicated `emissiveMap` | 65 |
| RGB `emissiveFactor` | 68 (min 0.00, p50 **4.71**, p90 10.00, max **16.06**) |
| `glow` / `glowFactor` | 3 |
| by kind | sign 21, building 13, window 11, lamp 9, tunnel/tnl 14, ad 3, neon 1 |
| footprint in the map (`matarea.json`) | 184 materials, **19.7 % of surface area** (25.9 M m² of 131.4 M m²), 1.35 M faces |
| that 19.7 % is dominated by | `mat_mat_window3_glass_sh` = 18.9 % (24.9 M m²), factor **[1.20, 1.20, 1.20]** with its own AEM mask map |

Representative rows:

```
building_window1        map building_internal_lights1   factor [7.06, 4.48, 3.16]   warm interior light
building_window8        map building_internal_lights1   factor [7.35, 4.47, 4.31]
building_black1         map building_black1             factor [4.71, 4.71, 4.71]
mat_tokyotower_sh_glow  map ...189em                    factor [2.35, 0.37, 0.00]   orange
mat_mat_sitamiti00_sh   no map, no factor               emissive:true -> base colour at ~1.0
```

### 1.2 What ships today — `zzz_AMC_C1Base_v3_P.pak` (client Pak2)

```
MIs in pak ........................ 1,653
emissive source, MI present ....... 186
  opaque (can take M_PolygonMaster)  154   <- 19.4 % of map area
  alphaTest (need a masked master)    32   <- 0.284 % of map area
  with emissiveMap ................  66   (58 resolve to a shipped texture, 8 naming variants)
  no map (base colour source) ..... 120
  with emissiveFactor .............  69
  declared doubleSided ............   5   (mat_wal_tnl_08_*, 0.007 %)
```

Dumped instances:

```
MI_C1_building_window1   parent M_PropMaster   scalars Roughness=0.65 Metallic=0   textures BaseColor
MI_C1_building_black1    parent M_PropMaster   BaseColor only
MI_C1_building_window12  parent M_PropMaster   BaseColor only
MI_C1_mat_lamp_tnl_01_mrc parent M_AlphaTestOneSided  Texture + Opacity
```

Two independent blockers, both confirmed by dump:

1. **`M_PropMaster` has no emissive input.** Its full parameter set is `BaseColor, Mask, Metallic, Normal,
   Roughness, Specular, Use_MaskTexture, Use_NormalTexture, UV_Tiling`. Same story for `M_AlphaTestOneSided`.
2. **The builder never maps emissive.** `c1/tools/build_materials.py` (539 lines) classifies only
   masked / bake / ownalpha / opaque; `grep -i emissive` returns nothing. `building_window1` even imports
   `building_internal_lights1` and never binds it.

The emissive **textures are already shipped** — `Mods/C1/Textures/{lamp,glass,tunnel,other}/…` (2,314 textures
in the pak), e.g. `lamp/building_internal_lights1`, `glass/area_zz_01_gtf_tex_273_aem_color`. Nothing needs
re-importing; the maps were imported and then orphaned.

### 1.3 Parent review — verified at runtime, not assumed

Read from the live client (`FindAllOf("Material")` / `MaterialInstanceConstant`), because a cooked
material's blend mode is not in its asset dump:

| master | blend | two-sided | emissive input | verdict |
|---|---|---|---|---|
| **M_PolygonMaster** | **0 Opaque** | false | `Emissive` + `Emissive_Tint` + `EmissiveIntensity` + `Use_Emissive` | **usable — opaque only** |
| M_PropMaster (today) | 0 Opaque | false | none | current parent, no emissive possible |
| M_AlphaTest | 1 Masked | true | **none** | masked, no emissive |
| M_AlphaTestOneSided (today, for masked) | 1 Masked | false | none | masked, no emissive |
| M_Transparent | 1 Masked | false | none | — |
| M_GlassTrans / M_Glass | 2 Translucent | true | none | — |
| M_Signals | 0 Opaque | false | (declares Emissive) | signals are opaque |

Parameter **types** confirmed by finding real vanilla instances that override them — not inferred from the
NameMap:

```
Emissive           -> TextureParameterValues  T_PolygonStreetRacer_Emissive_01   on MI_PolygonStreetRacer_Master
EmissiveIntensity  -> ScalarParameterValues   2.500                             on MI_PolygonPoliceStation_01_A
Emissive_Tint      -> VectorParameterValues   LinearColor                       on MI_Halloween_01_A
Use_Emissive       -> no instance anywhere sets it (620 instances scanned)
```

So `M_PolygonMaster` supports exactly what we need for opaque materials, and the workbook of the vanilla
emissive chain is: bind `Emissive`, set `EmissiveIntensity`, optionally `Emissive_Tint` — the switch is left
alone by the game itself.

**Three findings that change the plan:**

1. **`M_PolygonMaster` is Opaque — it cannot serve alpha-tested materials.** Of the 186 emissive instances,
   **154 are opaque** and **32 are `alphaTest`** (`mat_lamp_tnl_01_mrc`, `building_flash1`,
   `mat_all_komono_00`, sign/lamp/prop sheets). Reparenting those 32 onto an opaque master would replace
   their cutouts with solid slabs. There is **no masked master with an emissive input** anywhere in the game:
   of the 28 loaded masked materials, none expose `Emissive`, and the emissive scan found zero masked-parent
   instances using it.
2. Those 32 are worth **0.284 % of map area** (373,443 m²), against 19.4 % for the opaque group.
3. `Use_Emissive` is declared but **never set by any vanilla instance**, and `--set-mi-params` cannot create a
   static-switch entry unless the instance already has a donor entry (`BindStaticParam` returns false when
   `StaticParametersRuntime.StaticSwitchParameters` is empty, and opaque instances have none). Whether the
   switch is even required is therefore unproven — it needs a one-material experiment (Task 0), not a guess.

**Also note:** 5 emissive materials are `doubleSided` in the source (all `mat_wal_tnl_08_*` tunnel walls,
0.007 % of area). They are already on a one-sided master today (`M_PropMaster`), so `M_PolygonMaster` is not a
regression — but it also does not fix them.

### 1.4 Tooling reality

- The MI editor is **not** in this repo: it lives at
  `/opt/data/workspace/amc-server/mt-pak-extract-wt-0719/csharp/UAssetTool/` and is what `c1/pipeline/00_env.sh`
  points `UATT_DLL` at. Relevant ops already present:
  `--set-mi-params`, `--set-mi-parent`, `--set-texparam`, `--ensure-texparam`, `--set-clip`,
  `--clear-overrides`, `--rename-texture-param`, `--dump-batch`, `--set-bool`, `--set-blend`.
- `--set-mi-params <config.json>` does reparent + textures + scalars + static switches in **one** pass
  (one parent per run). Config shape from the source comment:

```json
{ "inDir": "...", "outDir": "...",
  "parent": { "pkg": "/Game/Env/Materials/Master/M_PolygonMaster", "name": "M_PolygonMaster" },
  "instances": { "MI_C1_building_window1": {
      "textures": { "Emissive": { "pkg": "/Game/Mods/C1/Textures/lamp", "name": "building_internal_lights1" } },
      "scalars":  { "EmissiveIntensity": 7.06 },
      "static":   { "Use_Emissive": true } } } }
```

- **Gap:** `--set-mi-params` supports `textures`, `scalars`, `static` — **not `vectors`**. `Emissive_Tint` is a
  vector parameter, so the RGB skew (warm windows `7.06/4.48/3.16`, orange tower `2.35/0.37/0`) cannot be
  expressed today. Task 1 closes that.
- `c1/tools/build_matspak.sh` builds a material-only pak, but a **new pak file cannot be mounted**: the client
  `CustomPak.ini` has `Count=9` and the standing rule is *never regenerate that ini, never hand-add a 10th
  entry*. Therefore the 186 updated instances must be written **back into `zzz_AMC_C1Base_v3_P.pak` in place,
  same filename** (Pak2).

### 1.5 Convention to follow (from `c1/scripts/split_nocollision.py`)

That script is the house style for this class of work and the new pass copies it:

- classification is driven **from the source contract**, never inferred from names or face order;
- every rule that could silently drop content has a **counter in the report** (`unknown_materials`,
  `tri_mismatch`, `bbox_drift`, `empty_outputs`) and `ok` is the AND of the gates;
- output is compacted to what is actually referenced;
- anything unclassifiable goes to the **safe** branch and is listed, not guessed.

For materials the safe branch is: **leave the instance untouched and list it** (`unresolved`), because a
half-applied material is indistinguishable from "no effect" in game.

---

## 2. Approach

Scope is now two-tier, because the parent review proved only one master class can carry emissive:

| class | instances | area | parent | emissive |
|---|---|---|---|---|
| opaque (`alphaTest` false) | **154** | 19.4 % | `M_PolygonMaster` | bind `Emissive` + `EmissiveIntensity` + `Emissive_Tint` |
| alpha-tested (`alphaTest` true) | **32** | 0.284 % | unchanged (`M_AlphaTest*`) | **none** — no masked master has an emissive input |

The masked 32 are left exactly as they are (cutouts keep working) and are listed in the report as
`skipped_masked`. If the user later wants them lit, the only correct route is authoring a masked emissive
master in the editor — a separate job, deliberately out of scope here.

For the 154, a standalone pass `c1/tools/emissive_materials.py`:

1. reads the source contract (`merged.materials.json`) and the actual MI list of the pak;
2. decides, per instance, **(emissive texture, intensity, tint)**:

   | source | Emissive texture | EmissiveIntensity | Emissive_Tint |
   |---|---|---|---|
   | `emissiveMap` present | that map | `max(factor)` (default 1.0) | `factor / max(factor)` |
   | `emissive`/`factor`, no map | the instance's **own BaseColor** texture | `max(factor)` (default 1.0) | `factor / max(factor)` |

   Rationale: BeamNG evaluates `emissive = source.rgb * emissiveFactor`. `M_PolygonMaster` evaluates
   `Emissive * EmissiveIntensity * Emissive_Tint`, so splitting the factor into magnitude × normalised hue
   reproduces the source instead of flattening warm windows to white;

3. emits `config.json` for `--set-mi-params` (one run: all instances share `M_PolygonMaster`);
4. writes `emissive_report.json` with the gates below.

Non-emissive instances are **copied through unchanged** and their bytes are hash-gated (§4, Task 5).
Masked emissive instances are copied through unchanged too — no reparent, no parameter writes.

**Why a new script instead of extending `build_materials.py`:** that file's four-way masked/bake split is the
thing that has repeatedly broken the port (silent reparent reverts, `Color` vs `Texture`, alpha baking). The
emissive pass is orthogonal — an opacity-safe instance can also be emissive — and mixing them would put the
alpha contract at risk for a cosmetic gain. `build_matspak.sh` stays as-is.

---

## 3. Tasks

### Task 0 — single-material experiment (do this BEFORE touching 154 instances)

**Why:** `Use_Emissive` is the one parameter whose necessity is unproven — no vanilla instance sets it, and the
tool cannot synthesise a static-switch entry because opaque instances have no donor. One material answers it.

1. Extract `MI_C1_building_window1` (and its `.uexp`) from `zzz_AMC_C1Base_v3_P.pak`.
2. Build **variant A**: reparent to `M_PolygonMaster`, `Emissive=lamp/building_internal_lights1`,
   `EmissiveIntensity=7.06`, `Emissive_Tint=(1.0, 0.635, 0.447)`. No static switch.
3. Build **variant B**: identical, plus `Use_Emissive=true` **if** the tool can write it (it will print
   `SKIP … no static entry to clone` when it cannot — record that fact, don't work around it silently).
4. Write both into a throwaway pak, install, look at the same Shibaura façade at night.

**Decision gate:**
- variant A glows → the switch is unnecessary; Task 1 drops `vectors`-only scope and nothing else changes;
- only variant B glows → Task 1 must also add an "ensure static switch entry" path (synthesise the
  `StaticSwitchParameters` element, not clone-rename);
- neither glows → the parent cannot carry emissive at all; **stop and re-plan** rather than mass-applying.

### Task 1 — add `vectors` (and, conditionally, `ensure-static`) to `--set-mi-params`

**File:** `/opt/data/workspace/amc-server/mt-pak-extract-wt-0719/csharp/UAssetTool/Program.cs`
(`SetMiParams`, ~line 8466; mirror `BindScalarParam` at ~6709 and the `VectorParameterValues` handling at ~6637)

- Add `BindVectorParam(asset, exp, name, (r,g,b,a))` — find/create the `VectorParameterValues` array, match
  `ParameterInfo.Name`, write `ParameterValue` as `FLinearColor`.
- In `SetMiParams`: `if (spec.TryGetProperty("vectors", out var ve)) …` and count into `vecN`.
- Extend the summary line: `set_mi_params changed=… tex=… scalars=… vecs=… statics=…`.

Build:
```bash
cd /opt/data/workspace/amc-server/mt-pak-extract-wt-0719/csharp/UAssetTool
dotnet build -c Release
```
**Gate:** one MI with `"vectors": {"Emissive_Tint": {"r":1.0,"g":0.66,"b":0.45,"a":1}}` re-dumps showing the
vector entry present with those components; a second MI without `vectors` is byte-identical to its input.

### Task 2 — the plan generator

**Create:** `c1/tools/emissive_materials.py`

```
--source c1/source/merged.materials.json
--materials <dir of MI_*.uasset from the pak>     # extract via repak, see Task 4
--textures  <dir of Mods/C1/Textures>             # or a text listing for --dry-run
--out       <work>/emissive_{config.json,report.json}
[--dry-run]
```

Must reuse, not re-implement: `source_key()` (`MI_C1_` **and** `MI_C1X_` prefixes — stripping only the first
silently skipped 49 instances once) and the `Stages[0]` read pattern.

Report fields (all counters, `ok` = AND of gates):

```
{"instances_in_scope":186, "with_map":66, "map_resolved":58, "map_unresolved":[...8],
 "no_map":120, "with_factor":69, "intensity": {"min":..,"p50":..,"max":16.06},
 "by_library": {...}, "unknown_mi": [...], "ok": true}
```

**Gate:** `--dry-run` reproduces exactly `186 total / 154 opaque / 32 masked / 66 with map / 120 no map / 69 with
factor` from §1.2 and lists the same 8 unresolved maps.

### Task 3 — resolve the 8 unresolved emissive maps

They are naming variants of files that do exist under a different flattening:

```
mat_all_komono_00        -> Inkedmat_all_komono_00_file0em_LI_color
mat_daisi_all_komono     -> mat_daisi_all_komono_file0EM_color
mat_daisi_komono_etc     -> mat_daisi_komono_etc_file0EM
mat_daisi_window_etc     -> mat_daisi_window_etc_file0EM
mat_heiwajima_all_komono -> mat_daisi_all_komono_file0EM_color
mat_ooi_w_all_komono     -> mat_daisi_all_komono_file0EM_color
mat_singou_d             -> mat_singou_c_file0Eem_color
mat_singou_d_depth       -> mat_singou_c_file0Eem_color
```

Resolution order, each step logged: exact → lowercased exact → strip `inked`/`file0` prefixes and `_li`/`_color`
suffixes → substring match on the material stem + `em`. Anything still unmatched falls back to the base-colour
class **and is listed in `map_unresolved`** — never silently darkened.

**Gate:** `map_unresolved` shrinks to 0, or each leftover has an explicit `fallback: basecolor` note in the report.

### Task 4 — apply the pass

```bash
# extract the instances (container has repak; 1653 MIs, seconds)
mkdir -p /opt/data/cache/scratch/emis/in
target/release/repak get /opt/data/releases/c1/pakset_v10/zzz_AMC_C1Base_v3_P.pak \
  'MotorTown/Content/Mods/C1Full/Materials/*' > /opt/data/cache/scratch/emis/base_mats.tar   # or per-file loop
```

Then, on the host (dotnet + mappings required):

```bash
nix develop --command bash -c '
  export DOTNET_ROLL_FORWARD=Major DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
  dotnet /opt/data/workspace/amc-server/mt-pak-extract-wt-0719/csharp/UAssetTool/bin/Release/net8.0/UAssetTool.dll \
    --set-mi-params /opt/data/cache/scratch/emis/config.json'
```

**Post-conditions, checked with `--dump-batch` on the 186 outputs** (fail the stage rather than ship):

- `parent == M_PolygonMaster` for all 186;
- `Emissive` texture parameter present and pointing at the expected texture;
- `EmissiveIntensity > 0` and equal to the planned value (±0.01);
- `Use_Emissive == true`;
- `Emissive_Tint` present where the factor is non-uniform;
- the 1,467 non-emissive instances are byte-identical to their inputs (sha256 compare).

### Task 5 — write back into the Base pak in place

```bash
# repak cannot edit in place: extract all, swap the 186 pairs, repack to the SAME filename
repak unpack zzz_AMC_C1Base_v3_P.pak --output base_unpack
cp /opt/data/cache/scratch/emis/out/MI_*  base_unpack/MotorTown/Content/Mods/C1Full/Materials/
repak pack base_unpack zzz_AMC_C1Base_v3_P.pak.new --version V11 --mount-point "../../../" \
     --compression Zlib --path-hash-seed 0
```

**Gates:**

- record count identical (7,000+ entries), every non-material record's uncompressed sha256 unchanged;
- `repak list` output identical except the 186 material stems;
- total pak size grows by < 2 MB (emissive params are tens of bytes per instance);
- `CustomPak.ini` untouched (`Count=9`, `Pak2` filename unchanged) — assert by reading it before and after.

### Task 6 — verify in game (night)

1. Back up the guest copy: `zzz_AMC_C1Base_v3_P.pak.bak_preemissive` (sha recorded).
2. Copy the new pak over Pak2.
3. Restart the client, join via the UE4SS dev bridge (`ExecuteConsoleCommand(pc, "open steam.<session>:27780", pc)`).
4. Set night if the sky shader allows, otherwise use the current in-game clock; take screenshots at Shibaura
   and at Tokyo Tower (`mat_tokyotower_sh_glow`, orange) and a tunnel (`mat_lamp_tnl_01_mrc`).
5. Compare against the same three shots with the backup in place.

**Pass:** windows/signs/lamps visibly self-lit against an unlit background; no checkerboard anywhere (that
would mean a broken parent); non-emissive surfaces unchanged.
**Fail/rollback:** restore `.bak_preemissive`, restart, re-shoot — the pak filename never changes so the ini
needs no edit either way.

### Task 7 — publish (only after the user signs off on the screenshots)

Rebuild the aggregate client release pak and re-publish the release set per the standing flow
(`/opt/data/releases/c1/pakset_release_v2/` → new `pakset_release_v3/`, store `mods/` + archive the previous),
then bump the server/client pins as applicable.

---

## 4. Risks and how the plan handles them

| risk | mitigation |
|---|---|
| **`M_PolygonMaster` is Opaque** — the 32 alpha-tested emissive materials cannot join it | they are excluded by construction (Task 2's class split) and listed as `skipped_masked`; no masked master in the game has an emissive input, so this is a real limit, not a shortcut |
| **`Use_Emissive` may be required and may be unwritable** (no donor entry on opaque instances) | Task 0 tests it on one material first; if required, Task 1 adds entry synthesis; if impossible, stop and re-plan |
| Emissive is sun-independent — everything glows at noon too | intensities follow the source (p50 4.7, big glass only 1.2); Task 6 checks a daytime shot; if it reads wrong, cap intensity or gate on `BP_C1_Sky` time |
| Reparenting changes look of *non-emissive* materials | only the 154 opaque emissive instances are reparented; the other 1,499 are hash-gated unchanged |
| `M_PropMaster` uses a packed `Mask` texture that `M_PolygonMaster` lacks | the dumped instances set only BaseColor/Roughness/Metallic, so nothing is lost; Task 4's per-instance dump confirms no `Mask` or `Normal` override existed before the switch |
| 5 double-sided emissive tunnel walls stay one-sided | unchanged from today (`M_PropMaster` is one-sided too); recorded as a known gap, not silently claimed as fixed |
| 8 unresolved maps silently darken | they are counted, listed, and fall back to base colour explicitly |
| 120 "no map" materials over-brighten whole walls at 1.0 | that is the source's own contract (`emissive: true`); verified in Task 6 against the same wall by day and night, intensity 1.0 being the only knob |
| Pak rewrite corrupts the set | full-record hash gate + backup on both container and guest + unchanged filename |
| New pak file would need a 10th ini entry | in-place rewrite only; ini asserted unchanged |

## 5. Open questions

1. For the 120 no-map instances, is the intended look "whole façade faintly self-lit", or should they get a
   fraction (e.g. 0.35) so only sunlit surfaces dominate by day? Only a night+day screenshot pair settles it.
2. Do we want the two `mat_singou_*` signal materials emissive at all — they are traffic-light faces, and MT
   may already drive them via `BP_C1_Sky`/light actors.
3. Publish to the club release store in the same pass, or client-only until the next mod rollover (Mon/Thu 08:30 +07)?
