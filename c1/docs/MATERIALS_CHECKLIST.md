# Materials checklist — every material-pak iteration

Scope: material instances, masters, alpha/blending, and the textures those materials sample.
Nothing here touches geometry, level actors, nav, collision or the map cook — those belong to
`C1FULL_BUILD_CHECKLIST.md`, which is a different gate set for a different kind of build.

Rule: **a material iteration gets a written plan first, and the plan must pass every gate below
before the pak is installed.** Gates are measured on the built artifact, never on an exit code.

Mechanisms and history: `docs/MATERIALS_ALPHA_BLEND.md`.

---

## Preconditions

- **M1** — The game must be closed. A locked `zzzzz_AMC_C1Mats_P.pak` reports
  `MATS_SHA_MISMATCH` next to "being used by another process"; that is a lock, not a bad build.
  Do not rebuild in response — close and re-run the same install.
- **M2** — The previous pak is archived as the control, and the geometry pak's sha256 is recorded
  (`50956D9E…` for v26) so it can be proven untouched afterwards.
- **M3** — The iteration statement exists in the plan: **one** variable, what its result will mean,
  and what the rollback is.

## Build gates

- **M4 — no shader archives.** `mod_explore <pak> --list | grep -ci shaderarchive` = `0`.
  Shipping one crashes the client at boot (`GlobalShader.cpp:803`). `build_matspak.sh` gates this.
- **M5 — counts match.** Instances out == instances in; texture files out == textures staged;
  every master shipped is present. A batch pass that `continue`s on failure drops assets silently
  and the mesh falls back to the engine default — which reads as a new, unrelated bug.
- **M6 — absolute output path.** `build_matspak.sh` packs inside a temp dir and deletes relative
  outputs on exit. A relative `--out` yields `MATS_PAK_OK` for a file that does not exist.

## Per-asset gates (dump, don't assume)

Dump one instance **per route family and per destination master** — out of the built pak, not out
of the staging dir.

- **M7 — parent resolves.** Read `Parent (Object): Index=-N`, then `Imports[N-1]`. Never grep the
  name map: stale masters from earlier passes stay there and read as the wrong parent.
- **M8 — the colour parameter name matches that master's contract.** `M_plants`/`M_PropMaster`/
  `M_GlassTrans` take `BaseColor`; `M_AlphaTest` takes `Color`. A mismatch is a dead binding: the
  instance renders the master default, which on a cutout looks like a **black background**.
  Rename with `--rename-texture-param`, then re-dump.
- **M9 — texture bindings are non-null.** `ParameterValue (Object)` must be non-zero (`Index=-7`,
  never `Index=0`). `Index=0` means flat white and comes from cook output or a duplicated tree.
- **M10 — every texture the instances reference exists in the pak.** This is the gate pak A failed:
  it shipped the author's masters with none of their textures, so the masters could not compile and
  the whole map checkerboarded.
- **M11 — masked override serialised.** `TwoSided (Bool): True` **and** `OpacityMaskClipValue ≥ 0`
  in the same dump as the parent. The `BlendMode (Byte)` field is unreliable in UE5.5 dumps — do
  not read it as the pass condition. `changed=N` from the tool proves nothing about serialisation.
- **M12 — masking is only meaningful if the texture can cut.** Confirm the bound texture's format
  carries alpha (BC1/DXT1 does not, whatever the payload suggests) and that its alpha is actually
  transparent. Alpha present elsewhere in the file is not evidence.

## Install gate

- **M13 — `MATS_SHA_MATCH`** against the built pak's sha256, and the geometry pak's sha256
  re-checked as unchanged in the same step.

## On-screen decision (pre-committed in the plan)

- **M14** — State, before installing, what each outcome means. Specifically: a build that changes
  **nothing at all** across the whole set is a *targeting* failure, not a tuning failure — the
  instances changed are not the ones on screen. Verify the touched names belong to the family the
  user reported before touching the same flag again.
- **M15** — One variable per build. Never ship a second variant that differs in several ways; it
  discards the control and turns the investigation into guesswork.
- **M16** — Amend this checklist only after an on-screen result. A rule proven on screen is not
  retired because one reading contradicts it, and a rule is not loosened on an argument.

## Rollback

- **M17** — Reinstall the control pak and confirm its `MATS_SHA_MATCH`. Quote the hash when
  reporting the rollback: "restored, hash matches" is checkable, "reverted" is not.

---

## Open question this checklist deliberately records

**M18 — is §M7's "vanilla master only" rule absolute?** The release ships mod-owned masters
(`/Game/Mods/C1/Materials/M_C1_Surface*`, 3.6–3.8 KB, no shader strings, no shader archives) and
renders correctly, which contradicts the hard rule in `C1FULL_BUILD_CHECKLIST.md §2b`. Working
hypothesis: a mod-owned master renders **iff** its complete texture set ships, because its default
texture inputs are part of its compile inputs. Not yet proven on our build — until it is, host
masters remain the default and shipping a mod master is an explicit, documented A/B.
