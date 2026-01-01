#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG="${1:-assets.json}"

cd "$ROOT_DIR"

echo "=== MotorTown Asset Extractor ==="
echo "Config: $CONFIG"
echo

# Step 1: Extract from PAK using Rust
echo "Step 1: Extracting assets from PAK..."
cargo run --release --quiet -- --config "$CONFIG"

# Step 2: Parse extracted assets using C#
echo
echo "Step 2: Parsing extracted assets..."
cd csharp/CargoExtractor
dotnet run --configuration Release --verbosity quiet -- --batch

echo
echo "=== Complete! Output in out/ ==="
ls -la "$ROOT_DIR/out/"*.json 2>/dev/null | awk '{print "  " $NF}'
