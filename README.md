# MotorTown PAK Asset Extractor

Extract and parse game data from MotorTown's Unreal Engine 5.5 PAK files.

## Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled
- `MotorTown-WindowsServer.pak` file
- `Mappings.usmap` file (generated using [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) with the Dump Usmap feature)
- `.env` file with AES decryption key

### Setup

1. Place game files in the project root:
   ```
   MotorTown-WindowsServer.pak
   Mappings.usmap
   ```

2. Create `.env` with the AES key:
   ```
   KEY=0xYOUR_AES_KEY_HERE
   ```

## Usage

### One-Command Extraction

Extract all assets listed in `assets.json`:

```bash
nix run .#extract
```

Output goes to `out/` directory as parsed JSON files.

### Custom Asset List

Edit `assets.json` to specify which assets to extract:

```json
{
  "assets": [
    "MotorTown/Content/DataAsset/Cargos",
    "MotorTown/Content/DataAsset/Vehicles/Vehicles"
  ]
}
```

### Manual Commands

Enter the development shell:
```bash
nix develop
```

**List available DataAssets:**
```bash
cargo run -- --list
```

**Extract single asset:**
```bash
cargo run -- "MotorTown/Content/DataAsset/Cargos"
```

**Parse extracted assets:**
```bash
cd csharp/CargoExtractor
dotnet run -- --batch           # Parse all in out/
dotnet run -- Cargos.uasset     # Parse single file
```

## Output

```
out/
├── manifest.json           # List of extracted assets
├── Cargos_parsed.json      # Cargo data (84 rows)
├── Vehicles_parsed.json    # Vehicle data (162 rows)
├── Engines_parsed.json     # Engine parts (34 rows)
└── ...
```

## Project Structure

```
├── src/main.rs             # Rust PAK extractor
├── csharp/CargoExtractor/  # C# UAsset parser (UAssetAPI)
├── assets.json             # Config: assets to extract
├── flake.nix               # Nix build/dev environment
└── scripts/                # Helper scripts
```

## How It Works

1. **Rust extractor** decrypts PAK file using AES key, decompresses with Oodle, extracts `.uasset`/`.uexp` files
2. **C# parser** uses UAssetAPI with `.usmap` mappings to deserialize unversioned UE5.5 properties into JSON

## License

MIT
