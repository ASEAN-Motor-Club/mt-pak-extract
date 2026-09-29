#!/usr/bin/env python3
"""
modbase — Shared base module for MotorTown mod PAK creation.

Provides:
  - ModBuilder: base class with the standard 4-stage build flow
  - Shared helpers: run_dotnet, build_pak, verify_pak, compat-mod extraction
  - PAK staging utilities
  - mod.json loading and game version resolution

All mod-type scripts (create_tirepack.py, create_cargopack.py, etc.)
subclass ModBuilder and implement only their type-specific logic.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


MODS_DIR = "mods"
GAME_VERSIONS_FILE = "game_versions.json"


def get_active_game_version(repo_root: str = None) -> str | None:
    """Read the active game version from game_versions.json."""
    if repo_root is None:
        repo_root = str(Path(__file__).resolve().parent.parent)
    manifest_path = os.path.join(repo_root, GAME_VERSIONS_FILE)
    if not os.path.exists(manifest_path):
        return None
    with open(manifest_path) as f:
        manifest = json.load(f)
    return manifest.get("active")


def resolve_game_version(repo_root: str = None) -> str:
    """Resolve the active game version, stripping the 'v' prefix.

    Returns e.g. '0.7.18+1' from active version 'v0.7.18+1'.
    Exits with error if no active version is set.
    """
    active = get_active_game_version(repo_root)
    if not active:
        print("Error: No active game version set in game_versions.json", file=sys.stderr)
        print("  Run: scripts/mt-version.sh switch <version>", file=sys.stderr)
        sys.exit(1)
    if active.startswith("v"):
        return active[1:]
    return active


def load_mod_config(mod_dir: str) -> dict:
    """Load mod.json from a mod directory.

    Returns the parsed dict with resolved paths:
      - config_dir: absolute path to the mod directory
      - configs: absolute paths to config files
      - builds_dir: absolute path to the builds output directory
    """
    mod_json_path = os.path.join(mod_dir, "mod.json")
    if not os.path.exists(mod_json_path):
        print(f"Error: mod.json not found at {mod_json_path}", file=sys.stderr)
        sys.exit(1)

    with open(mod_json_path) as f:
        mod = json.load(f)

    mod["config_dir"] = os.path.abspath(mod_dir)
    mod["configs"] = [
        os.path.abspath(os.path.join(mod_dir, c))
        for c in mod.get("configs", [])
    ]
    mod["builds_dir"] = os.path.join(os.path.abspath(mod_dir), "builds")

    return mod


def compute_output_path(mod: dict, game_version: str = None,
                        compat_suffix: str = None,
                        flavor: str = None) -> str:
    """Compute the output PAK path from mod metadata and game version.

    Format: {prefix}{display_name}_v{mod_version}_{game_version}[_{flavor}][_{compat_suffix}]_P.pak
    Example: zzz_ASEAN_PoliceTyres_v0.1.9_0.7.18+1_MoreTuningCompat_P.pak
             Schedule_I_v0.7.3_0.7.19_CLIENT_P.pak
    """
    if game_version is None:
        game_version = resolve_game_version()

    prefix = mod.get("prefix", "")
    display_name = mod.get("display_name")
    mod_version = mod.get("version")
    if not display_name or not mod_version:
        raise ValueError(f"mod.json missing display_name/version for {mod}")

    parts = [f"{prefix}{display_name}_v{mod_version}_{game_version}"]
    if flavor:
        parts.append(flavor.upper())
    if compat_suffix:
        parts.append(compat_suffix)
    filename = "_".join(parts) + "_P.pak"

    return os.path.join(mod["builds_dir"], filename)


def list_mods(repo_root: str = None) -> list[dict]:
    """List all mods with valid mod.json in the mods/ directory."""
    if repo_root is None:
        repo_root = str(Path(__file__).resolve().parent.parent)
    mods_path = os.path.join(repo_root, MODS_DIR)
    if not os.path.isdir(mods_path):
        return []

    result = []
    for name in sorted(os.listdir(mods_path)):
        mod_dir = os.path.join(mods_path, name)
        mod_json = os.path.join(mod_dir, "mod.json")
        if os.path.isfile(mod_json):
            mod = load_mod_config(mod_dir)
            result.append(mod)
    return result


class ModBuilder:
    """Base class for MotorTown mod PAK creation.

    Subclasses implement:
      - transform_assets(): create/patch type-specific UAsset files
      - register_in_tables(): add rows to DataTables
      - assemble_pak(): arrange files in PAK directory layout

    The build() method orchestrates the full pipeline:
      1. transform_assets()
      2. register_in_tables()
      3. assemble_pak()
      4. build_pak()
      5. verify_pak()
    """

    def __init__(self, name: str, config_path: str, output_path: str,
                 compat_mods: list[str] | None = None):
        self.name = name
        self.config_path = os.path.abspath(config_path)
        self.output_path = os.path.abspath(output_path)
        self.compat_mods = [os.path.abspath(m) for m in (compat_mods or [])]

        self.repo_root = str(Path(__file__).resolve().parent.parent)
        self.csharp_dir = os.path.join(self.repo_root, "csharp", "UAssetTool")

        # Set during build()
        self.build_dir: str | None = None
        self.pak_staging: str | None = None
        self.config: dict = {}

        # Load config
        if not os.path.exists(self.config_path):
            self.fail(f"Config not found: {self.config_path}")
        with open(self.config_path) as f:
            self.config = json.load(f)

    # ── Shared infrastructure ──────────────────────────────────────────

    def fail(self, msg: str):
        """Print error and exit."""
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

    def log(self, msg: str):
        """Print a log message."""
        print(msg)

    def log_step(self, step_num: int | str, label: str):
        """Print a step header."""
        print(f"\n=== Step {step_num}: {label} ===")

    def run_dotnet(self, args: list[str], label: str):
        """Run a C# dotnet command in the UAssetTool project.

        Prefers the prebuilt binary when available to avoid MSBuild overhead.
        Falls back to `dotnet run` for development builds.

        Args:
            args: command-line arguments after '--'
            label: human-readable description for error messages
        """
        env = os.environ.copy()
        # Use build_dir for dotnet temp to avoid disk-full issues on /tmp
        if self.build_dir:
            env["TMPDIR"] = self.build_dir

        # Try prebuilt binary first (faster, no MSBuild)
        prebuilt = os.path.join(self.csharp_dir, "bin", "Release", "net8.0", "UAssetTool")
        if os.path.isfile(prebuilt):
            result = subprocess.run(
                [prebuilt] + args,
                cwd=self.csharp_dir,
                capture_output=True, text=True,
                env=env,
            )
        else:
            result = subprocess.run(
                ["dotnet", "run", "--configuration", "Debug",
                 "--verbosity", "quiet", "--"] + args,
                cwd=self.csharp_dir,
                capture_output=True, text=True,
                env=env,
            )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            print(f"Error: {label} failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
        return result

    def run_generic(self, operation: str, config: dict,
                    template: str, output_dir: str, label: str):
        """Run a generic C# UAssetTool operation with a generated config.

        Writes config to a temp JSON file in the build dir and invokes
        the C# tool with the specified operation.

        Args:
            operation: one of '--add-rows', '--clone-asset', '--patch-cdo-arrays'
            config: dict to serialize as the operation's config JSON
            template: path to the template .uasset file
            output_dir: directory for output files
            label: human-readable label for error messages
        """
        config_path = os.path.join(self.build_dir, f"{label.replace(' ', '_')}.json")
        with open(config_path, 'w') as f:
            json.dump(config, f)
        self.run_dotnet([operation, config_path, template, output_dir], label)

    def ensure_mod_pack(self) -> str:
        """Ensure mod_pack binary is built. Returns path to binary."""
        mod_pack = os.path.join(self.repo_root, "target", "release", "mod_pack")
        if not os.path.isfile(mod_pack):
            self.log("  Building mod_pack...")
            result = subprocess.run(
                ["cargo", "build", "--release", "--bin", "mod_pack"],
                cwd=self.repo_root, capture_output=True, text=True,
            )
            if result.returncode != 0:
                self.fail(f"Failed to build mod_pack:\n{result.stderr}")
        return mod_pack

    def build_pak(self, staging_dir: str):
        """Build a mod PAK from a staged directory using mod_pack."""
        mod_pack = self.ensure_mod_pack()
        # Try direct execution first, fallback to explicit interpreter
        # (needed when the binary was built against a nix store glibc
        # that may not be in the default loader search path)
        # Find a working glibc interpreter for binaries built against a
        # different nix store path
        interpreter = None
        for glibc_path in [
            "/nix/store/l0l2ll1lmylczj1ihqn351af2kyp5x19-glibc-2.42-51/lib/ld-linux-x86-64.so.2",
            "/nix/store/wn7v2vhyyyi6clcyn0s9ixvl7d4d87ic-glibc-2.40-36/lib/ld-linux-x86-64.so.2",
            "/nix/store/i3ibgfskl99qd8rslafbpaa1dmxdzh1z-glibc-2.40-66/lib/ld-linux-x86-64.so.2",
        ]:
            if os.path.isfile(glibc_path):
                interpreter = glibc_path
                break
        env = os.environ.copy()
        if interpreter:
            cmd = [interpreter, mod_pack, staging_dir, self.output_path]
        else:
            cmd = [mod_pack, staging_dir, self.output_path]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            env=env,
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            self.fail(f"mod_pack failed:\n{result.stderr}")

    def verify_pak(self):
        """List PAK contents + run flavor canary using mod_explore/UAssetTool."""
        mod_explore = os.path.join(self.repo_root, "target", "release", "mod_explore")
        if os.path.isfile(mod_explore) and os.path.isfile(self.output_path):
            print(f"\n--- PAK contents ---")
            subprocess.run(
                [mod_explore, self.output_path, "--list"],
                capture_output=False,
            )
        self.flavor_canary()

    # ── Flavor canary ──────────────────────────────────────────────────

    CANARY_ASSET = "MotorTown/Content/Objects/Mission/Delivery/DeliveryPoint/Supermarket"

    def flavor_canary(self):
        """Post-build check: extract a DP from the built pak and assert its
        cook flavor matches the build flavor (client=unversioned, server=tagged).

        Catches both provenance failure modes on the artifact itself:
          - server-cooked bytes shipped in a client pak (DP prompts die), and
          - WRITE_VERSIONED=1 leaking into a client build.
        Skipped for builds without build_flavor set.
        """
        flavor = getattr(self, "build_flavor", None)
        if not flavor:
            return
        uasset_tool = os.path.join(
            self.csharp_dir, "bin", "Release", "net8.0", "UAssetTool")
        mod_explore = os.path.join(self.repo_root, "target", "release", "mod_explore")
        if not (os.path.isfile(uasset_tool) and os.path.isfile(mod_explore)):
            print("  Flavor canary: SKIPPED (tools not built)")
            return
        if not os.path.isfile(self.output_path):
            return

        expected = "HasUnversioned=True" if flavor == "client" else "HasUnversioned=False"
        tmpdir = os.path.join(self.build_dir or tempfile.gettempdir(), "canary")
        os.makedirs(tmpdir, exist_ok=True)
        base = os.path.basename(self.CANARY_ASSET)
        for ext in ("uasset", "uexp"):
            r = subprocess.run(
                [mod_explore, self.output_path, "--extract",
                 f"{self.CANARY_ASSET}.{ext}"],
                capture_output=True, text=True, cwd=self.repo_root)
            src = os.path.join(self.repo_root, "mod_out", f"{base}.{ext}")
            if not os.path.exists(src):
                print(f"  Flavor canary: SKIPPED ({base}.{ext} not in pak)")
                return
            os.replace(src, os.path.join(tmpdir, f"{base}.{ext}"))
        r = subprocess.run(
            [uasset_tool, "--dump", os.path.join(tmpdir, f"{base}.uasset")],
            capture_output=True, text=True, cwd=self.csharp_dir)
        m = re.search(r"HasUnversioned=(True|False)", r.stdout)
        if not m:
            print(f"  Flavor canary: UNREADABLE (dump failed) — inspect manually")
            return
        if m.group(0) != expected:
            self.fail(
                f"Flavor canary FAILED: {base} is {m.group(0)}, expected {expected}\n"
                f"  The {flavor} pak contains wrong-flavor template bytes. "
                f"Re-bootstrap and rebuild."
            )
        print(f"  Flavor canary: OK ({base} {m.group(0)} as expected for {flavor})")

    # ── Provenance gates ───────────────────────────────────────────────

    def check_provenance(self, flavor: str | None = None):
        """Fail the build if the template-root tree lacks valid provenance.

        Reads <template_root>/provenance.json (written by scripts/bootstrap.py)
        and asserts it exists and references a pak recorded in paks.json.
        If `flavor` is given, also assert the provenance flavor matches.

        The gate is skipped when:
          - SKIP_PROVENANCE_CHECK=1 is set (explicit opt-out for exploration), or
          - the builder sets self.skip_provenance_check = True (mod types that
            don't ship game-template assets, e.g. decals/fonts).
        """
        if os.environ.get("SKIP_PROVENANCE_CHECK") == "1":
            print("  Provenance check: SKIPPED (SKIP_PROVENANCE_CHECK=1)")
            return
        if getattr(self, "skip_provenance_check", False):
            print("  Provenance check: SKIPPED (builder opt-out)")
            return

        prov_path = os.path.join(self.template_root, "provenance.json")
        if not os.path.isfile(prov_path):
            self.fail(
                f"No provenance manifest at {prov_path}.\n"
                f"  Templates in '{self.template_root}' are unverified — a polluted\n"
                f"  tree (e.g. server-cooked bytes in a client tree) ships broken paks.\n"
                f"  Fix: nix run .#bootstrap -- <game_version> client|server"
            )
        try:
            with open(prov_path) as f:
                prov = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            self.fail(f"Cannot read provenance manifest {prov_path}: {e}")

        required = ("flavor", "game_version", "source_pak_md5", "source_pak_size")
        missing = [k for k in required if k not in prov]
        if missing:
            self.fail(f"Provenance manifest {prov_path} missing fields: {missing}")

        if flavor and prov["flavor"] != flavor:
            self.fail(
                f"Template provenance flavor is '{prov['flavor']}' but this build "
                f"requires '{flavor}'. Bootstrap the right tree: "
                f"nix run .#bootstrap -- {prov.get('game_version')} {flavor}"
            )

        # The recorded source pak must still exist and match paks.json.
        paks_json = os.path.join(self.repo_root, "paks.json")
        if os.path.isfile(paks_json):
            with open(paks_json) as f:
                table = json.load(f)
            gv = prov.get("game_version")
            entry = table.get(gv, {}).get(prov["flavor"])
            if entry:
                if entry.get("md5") != prov.get("source_pak_md5"):
                    self.fail(
                        f"Provenance md5 ({prov.get('source_pak_md5')}) does not match "
                        f"paks.json ({entry.get('md5')}) for {gv} {prov['flavor']}. "
                        f"Re-bootstrap: nix run .#bootstrap -- {gv} {prov['flavor']}"
                    )
                src_path = entry.get("path", "")
                if src_path and not os.path.isabs(src_path):
                    src_path = os.path.join(self.repo_root, src_path)
                if src_path and os.path.isfile(src_path):
                    actual = os.path.getsize(src_path)
                    if actual != entry.get("size"):
                        self.fail(
                            f"Source pak {src_path} size changed ({actual} vs "
                            f"{entry.get('size')}). Re-bootstrap."
                        )

        print(f"  Provenance check: OK (flavor={prov['flavor']}, "
              f"game={prov['game_version']}, md5={prov['source_pak_md5'][:12]}…)")

    # ── Compat mod support ─────────────────────────────────────────────

    def extract_from_compat_mod(self, pak_path: str, asset_pak_path: str,
                                 dest_dir: str) -> str | None:
        """Extract a single asset from another mod's PAK file.

        Args:
            pak_path: path to the .pak file
            asset_pak_path: asset path inside the PAK
                (e.g., 'MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset')
            dest_dir: directory to store extracted files

        Returns:
            path to extracted .uasset, or None if not found
        """
        basename = os.path.splitext(os.path.basename(asset_pak_path))[0]
        os.makedirs(dest_dir, exist_ok=True)

        for ext in ["uasset", "uexp"]:
            full_pak_path = asset_pak_path.replace(".uasset", f".{ext}")
            result = subprocess.run(
                ["cargo", "run", "--release", "--quiet", "--bin", "mod_explore",
                 "--", pak_path, "--extract", full_pak_path],
                cwd=self.repo_root,
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                # mod_explore writes to mod_out/ in CWD
                src = os.path.join(self.repo_root, "mod_out", f"{basename}.{ext}")
                dst = os.path.join(dest_dir, f"{basename}.{ext}")
                if os.path.exists(src):
                    shutil.move(src, dst)
            else:
                mod_name = os.path.basename(pak_path)
                print(f"  Warning: Could not extract {basename}.{ext} from {mod_name}")

        extracted = os.path.join(dest_dir, f"{basename}.uasset")
        return extracted if os.path.exists(extracted) else None

    def resolve_template_with_compat(self, base_template: str,
                                       asset_pak_path: str) -> str:
        """Resolve a DataTable template, preferring compat mod version if available.

        Iterates through --compat-mod PAKs in order; the last one that contains
        the asset wins. Falls back to base_template if none have it.

        Args:
            base_template: path to the base game template .uasset
            asset_pak_path: PAK-internal path to extract from compat mods

        Returns:
            path to the resolved template .uasset
        """
        if not self.compat_mods:
            return base_template

        template = base_template
        for mod_pak in self.compat_mods:
            if not os.path.exists(mod_pak):
                self.fail(f"Compat mod PAK not found: {mod_pak}")

            mod_name = os.path.basename(mod_pak)
            self.log(f"\n  Extracting from compat mod: {mod_name}")

            extract_dir = tempfile.mkdtemp(prefix="compat_", dir=self.build_dir)
            extracted = self.extract_from_compat_mod(mod_pak, asset_pak_path, extract_dir)
            if extracted:
                template = extracted
                self.log(f"  ✓ Using template from: {mod_name}")
            else:
                basename = os.path.basename(asset_pak_path)
                self.log(f"  Warning: {mod_name} does not contain {basename}, skipping")

        return template

    # ── PAK staging helpers ────────────────────────────────────────────

    def init_staging(self) -> str:
        """Create and return the PAK staging directory."""
        self.pak_staging = os.path.join(self.build_dir, "pak_staging")
        os.makedirs(self.pak_staging, exist_ok=True)
        return self.pak_staging

    def stage_asset(self, src_uasset: str, pak_relative_dir: str, name: str | None = None):
        """Copy a .uasset/.uexp pair to the PAK staging directory.

        Args:
            src_uasset: path to the source .uasset file
            pak_relative_dir: path relative to MotorTown/Content/
                (e.g., 'Cars/Parts/Tire')
            name: override filename (without extension). If None, uses source filename.
        """
        if name is None:
            name = os.path.splitext(os.path.basename(src_uasset))[0]

        dest_dir = os.path.join(self.pak_staging, "MotorTown", "Content", pak_relative_dir)
        os.makedirs(dest_dir, exist_ok=True)

        for ext in [".uasset", ".uexp", ".ubulk"]:
            src = src_uasset.replace(".uasset", ext)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dest_dir, f"{name}{ext}"))
                self.log(f"  Staged: {pak_relative_dir}/{name}{ext}")

    def stage_datatable(self, src_path: str, datatable_name: str, pak_subdir: str):
        """Stage a DataTable asset into the PAK layout.

        Convenience wrapper around stage_asset for DataTables.

        Args:
            src_path: path to the .uasset file
            datatable_name: name of the DataTable (e.g., 'VehicleParts0')
            pak_subdir: PAK content subdirectory (e.g., 'DataAsset/VehicleParts')
        """
        self.stage_asset(src_path, pak_subdir, name=datatable_name)

    def stage_blueprint(self, src_path: str, blueprint_name: str, pak_subdir: str):
        """Stage a blueprint asset into the PAK layout.

        Convenience wrapper around stage_asset for vehicle blueprints.

        Args:
            src_path: path to the .uasset file
            blueprint_name: name of the blueprint (e.g., 'Zydro_Police')
            pak_subdir: PAK content subdirectory (e.g., 'Cars/Models/Zydro_Police')
        """
        self.stage_asset(src_path, pak_subdir, name=blueprint_name)

    # ── Main build flow ────────────────────────────────────────────────

    def build(self):
        """Execute the full mod build pipeline.

        Template method pattern — subclasses implement the hooks:
          transform_assets()  → create/patch type-specific asset files
          register_in_tables() → add rows to DataTables
          assemble_pak()      → arrange files in PAK directory layout
        """
        print(f"\n=== Building {self.name} ===")

        flavor = getattr(self, "build_flavor", None)
        self.check_provenance(flavor)
        if flavor == "client" and os.environ.get("WRITE_VERSIONED") == "1":
            self.fail(
                "WRITE_VERSIONED=1 is set but this is a CLIENT build.\n"
                "  Client paks must ship unversioned (WRITE_VERSIONED unset) —\n"
                "  tagged writes crash the game client (DP interaction dies)."
            )

        with tempfile.TemporaryDirectory(prefix=f"modpack_{self.name}_") as build_dir:
            self.build_dir = build_dir
            self.init_staging()

            self.transform_assets()
            self.register_in_tables()
            self.assemble_pak()

            print(f"\n=== Building PAK ===")
            self.build_pak(self.pak_staging)

        # Ensure builds/ directory exists
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

        # Report results
        if os.path.exists(self.output_path):
            size = os.path.getsize(self.output_path)
            print(f"\n=== Success! ===")
            print(f"  Output: {self.output_path}")
            print(f"  Size: {size:,} bytes")
            self.print_summary()
            self.verify_pak()
        else:
            self.fail(f"Output PAK not created: {self.output_path}")

        self.check_output_gates()

    def check_output_gates(self):
        """Post-build gates: size band + file-set regression vs prior builds.

        - Size band: fails if mod.json declares
          `expected_sizes: {client|server: bytes}` and the output differs by
          more than 25%; otherwise warns when the pak is >40% smaller than the
          largest prior pak for the same flavor (silent under-build detector).
        - File set: warns if the newest prior pak of the same flavor shipped
          files this build dropped (only files, never sizes).
        Both gates only apply when build_flavor is set.
        """
        flavor = getattr(self, "build_flavor", None)
        if not flavor or not os.path.isfile(self.output_path):
            return
        size = os.path.getsize(self.output_path)

        # Explicit expectation from mod.json.
        expected = (getattr(self, "mod_config", None) or {}).get(
            "expected_sizes", {}).get(flavor)
        if expected:
            if abs(size - expected) > expected * 0.25:
                self.fail(
                    f"Output size {size:,} is >25% off the expected "
                    f"{flavor} size {expected:,}. Likely under/over-built — "
                    f"check the build log for failed staging steps."
                )
            print(f"  Size gate: OK ({size:,} bytes, expected ≈{expected:,})")

        # File-set diff vs newest prior pak of the same flavor.
        builds_dir = os.path.dirname(self.output_path)
        fname = os.path.basename(self.output_path)
        prior = []
        if os.path.isdir(builds_dir):
            for f in os.listdir(builds_dir):
                if not f.endswith("_P.pak") or f == fname:
                    continue
                if flavor == "client" and "SERVER" in f.upper():
                    continue
                if flavor == "server" and "CLIENT" in f.upper():
                    continue
                p = os.path.join(builds_dir, f)
                if os.path.getmtime(p) < os.path.getmtime(self.output_path):
                    prior.append((os.path.getmtime(p), p, os.path.getsize(p)))
        if not prior:
            return
        prior.sort()
        prev_path, prev_size = prior[-1][1], prior[-1][2]

        # Largest prior same-flavor pak: strong under-build signal.
        largest = max(s for _, _, s in prior)
        if largest > 0 and size < largest * 0.6:
            print(f"  Size gate: WARNING — output {size:,} is <60% of the "
                  f"largest prior {flavor} pak ({largest:,}). Verify content.")

        mod_explore = os.path.join(self.repo_root, "target", "release", "mod_explore")
        if os.path.isfile(mod_explore):
            def listing(pak):
                r = subprocess.run([mod_explore, pak, "--list"],
                                   capture_output=True, text=True)
                return {ln for ln in r.stdout.splitlines() if ln.endswith(".uasset")}
            new_files, old_files = listing(self.output_path), listing(prev_path)
            dropped = old_files - new_files
            if dropped:
                print(f"  File-set gate: WARNING — {len(dropped)} file(s) shipped in "
                      f"{os.path.basename(prev_path)} but not this build:")
                for f in sorted(dropped)[:10]:
                    print(f"    - {f}")

    # ── Subclass hooks ─────────────────────────────────────────────────

    def transform_assets(self):
        """Create or patch type-specific UAsset files.

        Override in subclasses to implement mod-type-specific asset creation
        (e.g., tire physics patching, cargo blueprint creation, image injection).
        """
        pass

    def register_in_tables(self):
        """Add rows to DataTables.

        Override in subclasses to register new items in the appropriate
        DataTables (e.g., VehicleParts0, Cargos, Decals).
        """
        pass

    def assemble_pak(self):
        """Arrange output files into the PAK directory layout.

        Override in subclasses to call stage_asset() / stage_datatable()
        with the correct PAK-relative paths for each mod type.
        """
        pass

    def print_summary(self):
        """Print a mod-type-specific summary after successful build.

        Override in subclasses to report what was built.
        """
        pass


def add_common_args(parser):
    """Add arguments common to all mod builders."""
    parser.add_argument("--config", "-c", required=True,
                        help="Mod config JSON file")
    parser.add_argument("--output", "-o", required=True,
                        help="Output PAK file path (must end in _P.pak)")
    parser.add_argument("--compat-mod", action="append", default=[], metavar="PAK",
                        help="Build on top of another mod's DataTable "
                             "(can specify multiple, last wins)")