{
  description = "MT pak extraction and decal pack creation tool";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # uv2nix for Python dependency management
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, rust-overlay, pyproject-nix, uv2nix, pyproject-build-systems }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        inherit (nixpkgs) lib;
        overlays = [ (import rust-overlay) ];
        pkgs = import nixpkgs {
          inherit system overlays;
        };
        rustToolchain = pkgs.rust-bin.stable.latest.default;

        # --- uv2nix Python setup ---
        workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

        overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };

        editableOverlay = workspace.mkEditablePyprojectOverlay {
          root = "$REPO_ROOT";
        };

        pythonSet =
          (pkgs.callPackage pyproject-nix.build.packages {
            python = pkgs.python312;
          }).overrideScope
          (lib.composeManyExtensions [
            pyproject-build-systems.overlays.wheel
            overlay
          ]);

        editablePythonSet = pythonSet.overrideScope editableOverlay;
        virtualenv = editablePythonSet.mkVirtualEnv "mt-pak-extract-env" workspace.deps.all;
        # --- end uv2nix ---

        # Script to run both extraction and parsing
        extractScript = pkgs.writeShellApplication {
          name = "extract-assets";
          runtimeInputs = with pkgs; [
            rustToolchain
            cargo
            dotnet-sdk_8
            openssl
            pkg-config
            gcc.cc.lib  # libstdc++.so.6 for Oodle decompression
          ];
          text = ''
            set -euo pipefail

            CONFIG="''${1:-assets.json}"

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
            ls -1 ../../out/*_parsed.json 2>/dev/null || echo "No parsed files found"
          '';
        };

        # Script to aggregate parsed data into SQLite
        aggregateScript = pkgs.writeShellApplication {
          name = "aggregate-to-sqlite";
          runtimeInputs = [ virtualenv ];
          text = ''
            set -euo pipefail

            echo "=== MotorTown Data Aggregation ==="
            echo "Aggregating parsed JSON into SQLite database..."
            echo

            python3 scripts/aggregate_to_sqlite.py

            echo
            echo "=== Database Export ==="
            if [ -f motortown.db ]; then
              sqlite3 motortown.db .dump > motortown_data.sql
              echo "Exported to motortown_data.sql"
            fi
          '';
        };
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            rustToolchain
            pkg-config
            openssl
            dotnet-sdk_8
            gcc.cc.lib  # libstdc++.so.6 for Oodle decompression + libgomp for texconv
            uv
            virtualenv
          ];

          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = editablePythonSet.python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
          };

          shellHook = ''
            unset PYTHONPATH
            export REPO_ROOT=$(git rev-parse --show-toplevel)
            export LD_LIBRARY_PATH="${pkgs.gcc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

            echo "MotorTown PAK Extraction Environment"
            echo "  Rust: $(rustc --version 2>/dev/null || echo 'not in PATH')"
            echo "  .NET: $(dotnet --version 2>/dev/null || echo 'not in PATH')"
            echo "  Python: $(python3 --version 2>/dev/null || echo 'not in PATH')"
            echo ""
            echo "Commands:"
            echo "  nix run .#extract        - Extract all assets from assets.json"
            echo "  nix run .#aggregate      - Aggregate JSON to SQLite database"
            echo "  cargo run -- --list      - List available DataAssets"
            echo "  cargo run -- --config X  - Extract assets from config file"
            echo "  mt-decal-inject          - Inject image into texture asset"
          '';
        };

        apps.extract = {
          type = "app";
          program = "${extractScript}/bin/extract-assets";
        };

        apps.aggregate = {
          type = "app";
          program = "${aggregateScript}/bin/aggregate-to-sqlite";
        };
      }
    );
}
