#!/usr/bin/env python3
"""Bootstrap the MT pak build pipeline for a game version.

Resolves the client/server game paks from paks.json, verifies md5 + size,
repoints the MotorTown-Windows.pak symlink, runs the extract+parse pipeline
into out/<flavor>/, and writes out/<flavor>/provenance.json so the build
gates can verify flavor provenance.

Usage:
    python3 scripts/bootstrap.py <game_version> [client|server] [--no-extract]

Example:
    nix run .#bootstrap -- 0.7.19 client
"""

import hashlib
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKS_JSON = os.path.join(REPO_ROOT, "paks.json")
GAME_PAK_LINK = os.path.join(REPO_ROOT, "MotorTown-Windows.pak")


def fail(msg: str):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def md5_of(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    argv = [a for a in sys.argv[1:] if a != "--no-extract"]
    no_extract = "--no-extract" in sys.argv[1:]
    if not argv:
        fail("usage: bootstrap.py <game_version> [client|server] [--no-extract]")
    game_version = argv[0]
    flavor = argv[1] if len(argv) > 1 else "client"
    if flavor not in ("client", "server"):
        fail(f"flavor must be 'client' or 'server', got: {flavor}")

    try:
        with open(PAKS_JSON) as f:
            table = json.load(f)
    except FileNotFoundError:
        print(f"Error: paks.json not found: {PAKS_JSON}", file=sys.stderr)
        sys.exit(1)

    entry = table.get(game_version)
    if not entry:
        fail(f"game version {game_version} not in paks.json; "
             f"known: {', '.join(k for k in table if not k.startswith('_'))}")
    pak_entry = entry.get(flavor)
    if not pak_entry:
        fail(f"no {flavor} pak recorded for {game_version}")

    path = pak_entry["path"]
    if not os.path.isabs(path):
        path = os.path.join(REPO_ROOT, path)
    if not os.path.isfile(path):
        fail(f"{flavor} pak for {game_version} not found at {path} "
             f"(recorded in paks.json; update the path or fetch the pak)")

    size = os.path.getsize(path)
    if size != pak_entry["size"]:
        fail(f"{flavor} pak size mismatch: {size} vs recorded {pak_entry['size']}. "
             f"Refusing to bootstrap against an unverified pak.")
    print(f"Verifying md5 of {path} ({size:,} bytes)...")
    digest = md5_of(path)
    if digest != pak_entry["md5"]:
        fail(f"{flavor} pak md5 mismatch: {digest} vs recorded {pak_entry['md5']}. "
             f"Refusing to bootstrap against an unverified pak.")

    # Sanity: flavor-specific size shape. Client cooks are unversioned and
    # large; server cooks are tagged and much smaller. A swap between the two
    # is the wiki-pipeline trap that broke the 0.7.3 client pak.
    if flavor == "server" and size > 2_000_000_000:
        print("Warning: 'server' pak larger than 2 GB — client/server swap?")
    if flavor == "client" and size < 2_000_000_000:
        print("Warning: 'client' pak smaller than 2 GB — client/server swap?")
    other = entry.get("server" if flavor == "client" else "client", {})
    other_path = other.get("path", "")
    if other_path and not os.path.isabs(other_path):
        other_path = os.path.join(REPO_ROOT, other_path)
    if other_path and os.path.isfile(other_path):
        if os.path.realpath(path) == os.path.realpath(other_path):
            fail(f"client and server paks resolve to the same file: {path}")

    # Repoint the game pak symlink.
    if os.path.islink(GAME_PAK_LINK) or os.path.exists(GAME_PAK_LINK):
        os.remove(GAME_PAK_LINK)
    os.symlink(path, GAME_PAK_LINK)
    print(f"Linked MotorTown-Windows.pak -> {path}")

    out_dir = os.path.join(REPO_ROOT, "out", flavor)
    prov_path = os.path.join(out_dir, "provenance.json")
    prov = {
        "flavor": flavor,
        "game_version": game_version,
        "source_pak": path,
        "source_pak_md5": digest,
        "source_pak_size": size,
    }

    if not no_extract:
        # Full extract + parse into the flavor tree. OUT_DIR is honored by the
        # Rust extractor and the C# batch parser.
        env = dict(os.environ, OUT_DIR=os.path.relpath(out_dir, REPO_ROOT))
        print(f"\nExtracting {flavor} templates into {out_dir} ...")
        r = subprocess.run(
            ["cargo", "run", "--release", "--quiet", "--", "--config", "assets.json"],
            cwd=REPO_ROOT, env=env)
        if r.returncode != 0:
            fail(f"asset extraction failed (exit {r.returncode})")
        r = subprocess.run(
            ["dotnet", "run", "--project", "csharp/UAssetTool",
             "--configuration", "Release", "--verbosity", "quiet", "--", "--batch"],
            cwd=REPO_ROOT, env=env)
        if r.returncode != 0:
            fail(f"asset parsing failed (exit {r.returncode})")

    os.makedirs(out_dir, exist_ok=True)
    with open(prov_path, "w") as f:
        json.dump(prov, f, indent=2)
    print(f"Wrote {prov_path}: flavor={flavor} game={game_version} md5={digest}")

    print("\nBootstrap OK. Build with flavor gates:")
    print(f"  python3 scripts/mods.py build schedule-i --flavor {flavor}")


if __name__ == "__main__":
    main()
