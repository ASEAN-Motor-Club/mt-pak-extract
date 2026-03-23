#!/usr/bin/env python3
"""
Create decal texture packs for MotorTown.

Takes a directory of images (PNG/TGA) and injects them into template
decal texture .uasset files using the vendored UE4-DDS-Tools.

Usage:
    python scripts/create_decal_pack.py --input images/ --template out/014-kite.uasset --output decal_pack/
    python scripts/create_decal_pack.py --input images/ --template out/014-kite.uasset --output decal_pack/ --search GeomShape_01

The template must be an extracted decal texture from the base game
(512x512 PF_DXT5 Texture2D). All injected textures will use the same
dimensions and format as the template.

Output structure:
    decal_pack/
    ├── Texture1.uasset
    ├── Texture1.uexp
    ├── Texture2.uasset
    └── Texture2.uexp

To package into a mod PAK, place the output files under:
    MotorTown/Content/Materials/Decal/DecalTextures/{Category}/{name}.uasset
"""
import argparse
import os
import sys

# Add vendored UE4-DDS-Tools to path
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_tools_src = os.path.join(_repo_root, "tools", "ue4-dds-tools", "src")
if _tools_src not in sys.path:
    sys.path.insert(0, _tools_src)


def inject_image(template_uasset: str, image_path: str, output_dir: str,
                 version: str = "5.5", no_mipmaps: bool = False,
                 force_uncompressed: bool = False):
    """Inject a single image into a template uasset."""
    from main import inject
    import argparse as ap

    args = ap.Namespace(
        file=template_uasset,
        texture=image_path,
        save_folder=output_dir,
        mode="inject",
        version=version,
        export_as="dds",
        convert_to="tga",
        no_mipmaps=no_mipmaps,
        force_uncompressed=force_uncompressed,
        disable_tempfile=False,
        skip_non_texture=False,
        image_filter="linear",
        save_detected_version=False,
        max_workers=1,
    )

    folder = os.path.dirname(template_uasset)
    file = os.path.basename(template_uasset)
    inject(folder, file, args)


def main():
    parser = argparse.ArgumentParser(
        description="Create decal texture packs for MotorTown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Directory containing PNG/TGA images")
    parser.add_argument("--template", "-t", required=True,
                        help="Template .uasset file (extracted decal texture)")
    parser.add_argument("--output", "-o", required=True,
                        help="Output directory for injected textures")
    parser.add_argument("--version", "-v", default="5.5",
                        help="UE version (default: 5.5)")
    parser.add_argument("--no-mipmaps", action="store_true",
                        help="Remove mipmaps from output textures")
    parser.add_argument("--uncompressed", action="store_true",
                        help="Use uncompressed format (larger files)")
    parser.add_argument("--extension", default=".tga",
                        help="Image extension to look for (default: .tga)")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"Error: Input directory not found: {args.input}")
        sys.exit(1)

    if not os.path.isfile(args.template):
        print(f"Error: Template file not found: {args.template}")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    # Find images
    extensions = [args.extension.lower(), ".png", ".tga", ".jpg", ".bmp", ".dds"]
    images = []
    for f in sorted(os.listdir(args.input)):
        if any(f.lower().endswith(ext) for ext in extensions):
            images.append(os.path.join(args.input, f))

    if not images:
        print(f"No images found in {args.input}")
        sys.exit(1)

    print(f"=== MotorTown Decal Pack Creator ===")
    print(f"Template: {args.template}")
    print(f"Images:   {len(images)}")
    print(f"Output:   {args.output}")
    print(f"Version:  {args.version}")
    print()

    ok = 0
    fail = 0
    for img_path in images:
        name = os.path.splitext(os.path.basename(img_path))[0]
        print(f"Injecting: {name} ... ", end="", flush=True)
        try:
            inject_image(
                args.template, img_path, args.output,
                version=args.version,
                no_mipmaps=args.no_mipmaps,
                force_uncompressed=args.uncompressed,
            )
            # Rename output to match image name
            template_name = os.path.splitext(os.path.basename(args.template))[0]
            src_uasset = os.path.join(args.output, f"{template_name}.uasset")
            src_uexp = os.path.join(args.output, f"{template_name}.uexp")
            dst_uasset = os.path.join(args.output, f"{name}.uasset")
            dst_uexp = os.path.join(args.output, f"{name}.uexp")
            if os.path.exists(src_uasset):
                os.rename(src_uasset, dst_uasset)
            if os.path.exists(src_uexp):
                os.rename(src_uexp, dst_uexp)
            size = os.path.getsize(dst_uexp)
            print(f"OK ({size:,} bytes)")
            ok += 1
        except Exception as e:
            print(f"FAILED: {e}")
            fail += 1

    print()
    print(f"=== Done: {ok} injected, {fail} failed ===")
    if ok > 0:
        print()
        print("To use as a mod, place files under:")
        print("  MotorTown/Content/Materials/Decal/DecalTextures/{Category}/")


if __name__ == "__main__":
    main()
