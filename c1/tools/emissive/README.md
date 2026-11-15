# C1 emissive materials — working recipe (verified in-game 2026-11-15)

Result: a C1 building material renders **lit, opaque, non-reflective**, with its windows
**emitting**, on the live client. Verified by runtime probe (parent resolves to our
instance) and by eye.

Working pak: `zz…z_AMC_C1EmisMatte_P.pak` (archived at `/opt/data/releases/c1/`).

## The recipe

1. In `D:\UEProjects\C1`, create a **dummy parent** at the *exact package path and name*
   of a vanilla material that already has emissive enabled:
   `/Game/Env/Materials/Color/MI_MatteBlue_01_E`, class **MaterialInstanceConstant**.
   Parent it to a dummy `/Game/Env/Materials/Master/M_PolygonMaster` (a plain Material).
2. Create the C1 instance **fresh** (`AT.create_asset`, do not reuse an instance that
   previously had static switches) at the exact path/name the meshes reference:
   `/Game/Mods/C1Full/Materials/MI_C1_mat_mat_window3_glass_sh`.
3. Set its parent to the dummy. Override only:
   - `BaseColor` → the material's own colour texture
   - `Emissive` → the matching `…_aem_color` texture
   - `EmissiveIntensity` → 5.0
   - `BaseColor_Tint`, `Emissive_Tint` → white (the matte parent is blue by default)
4. **No static switch parameters.** This is what keeps the cook from attaching a
   `bHasStaticPermutationResource` + `StaticParametersRuntime` block.
5. Save with `EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)`.
6. Cook: `-run=cook -TargetPlatform=Windows -CookAll` (`cook_client.ps1`, which first
   deletes the previous cooked instance so the cook cannot silently reuse it).
7. Ship **only the C1 instance** in the pak. Never ship the dummies — they would
   overwrite the real vanilla masters.

Verified cooked shape: ~5–6 properties, ~1–2 KB export. The original game instance has
4 properties / 1,088 B. If your export is ~15 KB with `bHasStaticPermutationResource`,
it will render **grey**.

## Why this works

The game cannot use the shader permutation our cook embeds in a material instance.
Instances must **inherit the parent's compiled shaders**. Any instance carrying
`bHasStaticPermutationResource=True` + `StaticParametersRuntime` renders as default grey
on a lit parent. (An unlit parent, `M_FlashLight_LF`, tolerates it and emits, but is
black in daylight.)

So: pick a parent that *already* has emissive enabled, override textures/scalars only,
and the instance inherits an emissive-capable shader without requesting a permutation.

## Parent choices measured

- `MI_MatteBlue_01_E` (Color/) — **chosen**: lit, matte, emissive on. Needs white tints.
- `MI_FishingVil_Glass_01` — works but is glass: translucent + reflective. Not for walls.
- `M_PolygonMaster` / `MI_PolygonMaster` + `Use_Emissive` override — grey (permutation).
- `M_PropMaster` (original parent) — no emissive support.
- `M_FlashLight_LF` — unlit; emits, but black in daylight.

## Replication for other materials

For each C1 material that has an `…_aem_color` texture companion, repeat steps 1–7 with
that material's own asset name and its two textures. Same parent, same tints, same
cook. Do not invent per-material parents.

## Scripts

- `matte_parent.py` — the exact working build (dummy parent + fresh instance + params).
- `cook_client.ps1` — client cook; deletes the previous cooked instance first.
- `fix_whitelist.ps1` — install: copies the pak into `Paks`, deletes stale probes,
  rewrites `CustomPak.ini` (Count + PakN), reads it back. Set `$keep` to the pak name.
- `autoload.sh`, `open_level.lua` — launch settle (15 s), `open` the C1 map, probe.
- `probe_mat.lua` — prints the live instance's resolved parent at both candidate paths.
- `probe_tex.lua` — confirms textures resolve in-game.
- `kill_any.ps1`, `launch_game4.ps1` — close / relaunch the client.

## Verification gates (all required, in order)

1. `save_asset(..., only_if_is_dirty=False)` returned True.
2. Cooked hash **differs** from the previous build.
3. Dump shows the intended parent import and **no** `bHasStaticPermutationResource`.
4. Pak copied into `Paks` (the script prints COPIED) — an install that only writes the
   whitelist installs nothing.
5. `CustomPak.ini` written **while the game is closed**; it rewrites the file on exit.
6. Runtime probe returns *our* parent, not the vanilla one.

## Traps that cost the most time (do not repeat)

- **Unsaved edits**: `set_material_instance_parent` etc. do not dirty the package;
  `save_loaded_asset` then logs "All files are already saved" and writes nothing. Use
  `save_asset(..., only_if_is_dirty=False)`. `mark_package_dirty()` is not exposed.
- **Stale cook output**: identical sha256 across three "different" builds proved the
  cook was not regenerating. Delete the cooked asset before cooking; compare hashes.
- **Install script that never copied the pak**: five builds were tested with no pak on
  disk. The whitelist entry pointing at a missing file yields the *original* material,
  which looks like "correct but no glow".
- **Stripping the permutation block post-cook** made the package fail to load; the
  original material then rendered, masquerading as success. Prevent the block at
  creation instead (no static switches).
- **Binary patching of cooked instances** (`--set-mi-params`, clones) is not a viable
  route: parameter overrides were visually inert. Editor-authored instances are.
- **Dummy class must match** the vanilla asset's class (MaterialInstanceConstant vs
  Material) or the load fails.
- **Never probe objects at the frontend**; it crashed the client. Probe only after the
  map is loaded.
