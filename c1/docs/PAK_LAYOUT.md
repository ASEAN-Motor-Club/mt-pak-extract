# Pak layout: one asset, one pak

How the C1Full/Shuto work is split into paks, why it is split that way, and the gates that keep it
that way. Supersedes the earlier "one content pak plus small extras" model.

## The rule

Pak mounting keeps exactly **one** copy of each `/Game/...` path. If two installed paks ship the
same asset, the engine does not report a conflict — it silently drops one, chosen by filename sort.
So any overlap is a latent eviction, and the only durable fix is **exclusive ownership**: every
asset path is shipped by exactly one pak.

Consequences that follow from it:

- "Override paks" (`zzzz_thing_P.pak` shadowing a fix inside a bigger pak) are a race, not a
  mechanism. Split ownership instead of layering.
- Filename sort must not decide whether a feature exists. Leading-`z` counts are no longer
  load-bearing; the names below are plain labels.
- Rebuilding a pak must never re-ship another pak's assets. A mesh rebuild that also carries
  `Maps/<Map>.umap` re-ships a **raw cook** — no `DefaultGameMode`, no SunSky child actor class, no
  post-cook PlayerStart/garage edits — and a nav-less roads level.

## Ownership table

| pak | owns |
|---|---|
| `zzz_AMC_C1Base_v2_P.pak` | `/Game/Mods/C1/**` shared textures (6,113 files) + `BP_C1_Prop`, `BP_C1_Sky` |
| `zzzzz_AMC_C1Mesh_v2_P.pak` | `Mods/C1Full/Meshes/**` — 554 cell meshes |
| `zzzzz_AMC_C1Mats_P21_P.pak` | `Mods/C1Full/Materials/**` — 1,653 material instances |
| `zzzzzz_AMC_C1Map_v3_P.pak` | `C1Full.umap` — persistent level, **sole owner** of the sublevel references |
| `zzzzzzzz_AMC_C1NavTest_v2_P.pak` | `C1Full_Roads.umap` — roads + nav bake |
| `zzzzzzzzzz_AMC_Shuto_Lights_v12_P.pak` | `C1Full_Lights.umap` — 10,474 lights |

The base pak deliberately keeps the legacy `/Game/Mods/C1` tree: shipped material instances
reference it **806 times**. It must keep nothing else that another pak owns.

## What this replaced

`zzzz_AMC_C1Test_P.pak` was a single 699 MB "geometry" pak that actually contained meshes,
materials, all four `Maps/*.umap` **and** the legacy texture tree. Across the installed set that was
6 paks / 10,535 entries with **4,420 entries claimed twice**, resolved by alphabet.

After the split: 6 paks, 10,537 entries, **0 duplicates**, shipped set **1.96 GB → 664 MB**.

## Build tooling

| tool | gate |
|---|---|
| `c1/tools/build_levelpak.sh <cooked-maps> <out> <stem>` | exactly one level asset; fails if a second appears; for `C1Full` greps the `.umap` for `DriveGameModeBP` / `MTSunSky` / `GarageActorBP` and refuses a raw cook |
| `c1/tools/build_meshpak.sh <cooked-meshes> <out> [count]` | meshes only; fails on a leaked `.umap`, a `Materials/` dir, a missing `.uexp`, or a wrong mesh count |
| `c1/tools/build_basepak.sh <source-pak> <out>` | `repak unpack -i` only the owned trees, strip the rest, then gate both ways: no Meshes/Materials/Maps survive, and the shared texture tree still has thousands of files |
| `c1/tools/build_matspak.sh <content-dir> <out>` | material instances only |
| `c1/tools/pakset.py manifest <pak> <dir>` | writes `{pak, bytes, sha256, assets[]}` |
| `c1/tools/pakset.py check <dir>` | **the ship gate** — fails on any asset with two owners, and on two versions of one pak installed together |

## Ship procedure

1. Build the single pak you changed; the builder refuses if it stages another pak's assets.
2. `pakset.py manifest <new-or-changed-pak> c1/out/pakset` to refresh its manifest.
3. `pakset.py check c1/out/pakset` — must print `OK: every asset has exactly one owner`.
4. Upload; install with the game **closed** (cooks and reimports do not need it closed).
5. **Remove the superseded pak in the same step that copies the new one.** Never leave two versions
   of one pak in `Content/Paks` — that is the stem failure `pakset.py check` reports.
6. Re-read size + sha256 from the installed directory and compare with the validated manifest. Trust
   the bytes on disk, not the build log.

## Manifests

`c1/out/pakset/*.json` is the record of the **shipped** set — one manifest per installed pak, each
carrying its byte size, sha256 and full asset list. Commit it alongside the build that produced it:
it is the only artifact that lets a later session answer "which pak owned this asset, and was it the
one on disk" without re-listing 700 MB of paks.

## Dev vs release

The split above is the **development** layout: six paks, each rebuilt independently, so iterating on
meshes never touches lights and a nav bake never evicts a lighting pass.

A **release** is still one consolidated pak (`zzz_AMC_Shuto_P.pak`), because players should install
one file. It is built by *unpacking the family paks and repacking the union* — never by shipping two
paks that claim the same asset. The ownership rule still applies while assembling it: the union must
contain each path exactly once, and `pakset.py check` on the pre-consolidation set is what proves the
merge is a union rather than a race with a winner.
