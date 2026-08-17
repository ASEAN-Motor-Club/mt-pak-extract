use std::fs::{self, File};
use std::io::BufReader;
use std::path::Path;

use aes::cipher::KeyInit;
use aes::Aes256;
use repak::PakBuilder;

/// Extract the game's Game.locres files (one per culture) from MotorTown-Windows.pak.
/// Writes each culture's locres to <out_dir>/<culture>/Game.locres.
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let key_hex = std::env::var("KEY")?;
    let key_hex = key_hex.strip_prefix("0x").unwrap_or(&key_hex);
    let key_bytes: [u8; 32] = hex::decode(key_hex)?.try_into().map_err(|_| "Key must be 32 bytes")?;
    let aes_key = Aes256::new_from_slice(&key_bytes)?;

    let pak_path = "MotorTown-Windows.pak";
    let out_dir = std::env::args().nth(1).unwrap_or_else(|| "locres_out".to_string());

    let cultures = [
        "cs", "de", "en", "es-419", "es-ES", "fi", "fr", "hu", "it", "ja", "ko",
        "lt", "nl", "no", "pl", "pt-BR", "ru", "sv", "tr", "uk", "vi", "zh-Hans", "zh-Hant",
    ];

    let mut file = BufReader::new(File::open(pak_path)?);
    let pak = PakBuilder::new().key(aes_key).reader(&mut file)?;

    fs::create_dir_all(&out_dir)?;
    let mut total = 0;
    for culture in cultures {
        let target = format!("MotorTown/Content/Localization/Game/{culture}/Game.locres");
        match pak.get(&target, &mut file) {
            Ok(data) => {
                let dir = Path::new(&out_dir).join(culture);
                fs::create_dir_all(&dir)?;
                fs::write(dir.join("Game.locres"), &data)?;
                println!("OK {culture}: {} bytes", data.len());
                total += data.len();
            }
            Err(e) => println!("FAIL {culture}: {e}"),
        }
    }
    println!("Extracted {total} total bytes to {out_dir}");
    Ok(())
}
