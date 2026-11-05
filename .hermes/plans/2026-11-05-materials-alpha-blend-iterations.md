# Plan — materials/alpha/blending iterations (C1Full)

Rule for this task: **every iteration gets a written plan first, and the plan is gated against
`c1/docs/MATERIALS_CHECKLIST.md` (gates M1–M18) — the materials checklist only.** The full
`C1FULL_BUILD_CHECKLIST.md` covers geometry, cook, maps, nav and shipping, and does not apply to a
material-pak iteration. No build without a stated single variable, the gate list it must pass, and
the decision rule for what its result means.

History and mechanisms: `c1/docs/MATERIALS_ALPHA_BLEND.md`.
Prior state: material paks A–F shipped; trees still render a black background.

---

## Where the evidence stands

- Foliage instances now carry the correct parameter (`BaseColor`), correct parent (`M_plants`),
  `BLEND_Masked` + TwoSided + clip 0.3333, and a texture with real alpha (measured 62.5 %
  transparent on `area_zz_02_gtf_tex_191`). **Still black.** So the remaining fault is not in
  the instance.
- The release build renders correctly and ships, verbatim: 1,633 material instances, **four**
  masters (`M_C1_Surface`, `_Tex`, `_Masked`, `_Trans`), and **2,314 textures**, with
  **zero** shader archives.
- The release's own `MI_C1X_mat_tree_02` parents `M_C1_Surface_Masked` at
  `/Game/Mods/C1/Materials/` — a mod-owned master — and carries `BaseColor` → `area_zz_02_gtf_tex_191`,
  TwoSided true, clip 0.3333.
- Our pak A shipped those same masters (byte-identical sizes, 3,600–3,779 B) and checkerboarded.
  The difference: **pak A shipped no textures.** Our port carried 2,148 textures, the release
  2,314 — the masters' own default texture inputs were not in our set, so they could not compile.

## Checklist conflict this resolves (read before building)

`MATERIALS_CHECKLIST.md` **M18** records the open question, inherited from
`C1FULL_BUILD_CHECKLIST.md §2b`: *parent must be a vanilla MT master*. Pak G deliberately violates that by shipping
the author's masters at their original path. This is an **A/B against a measured release**, not a
hypothesis: the release is byte-for-byte this configuration and renders. Per the skill's rule, the
checklist entry is amended **only after G renders on screen** — not before, and not on the strength
of this argument alone.

---

## Iteration G (built, awaiting install)

**Single variable**: ship the release's complete material set (instances + 4 masters + all
2,314 textures) instead of our hand-routed instances on host masters.

**Artifact**: `zzzzz_AMC_C1Mats_G_P.pak`, 119,152,165 B, sha256 `7d2ea7cfbf627ea4…`.

**Gate status against `MATERIALS_CHECKLIST.md`:**

- **M4** no shader archives — **PASS**: `grep -ci shaderarchive` = 0 on the built pak.
- **M5** counts — **PASS**: 1,625 instances in / 1,625 out; 2,314 textures; 4/4 masters;
  0 shader files. (`Materials/` also carries 4 unused test masters from the release — inert.)
- **M6** absolute output path — **PASS after a failure**: the first build used a relative `--out`,
  reported `MATS_PAK_OK`, and left no file (temp dir deleted). Rebuilt absolute.
- **M7** parent resolves — **PASS**: `MI_C1X_mat_tree_02` → `Parent (Object): Index=-2` →
  `Imports[1] = M_C1_Surface_Masked`.
- **M8** colour parameter matches master contract — **PASS**: `BaseColor`, which is what
  `M_C1_Surface_Masked` declares (verified against the release's own instance).
- **M9** bindings non-null — **PASS**: `ParameterValue (Object): Index=-7` on the instance
  extracted back out of the pak.
- **M10** every referenced texture ships — **PASS**: 2,314 textures; `area_zz_02_gtf_tex_191.uasset`
  present. This is the gate pak A failed (masters shipped, zero textures).
- **M11** masked override serialised — **PASS**: `TwoSided (Bool): True` and
  `OpacityMaskClipValue 0.3333` in the same dump (blend byte not used as a pass condition).
- **M12** texture can actually cut — **PASS**: `area_zz_02_gtf_tex_191` is PF_BC7 with 62.5 %
  transparent pixels, measured by the alpha census.
- **M2** control retained — pak F archived; geometry pak `50956D9E…` untouched.
- **M13** install gate — pending: `MATS_SHA_MATCH` against `7d2ea7cf…` (blocked, game running).
- **M18** — this iteration is the A/B that decides it: mod-owned masters + complete texture set.

**Decision rule:**

- Trees cut and markings blend → configuration proven; amend §2b to record that a mod-owned
  master renders **iff** its complete texture set ships, and make the texture-coverage gate
  mandatory for any non-vanilla parent.
- Trees still black → the fault is downstream of the material set (mesh slot/UV/level), and the
  next iteration's variable is geometry, not materials. Do not ship another material variant.
- Something else breaks (opaque surfaces, markings) → the release set differs from our mesh
  expectations; bisect between pak F and G by name family, one family per iteration.

**Rollback**: reinstall pak F (`FE387B84CE76A0CF`, 4,910,981 B) and confirm `MATS_SHA_MATCH`.

---

## Standing rules for the next iterations

1. One variable per build; state it in the plan before building.
2. Every plan lists the gates it must pass and how each is measured.
3. Build into an **absolute** output path (`build_matspak.sh` runs in a temp dir and deletes
   relative outputs on exit — pak G was lost once this way).
4. Gate on asset dumps, not exit codes; assert input count == output count.
5. Keep the previous pak installed-and-archived as the control; never test two paks at once.
6. Do not amend a checklist rule on an argument — only on an on-screen result.
