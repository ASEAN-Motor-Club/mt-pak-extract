#!/usr/bin/env python3
"""
mt-decal-pack — Create MotorTown decal mod PAKs from images.

Single command to go from images to a working mod PAK:

    mt-decal-pack --input logos/ --output MyPack_P.pak
    mt-decal-pack --input logos/ --category Tuners --cost 500 --output TunersPack_P.pak

Pipeline:
  1. Inject each image into a base game decal texture template (auto-resize to 512x512)
  2. Patch uasset internal metadata (asset path, name, hashes)
  3. Generate Decals DataTable entries for each texture
  4. Package everything into a mod PAK with correct mount point

Requirements:
  - Base game Decals.uasset + Decals.uexp in current directory (from extraction)
  - A template decal texture .uasset in out/ (e.g. out/001-circle.uasset)
  - Mappings.usmap in current directory
"""
import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile


def find_template(template_dir: str = "out") -> str:
    """Find a suitable template decal texture."""
    # Prefer GeomShape textures (short names, standard 512x512 DXT5)
    preferred = [
        "001-circle.uasset", "002-triangle.uasset", "003-square.uasset",
        "004-diamond.uasset", "005-star.uasset",
    ]
    for name in preferred:
        path = os.path.join(template_dir, name)
        if os.path.isfile(path):
            return path
    # Fall back to any .uasset with a matching .uexp
    if os.path.isdir(template_dir):
        for f in sorted(os.listdir(template_dir)):
            if f.endswith(".uasset"):
                uexp = os.path.join(template_dir, f.replace(".uasset", ".uexp"))
                if os.path.isfile(uexp):
                    return os.path.join(template_dir, f)
    return None


def find_template_strings(template_path: str):
    """Extract the old path and name strings from a template uasset."""
    import re
    data = open(template_path, "rb").read()
    old_path = None
    old_name = None
    for m in re.finditer(b'/Game/Materials/Decal/DecalTextures/[^\\x00]+', data):
        old_path = m.group(0)
        break
    if old_path:
        # Name is the last component
        old_name = old_path.split(b"/")[-1]
    return old_path, old_name


def inject_image(template_uasset: str, image_path: str, output_dir: str,
                 version: str = "5.5", tools_src: str = None):
    """Inject an image into a template uasset using UE4-DDS-Tools."""
    if tools_src is None:
        tools_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "tools", "ue4-dds-tools", "src")

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = tools_src + (os.pathsep + existing if existing else "")

    cmd = [
        sys.executable,
        os.path.join(tools_src, "main.py"),
        template_uasset,
        image_path,
        "--mode", "inject",
        "--version", version,
        "--save_folder", output_dir,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Injection failed: {result.stderr.strip()}")


def patch_uasset(injected_path: str, template_path: str, new_path: str, new_name: str):
    """Patch injected uasset metadata to match new asset path/name."""
    template_data = open(template_path, "rb").read()
    data = bytearray(open(injected_path, "rb").read())

    if len(template_data) != len(data):
        raise ValueError(f"Size mismatch: template={len(template_data)}B injected={len(data)}B")

    old_path, old_name = find_template_strings(template_path)
    if old_path is None or old_name is None:
        raise ValueError("Could not find template strings")

    new_path_b = new_path.encode()
    new_name_b = new_name.encode()

    # Replace strings in-place
    for old, new_b in [(old_path, new_path_b), (old_name, new_name_b)]:
        idx = 0
        while True:
            pos = data.find(old, idx)
            if pos == -1:
                break
            if data[pos + len(old)] == 0:
                for i in range(len(old)):
                    data[pos + i] = new_b[i] if i < len(new_b) else 0
            idx = pos + 1

    # Fix FString length prefixes
    for old, new_b in [(old_path, new_path_b), (old_name, new_name_b)]:
        old_len = struct.pack('<i', len(old) + 1)
        new_len = struct.pack('<i', len(new_b) + 1)
        idx = 0
        while True:
            pos = data.find(old_len, idx)
            if pos == -1:
                break
            if data[pos + 4:pos + 4 + len(old)] == old:
                data[pos:pos + 4] = new_len
            idx = pos + 1

    # Copy hashes/metadata from template (preserve string sites)
    string_sites = set()
    for s in (new_path_b, new_name_b):
        idx = 0
        while True:
            pos = data.find(s, idx)
            if pos == -1:
                break
            for i in range(pos, pos + len(s)):
                string_sites.add(i)
            idx = pos + 1
    for s, old in [(new_path_b, old_path), (new_name_b, old_name)]:
        idx = 0
        while True:
            pos = data.find(s, idx)
            if pos == -1:
                break
            for i in range(pos + len(s), pos + len(old)):
                string_sites.add(i)
            idx = pos + 1

    for i in range(len(data)):
        if i not in string_sites:
            data[i] = template_data[i]

    open(injected_path, "wb").write(data)


def add_decal_entries(config_path: str, template_deals_path: str, output_dir: str,
                      repo_root: str = None):
    """Run the C# --add-decals tool to create modified Decals.uasset."""
    if repo_root is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    csproj_dir = os.path.join(repo_root, "csharp", "CargoExtractor")
    mappings = os.path.join(repo_root, "Mappings.usmap")

    cmd = [
        "dotnet", "run", "--configuration", "Release", "--verbosity", "quiet", "--",
        "--add-decals", config_path, template_deals_path, output_dir,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=csproj_dir)
    if result.returncode != 0:
        raise RuntimeError(f"add-decals failed: {result.stderr.strip()}")


def build_pak(input_dir: str, output_pak: str, repo_root: str = None):
    """Build a mod PAK using mod_pack."""
    if repo_root is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    mod_pack = os.path.join(repo_root, "target", "release", "mod_pack")
    if not os.path.isfile(mod_pack):
        # Try building it
        subprocess.run(
            ["cargo", "build", "--release", "--bin", "mod_pack"],
            cwd=repo_root, capture_output=True,
        )

    result = subprocess.run(
        [mod_pack, input_dir, output_pak],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mod_pack failed: {result.stderr.strip()}")


def main():
    parser = argparse.ArgumentParser(
        prog="mt-decal-pack",
        description="Create MotorTown decal mod PAKs from images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mt-decal-pack --input logos/ --output MyPack_P.pak
  mt-decal-pack --input logos/ --category Tuners --cost 500 --output TunersPack_P.pak
  mt-decal-pack --input logos/ --template out/001-circle.uasset --output Pack_P.pak

Input images (PNG/TGA/BMP/JPG) should be in the --input directory.
Each image becomes a decal named after its filename (without extension).
        """,
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Directory containing images (PNG/TGA/BMP/JPG)")
    parser.add_argument("--output", "-o", required=True,
                        help="Output .pak file path (e.g. MyPack_P.pak)")
    parser.add_argument("--template", "-t",
                        help="Template decal texture .uasset (auto-detected from out/)")
    parser.add_argument("--decals", "-d",
                        help="Template Decals.uasset (auto-detected from out/)")
    parser.add_argument("--category", "-c", default="Custom",
                        help="Category folder name (default: Custom)")
    parser.add_argument("--cost", type=int, default=100,
                        help="Decal cost in-game (default: 100)")
    parser.add_argument("--version", "-v", default="5.5",
                        help="UE version (default: 5.5)")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Validate inputs
    if not os.path.isdir(args.input):
        print(f"Error: Input directory not found: {args.input}")
        sys.exit(1)

    # Auto-detect template
    template = args.template
    if template is None:
        template = find_template(os.path.join(repo_root, "out"))
    if template is None or not os.path.isfile(template):
        print("Error: No template decal texture found.")
        print("Run the extractor first: nix run .#extract")
        sys.exit(1)

    # Auto-detect Decals.uasset
    decals = args.decals
    if decals is None:
        decals = os.path.join(repo_root, "out", "Decals.uasset")
    if not os.path.isfile(decals):
        decals = os.path.join(repo_root, "Decals.uasset")
    if not os.path.isfile(decals):
        print("Error: No Decals.uasset found.")
        print("Run the extractor first: nix run .#extract")
        sys.exit(1)

    # Find images
    extensions = (".png", ".tga", ".jpg", ".jpeg", ".bmp", ".dds")
    images = sorted([
        f for f in os.listdir(args.input)
        if any(f.lower().endswith(ext) for ext in extensions)
    ])
    if not images:
        print(f"Error: No images found in {args.input}")
        sys.exit(1)

    template_name = os.path.splitext(os.path.basename(template))[0]

    print(f"=== mt-decal-pack ===")
    print(f"  Template:  {os.path.basename(template)}")
    print(f"  Decals:    {os.path.basename(decals)}")
    print(f"  Category:  {args.category}")
    print(f"  Cost:      {args.cost}")
    print(f"  Images:    {len(images)}")
    print(f"  Output:    {args.output}")
    print()

    with tempfile.TemporaryDirectory(prefix="mt_decal_") as work_dir:
        textures_dir = os.path.join(work_dir, "textures")
        os.makedirs(textures_dir)

        # Step 1 & 2: Inject images + patch metadata
        print("Step 1: Injecting images...")
        decal_entries = []
        ok = 0
        fail = 0

        for img_file in images:
            name = os.path.splitext(img_file)[0]
            img_path = os.path.join(args.input, img_file)
            row_name = f"{args.category}_{name}"
            asset_path = f"/Game/Materials/Decal/DecalTextures/{args.category}/{name}"

            print(f"  {name} ... ", end="", flush=True)
            try:
                inject_image(template, img_path, textures_dir, version=args.version)

                # Rename output
                src_uasset = os.path.join(textures_dir, f"{template_name}.uasset")
                src_uexp = os.path.join(textures_dir, f"{template_name}.uexp")
                dst_uasset = os.path.join(textures_dir, f"{name}.uasset")
                dst_uexp = os.path.join(textures_dir, f"{name}.uexp")
                if os.path.exists(src_uasset):
                    os.rename(src_uasset, dst_uasset)
                if os.path.exists(src_uexp):
                    os.rename(src_uexp, dst_uexp)

                # Patch metadata
                patch_uasset(dst_uasset, template, asset_path, name)

                print("OK")
                decal_entries.append({
                    "row_name": row_name,
                    "folder": args.category,
                    "file": name,
                    "cost": args.cost,
                    "flags": 0,
                })
                ok += 1
            except Exception as e:
                print(f"FAILED: {e}")
                fail += 1

        if ok == 0:
            print("\nError: No images were injected successfully.")
            sys.exit(1)

        print(f"\n  {ok} injected, {fail} failed")

        # Step 3: Generate Decals DataTable
        print("\nStep 2: Generating Decals DataTable...")
        config_path = os.path.join(work_dir, "decal_entries.json")
        with open(config_path, "w") as f:
            json.dump({"entries": decal_entries}, f, indent=2)

        decals_out = os.path.join(work_dir, "decals")
        os.makedirs(decals_out)

        add_decal_entries(config_path, decals, decals_out, repo_root=repo_root)

        # UAssetAPI writes without .uasset extension — fix if needed
        raw_path = os.path.join(decals_out, "Decals")
        uasset_path = os.path.join(decals_out, "Decals.uasset")
        if os.path.isfile(raw_path) and not os.path.isfile(uasset_path):
            os.rename(raw_path, uasset_path)

        # Step 4: Build mod PAK directory structure
        print("\nStep 3: Building mod PAK...")
        pak_dir = os.path.join(work_dir, "pak_root")
        pak_decals = os.path.join(pak_dir, "MotorTown", "Content", "DataAsset")
        pak_textures = os.path.join(pak_dir, "MotorTown", "Content", "Materials",
                                     "Decal", "DecalTextures", args.category)
        os.makedirs(pak_decals)
        os.makedirs(pak_textures)

        # Copy Decals DataTable (both files from same Write() call)
        import shutil
        shutil.copy2(os.path.join(decals_out, "Decals.uasset"), pak_decals)
        shutil.copy2(os.path.join(decals_out, "Decals.uexp"), pak_decals)

        # Copy texture assets
        for img_file in images:
            name = os.path.splitext(img_file)[0]
            for ext in (".uasset", ".uexp"):
                src = os.path.join(textures_dir, f"{name}{ext}")
                if os.path.isfile(src):
                    shutil.copy2(src, pak_textures)

        # Build PAK
        build_pak(pak_dir, args.output, repo_root=repo_root)

        size_kb = os.path.getsize(args.output) / 1024
        print(f"\n=== Done: {args.output} ({size_kb:.0f} KB, {ok} decals) ===")


if __name__ == "__main__":
    main()
