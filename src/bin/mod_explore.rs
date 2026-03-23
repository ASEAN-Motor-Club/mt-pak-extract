use std::fs::{self, File};
use std::io::BufReader;
use std::path::Path;

use repak::PakBuilder;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    
    if args.len() < 2 {
        eprintln!("Usage: mod_explore <pak_file> [--list] [--search <pattern>] [--extract <path>] [--extract-all]");
        std::process::exit(1);
    }
    
    let pak_path = &args[1];
    let list_mode = args.iter().any(|a| a == "--list");
    let search_idx = args.iter().position(|a| a == "--search");
    let extract_idx = args.iter().position(|a| a == "--extract");
    let extract_all = args.iter().any(|a| a == "--extract-all");
    
    println!("Opening mod PAK: {}", pak_path);
    
    let mut file = BufReader::new(File::open(pak_path)?);
    
    // Try without key first (mod PAKs are usually unencrypted)
    let pak = match PakBuilder::new().reader(&mut file) {
        Ok(pak) => pak,
        Err(e) => {
            eprintln!("Failed to open without key: {}", e);
            eprintln!("Mod PAK might be encrypted. This tool only supports unencrypted mod PAKs.");
            std::process::exit(1);
        }
    };
    
    let mount_point = pak.mount_point();
    let version = pak.version();
    println!("Version: {:?}", version);
    println!("Mount point: {}", mount_point);
    
    let files: Vec<String> = pak.files().into_iter().collect();
    println!("Total files: {}", files.len());
    println!();
    
    // List all files
    if list_mode || (search_idx.is_none() && extract_idx.is_none() && !extract_all) {
        println!("=== All files in PAK ===");
        let mut uasset_count = 0;
        let mut uexp_count = 0;
        let mut other_count = 0;
        
        for path in &files {
            println!("  {}", path);
            if path.ends_with(".uasset") { uasset_count += 1; }
            else if path.ends_with(".uexp") { uexp_count += 1; }
            else { other_count += 1; }
        }
        
        println!();
        println!("Summary: {} .uasset, {} .uexp, {} other", uasset_count, uexp_count, other_count);
    }
    
    // Search mode
    if let Some(idx) = search_idx {
        let pattern = args.get(idx + 1)
            .ok_or("--search requires a pattern")?;
        
        println!("=== Searching for '{}' ===", pattern);
        let mut count = 0;
        for path in &files {
            if path.to_lowercase().contains(&pattern.to_lowercase()) {
                println!("  {}", path);
                count += 1;
            }
        }
        println!("Total: {} matches", count);
    }
    
    // Extract single file
    if let Some(idx) = extract_idx {
        let path = args.get(idx + 1)
            .ok_or("--extract requires a file path")?;
        
        let out_dir = Path::new("mod_out");
        fs::create_dir_all(out_dir)?;
        
        let file_name = Path::new(path)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("extracted");
        
        match pak.get(path, &mut file) {
            Ok(data) => {
                let out_path = out_dir.join(file_name);
                fs::write(&out_path, &data)?;
                println!("Extracted: {} ({} bytes)", out_path.display(), data.len());
            }
            Err(e) => {
                eprintln!("Failed to extract {}: {}", path, e);
            }
        }
    }
    
    // Extract all files
    if extract_all {
        let out_dir = Path::new("mod_out");
        fs::create_dir_all(out_dir)?;
        
        println!("=== Extracting all files to mod_out/ ===");
        let mut ok_count = 0;
        let mut fail_count = 0;
        
        for path in &files {
            // Create subdirectory structure
            let relative = path.trim_start_matches('/');
            let out_path = out_dir.join(relative);
            if let Some(parent) = out_path.parent() {
                fs::create_dir_all(parent)?;
            }
            
            match pak.get(path, &mut file) {
                Ok(data) => {
                    fs::write(&out_path, &data)?;
                    println!("  OK: {} ({} bytes)", path, data.len());
                    ok_count += 1;
                }
                Err(e) => {
                    println!("  FAIL: {} - {}", path, e);
                    fail_count += 1;
                }
            }
        }
        
        println!();
        println!("Extracted: {} OK, {} failed", ok_count, fail_count);
    }
    
    Ok(())
}
