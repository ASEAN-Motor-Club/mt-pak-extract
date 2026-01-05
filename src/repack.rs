//! PAK Repacker - Creates mod PAK files from modified assets
//! 
//! Usage: cargo run --bin repack -- [options]
//!   --input <file>    Modified asset file to include (can specify multiple)
//!   --output <file>   Output PAK file path
//!   --version <ver>   PAK version (default: V11)

use std::fs::File;
use std::io::{BufWriter, Read, Seek, Write};
use std::path::Path;

use aes::Aes256;
use aes::cipher::KeyInit;
use repak::{PakBuilder, Version};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    
    println!("=== MotorTown PAK Repacker ===");
    
    // Parse command line arguments
    let mut input_files: Vec<String> = Vec::new();
    let mut output_path = "MotorTown-CustomContent.pak".to_string();
    
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--input" | "-i" => {
                if let Some(path) = args.get(i + 1) {
                    input_files.push(path.clone());
                    i += 2;
                } else {
                    return Err("--input requires a file path".into());
                }
            }
            "--output" | "-o" => {
                if let Some(path) = args.get(i + 1) {
                    output_path = path.clone();
                    i += 2;
                } else {
                    return Err("--output requires a file path".into());
                }
            }
            "--help" | "-h" => {
                print_usage(&args[0]);
                return Ok(());
            }
            _ => {
                // Treat unknown args as input files
                input_files.push(args[i].clone());
                i += 1;
            }
        }
    }
    
    if input_files.is_empty() {
        println!("No input files specified.");
        print_usage(&args[0]);
        return Ok(());
    }
    
    // Load AES key from .env file
    dotenvy::dotenv().ok();
    let key_hex = std::env::var("KEY")?;
    
    let key_hex = key_hex.strip_prefix("0x").unwrap_or(&key_hex);
    let key_bytes: [u8; 32] = hex::decode(key_hex)?
        .try_into()
        .map_err(|_| "Key must be 32 bytes")?;
    
    let aes_key = Aes256::new_from_slice(&key_bytes)?;
    
    println!("Creating mod PAK: {}", output_path);
    println!("  Version: V11 (UE5.5)");
    println!("  Encryption: None (mod files)");
    println!();
    
    // Create output PAK file
    let output_file = BufWriter::new(File::create(&output_path)?);
    
    // Create PAK writer - NO encryption for mod files
    let mut pak_writer = PakBuilder::new()
        .writer(
            output_file,
            Version::V11,  // MotorTown uses UE5.5
            "../../../".to_string(),  // Mount point
            None,  // Path hash seed
        );
    
    // Process each input file
    for input_path in &input_files {
        let path = Path::new(input_path);
        
        if !path.exists() {
            println!("  ⚠ Skipping (not found): {}", input_path);
            continue;
        }
        
        // Determine PAK internal path from filename
        // e.g., "out/Cargos.uasset" -> "MotorTown/Content/DataAsset/Cargos.uasset"
        let pak_path = get_pak_path(input_path)?;
        
        // Read file contents
        let mut file = File::open(path)?;
        let mut contents = Vec::new();
        file.read_to_end(&mut contents)?;
        
        // Add to PAK with Zlib compression
        pak_writer.write_file(&pak_path, true, contents)?;
        println!("  ✓ Added: {} -> {}", input_path, pak_path);
        
        // Also add .uexp if exists
        let uexp_path = input_path.replace(".uasset", ".uexp");
        if Path::new(&uexp_path).exists() {
            let mut uexp_file = File::open(&uexp_path)?;
            let mut uexp_contents = Vec::new();
            uexp_file.read_to_end(&mut uexp_contents)?;
            
            let pak_uexp_path = pak_path.replace(".uasset", ".uexp");
            pak_writer.write_file(&pak_uexp_path, true, uexp_contents)?;
            println!("  ✓ Added: {} -> {}", uexp_path, pak_uexp_path);
        }
    }
    
    // Finalize PAK
    pak_writer.write_index()?;
    
    println!();
    println!("✅ Created: {}", output_path);
    println!();
    println!("Installation:");
    println!("  Copy {} to your game's Paks/ folder.", output_path);
    println!("  The mod will override base game assets.");
    
    Ok(())
}

fn print_usage(program: &str) {
    println!();
    println!("Usage: {} [options] [input_files...]", program);
    println!();
    println!("Options:");
    println!("  -i, --input <file>   Modified asset file to include");
    println!("  -o, --output <file>  Output PAK file (default: MotorTown-CustomContent.pak)");
    println!("  -h, --help           Show this help message");
    println!();
    println!("Examples:");
    println!("  {} out/Cargos_modified.uasset", program);
    println!("  {} -i out/Cargos_modified.uasset -i out/Factory_Cheese_modified.uasset", program);
    println!();
}

/// Map local file path to PAK internal path
/// Based on analysis of working ASEAN_P.pak:
///   - Cargos -> DataAsset/Cargos
///   - Factory_Cheese -> Objects/Mission/Delivery/DeliveryPoint/Factory_Cheese
fn get_pak_path(local_path: &str) -> Result<String, Box<dyn std::error::Error>> {
    let filename = Path::new(local_path)
        .file_name()
        .ok_or("Invalid path")?
        .to_str()
        .ok_or("Invalid UTF-8")?;
    
    // Remove _modified suffix if present
    let clean_name = filename.replace("_modified", "");
    
    // Determine content type from name pattern - match ASEAN_P.pak structure
    let pak_path = if clean_name.starts_with("Factory_") || 
                      clean_name.starts_with("Farm_") ||
                      clean_name.starts_with("Mine_") ||
                      clean_name.starts_with("Sawmill_") ||
                      clean_name.starts_with("Port_") ||
                      clean_name.starts_with("Warehouse_") ||
                      clean_name.starts_with("Store_") {
        // Delivery points: Objects/Mission/Delivery/DeliveryPoint/
        format!("Objects/Mission/Delivery/DeliveryPoint/{}", clean_name)
    } else if clean_name == "Cargos.uasset" || clean_name == "Cargos.uexp" {
        // DataAsset files
        format!("DataAsset/{}", clean_name)
    } else if clean_name.starts_with("Vehicles") {
        format!("DataAsset/{}", clean_name)
    } else {
        // Default to DataAsset folder
        format!("DataAsset/{}", clean_name)
    };
    
    Ok(pak_path)
}
