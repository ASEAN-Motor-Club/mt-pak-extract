use std::fs::{self, File};
use std::io::BufReader;
use std::path::Path;

use aes::Aes256;
use aes::cipher::KeyInit;
use repak::PakBuilder;
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Config {
    assets: Vec<String>,
}

#[derive(Serialize)]
struct Manifest {
    extracted: Vec<ExtractedAsset>,
}

#[derive(Serialize)]
struct ExtractedAsset {
    name: String,
    pak_path: String,
    uasset: String,
    uexp: Option<String>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    
    let list_mode = args.contains(&"--list".to_string());
    let config_idx = args.iter().position(|a| a == "--config");
    
    println!("=== MotorTown PAK Asset Extractor ===");
    println!("Usage: {} [--list] [--config <file>] [asset_path]", args[0]);
    println!("  --list: Show all DataAsset files in PAK");
    println!("  --config <file>: Batch extract assets listed in JSON config");
    println!("  asset_path: Extract single asset (default: Cargos)");
    println!();
    
    // Load AES key from .env file
    dotenvy::dotenv().ok();
    let key_hex = std::env::var("KEY")?;
    
    let key_hex = key_hex.strip_prefix("0x").unwrap_or(&key_hex);
    let key_bytes: [u8; 32] = hex::decode(key_hex)?
        .try_into()
        .map_err(|_| "Key must be 32 bytes")?;
    
    let aes_key = Aes256::new_from_slice(&key_bytes)?;
    
    // Open the PAK file
    let pak_path = "MotorTown-WindowsServer.pak";
    let mut file = BufReader::new(File::open(pak_path)?);
    
    println!("Opening PAK file: {}", pak_path);
    
    let pak = PakBuilder::new()
        .key(aes_key)
        .reader(&mut file)?;
    
    // Handle --list mode
    if list_mode {
        println!("=== Available DataAsset files ===");
        let mut count = 0;
        for path in pak.files() {
            if path.ends_with(".uasset") && path.contains("DataAsset") {
                println!("  {}", path.trim_end_matches(".uasset"));
                count += 1;
            }
        }
        println!("Total: {} DataAsset files", count);
        return Ok(());
    }
    
    // Handle --search mode
    let search_idx = args.iter().position(|a| a == "--search");
    if let Some(idx) = search_idx {
        let pattern = args.get(idx + 1)
            .ok_or("--search requires a pattern")?;
        
        println!("=== Searching for assets containing '{}' ===", pattern);
        let mut count = 0;
        for path in pak.files() {
            if path.ends_with(".uasset") && path.to_lowercase().contains(&pattern.to_lowercase()) {
                println!("  {}", path.trim_end_matches(".uasset"));
                count += 1;
            }
        }
        println!("Total: {} matching assets", count);
        return Ok(());
    }
    
    // Handle --config mode (batch extraction)
    if let Some(idx) = config_idx {
        let config_path = args.get(idx + 1)
            .ok_or("--config requires a file path")?;
        
        println!("Loading config: {}", config_path);
        let config_content = fs::read_to_string(config_path)?;
        let config: Config = serde_json::from_str(&config_content)?;
        
        // Create output directory
        let out_dir = Path::new("out");
        fs::create_dir_all(out_dir)?;
        
        println!("Extracting {} assets to {}/", config.assets.len(), out_dir.display());
        
        let mut manifest = Manifest { extracted: Vec::new() };
        
        for asset_path in &config.assets {
            let asset_path = asset_path
                .trim_end_matches(".uasset")
                .trim_end_matches(".uexp");
            
            let name = Path::new(asset_path)
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("asset");
            
            let uasset_pak_path = format!("{}.uasset", asset_path);
            let uexp_pak_path = format!("{}.uexp", asset_path);
            
            print!("  {} ... ", name);
            
            match pak.get(&uasset_pak_path, &mut file) {
                Ok(uasset_data) => {
                    let uasset_out = out_dir.join(format!("{}.uasset", name));
                    fs::write(&uasset_out, &uasset_data)?;
                    
                    let uexp_out = match pak.get(&uexp_pak_path, &mut file) {
                        Ok(uexp_data) => {
                            let path = out_dir.join(format!("{}.uexp", name));
                            fs::write(&path, &uexp_data)?;
                            Some(format!("{}.uexp", name))
                        }
                        Err(_) => None,
                    };
                    
                    println!("OK ({} bytes)", uasset_data.len());
                    
                    manifest.extracted.push(ExtractedAsset {
                        name: name.to_string(),
                        pak_path: asset_path.to_string(),
                        uasset: format!("{}.uasset", name),
                        uexp: uexp_out,
                    });
                }
                Err(e) => {
                    println!("FAILED: {}", e);
                }
            }
        }
        
        // Write manifest
        let manifest_path = out_dir.join("manifest.json");
        let manifest_json = serde_json::to_string_pretty(&manifest)?;
        fs::write(&manifest_path, &manifest_json)?;
        
        println!("\n=== Extracted {} assets ===", manifest.extracted.len());
        println!("Manifest: {}", manifest_path.display());
        println!("\nRun C# parser: cd csharp/CargoExtractor && dotnet run -- --batch");
        
        return Ok(());
    }
    
    // Single asset mode (existing behavior)
    let asset_path = args.iter()
        .skip(1)
        .find(|a| !a.starts_with("--"))
        .cloned()
        .unwrap_or_else(|| "MotorTown/Content/DataAsset/Cargos".to_string());
    
    let asset_path = asset_path
        .trim_end_matches(".uasset")
        .trim_end_matches(".uexp")
        .to_string();
    
    let uasset_path = format!("{}.uasset", asset_path);
    let uexp_path = format!("{}.uexp", asset_path);
    
    println!("Extracting: {}", uasset_path);
    
    let uasset_data = pak.get(&uasset_path, &mut file)?;
    let uexp_data = match pak.get(&uexp_path, &mut file) {
        Ok(data) => {
            println!("  uexp: {} bytes", data.len());
            Some(data)
        }
        Err(_) => {
            println!("  No .uexp file");
            None
        }
    };
    
    println!("  uasset: {} bytes", uasset_data.len());
    
    let output_name = Path::new(&asset_path)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("asset");
    
    fs::write(format!("{}.uasset", output_name), &uasset_data)?;
    println!("Saved: {}.uasset", output_name);
    
    if let Some(uexp) = uexp_data {
        fs::write(format!("{}.uexp", output_name), &uexp)?;
        println!("Saved: {}.uexp", output_name);
    }
    
    println!("\nDone! Use the C# parser to extract properties:");
    println!("  cd csharp/CargoExtractor && dotnet run -- {}.uasset", output_name);
    
    Ok(())
}
