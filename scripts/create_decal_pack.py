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

from modbase import ModBuilder, load_mod_config, compute_output_path, resolve_game_version


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
    for m in re.finditer(b'/Game/Materials/Decal/DecalTextures/[^\x00]+', data):
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


class DecalModBuilder(ModBuilder):
    """Builds decal mod PAKs from image files."""

    def __init__(self, config_path, output_path, input_dir, category="Custom",
                 cost=100, template=None, decals_template=None,
                 ue_version="5.5"):
        # Decals use a synthetic config — create it from the image list
        self.input_dir = os.path.abspath(input_dir)
        self.category = category
        self.cost = cost
        self.ue_version = ue_version
        self.decal_entries = []
        self.textures_dir = None

        repo_root = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Find images
        extensions = (".png", ".tga", ".jpg", ".jpeg", ".bmp", ".dds")
        self.images = sorted([
            f for f in os.listdir(self.input_dir)
            if any(f.lower().endswith(ext) for ext in extensions)
        ])
        if not self.images:
            print(f"Error: No images found in {self.input_dir}")
            sys.exit(1)

        # Auto-detect texture template
        self.texture_template = template
        if self.texture_template is None:
            self.texture_template = find_template(os.path.join(repo_root, "out"))
        if self.texture_template is None or not os.path.isfile(self.texture_template):
            print("Error: No template decal texture found.")
            print("Run the extractor first: nix run .#extract")
            sys.exit(1)

        # Auto-detect Decals.uasset
        self.decals_template = decals_template
        if self.decals_template is None:
            self.decals_template = os.path.join(repo_root, "out", "Decals.uasset")
        if not os.path.isfile(self.decals_template):
            self.decals_template = os.path.join(repo_root, "Decals.uasset")
        if not os.path.isfile(self.decals_template):
            print("Error: No Decals.uasset found.")
            print("Run the extractor first: nix run .#extract")
            sys.exit(1)

        self.template_name = os.path.splitext(os.path.basename(self.texture_template))[0]

        # Create a minimal config for the base class
        tmp_config = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, prefix='decal_cfg_')
        json.dump({"images": [os.path.splitext(f)[0] for f in self.images]}, tmp_config)
        tmp_config.close()

        super().__init__("decal mod", tmp_config.name, output_path)
        os.unlink(tmp_config.name)

        self.log(f"=== mt-decal-pack ===")
        self.log(f"  Template:  {os.path.basename(self.texture_template)}")
        self.log(f"  Decals:    {os.path.basename(self.decals_template)}")
        self.log(f"  Category:  {self.category}")
        self.log(f"  Cost:      {self.cost}")
        self.log(f"  Images:    {len(self.images)}")
        self.log(f"  Output:    {self.output_path}")

    def transform_assets(self):
        """Inject images into template uassets and patch metadata."""
        self.log_step(1, "Injecting images")
        self.textures_dir = os.path.join(self.build_dir, "textures")
        os.makedirs(self.textures_dir)

        ok = 0
        fail = 0

        for img_file in self.images:
            name = os.path.splitext(img_file)[0]
            img_path = os.path.join(self.input_dir, img_file)
            row_name = f"{self.category}_{name}"
            asset_path = f"/Game/Materials/Decal/DecalTextures/{self.category}/{name}"

            print(f"  {name} ... ", end="", flush=True)
            try:
                inject_image(self.texture_template, img_path, self.textures_dir,
                             version=self.ue_version)

                # Rename output
                src_uasset = os.path.join(self.textures_dir, f"{self.template_name}.uasset")
                src_uexp = os.path.join(self.textures_dir, f"{self.template_name}.uexp")
                dst_uasset = os.path.join(self.textures_dir, f"{name}.uasset")
                dst_uexp = os.path.join(self.textures_dir, f"{name}.uexp")
                if os.path.exists(src_uasset):
                    os.rename(src_uasset, dst_uasset)
                if os.path.exists(src_uexp):
                    os.rename(src_uexp, dst_uexp)

                # Patch metadata
                patch_uasset(dst_uasset, self.texture_template, asset_path, name)

                print("OK")
                self.decal_entries.append({
                    "row_name": row_name,
                    "folder": self.category,
                    "file": name,
                    "cost": self.cost,
                    "flags": 0,
                })
                ok += 1
            except Exception as e:
                print(f"FAILED: {e}")
                fail += 1

        if ok == 0:
            self.fail("No images were injected successfully.")

        self.log(f"\n  {ok} injected, {fail} failed")

    def register_in_tables(self):
        """Generate Decals DataTable entries using construct_rows mode."""
        self.log_step(2, "Generating Decals DataTable")

        self.decals_output_dir = os.path.join(self.build_dir, "decals")
        os.makedirs(self.decals_output_dir)

        # Build construct_rows config from decal entries
        construct_rows = []
        for entry in self.decal_entries:
            row_name = entry["row_name"]
            folder = entry["folder"]
            file_name = entry["file"]
            cost = entry["cost"]
            flags = entry["flags"]

            package_path = f"/Game/Materials/Decal/DecalTextures/{folder}/{file_name}"
            construct_rows.append({
                "row_name": row_name,
                "struct_type": "MTDecalRow",
                "copy_ancestry": True,
                "properties": [
                    {"name": "Texture", "type": "SoftObject",
                     "package": package_path, "asset": file_name},
                    {"name": "BrushMaterial", "type": "ObjectRef",
                     "match_import": "M_DecalBounds_Test"},
                    {"name": "Flags", "type": "Int", "value": flags},
                    {"name": "Cost", "type": "Int", "value": cost},
                ],
            })

        config = {"construct_rows": construct_rows}
        self.run_generic("--add-rows", config,
                         self.decals_template, self.decals_output_dir,
                         "add-decal-rows")

        # UAssetAPI writes without .uasset extension — fix if needed
        raw_path = os.path.join(self.decals_output_dir, "Decals")
        uasset_path = os.path.join(self.decals_output_dir, "Decals.uasset")
        if os.path.isfile(raw_path) and not os.path.isfile(uasset_path):
            os.rename(raw_path, uasset_path)

    def assemble_pak(self):
        """Stage Decals DataTable and texture assets."""
        self.log_step(3, "Assemble PAK directory")
        import shutil

        # Decals DataTable
        decals_asset = os.path.join(self.decals_output_dir, "Decals.uasset")
        self.stage_datatable(decals_asset, "Decals", "DataAsset")

        # Texture assets
        tex_dir = f"Materials/Decal/DecalTextures/{self.category}"
        for img_file in self.images:
            name = os.path.splitext(img_file)[0]
            tex_asset = os.path.join(self.textures_dir, f"{name}.uasset")
            if os.path.isfile(tex_asset):
                self.stage_asset(tex_asset, tex_dir, name=name)

    def print_summary(self):
        self.log(f"  Decals: {len(self.decal_entries)}")


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
    parser.add_argument("--output", "-o", default=None,
                        help="Output .pak file path (auto-generated from mod.json if omitted)")
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
    parser.add_argument("--mod", default=None,
                        help="Mod directory (e.g. mods/my-decals) to load mod.json from")
    args = parser.parse_args()

    if args.mod and not args.output:
        mod = load_mod_config(args.mod)
        game_ver = resolve_game_version()
        output_path = compute_output_path(mod, game_ver)
    elif args.output:
        output_path = args.output
    else:
        parser.error("Either --output or --mod is required")

    builder = DecalModBuilder(
        config_path="/dev/null",  # config is built from images
        output_path=output_path,
        input_dir=args.input,
        category=args.category,
        cost=args.cost,
        template=args.template,
        decals_template=args.decals,
        ue_version=args.version,
    )
    builder.build()


if __name__ == "__main__":
    main()
