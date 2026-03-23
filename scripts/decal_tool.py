#!/usr/bin/env python3
"""CLI wrappers for UE4-DDS-Tools (vendored)."""
import sys
import os


def _setup_ue4_dds_tools():
    """Add vendored UE4-DDS-Tools src/ to sys.path."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools_src = os.path.join(repo_root, "tools", "ue4-dds-tools", "src")
    if tools_src not in sys.path:
        sys.path.insert(0, tools_src)


def inject_cli():
    """Entry point for texture injection."""
    _setup_ue4_dds_tools()
    from main import main as ue4_main, get_args, get_config

    sys.argv[0] = "mt-decal-inject"
    args = get_args()
    config = get_config()
    ue4_main(args, config=config)


def export_cli():
    """Entry point for texture export."""
    _setup_ue4_dds_tools()
    from main import main as ue4_main, get_args, get_config

    sys.argv.insert(1, "--mode")
    sys.argv.insert(2, "export")
    sys.argv[0] = "mt-decal-export"
    args = get_args()
    config = get_config()
    ue4_main(args, config=config)


if __name__ == "__main__":
    inject_cli()
