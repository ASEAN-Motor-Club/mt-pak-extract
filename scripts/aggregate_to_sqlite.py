#!/usr/bin/env python3
"""
Aggregate MotorTown JSON data into SQLite database.
"""

import json
import sqlite3
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def strip_enum(value: str) -> str:
    """Strip enum prefix from values like 'EMTVehicleType::Small' -> 'Small'."""
    if "::" in value:
        return value.split("::")[-1]
    return value


def get_object_path(obj: Any) -> Optional[str]:
    """Extract path from object reference."""
    if isinstance(obj, dict) and obj.get("Type") in ("Import", "Export"):
        return obj.get("Path") or obj.get("ObjectName")
    return None


def create_schema(conn: sqlite3.Connection):
    """Create database schema."""
    cursor = conn.cursor()
    
    # Schema version for bot compatibility
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            game_version TEXT
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO schema_version (version, game_version) 
        VALUES (1, '0.7.17')
    """)
    
    # Vehicles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id TEXT PRIMARY KEY,
            name TEXT,
            vehicle_type TEXT,
            truck_class TEXT,
            blueprint_path TEXT,
            cost INTEGER,
            comport INTEGER,
            is_taxiable BOOLEAN,
            is_limoable BOOLEAN,
            is_busable BOOLEAN,
            is_race_car BOOLEAN,
            can_haul_trailer BOOLEAN,
            has_fuel_pump BOOLEAN,
            is_hidden BOOLEAN,
            is_disabled BOOLEAN,
            exhaust_smoke_density REAL,
            delivery_payment_multiplier REAL,
            source_file TEXT
        )
    """)
    
    # Vehicle parts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_parts (
            id TEXT PRIMARY KEY,
            name TEXT,
            part_type TEXT,
            cost INTEGER,
            mass_kg REAL,
            air_drag_multiplier REAL,
            engine_asset_path TEXT,
            transmission_asset_path TEXT,
            lsd_asset_path TEXT,
            final_drive_ratio REAL,
            is_hidden BOOLEAN,
            source_file TEXT
        )
    """)
    
    # Vehicle default parts junction
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_default_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT,
            slot TEXT,
            part_id TEXT,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id),
            FOREIGN KEY (part_id) REFERENCES vehicle_parts(id)
        )
    """)
    
    # Vehicle tags
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT,
            tag TEXT,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
        )
    """)
    
    # Cargos table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cargos (
            id TEXT PRIMARY KEY,
            name TEXT,
            cargo_type TEXT,
            volume_size INTEGER,
            weight_min REAL,
            weight_max REAL,
            payment_per_km INTEGER,
            payment_multiplier REAL,
            base_payment INTEGER,
            actor_class_path TEXT,
            allow_stacking BOOLEAN,
            use_damage BOOLEAN,
            fragile INTEGER,
            spawn_probability INTEGER,
            num_cargo_min INTEGER,
            num_cargo_max INTEGER,
            is_deprecated BOOLEAN,
            source_file TEXT
        )
    """)
    
    # Cargo space types
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cargo_space_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cargo_id TEXT,
            space_type TEXT,
            FOREIGN KEY (cargo_id) REFERENCES cargos(id)
        )
    """)
    
    # Cargo weights from blueprints
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cargo_weights (
            cargo_id TEXT PRIMARY KEY,
            total_weight_kg REAL,
            blueprint_path TEXT,
            FOREIGN KEY (cargo_id) REFERENCES cargos(id)
        )
    """)
    
    # Cargo weight components
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cargo_weight_components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cargo_id TEXT,
            component_name TEXT,
            mass_kg REAL,
            FOREIGN KEY (cargo_id) REFERENCES cargo_weights(cargo_id)
        )
    """)
    
    # Part compatible vehicle types
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS part_compatible_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id TEXT,
            vehicle_type TEXT,
            FOREIGN KEY (part_id) REFERENCES vehicle_parts(id)
        )
    """)
    
    conn.commit()


def process_vehicles(conn: sqlite3.Connection, json_files: List[Path]):
    """Process all vehicle JSON files."""
    cursor = conn.cursor()
    
    for json_file in json_files:
        if not json_file.name.startswith("Vehicles"):
            continue
            
        print(f"Processing vehicles from {json_file.name}...")
        with open(json_file) as f:
            data = json.load(f)
        
        if data.get("Data", {}).get("Type") != "DataTable":
            continue
        
        for row in data["Data"]["Rows"]:
            vehicle_id = row["RowName"]
            
            # Extract basic fields
            cursor.execute("""
                INSERT OR REPLACE INTO vehicles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vehicle_id,
                row.get("VehicleName"),
                strip_enum(row.get("VehicleType", "")),
                strip_enum(row.get("TruckClass", "")),
                get_object_path(row.get("VehicleClass")),
                row.get("Cost"),
                row.get("Comport"),
                row.get("bIsTaxiable"),
                row.get("bIsLimoable"),
                row.get("bIsBusable"),
                row.get("bIsRaceCar"),
                row.get("bTrailerHauling"),
                row.get("bHasFuelPump"),
                row.get("bHidden"),
                row.get("bDisabled"),
                row.get("ExhaustBlackSmokeDensity"),
                row.get("DeliveryPaymentMultiplier"),
                json_file.name
            ))
            
            # Extract GameplayTags
            tags = row.get("GameplayTags", {})
            if isinstance(tags, dict):
                tag_list = tags.get("GameplayTags", [])
                for tag in tag_list:
                    cursor.execute("""
                        INSERT INTO vehicle_tags (vehicle_id, tag) VALUES (?, ?)
                    """, (vehicle_id, tag))
            
            # Extract default parts
            parts = row.get("Parts", {})
            if isinstance(parts, dict) and parts.get("_Type") == "Map":
                for entry in parts.get("Entries", []):
                    slot = strip_enum(entry.get("Key", ""))
                    part_id = entry.get("Value")
                    if slot and part_id:
                        cursor.execute("""
                            INSERT INTO vehicle_default_parts (vehicle_id, slot, part_id)
                            VALUES (?, ?, ?)
                        """, (vehicle_id, slot, part_id))
    
    conn.commit()
    print(f"Inserted {cursor.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0]} vehicles")


def process_vehicle_parts(conn: sqlite3.Connection, json_files: List[Path]):
    """Process all vehicle parts JSON files."""
    cursor = conn.cursor()
    
    # Part files to process
    part_files = ["VehicleParts", "VehicleParts0", "Engines", "Transmissions", 
                  "Wheels", "Suspensions", "BrakePads", "BrakePower", "BrakeBalance",
                  "FinalDriveRatio", "LSD", "AeroParts", "CargoBed", "Headlights", "UtilityParts"]
    
    for json_file in json_files:
        if not any(json_file.name.startswith(pf) for pf in part_files):
            continue
            
        print(f"Processing parts from {json_file.name}...")
        with open(json_file) as f:
            data = json.load(f)
        
        if data.get("Data", {}).get("Type") != "DataTable":
            continue
        
        for row in data["Data"]["Rows"]:
            part_id = row["RowName"]
            
            # Extract basic fields
            cursor.execute("""
                INSERT OR REPLACE INTO vehicle_parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                part_id,
                row.get("Name"),
                strip_enum(row.get("PartType", "")),
                row.get("Cost"),
                row.get("MassKg"),
                row.get("AirDragMultiplier"),
                get_object_path(row.get("EngineAsset")),
                get_object_path(row.get("TransmissionAsset")),
                get_object_path(row.get("LSDAsset")),
                row.get("FinalDriveRatio"),
                row.get("bIsHidden"),
                json_file.name
            ))
            
            # Extract compatible vehicle types
            vehicle_types = row.get("VehicleTypes", [])
            for vtype in vehicle_types:
                cursor.execute("""
                    INSERT INTO part_compatible_types (part_id, vehicle_type)
                    VALUES (?, ?)
                """, (part_id, strip_enum(vtype)))
    
    conn.commit()
    print(f"Inserted {cursor.execute('SELECT COUNT(*) FROM vehicle_parts').fetchone()[0]} parts")


def process_cargos(conn: sqlite3.Connection, json_files: List[Path]):
    """Process cargo JSON files."""
    cursor = conn.cursor()
    
    for json_file in json_files:
        if not json_file.name.startswith("Cargos"):
            continue
            
        print(f"Processing cargos from {json_file.name}...")
        with open(json_file) as f:
            data = json.load(f)
        
        if data.get("Data", {}).get("Type") != "DataTable":
            continue
        
        for row in data["Data"]["Rows"]:
            cargo_id = row["RowName"]
            
            # Extract weight range
            weight_range = row.get("WeightRange", {})
            if isinstance(weight_range, dict):
                weight_data = weight_range.get("WeightRange", {})
                weight_min = weight_data.get("X", 0)
                weight_max = weight_data.get("Y", 0)
            else:
                weight_min = weight_max = 0
            
            # Extract basic fields
            cursor.execute("""
                INSERT OR REPLACE INTO cargos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cargo_id,
                row.get("Name"),
                strip_enum(row.get("CargoType", "")),
                row.get("VolumeSize"),
                weight_min,
                weight_max,
                row.get("PaymentPer1Km"),
                row.get("PaymentPer1KmMultiplierByMaxWeight"),
                row.get("BasePayment"),
                get_object_path(row.get("ActorClass")),
                row.get("bAllowStacking"),
                row.get("bUseDamage"),
                row.get("Fragile"),
                row.get("SpawnProbability"),
                row.get("NumCargoMin"),
                row.get("NumCargoMax"),
                row.get("bDepcreated"),
                json_file.name
            ))
            
            # Extract cargo space types
            space_types = row.get("CargoSpaceTypes", [])
            for space_type in space_types:
                cursor.execute("""
                    INSERT INTO cargo_space_types (cargo_id, space_type)
                    VALUES (?, ?)
                """, (cargo_id, strip_enum(space_type)))
    
    conn.commit()
    print(f"Inserted {cursor.execute('SELECT COUNT(*) FROM cargos').fetchone()[0]} cargos")


def process_cargo_weights(conn: sqlite3.Connection, json_files: List[Path]):
    """Process cargo actor blueprints to extract weights."""
    cursor = conn.cursor()
    
    # Step 1: Build mapping from ActorClass path to blueprint filename
    print("Building cargo-to-blueprint mapping...")
    cargo_blueprint_map = {}  # cargo_id -> blueprint_filename
    
    for row in cursor.execute("SELECT id, actor_class_path FROM cargos WHERE actor_class_path IS NOT NULL"):
        cargo_id, actor_path = row
        if actor_path:
            # Extract blueprint name from path
            # e.g., /Game/Objects/Mission/Delivery/BottleBox/BottleBox_C -> BottleBox
            parts = actor_path.split("/")
            if len(parts) >= 2:
                blueprint_name = parts[-1].replace("_C", "")
                cargo_blueprint_map[cargo_id] = blueprint_name
    
    print(f"Mapped {len(cargo_blueprint_map)} cargos to blueprint names")
    
    # Step 2: Build reverse mapping from blueprint filename to cargo IDs
    blueprint_to_cargos = {}  # blueprint_filename -> [cargo_ids]
    for cargo_id, blueprint_name in cargo_blueprint_map.items():
        if blueprint_name not in blueprint_to_cargos:
            blueprint_to_cargos[blueprint_name] = []
        blueprint_to_cargos[blueprint_name].append(cargo_id)
    
    # Step 3: Process blueprint files
    for json_file in json_files:
        if not json_file.name.endswith("_parsed.json"):
            continue
            
        with open(json_file) as f:
            data = json.load(f)
        
        # Only process Blueprint types
        if data.get("Data", {}).get("Type") != "Blueprint":
            continue
        
        # Extract blueprint filename (e.g., BottleBox_parsed.json -> BottleBox)
        blueprint_name = json_file.stem.replace("_parsed", "")
        
        # Find matching cargo(s) using the mapping
        matching_cargos = blueprint_to_cargos.get(blueprint_name, [])
        if not matching_cargos:
            continue
        
        print(f"Processing cargo weights from {json_file.name}...")
        
        # Extract all MassInKgOverride values from exports
        total_mass = 0
        components = []
        
        for export in data["Data"].get("Exports", []):
            export_name = export.get("ExportName", "Unknown")
            props = export.get("Properties", {})
            
            # Check for BodyInstance with mass
            body_instance = props.get("BodyInstance")
            if isinstance(body_instance, dict):
                mass = body_instance.get("MassInKgOverride")
                if mass and mass > 0:
                    total_mass += mass
                    components.append((export_name, mass))
        
        if total_mass > 0:
            # Get blueprint path from first export
            blueprint_path = None
            if data["Data"].get("Exports"):
                first_export = data["Data"]["Exports"][0]
                blueprint_path = first_export.get("ExportName")
            
            # Insert weights for all matching cargos
            for cargo_id in matching_cargos:
                cursor.execute("""
                    INSERT OR REPLACE INTO cargo_weights VALUES (?, ?, ?)
                """, (cargo_id, total_mass, blueprint_path))
                
                # Insert components
                for component_name, mass in components:
                    cursor.execute("""
                        INSERT INTO cargo_weight_components (cargo_id, component_name, mass_kg)
                        VALUES (?, ?, ?)
                    """, (cargo_id, component_name, mass))
    
    conn.commit()
    print(f"Inserted weights for {cursor.execute('SELECT COUNT(*) FROM cargo_weights').fetchone()[0]} cargos")


def create_views(conn: sqlite3.Connection):
    """Create useful views."""
    cursor = conn.cursor()
    
    # View: cargos with their actual weights (including blueprint weights)
    cursor.execute("""
        CREATE VIEW IF NOT EXISTS cargos_with_weights AS
        SELECT 
            c.*,
            COALESCE(cw.total_weight_kg, c.weight_max, 0) as actual_weight_kg,
            cw.blueprint_path
        FROM cargos c
        LEFT JOIN cargo_weights cw ON c.id = cw.cargo_id
    """)
    
    # View: active, valid cargos (excludes deprecated and invalid entries)
    cursor.execute("""
        CREATE VIEW IF NOT EXISTS active_cargos AS
        SELECT 
            c.*,
            COALESCE(cw.total_weight_kg, c.weight_max, 0) as actual_weight_kg,
            cw.blueprint_path
        FROM cargos c
        LEFT JOIN cargo_weights cw ON c.id = cw.cargo_id
        WHERE (c.is_deprecated = 0 OR c.is_deprecated IS NULL)
          AND c.actor_class_path IS NOT NULL 
          AND c.actor_class_path != ''
    """)
    
    # View: vehicle default engines
    cursor.execute("""
        CREATE VIEW IF NOT EXISTS vehicles_with_engines AS
        SELECT 
            v.id,
            v.name,
            v.cost,
            vp.id as engine_id,
            vp.mass_kg as engine_mass_kg,
            vp.engine_asset_path
        FROM vehicles v
        LEFT JOIN vehicle_default_parts vdp ON v.id = vdp.vehicle_id AND vdp.slot = 'Engine'
        LEFT JOIN vehicle_parts vp ON vdp.part_id = vp.id
    """)
    
    conn.commit()


def main():
    """Main aggregation pipeline."""
    out_dir = Path("out")
    db_path = Path("motortown.db")
    
    if not out_dir.exists():
        print(f"Error: {out_dir} directory not found")
        return
    
    # Get all JSON files
    json_files = sorted(out_dir.glob("*_parsed.json"))
    print(f"Found {len(json_files)} JSON files")
    
    # Remove existing database
    if db_path.exists():
        print(f"Removing existing {db_path}")
        db_path.unlink()
    
    # Create database
    print("Creating database schema...")
    conn = sqlite3.connect(db_path)
    create_schema(conn)
    
    # Phase 1: Core tables
    print("\n=== Phase 1: Core Tables ===")
    process_vehicles(conn, json_files)
    process_vehicle_parts(conn, json_files)
    process_cargos(conn, json_files)
    
    # Phase 2: Cargo weights
    print("\n=== Phase 2: Cargo Weights ===")
    process_cargo_weights(conn, json_files)
    
    # Phase 3: Views
    print("\n=== Phase 3: Creating Views ===")
    create_views(conn)
    
    conn.close()
    
    # Print summary statistics
    print("\n=== Summary ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    stats = [
        ("Vehicles", "SELECT COUNT(*) FROM vehicles"),
        ("Vehicle Parts", "SELECT COUNT(*) FROM vehicle_parts"),
        ("Cargos (Total)", "SELECT COUNT(*) FROM cargos"),
        ("Cargo Weights", "SELECT COUNT(*) FROM cargo_weights"),
        ("Default Parts", "SELECT COUNT(*) FROM vehicle_default_parts"),
        ("Vehicle Tags", "SELECT COUNT(*) FROM vehicle_tags"),
    ]
    
    for name, query in stats:
        result = cursor.execute(query).fetchone()
        count = result[0] if result else 0
        print(f"{name}: {count}")
    
    # Data quality statistics
    print("\n=== Data Quality ===")
    quality_stats = [
        ("Deprecated Cargos", "SELECT COUNT(*) FROM cargos WHERE is_deprecated = 1"),
        ("Cargos Missing ActorClass", "SELECT COUNT(*) FROM cargos WHERE actor_class_path IS NULL OR actor_class_path = ''"),
        ("Cargos with Zero WeightRange", "SELECT COUNT(*) FROM cargos WHERE weight_max = 0"),
        ("Active Cargos (Valid)", "SELECT COUNT(*) FROM active_cargos"),
    ]
    
    for name, query in quality_stats:
        result = cursor.execute(query).fetchone()
        count = result[0] if result else 0
        print(f"{name}: {count}")
    
    conn.close()
    print(f"\nDatabase created: {db_path}")
    print(f"To export: sqlite3 {db_path} .dump > motortown_data.sql")


if __name__ == "__main__":
    main()
