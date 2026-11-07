# Plan — one content namespace for C1 and C1Full

Status: proposed (2026-11-05). Owner: Yumemi. Approval: freeman.

## Decision

C1 (corridor) and C1Full (full map) are **alternative installs, never co-installed**. A player
picks one. Therefore both may share the *same* package paths, and there is no reason to keep two
copies of the same meshes, materials and textures.

Canonical namespace: **`/Game/Mods/C1Full/`** — it already holds the newest content generation
(555 meshes, 1,609 instances) and the full map's cell actors now point at it. The `C1` tree in the
project becomes retired.

Reason the namespace is not `/Game/Mods/C1/`: the published corridor pak is frozen and will not be
rebuilt; pointing new work at the tree the live release already owns would make the corridor pak
shadow a future full-map build if anyone ever installed both. Keeping full-map content in
`C1Full` keeps release identity unambiguous at the path level.

## What is wrong today

- Two full copies of the same assets: `Content/Mods/C1` (4,587 uassets) and `Content/Mods/C1Full`
  (5,300). They have already diverged — e.g. `c-10_-20` is 71,574 B vs 72,890 B, `c-10_-21` is
  1,156,873 B vs 1,276,103 B.
- Materials exist twice, and alternated between "parent our own master" and "parent the game's
  master" depending on which tree was last touched.
- Textures live only in `C1/Textures` (2,148) while `C1Full/Textures` has 1 asset, so instances in
  the `C1Full` tree reference the other tree anyway. Half-shared, fully confusing.
- The level referenced `C1/Meshes` until 2026-11-05 even though `C1Full` was the newer generation.

## Target layout

```
Content/Mods/C1Full/
  Maps/            C1Full.umap, C1Full_Roads.umap   (+ C1.umap, C1_Roads.umap if corridor is rebuilt)
  Meshes/          554 tiles + uvquad
  Materials/       1,609 instances, parented to the game's own M_PropMaster / M_PolygonMaster
  Textures/        2,148 assets moved from C1/Textures
  Collision/       collision-only proxies (61)
  Kit/             shared kit meshes (83)
```

No `Content/Mods/C1/` at all. Release identity is carried by **the map package**, **the pak
filename**, and the installer guard — not by duplicated asset paths.

## Steps

1. **Prove the superset.** Diff `C1` against `C1Full` asset-by-asset (name, size, sha256). Produce
   three lists: identical, differing, only-in-C1. Nothing is deleted until
   `only-in-C1` is empty or explicitly accounted for.
2. **Decide divergent meshes.** For every "differing" mesh, the `C1Full` copy wins (later
   generation, produced after the scale-100 and single-LOD fixes). Record the decision in the
   build facts block.
3. **Move textures.** `C1/Textures` → `C1Full/Textures`, then rewrite the `/Game/Mods/C1/Textures/`
   references inside every instance and mesh in the editor (rename folder + fix up redirectors,
   not byte patching).
4. **One material set.** Author the instances once in `C1Full/Materials`, parented to the game's
   own masters, `BaseColor` as the only texture parameter, `Metallic`/`Roughness` as scalars.
   Masked surfaces keep the plant/polygon route with an explicit blend override. Nothing parents
   to an asset we ship.
5. **Retire `Content/Mods/C1/`.** Delete after step 1–4 evidence, in a commit that can be reverted
   on its own.
6. **Corridor release policy.** The published corridor pak is frozen. If corridor ever needs a
   rebuild, build it from this same tree with only the corridor map + its subset of cells, so it
   inherits the identical meshes and materials. No second content tree is created for it.
7. **Installer guard.** Both installers refuse to proceed when the other release is present:
   `zzz_AMC_C1Full_*_P.pak` must not coexist with `zzz_AMC_C1_*_P.pak`. This is the only protection
   needed for shared package paths, because shared paths are only dangerous when both are mounted.
8. **Pipeline constants.** Put the namespace in `c1/pipeline/constants.json` (`content_root`,
   `map_names`) so no script hardcodes `Mods/C1` or `Mods/C1Full` again.

## Gates (add to `C1FULL_BUILD_CHECKLIST.md`)

- **G-namespace**: no shipped pak entry may contain `/Game/Mods/C1/` when the build is a C1Full
  release, and no source asset may reference both roots.
- **G-superset**: every mesh referenced by the map exists in the pak, and every material referenced
  by those meshes exists in the pak (name-level coverage, counted, not eyeballed).
- **G-shaderarchive** (§8b, already committed): zero `ShaderArchive-*` entries.
- **G-coinstall**: installer guard rejects a co-install attempt with a clear message.

## Rollback

Each step is its own commit. `Content/Mods/C1` is deleted only after a verified diff, and the
deletion commit is separate so `git revert` restores the entire tree.

## Open questions

- Whether the corridor map package is also moved into `C1Full/Maps` in the editor (it currently
  lives in `C1/Maps`) — required if the corridor is ever rebuilt; not required to ship the full map.
- Whether `Kit/` and `Collision/` are referenced by anything the full map ships, or are authoring
  leftovers (to be answered by the step-1 diff rather than assumption).
