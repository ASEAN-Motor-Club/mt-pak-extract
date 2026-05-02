use std::fs::File;
use std::io::BufReader;

use aes::cipher::KeyInit;
use aes::Aes256;
use repak::PakBuilder;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let key_hex = std::env::var("KEY")?;
    let key_hex = key_hex.strip_prefix("0x").unwrap_or(&key_hex);
    let key_bytes: [u8; 32] = hex::decode(key_hex)?.try_into().map_err(|_| "Key must be 32 bytes")?;
    let aes_key = Aes256::new_from_slice(&key_bytes)?;

    let pak_path = "MotorTown-Windows.pak";
    let target = "MotorTown/Config/DefaultEngine.ini";

    let mut file = BufReader::new(File::open(pak_path)?);
    let pak = PakBuilder::new().key(aes_key).reader(&mut file)?;

    let data = pak.get(target, &mut file)?;
    std::fs::write("DefaultEngine.ini", &data)?;

    println!("Extracted {} -> DefaultEngine.ini ({} bytes)", target, data.len());
    Ok(())
}
