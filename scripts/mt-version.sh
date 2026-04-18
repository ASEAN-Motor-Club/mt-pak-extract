#!/usr/bin/env bash
set -euo pipefail

# mt-version — Motor Town game version management
#
# Manages extracted game data across multiple game versions.
# Stores versioned data in versions/<version>/ and symlinks it into the working tree.
#
# Usage:
#   mt-version archive <version>   — archive current out/ + db to versions/<version>/
#   mt-version restore <version>   — restore versions/<version>/ data to working tree
#   mt-version switch <version>    — switch active version (restore + update manifest)
#   mt-version status              — show current active version and data state
#   mt-version list                — list all archived versions
#   mt-version tag <version>       — git add + commit + tag current state as <version>
#   mt-version worktree <version>  — create a git worktree for parallel mod building
#   mt-version diff <v1> <v2>      — compare two versions' parsed JSON outputs

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSIONS_DIR="$ROOT_DIR/versions"
MANIFEST="$ROOT_DIR/game_versions.json"

# Directories/files that are version-specific
VERSIONED_PATHS=(
  "out"
  "motortown.db"
  "game_data.db"
  "motortown_data.sql"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[mt-version]${NC} $*"; }
warn() { echo -e "${YELLOW}[mt-version]${NC} $*"; }
err()  { echo -e "${RED}[mt-version]${NC} $*" >&2; }

usage() {
  cat <<'EOF'
Motor Town Game Version Manager

Usage: mt-version <command> [args]

Commands:
  archive <version>   Archive current extracted data to versions/<version>/
  restore <version>   Restore version data to working tree
  switch <version>    Switch active version (archive current, restore target)
  status              Show current version and data state
  list                List archived versions with details
  tag <version>       Git commit + tag current state
  worktree <version>  Create git worktree for parallel mod building
  diff <v1> <v2>      Compare parsed JSON between two versions

Examples:
  mt-version archive v0.7.18
  mt-version switch v0.7.17
  mt-version status
  mt-version tag v0.7.18
  mt-version worktree v0.7.17
EOF
}

ensure_manifest() {
  if [[ ! -f "$MANIFEST" ]]; then
    cat > "$MANIFEST" <<'MANIFEST_JSON'
{
  "active": null,
  "versions": {}
}
MANIFEST_JSON
  fi
}

get_active_version() {
  ensure_manifest
  python3 -c "import json; print(json.load(open('$MANIFEST')).get('active', ''))" 2>/dev/null || echo ""
}

set_active_version() {
  local version="$1"
  python3 -c "
import json
m = json.load(open('$MANIFEST'))
m['active'] = '$version'
json.dump(m, open('$MANIFEST', 'w'), indent=2)
"
}

get_version_field() {
  local version="$1" field="$2"
  python3 -c "
import json
m = json.load(open('$MANIFEST'))
v = m.get('versions', {}).get('$version', {})
print(v.get('$field', ''))
" 2>/dev/null || echo ""
}

# ── archive ───────────────────────────────────────────────────────────────
cmd_archive() {
  local version="${1:?Usage: mt-version archive <version>}"
  local force=false
  [[ "${2:-}" == "-f" || "${2:-}" == "--force" ]] && force=true
  local dest="$VERSIONS_DIR/$version"

  if [[ -d "$dest" && "$force" == false ]]; then
    warn "Version $version already archived at $dest"
    read -rp "Overwrite? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { log "Aborted."; return 0; }
  fi

  mkdir -p "$dest"

  log "Archiving current data to versions/$version/..."

  # Archive out/ directory
  if [[ -d "$ROOT_DIR/out" ]]; then
    local out_count
    out_count=$(ls "$ROOT_DIR/out"/*.uasset 2>/dev/null | wc -l | tr -d ' ')
    log "  Copying out/ ($out_count assets)..."
    rsync -a --delete "$ROOT_DIR/out/" "$dest/out/"
  else
    warn "  out/ not found, skipping"
  fi

  # Archive databases and SQL dumps
  for f in motortown.db game_data.db motortown_data.sql; do
    if [[ -f "$ROOT_DIR/$f" ]]; then
      cp "$ROOT_DIR/$f" "$dest/$f"
      log "  Copied $f"
    fi
  done

  # Archive Mappings.usmap (follow symlink to get real file)
  if [[ -f "$ROOT_DIR/Mappings.usmap" ]]; then
    cp -L "$ROOT_DIR/Mappings.usmap" "$dest/Mappings.usmap"
    log "  Copied Mappings.usmap"
  fi

  # Archive *_parsed.json files from root
  local parsed_count=0
  for f in "$ROOT_DIR"/*_parsed.json; do
    [[ -f "$f" ]] || continue
    cp "$f" "$dest/"
    parsed_count=$((parsed_count + 1))
  done
  log "  Copied $parsed_count parsed JSON files"

  # Record PAK hash (background, may be slow)
  local pak_file
  pak_file=$(python3 -c "import json; print(json.load(open('$MANIFEST')).get('versions',{}).get('$version',{}).get('pak_file',''))" 2>/dev/null || echo "")
  if [[ -n "$pak_file" && -f "$ROOT_DIR/$pak_file" ]]; then
    log "  Computing PAK SHA256 (background)..."
    (sha256sum "$ROOT_DIR/$pak_file" 2>/dev/null || shasum -a 256 "$ROOT_DIR/$pak_file") | awk '{print $1}' > "$dest/pak.sha256" &
  fi

  # Update manifest
  python3 -c "
import json, os, datetime
m = json.load(open('$MANIFEST'))
if '$version' not in m.get('versions', {}):
    m.setdefault('versions', {})['$version'] = {}
m['versions']['$version']['archived_at'] = datetime.datetime.now().isoformat()
m['versions']['$version']['has_data'] = True
json.dump(m, open('$MANIFEST', 'w'), indent=2)
"

  log "Archived to $dest"
}

# ── restore ───────────────────────────────────────────────────────────────
cmd_restore() {
  local version="${1:?Usage: mt-version restore <version>}"
  local src="$VERSIONS_DIR/$version"

  if [[ ! -d "$src" ]]; then
    err "No archived data for version $version at $src"
    err "Available versions: $(ls "$VERSIONS_DIR" 2>/dev/null | tr '\n' ' ')"
    return 1
  fi

  log "Restoring version $version to working tree..."

  # Symlink out/ (avoid copying hundreds of MB of assets)
  if [[ -d "$src/out" ]]; then
    rm -rf "$ROOT_DIR/out" 2>/dev/null || rm -f "$ROOT_DIR/out"
    ln -sf "$src/out" "$ROOT_DIR/out"
    log "  Linked out/ → $src/out"
  fi

  # Symlink databases
  for f in motortown.db game_data.db motortown_data.sql; do
    if [[ -f "$src/$f" ]]; then
      rm -f "$ROOT_DIR/$f"
      ln -sf "$src/$f" "$ROOT_DIR/$f"
      log "  Linked $f → $src/$f"
    fi
  done

  # Symlink Mappings.usmap from archive
  if [[ -f "$src/Mappings.usmap" ]]; then
    rm -f "$ROOT_DIR/Mappings.usmap"
    ln -sf "$src/Mappings.usmap" "$ROOT_DIR/Mappings.usmap"
    log "  Linked Mappings.usmap → $src/Mappings.usmap"
  fi

  # Symlink parsed JSON files
  for f in "$src"/*_parsed.json; do
    [[ -f "$f" ]] || continue
    local basename
    basename=$(basename "$f")
    rm -f "$ROOT_DIR/$basename"
    ln -sf "$f" "$ROOT_DIR/$basename"
  done
  log "  Linked parsed JSON files"

  log "Restored version $version"
}

# ── switch ────────────────────────────────────────────────────────────────
cmd_switch() {
  local version="${1:?Usage: mt-version switch <version>}"
  local current
  current=$(get_active_version)

  if [[ "$current" == "$version" ]]; then
    log "Already on version $version"
    return 0
  fi

  # Archive current state if there's data and a current version
  if [[ -n "$current" && -d "$ROOT_DIR/out" && ! -d "$VERSIONS_DIR/$current/out" ]]; then
    warn "Current version $current is not archived. Archiving first..."
    cmd_archive "$current"
  fi

  # Restore target version
  cmd_restore "$version"

  # Update manifest
  set_active_version "$version"

  # Symlink the correct PAK file (avoid copying 2.6GB+ files)
  local pak_file
  pak_file=$(get_version_field "$version" "pak_file")
  if [[ -n "$pak_file" && -f "$ROOT_DIR/$pak_file" ]]; then
    rm -f "$ROOT_DIR/MotorTown-Windows.pak"
    ln -sf "$pak_file" "$ROOT_DIR/MotorTown-Windows.pak"
    log "Linked MotorTown-Windows.pak → $pak_file"
  fi

  log "Switched to version $version"
}

# ── status ────────────────────────────────────────────────────────────────
cmd_status() {
  local active
  active=$(get_active_version)

  echo -e "${CYAN}Motor Town Version Status${NC}"
  echo "─────────────────────────────"
  echo -e "  Active version: ${GREEN}${active:-none}${NC}"

  if [[ -d "$ROOT_DIR/out" ]]; then
    local out_count
    out_count=$(ls "$ROOT_DIR/out"/*.uasset 2>/dev/null | wc -l | tr -d ' ')
    echo -e "  out/ assets:    ${out_count} .uasset files"
  else
    echo -e "  out/ assets:    ${YELLOW}not found${NC}"
  fi

  if [[ -f "$ROOT_DIR/motortown.db" ]]; then
    local db_size
    db_size=$(ls -lh "$ROOT_DIR/motortown.db" | awk '{print $5}')
    echo -e "  motortown.db:   ${db_size}"
  else
    echo -e "  motortown.db:   ${YELLOW}not found${NC}"
  fi

  echo ""
  echo -e "${CYAN}Archived Versions:${NC}"
  if [[ -d "$VERSIONS_DIR" ]]; then
    for dir in "$VERSIONS_DIR"/*/; do
      [[ -d "$dir" ]] || continue
      local vname
      vname=$(basename "$dir")
      local has_out="no"
      local has_db="no"
      [[ -d "$dir/out" ]] && has_out="yes"
      [[ -f "$dir/motortown.db" ]] && has_db="yes"
      local marker=""
      [[ "$vname" == "$active" ]] && marker=" ${GREEN}← active${NC}"
      echo -e "  ${vname}: out=${has_out} db=${has_db}${marker}"
    done
  else
    echo "  (none)"
  fi

  echo ""
  echo -e "${CYAN}Git Tags:${NC}"
  git -C "$ROOT_DIR" tag -l 2>/dev/null | sed 's/^/  /' || echo "  (none)"

  echo ""
  echo -e "${CYAN}Git Worktrees:${NC}"
  git -C "$ROOT_DIR" worktree list 2>/dev/null | sed 's/^/  /'
}

# ── list ──────────────────────────────────────────────────────────────────
cmd_list() {
  ensure_manifest
  echo -e "${CYAN}Game Versions${NC}"
  echo "─────────────────────────────"

  python3 -c "
import json
m = json.load(open('$MANIFEST'))
active = m.get('active', '')
for name, info in m.get('versions', {}).items():
    marker = ' ← active' if name == active else ''
    tag = info.get('git_tag', '—')
    pak = info.get('pak_file', '—')
    size = info.get('pak_size', '—')
    date = info.get('pak_date', '—')
    print(f'  {name}{marker}')
    print(f'    PAK: {pak} ({size}, {date})')
    print(f'    Git tag: {tag}')
    print()
"
}

# ── tag ───────────────────────────────────────────────────────────────────
cmd_tag() {
  local version="${1:?Usage: mt-version tag <version>}"

  if git -C "$ROOT_DIR" tag -l "$version" | grep -q "$version"; then
    warn "Tag $version already exists"
    return 1
  fi

  log "Committing and tagging as $version..."

  # Stage tracked files only (not out/, not .pak, not .db)
  git -C "$ROOT_DIR" add -A
  git -C "$ROOT_DIR" commit --allow-empty -m "chore: snapshot for game version $version"
  git -C "$ROOT_DIR" tag "$version"

  # Update manifest
  python3 -c "
import json
m = json.load(open('$MANIFEST'))
if '$version' in m.get('versions', {}):
    m['versions']['$version']['git_tag'] = '$version'
json.dump(m, open('$MANIFEST', 'w'), indent=2)
"

  log "Tagged as $version"
}

# ── worktree ──────────────────────────────────────────────────────────────
cmd_worktree() {
  local version="${1:?Usage: mt-version worktree <version>}"
  local worktree_dir="$ROOT_DIR/../mt-$version"

  if [[ -d "$worktree_dir" ]]; then
    warn "Worktree already exists at $worktree_dir"
    return 0
  fi

  # Ensure the tag exists
  if ! git -C "$ROOT_DIR" tag -l "$version" | grep -q "$version"; then
    err "Tag $version does not exist. Run 'mt-version tag $version' first."
    return 1
  fi

  log "Creating worktree at $worktree_dir for version $version..."
  git -C "$ROOT_DIR" worktree add "$worktree_dir" "$version"

  # Symlink extracted data from versions/ archive
  local src="$VERSIONS_DIR/$version"
  if [[ -d "$src/out" ]]; then
    ln -sf "$src/out" "$worktree_dir/out"
    log "  Linked out/ → $src/out"
  fi
  for f in motortown.db game_data.db; do
    if [[ -f "$src/$f" ]]; then
      ln -sf "$src/$f" "$worktree_dir/$f"
      log "  Linked $f → $src/$f"
    fi
  done

  # Symlink MotorTown-Windows.pak if the versioned PAK exists
  local pak_file
  pak_file=$(get_version_field "$version" "pak_file")
  if [[ -n "$pak_file" && -f "$ROOT_DIR/$pak_file" ]]; then
    ln -sf "$ROOT_DIR/$pak_file" "$worktree_dir/MotorTown-Windows.pak"
    log "  Linked MotorTown-Windows.pak → $pak_file"
  fi

  # Symlink Mappings.usmap from version archive
  if [[ -f "$src/Mappings.usmap" ]]; then
    ln -sf "$src/Mappings.usmap" "$worktree_dir/Mappings.usmap"
    log "  Linked Mappings.usmap → $src/Mappings.usmap"
  else
    warn "  Mappings.usmap not found in archive — worktree will need it manually"
  fi

  log "Worktree ready. Build mods with:"
  log "  cd $worktree_dir && python3 scripts/mods.py build <mod-name>"
}

# ── diff ──────────────────────────────────────────────────────────────────
cmd_diff() {
  local v1="${1:?Usage: mt-version diff <v1> <v2>}"
  local v2="${2:?Usage: mt-version diff <v1> <v2>}"

  local dir1="$VERSIONS_DIR/$v1"
  local dir2="$VERSIONS_DIR/$v2"

  if [[ ! -d "$dir1" ]]; then
    err "Version $v1 not archived"
    return 1
  fi
  if [[ ! -d "$dir2" ]]; then
    err "Version $v2 not archived"
    return 1
  fi

  echo -e "${CYAN}Comparing $v1 vs $v2${NC}"
  echo "─────────────────────────────"

  # Compare parsed JSON files
  echo -e "\n${YELLOW}Parsed JSON differences:${NC}"
  local common_files
  common_files=$(comm -12 <(ls "$dir1"/*_parsed.json 2>/dev/null | xargs -I{} basename {} | sort) \
                           <(ls "$dir2"/*_parsed.json 2>/dev/null | xargs -I{} basename {} | sort))

  for f in $common_files; do
    if ! diff -q "$dir1/$f" "$dir2/$f" >/dev/null 2>&1; then
      local changes
      changes=$(diff "$dir1/$f" "$dir2/$f" 2>/dev/null | grep "^[<>]" | wc -l | tr -d ' ')
      echo "  $f: ${changes} lines differ"
    fi
  done

  # Files only in one version
  local only_v1 only_v2
  only_v1=$(comm -23 <(ls "$dir1"/*_parsed.json 2>/dev/null | xargs -I{} basename {} | sort) \
                      <(ls "$dir2"/*_parsed.json 2>/dev/null | xargs -I{} basename {} | sort))
  only_v2=$(comm -13 <(ls "$dir1"/*_parsed.json 2>/dev/null | xargs -I{} basename {} | sort) \
                      <(ls "$dir2"/*_parsed.json 2>/dev/null | xargs -I{} basename {} | sort))
  [[ -n "$only_v1" ]] && echo -e "\n  Only in $v1: $only_v1"
  [[ -n "$only_v2" ]] && echo -e "\n  Only in $v2: $only_v2"

  # Compare SQLite databases
  echo -e "\n${YELLOW}Database table differences:${NC}"
  if [[ -f "$dir1/motortown.db" && -f "$dir2/motortown.db" ]]; then
    local tables1 tables2
    tables1=$(sqlite3 "$dir1/motortown.db" ".tables" 2>/dev/null | tr ' ' '\n' | sort)
    tables2=$(sqlite3 "$dir2/motortown.db" ".tables" 2>/dev/null | tr ' ' '\n' | sort)
    for t in $(comm -12 <(echo "$tables1") <(echo "$tables2")); do
      local count1 count2
      count1=$(sqlite3 "$dir1/motortown.db" "SELECT COUNT(*) FROM \"$t\"" 2>/dev/null || echo "?")
      count2=$(sqlite3 "$dir2/motortown.db" "SELECT COUNT(*) FROM \"$t\"" 2>/dev/null || echo "?")
      if [[ "$count1" != "$count2" ]]; then
        echo "  $t: $count1 → $count2 rows"
      fi
    done
  else
    echo "  (database not available for both versions)"
  fi
}

# ── Main dispatch ─────────────────────────────────────────────────────────
case "${1:-}" in
  archive)  shift; cmd_archive "$@" ;;
  restore)  shift; cmd_restore "$@" ;;
  switch)   shift; cmd_switch "$@" ;;
  status)   cmd_status ;;
  list)     cmd_list ;;
  tag)      shift; cmd_tag "$@" ;;
  worktree) shift; cmd_worktree "$@" ;;
  diff)     shift; cmd_diff "$@" ;;
  -h|--help|help|"") usage ;;
  *) err "Unknown command: $1"; usage; exit 1 ;;
esac
