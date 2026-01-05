//! PAK Verification - Verifies a created PAK file can be read and parsed
//!
//! Usage: cargo run --bin verify-pak -- <pak_file>

use std::fs::File;
use std::io::BufReader;

use aes::Aes256;
use aes::cipher::KeyInit;
use repak::PakBuilder;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    
    let pak_path = args.get(1).ok_or("Usage: verify-pak <pak_file>")?;
    
    println!("=== PAK Verification ===");
    println!();
    
    // Load AES key from .env file
    dotenvy::dotenv().ok();
    let key_hex = std::env::var("KEY")?;
    
    let key_hex = key_hex.strip_prefix("0x").unwrap_or(&key_hex);
    let key_bytes: [u8; 32] = hex::decode(key_hex)?
        .try_into()
        .map_err(|_| "Key must be 32 bytes")?;
    
    let aes_key = Aes256::new_from_slice(&key_bytes)?;
    
    println!("Opening PAK: {}", pak_path);
    
    // Try to open and read the PAK
    let mut file = BufReader::new(File::open(pak_path)?);
    
    let pak = PakBuilder::new()
        .key(aes_key)
        .reader(&mut file)?;
    
    println!("✓ PAK opened successfully");
    println!();
    
    // List files in the PAK
    let files = pak.files();
    println!("Files in PAK: {}", files.len());
    
    for path in &files {
        println!("  {}", path);
    }
    
    println!();
    
    // Extract assets for parsing verification
    std::fs::create_dir_all("out/verify")?;
    
    // Need to reopen file for each extraction (repak consumes reader)
    for path in &files {
        if path.ends_with(".uasset") || path.ends_with(".uexp") {
            let mut reader = BufReader::new(File::open(pak_path)?);
            let pak = PakBuilder::new()
                .key(Aes256::new_from_slice(&key_bytes)?)
                .reader(&mut reader)?;
            
            let data = pak.get(path, &mut reader)?;
            
            // Save to verify directory
            let filename = std::path::Path::new(path)
                .file_name()
                .unwrap()
                .to_str()
                .unwrap();
            
            let verify_path = format!("out/verify/{}", filename);
            std::fs::write(&verify_path, &data)?;
            println!("  Extracted: {} ({} bytes)", verify_path, data.len());
        }
    }
    
    println!();
    println!("✅ PAK verification passed!");
    println!();
    println!("To verify parsing, run:");
    println!("  cd csharp/AssetEditor && dotnet run -- list-productions ../../out/verify/Factory_Cheese.uasset");
    
    Ok(())
}
