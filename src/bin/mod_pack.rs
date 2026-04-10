use std::fs::{self, File};
use std::io::BufWriter;
use std::path::Path;

use repak::PakBuilder;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 3 {
        eprintln!("Usage: mod_pack <input_dir> <output.pak> [--mount <mount_point>]");
        eprintln!("  Creates a UE5 PAK file from a directory tree.");
        eprintln!("  Default mount point: ../../../ (MotorTown content root)");
        std::process::exit(1);
    }

    let input_dir = &args[1];
    let output_pak = &args[2];
    let mount_idx = args.iter().position(|a| a == "--mount");
    let mount_point = mount_idx
        .and_then(|i| args.get(i + 1))
        .map(|s| s.as_str())
        .unwrap_or("../../../");

    if !Path::new(input_dir).is_dir() {
        eprintln!("Error: {} is not a directory", input_dir);
        std::process::exit(1);
    }

    println!("Creating PAK: {}", output_pak);
    println!("Input: {}", input_dir);
    println!("Mount point: {}", mount_point);

    // Collect all files recursively
    let mut paths: Vec<std::path::PathBuf> = Vec::new();
    collect_files(&mut paths, Path::new(input_dir))?;
    paths.sort();

    println!("Files to pack: {}", paths.len());

    let input_path = Path::new(input_dir);
    let mut pak = PakBuilder::new().writer(
        BufWriter::new(File::create(output_pak)?),
        repak::Version::V11,
        mount_point.to_string(),
        Some(0),
    );

    let entry_builder = pak.entry_builder();

    for p in &paths {
        let rel = p
            .strip_prefix(input_path)
            .expect("file not in input directory")
            .to_string_lossy()
            .replace('\\', "/");
        let data = fs::read(p)?;
        let entry = entry_builder.build_entry(false, data)?;
        pak.write_entry(rel.clone(), entry)?;
        println!("  {} ({} bytes)", rel, fs::metadata(p)?.len());
    }

    pak.write_index()?;

    println!();
    println!("Done! PAK created: {}", output_pak);
    Ok(())
}

fn collect_files(paths: &mut Vec<std::path::PathBuf>, dir: &Path) -> std::io::Result<()> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_files(paths, &path)?;
        } else {
            paths.push(entry.path());
        }
    }
    Ok(())
}
