# C1 Emissive — Binding Fix Plan

> **For Hermes:** implement task-by-task. Do NOT install anything on the client before the
> dump gate in Task 4 passes. Plan mode only until the user says go.

**Goal:** make `MI_C1_mat_mat_window3_glass_sh` (and later the whole C1 emissive set)
actually emit in-game, by fixing `UAssetTool` so texture bindings land in the serialized
parameter array the engine reads.

**Architecture:** no more probe paks until a `--dump` proves the target asset's
`TextureParameterValues` entries point at C1 textures instead of `T_GhostLight_*`.
One verified instance, then a mechanical rollout.

**Toolchain:** `dotnet` + `UAssetTool.dll` (`mt-pak-extract-wt-0719/csharp/UAssetTool`),
`Mappings.usmap`, `mod_pack`, repak, `winps.sh`/`win_put.sh` bridge to the Windows client.

---

## Proven facts (do not re-litigate)

1. The map's materials are **not** parented to our own masters. Runtime probe of the
   shipped instance returned `Parent = Material /Game/Env/Materials/Master/M_PropMaster`
   (a vanilla master with no emissive parameter).
2. Our own cooked master ships **without** a shader map (0 shader strings) even after a
   full `-CookAll` WindowsServer cook. Do not spend time cooking masters again.
3. Asset NAME is what makes the override visible. v14–v20 shipped `MI_C1Emis_*` names the
   meshes never reference → nothing changed on screen. v21 used the real name
   `MI_C1_mat_mat_window3_glass_sh` → surface changed. **The override pipeline works.**
4. `--set-mi-params` `parent` must be at **root level** of the config; inside the instance
   spec it is ignored silently (v11/v18 no-ops).
5. Vanilla paths: `MI_Halloween_Master` = `/Game/Env/Materials/MI_Halloween_Master`.
   There is NO `Env/Materials/Master/M_PolygonMaster` package — v19's parent resolved to
   nil. Never hand-write a package path that hasn't been read out of a vanilla import table.
6. **The remaining bug:** after v22 the dump still shows
   `TextureParameterValues = { T_GhostLight_Halloween_01_BC, _E, _N }` even though the tool
   reported `tex=2`. The write is landing somewhere the renderer does not read.
7. Original C1 texture bindings for that instance (from `zzzzz_AMC_C1Mats_P27_P.pak`):
   - `BaseColor` → `/Game/Mods/C1/Textures/glass/area_zz_01_gtf_tex_273_a`
   - emissive companion exists: `/Game/Mods/C1/Textures/glass/area_zz_01_gtf_tex_273_aem_color`

## Client state to restore first

`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_AMC_C1EmisProbe_v22_P.pak` is installed as Pak9 and makes
the facade render ghost textures. Remove it, restore the 9 real mods (`emis/restore2.ps1`
pattern), relaunch. No further client installs until Task 4's gate passes.

---

### Task 0: Restore the client to the clean 9-mod list

**Files:** reuse `/opt/data/cache/scratch/emis/restore2.ps1`, `kill_any.ps1`, `launch_game4.ps1`

Run, in order: `kill_any.ps1` → `restore2.ps1` → `launch_game4.ps1`.
Expected: `DELETED ...C1EmisProbe...`, `Count=9`, `LAUNCHED ... pid=...`.
Do not run any UE4SS bridge probe at the frontend (that already crashed the client once).

### Task 1: Dump the REAL structure of a cooked MIC's texture array

**Files:** `/opt/data/workspace/amc-server/mt-pak-extract-wt-0719/out/MI_GhostLight_Halloween_01.uasset`,
same for `MI_PolygonMaster.uasset`.

Run `--dump` on both and capture the full `TextureParameterValues` block with the *property
types*, not just the names. The question that decides the fix:

- Are entries `ObjectPropertyData` named `ParameterValue` (what `BindTextureParam` expects)?
- Or a native/cooked representation the dump prints as `TextureName (Name)` plus an index?

`MiArray`/`MiParamName` (Program.cs:8562–8569) only inspect `ParameterInfo.Name`, and
`BindTextureParam` (8589–8612) only mutates `ObjectPropertyData` named `ParameterValue`.
If the cooked form stores the reference differently, the loop finds no match and the code
falls through to the clone-and-append path — producing a second, ignored parameter list.
That is the suspected v22 failure.

Deliverable: a written statement of the exact serialized shape, with the dump lines quoted.

### Task 2: Add a read-only `--dump-mi-params` op

**Files:** modify `csharp/UAssetTool/Program.cs` (add a new arg branch beside `--dump`).

Print, for each of `ScalarParameterValues`, `VectorParameterValues`,
`TextureParameterValues`, `StaticParameters`:

```
entry index, ParameterInfo.Name, value node C# type, value node name,
resolved import (package path + asset name) for object refs
```

Purpose: every future bind must be verifiable by name AND value, not by `tex=2` counters.
Expected output on the untouched ghost: three texture entries resolving to
`/Game/Env/Textures/Halloween/T_GhostLight_Halloween_01_{BC,E,N}`.

### Task 3: Fix `BindTextureParam` to write the real value node

**Files:** `csharp/UAssetTool/Program.cs:8589-8612`

Rules:
- If the existing entry's value is an `ObjectPropertyData` named `ParameterValue`, set it
  (current behaviour, keep).
- If the cooked form stores the reference differently (per Task 1), handle that form too.
- **Never silently fall through to clone-and-append when an entry with the requested name
  already exists.** Appending is only valid when the name is genuinely absent.
- Return `false` with a reason string instead of `bool` alone, so `SKIP` lines say *why*.

Sketch (adapt to Task 1's finding):

```csharp
foreach (var el in arr.Value.OfType<StructPropertyData>())
{
    if (MiParamName(el) != param) continue;
    var pv = el.Value.OfType<ObjectPropertyData>()
        .FirstOrDefault(o => o.Name?.Value?.Value == "ParameterValue");
    if (pv != null) { pv.Value = target; return true; }
    // cooked/native form discovered in Task 1 goes here
    return Fail($"entry '{param}' exists but has no writable object value node");
}
```

### Task 4: Build ONE instance and pass the dump gate BEFORE packing

Build `MI_C1_mat_mat_window3_glass_sh` from the ghost clone (`--clone-asset` to
`/Game/Mods/C1Full/Materials`), then `--set-mi-params` with **no parent override**:

```json
{ "textures": {
    "BaseColor": { "pkg": "/Game/Mods/C1/Textures/glass", "name": "area_zz_01_gtf_tex_273_a" },
    "Emissive":  { "pkg": "/Game/Mods/C1/Textures/glass", "name": "area_zz_01_gtf_tex_273_aem_color" } },
  "scalars": { "EmissiveIntensity": 5.0 },
  "vectors": { "Emissive_Tint": { "r": 1, "g": 1, "b": 1, "a": 1 } },
  "static":  { "Use_Emissive": true } }
```

**Gate:** `--dump-mi-params` must show
`BaseColor -> area_zz_01_gtf_tex_273_a` and `Emissive -> area_zz_01_gtf_tex_273_aem_color`
in the SAME array that previously listed the ghost textures, and no `T_GhostLight_*` left.
If the gate fails, stop — no pak, no install.

### Task 5: Single visual test

Pack that one instance (`mod_pack`, mount `../../../`, z-count one higher than v22),
`win_put.sh`, game closed → whitelist as Pak9 → launch → user loads C1 and reports.
Accept/reject purely on: facade texture correct AND lit windows emitting.

### Task 6: Roll out only after Task 5 passes

Apply the same recipe to the other emissive materials using each texture's own `_aem_color`
companion where present. Emit to `/Game/Mods/C1Full/Materials/`, keep original asset names,
one component pak, then fold into the normal materials build rather than a permanent probe.

### Task 7: Record the lessons

Append to `skills/motortown-map-pak-edit/references/materials-and-textures.md`:
- `--set-mi-params` `parent` belongs at root level
- cooked MIC texture arrays are not necessarily `ObjectPropertyData ParameterValue`
- asset name must equal the name the meshes reference
- the `--dump`/`--dump-mi-params` gate is mandatory before any client install

---

---

## Research outcome (2026-11-15) — the documented workflow replaces Tasks 1-5

Binary-patching cooked MICs is not how this is done. Two independent modding guides
describe the same editor-side workflow, and it avoids every failure hit this session:

- https://uemodding.spuds.casa/specific/materials/engine.html
- https://modding.wiki/en/UnrealEngineModdingGuides/CommonAssetReplacementRecipes
  (section "Replicating A Material / Material Instance")
- https://uemodding.spuds.casa/concepts/dummying.html

**The technique ("dummy parent"):**

1. Follow the instance's Parent chain down to a plain `Material` (FModel/UAssetTool).
2. In the UE project, recreate that base **at the exact same package path and name**,
   as a NEW plain Material containing only the parameters needed, each wired into the
   material node (connection semantics irrelevant; it only has to compile).
3. Create a Material Instance from that dummy, placed at the ORIGINAL instance's path
   and name (`/Game/Mods/C1Full/Materials/MI_C1_mat_mat_window3_glass_sh`).
4. Set BaseColor/Emissive/etc. in the real Material Instance Editor.
5. Cook, then **ship only the instance. Never package the dummy parent** — packaging it
   overwrites the real vanilla master with an empty stand-in (the documented
   "silently breaks everything" mistake).

Variation the guides call out for exactly my symptom ("instance still won't render your
texture"): instead of replicating the real base material, create a plain Material with the
**instance's** exact name and path (`/Game/Env/Materials/MI_Halloween_Master`) and instance
from that, ignoring the real chain above it.

Caution from the Rocket League modding wiki: static switch / static bool parameters can
break instances built this way — add `Use_Emissive` only if emission doesn't work without
it, and treat it as a separate test.

Why this fits the evidence: my editor-created instances would have proper
editor-serialized parameter blocks and a correct `ParameterStateId`, instead of
hand-cloned entries that the cooked renderer appears to ignore.

### Revised steps

1. Restore client (done — 9-mod list, pid 1260).
2. In `D:\UEProjects\C1`, create `/Game/Env/Materials/MI_Halloween_Master` as a plain
   Material with params: BaseColor (tex), Emissive (tex), EmissiveIntensity (scalar,
   default 1), Emissive_Tint (vector, white), Normal (tex). Wire each into the node.
3. Create `/Game/Mods/C1Full/Materials/MI_C1_mat_mat_window3_glass_sh` as an instance of
   that dummy; set BaseColor = `glass/area_zz_01_gtf_tex_273_a`,
   Emissive = `glass/area_zz_01_gtf_tex_273_aem_color`, EmissiveIntensity = 5.
4. Cook (project cook that includes these assets), then package ONLY the instance.
5. Dump-gate: Parent import = `/Game/Env/Materials/MI_Halloween_Master`,
   TextureParameterValues = the two C1 textures.
6. Install as Pak9 with the game closed, whitelist, launch, visual check.
7. Only then replicate for the rest of the emissive set.

Do not ship anything under `/Game/Env/` in the pak. That is the whole safety rule here.


- The cooked texture array may not be writable by UAssetAPI at all in this form; if Task 1
  shows that, the fallback is authoring the instances in the UE project against a parent
  that exists there, not more binary patching.
- `Use_Emissive` is a static switch: if the master has no cooked permutation with it on,
  instance-side enabling may do nothing. That is the next thing to test only after the
  texture bindings provably land.
- The emissive source texture `_aem_color` was inferred from its name; confirm it is an
  emissive mask (bright where lit) by viewing it before the rollout.

## RESOLVED (2026-11-15) — editor-authored instance on an emissive-enabled matte parent

Working configuration, verified by probe and by eye:
dummy `MI_MatteBlue_01_E` (MIC) at its vanilla path → fresh C1 instance with
BaseColor + `…_aem_color` Emissive + EmissiveIntensity 5 + white tints, **no static
switches** → client cook → ship the instance only.

Root cause of every grey build: `bHasStaticPermutationResource=True` +
`StaticParametersRuntime` embedded by our cook. The game cannot use our shader
permutation, so instances must inherit the parent's compiled shaders. Any static switch
override creates that block; a fresh instance without overrides does not.

Full recipe, scripts, verification gates and the traps (unsaved edits, stale cook,
install that never copied the pak, failed-load-after-strip) are documented in
`c1/tools/emissive/README.md`.
