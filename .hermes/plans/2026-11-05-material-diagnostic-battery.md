# Plan — diagnostic pak battery (materials/alpha), iteration H

Rule: plan first, gated against `c1/docs/MATERIALS_CHECKLIST.md` (M1–M20). One variable per pak,
one pak installed at a time, decision rule pre-committed.

Context: pak F is installed and is the control (`FE387B84CE76A0CF`). Pak G was rolled back — it
relocated the release's material tree into `C1Full`, violating **M19**, and defaulted every
material. Geometry pak is no longer v26: installed build is `FD746972…` (699,369,597 B), v26 was
`50956D9E…` (699,480,785 B).

We have been reasoning about *why* trees are black. This iteration stops reasoning and measures
three independent links in the chain, because any one of them being broken produces the same
picture:

- L1 — does a **texture** shipped in a material pak reach the screen at all?
- L2 — do **instance edits** shipped in the material pak reach the screen at all?
- L3 — does a texture we *know* carries an alpha mask produce a cutout on the tree instances?

If L1 or L2 fails, every alpha and blend conclusion drawn so far is void — those builds changed
assets the game never used — and that explains "still the same" without any new material theory.

## Paks to build (each is one variable, all M1–M20 gated)

- **D1 `tex-probe`** — material pak containing only a magenta version of one texture that the tree
  instances actually bind (`area_zz_02_gtf_tex_191`), plus the F instance set unchanged.
  *Variable: texture payload.* Expected if L1 holds: trees render magenta panels. If the map looks
  exactly like F, the texture override is not reaching the screen (geometry-pak copy wins, or the
  path is wrong).
- **D2 `inst-probe`** — every instance's `BaseColor` repointed to that same magenta texture.
  *Variable: instance binding.* Expected if L2 holds: essentially the whole world turns magenta.
  If nothing changes, our instance set is not the set the meshes resolve (M20 failure).
- **D3 `alpha-probe`** — the 25 tree/fence instances get a `BaseColor` pointing at a texture we
  ship and control: 60 % transparent pixels baked in, magenta where opaque.
  *Variable: coverage source.* If the trees now cut out with magenta leaves, the mask path works and
  the fault was the coverage in the texture they bound. If they stay black, mask/blend is broken for
  these instances regardless of texture content.

D3 subsumes D1 for the tree family, so if only two launches are affordable, run **D2 then D3**.

## Gates

- **M4** no shader archives; **M5** counts in == out; **M6** absolute output path.
- **M7/M8/M9** dump one touched instance out of the built pak: parent resolves, colour parameter
  matches the master contract, `ParameterValue (Object)` non-zero.
- **M19** every asset at the path its references use — magenta textures go to
  `/Game/Mods/C1/Textures/...` (where the instances' imports point), instances stay
  `/Game/Mods/C1Full/Materials/...`. **No relocation between namespaces.**
- **M20** diff the material names the installed geometry pak references against the pak's set
  before believing any screenshot.
- **M2/M13** control pak archived; geometry sha recorded beside the material sha.
- **M14** decision rules above are fixed before building.

## Decision matrix

- D1 magenta, D2 magenta → chain live; trees are a real material/coverage problem; D3 decides
  whether it is the texture or the mask path.
- D1 nothing, D2 magenta → textures are shadowed but instances are live; the alpha bakes were no-ops
  and the fix is texture-side at a path that wins.
- D2 nothing → instances are not the set the meshes resolve (or the geometry pak changed again).
  Stop material work; fix targeting first.
- D3 still black with a known-good alpha texture → mask/blend path broken for these instances; next
  variable is the parent master, not the texture.

## Rollback

Reinstall F (`FE387B84CE76A0CF`) after each probe and confirm `MATS_SHA_MATCH` (M17).
