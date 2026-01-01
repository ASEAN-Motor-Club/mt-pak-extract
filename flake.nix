{
  description = "MT pak extraction tool";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, rust-overlay }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        overlays = [ (import rust-overlay) ];
        pkgs = import nixpkgs {
          inherit system overlays;
        };
        rustToolchain = pkgs.rust-bin.stable.latest.default;
        
        # Script to run both extraction and parsing
        extractScript = pkgs.writeShellApplication {
          name = "extract-assets";
          runtimeInputs = with pkgs; [
            rustToolchain
            cargo
            dotnet-sdk_8
            openssl
            pkg-config
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
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            rustToolchain
            pkg-config
            openssl
            dotnet-sdk_8
            (python312.withPackages (ps: with ps; [
              pip
            ]))
          ];

          shellHook = ''
            echo "MotorTown PAK Extraction Environment"
            echo "  Rust: $(rustc --version)"
            echo "  .NET: $(dotnet --version)"
            echo ""
            echo "Commands:"
            echo "  nix run .#extract        - Extract all assets from assets.json"
            echo "  cargo run -- --list      - List available DataAssets"
            echo "  cargo run -- --config X  - Extract assets from config file"
          '';
        };
        
        apps.extract = {
          type = "app";
          program = "${extractScript}/bin/extract-assets";
        };
      }
    );
}
