#!/usr/bin/env bash
set -euo pipefail

# new-version — Full pipeline for handling a new Motor Town game update
#
# Usage:
#   new-version.sh <version> [pak_path]
#
# Examples:
#   new-version.sh v0.7.19 v0.7.19.pak
#   new-version.sh v0.7.19                    # uses <version>.pak automatically
#
# What it does:
#   1. Archives current extracted data → versions/<current_version>/
#   2. Registers the new PAK in game_versions.json
#   3. Symlinks new PAK as MotorTown-Windows.pak
#   4. Runs full extraction pipeline (Rust → C# → Python)
#   5. Archives new extracted data → versions/<new_version>/
#   6. Git commits + tags
#   7. Creates worktree for previous version (parallel mod building)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

NIX=/run/current-system/sw/bin/nix
MT_VERSION="$SCRIPT_DIR/mt-version.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}[new-version]${NC} $*"; }
warn() { echo -e "${YELLOW}[new-version]${NC} $*"; }
err()  { echo -e "${RED}[new-version]${NC} $*" >&2; }
step() { echo -e "\n${BOLD}${CYAN}═══ $* ═══${NC}"; }

usage() {
  cat <<'EOF'
Motor Town New Version Pipeline

Usage: new-version.sh <version> [pak_path]

Arguments:
  version    Version tag (e.g. v0.7.19)
  pak_path   Path to new .pak file (default: <version>.pak in repo root)

Examples:
  # PAK already downloaded and renamed
  new-version.sh v0.7.19 v0.7.19.pak

  # PAK named <version>.pak in repo root
  new-version.sh v0.7.19

  # Download from Windows first, then process
  scp freeman@100.85.236.98:'D:/SteamLibrary/steamapps/common/Motor Town/MotorTown/Content/Paks/MotorTown-Windows.pak' v0.7.19.pak
  new-version.sh v0.7.19 v0.7.19.pak

This script:
  1. Archives current game data → versions/<current>/
  2. Symlinks new PAK as MotorTown-Windows.pak
  3. Runs full extraction pipeline
  4. Archives new data → versions/<new>/
  5. Git commits + tags
  6. Creates worktree for previous version
EOF
}

# ── Preflight checks ─────────────────────────────────────────────────────
preflight() {
  local version="$1" pak_path="$2"

  if [[ ! -f "$pak_path" ]]; then
    err "PAK file not found: $pak_path"
    err ""
    err "To download from your Windows machine:"
    err "  scp freeman@100.85.236.98:'D:/SteamLibrary/steamapps/common/Motor Town/MotorTown/Content/Paks/MotorTown-Windows.pak' $pak_path"
    exit 1
  fi

  if [[ ! -f "$ROOT_DIR/.env" ]]; then
    err ".env file not found (AES key required)"
    exit 1
  fi

  if [[ ! -f "$ROOT_DIR/Mappings.usmap" ]]; then
    err "Mappings.usmap not found"
    err "  cp csharp/UAssetAPI/UAssetAPI.Tests/TestAssets/TestJson/MotorTown.usmap Mappings.usmap"
    exit 1
  fi

  # Check if version already exists
  if "$MT_VERSION" list 2>/dev/null | grep -q "$version"; then
    err "Version $version already exists. Use 'mt-version.sh switch $version' instead."
    exit 1
  fi
}

# ── Register new PAK in manifest ─────────────────────────────────────────
register_pak() {
  local version="$1" pak_path="$2"
  local pak_basename pak_size

  pak_basename=$(basename "$pak_path")
  pak_size=$(ls -lh "$pak_path" | awk '{print $5}')

  python3 -c "
import json, datetime
m = json.load(open('$ROOT_DIR/game_versions.json'))
m.setdefault('versions', {})['$version'] = {
    'pak_file': '$pak_basename',
    'pak_size': '$pak_size',
    'pak_date': datetime.date.today().isoformat(),
    'git_tag': None,
    'notes': ''
}
json.dump(m, open('$ROOT_DIR/game_versions.json', 'w'), indent=2)
"
  log "Registered $pak_basename ($pak_size) as $version"
}

# ── Main ──────────────────────────────────────────────────────────────────
main() {
  local version="${1:-}"
  local pak_path="${2:-$ROOT_DIR/${version}.pak}"

  if [[ -z "$version" || "$version" == "-h" || "$version" == "--help" ]]; then
    usage
    exit 0
  fi

  # Resolve relative paths
  if [[ "$pak_path" != /* ]]; then
    pak_path="$ROOT_DIR/$pak_path"
  fi

  preflight "$version" "$pak_path"

  local current
  current=$(python3 -c "import json; print(json.load(open('$ROOT_DIR/game_versions.json')).get('active', ''))" 2>/dev/null || echo "")

  echo -e "\n${BOLD}Motor Town — New Version Pipeline${NC}"
  echo -e "  Current: ${GREEN}${current:-none}${NC}"
  echo -e "  New:     ${GREEN}${version}${NC}"
  echo -e "  PAK:     $(basename "$pak_path") ($(ls -lh "$pak_path" | awk '{print $5}'))"
  echo ""

  # ── Step 1: Archive current ────────────────────────────────────────────
  step "Step 1/6: Archive current version ($current)"

  if [[ -n "$current" && -d "$ROOT_DIR/versions/$current/out" ]]; then
    log "Already archived, skipping"
  elif [[ -n "$current" && -d "$ROOT_DIR/out" ]]; then
    "$MT_VERSION" archive "$current" --force
    "$MT_VERSION" tag "$current"
  else
    warn "No current data to archive"
  fi

  # ── Step 2: Set up new PAK ─────────────────────────────────────────────
  step "Step 2/6: Set up new PAK"

  register_pak "$version" "$pak_path"

  # Symlink (not copy) the PAK
  local pak_basename
  pak_basename=$(basename "$pak_path")

  # If the current active version uses "MotorTown-Windows.pak" as its pak_file
  # (the original unnamed PAK), rename it to <current>.pak before replacing
  if [[ -n "$current" ]]; then
    local current_pak
    current_pak=$(python3 -c "import json; print(json.load(open('$ROOT_DIR/game_versions.json')).get('versions',{}).get('$current',{}).get('pak_file',''))" 2>/dev/null || echo "")
    if [[ "$current_pak" == "MotorTown-Windows.pak" && -f "$ROOT_DIR/MotorTown-Windows.pak" && ! -L "$ROOT_DIR/MotorTown-Windows.pak" ]]; then
      local renamed="${current}.pak"
      log "Renaming old PAK: MotorTown-Windows.pak → $renamed"
      mv "$ROOT_DIR/MotorTown-Windows.pak" "$ROOT_DIR/$renamed"
      # Update manifest
      python3 -c "
import json
m = json.load(open('$ROOT_DIR/game_versions.json'))
m['versions']['$current']['pak_file'] = '$renamed'
json.dump(m, open('$ROOT_DIR/game_versions.json', 'w'), indent=2)
"
    fi
  fi

  rm -f "$ROOT_DIR/MotorTown-Windows.pak"
  ln -sf "$pak_basename" "$ROOT_DIR/MotorTown-Windows.pak"
  log "Linked MotorTown-Windows.pak → $pak_basename"

  # Clean old extracted data (will be regenerated)
  if [[ -d "$ROOT_DIR/out" ]]; then
    log "Removing old out/ (will be regenerated)..."
    rm -rf "$ROOT_DIR/out"
  fi

  # ── Step 3: Extract assets ─────────────────────────────────────────────
  step "Step 3/6: Extract assets from PAK (Rust)"

  cd "$ROOT_DIR"
  log "Running: cargo run --release --quiet -- --config assets.json"
  "$NIX" develop --command bash -c 'cargo run --release --quiet -- --config assets.json'

  # ── Step 4: Parse extracted assets ─────────────────────────────────────
  step "Step 4/6: Parse .uasset files (C#)"

  log "Running: dotnet run -- --batch"
  "$NIX" develop --command bash -c 'cd csharp/UAssetTool && dotnet run --configuration Release --verbosity quiet -- --batch'

  # ── Step 5: Aggregate to SQLite ─────────────────────────────────────────
  step "Step 5/6: Aggregate to SQLite (Python)"

  log "Running: python3 scripts/aggregate_to_sqlite.py"
  "$NIX" develop --command bash -c 'python3 scripts/aggregate_to_sqlite.py'

  # ── Step 6: Archive + Tag + Worktree ────────────────────────────────────
  step "Step 6/6: Archive, tag, and set up worktree"

  "$MT_VERSION" archive "$version" --force

  # Update manifest active version
  python3 -c "
import json
m = json.load(open('$ROOT_DIR/game_versions.json'))
m['active'] = '$version'
json.dump(m, open('$ROOT_DIR/game_versions.json', 'w'), indent=2)
"

  # Git tag
  "$MT_VERSION" tag "$version"

  # Worktree for previous version (if different)
  if [[ -n "$current" && "$current" != "$version" && "$current" != "none" ]]; then
    local worktree_dir="$ROOT_DIR/../mt-$current"
    if [[ -d "$worktree_dir" ]]; then
      log "Worktree for $current already exists at $worktree_dir"
    else
      "$MT_VERSION" worktree "$current"
    fi
  fi

  # ── Done ────────────────────────────────────────────────────────────────
  echo ""
  step "Done!"
  echo ""
  log "Version $version is now active."
  log ""
  log "Next steps — rebuild mods:"
  log "  nix develop --command bash -c 'python3 scripts/create_tirepack.py --config tire_entries.json --output zzz_ASEAN_PoliceTyres_<mod_version>_P.pak'"
  log "  nix develop --command bash -c 'python3 scripts/create_cargopack.py --config cargo_entries.json --recipes recipe_entries.json --output MoneyRun_${version}_P.pak'"
  log ""
  if [[ -n "$current" && "$current" != "$version" ]]; then
    log "Old version $current is available at: ../mt-$current"
    log "  cd ../mt-$current && python3 scripts/create_tirepack.py ..."
  fi
}

main "$@"
