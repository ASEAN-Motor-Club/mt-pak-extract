# AGENTS.md

## Build & Run

Always use the Nix dev shell — do not rely on system tools:

```bash
# Enter dev shell
/run/current-system/sw/bin/nix develop

# Or run commands inside it
/run/current-system/sw/bin/nix develop --command bash -c '<command>'
```

**nix binary**: `/run/current-system/sw/bin/nix` (not in default PATH on this system).

## Full Pipeline

```bash
# 1. Extract assets from PAK (Rust)
nix develop --command bash -c 'cargo run --release --quiet -- --config assets.json'

# 2. Parse extracted .uasset files (C#)
nix develop --command bash -c 'cd csharp/CargoExtractor && dotnet run --configuration Release --verbosity quiet -- --batch'

# 3. Aggregate to SQLite (Python)
nix develop --command bash -c 'python3 scripts/aggregate_to_sqlite.py'
```

Output: `motortown.db` (SQLite), `out/*_parsed.json`.

## Required Files

- **`MotorTown-Windows.pak`** — game PAK file (2.9 GB, already in repo root)
- **`.env`** — AES key (`KEY=0x...`), gitignored
- **`Mappings.usmap`** — UE5 type mappings, gitignored. Source: `/tmp/UAssetAPI-source/UAssetAPI.Tests/TestAssets/TestJson/MotorTown.usmap` (clone https://github.com/atenfyr/UAssetAPI to `/tmp/UAssetAPI-source`)
- **UAssetAPI** — C# dependency at `/tmp/UAssetAPI-source/UAssetAPI/UAssetAPI.csproj`. Clone if missing:
  ```bash
  git clone --depth 1 https://github.com/atenfyr/UAssetAPI /tmp/UAssetAPI-source
  ```

## Gotchas

- **Oodle/libstdc++**: The Rust extractor uses Oodle decompression via `repak`, which `dlopen`s `libstdc++.so.6`. The dev shell includes `gcc.cc.lib` for this, but `LD_LIBRARY_PATH` may need to be set if running outside `nix develop`:
  ```bash
  export LD_LIBRARY_PATH=$(nix develop --command bash -c 'echo $LIBRARY_PATH' | tr : '\n' | xargs -I{} echo {}/lib | tr '\n' :)
  ```
- **Large output**: Parser output is massive. Redirect to file: `> /tmp/parser-output.log 2>&1`
- **`Mappings.usmap` permissions**: Must be owned by `opencode`. If copied from git clone, re-copy: `rm Mappings.usmap && cp /tmp/UAssetAPI-source/.../MotorTown.usmap Mappings.usmap`

## Lint / Typecheck

No lint or typecheck commands defined for this project. Rust is checked by `cargo build`, C# by `dotnet build`, Python has no type checking.

## Project Structure

```
src/main.rs                    # Rust PAK extractor (AES decrypt + Oodle decompress)
csharp/CargoExtractor/         # C# UAsset parser (uses UAssetAPI)
csharp/LevelExtractor/         # C# map/level actor extractor
scripts/aggregate_to_sqlite.py # Python: parsed JSON → normalized SQLite
assets.json                    # List of 264 asset paths to extract
blueprint_assets.json          # Blueprint variant paths for weight aggregation
flake.nix                      # Nix dev environment + apps
```
