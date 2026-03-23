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
        VALUES (5, '0.7.17')
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
            delivery_base_payment INTEGER,
            body_damage_threshold REAL,
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
            payment_sqrt_ratio REAL,
            payment_sqrt_ratio_min_capacity INTEGER,
            max_damage_payment_multiplier REAL,
            damage_bonus_multiplier REAL,
            manual_loading_payment INTEGER,
            min_delivery_distance INTEGER,
            max_delivery_distance INTEGER,
            has_timer BOOLEAN,
            base_time_seconds INTEGER,
            timer_by_speed_kph REAL,
            timer_by_road_speed_limit_ratio REAL,
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
    
    # Cargo bed specifications (dimensions and capacity)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cargo_bed_specs (
            part_id TEXT PRIMARY KEY,
            cargo_space_type TEXT,
            length_cm REAL,
            width_cm REAL,
            height_cm REAL,
            dump_volume_kl REAL,
            fix_cargo BOOLEAN,
            unlimited_height BOOLEAN,
            FOREIGN KEY (part_id) REFERENCES vehicle_parts(id)
        )
    """)
    
    # Part tuning values (EAV table)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS part_tuning (
            part_id TEXT,
            struct_type TEXT,
            field_name TEXT,
            field_value REAL,
            PRIMARY KEY (part_id, struct_type, field_name),
            FOREIGN KEY (part_id) REFERENCES vehicle_parts(id)
        )
    """)
    
    # All unique tuning values per part_type (handles duplicate RowNames)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS part_type_values (
            part_type TEXT,
            struct_type TEXT,
            field_name TEXT,
            field_value REAL,
            PRIMARY KEY (part_type, struct_type, field_name, field_value)
        )
    """)
    
    # Blueprint variant names (tire/LSD pak variants)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blueprint_variants (
            base_name TEXT,     -- e.g. 'BasicTire', '1WayClutchPackLSD'
            variant_name TEXT,  -- full pak asset name e.g. 'BasicTire_65'
            asset_type TEXT,    -- 'TirePhysics' or 'LSD'
            PRIMARY KEY (variant_name)
        )
    """)
    
    # Vehicle weights from blueprints (chassis mass)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_weights (
            vehicle_id TEXT PRIMARY KEY,
            chassis_mass_kg REAL,
            blueprint_path TEXT,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
        )
    """)
    
    # Delivery points table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_points (
            id TEXT PRIMARY KEY,
            mission_point_type TEXT,
            max_passive_deliveries INTEGER,
            destination_types TEXT,
            blueprint_path TEXT,
            source_file TEXT
        )
    """)
    
    # Production configurations for delivery points
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_point_id TEXT,
            config_index INTEGER,
            production_time_seconds INTEGER,
            local_food_supply REAL,
            production_speed_multiplier REAL,
            store_input_cargo BOOLEAN,
            is_hidden BOOLEAN,
            FOREIGN KEY (delivery_point_id) REFERENCES delivery_points(id)
        )
    """)
    
    # Production input cargos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_inputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            production_config_id INTEGER,
            cargo_id TEXT,
            quantity INTEGER,
            FOREIGN KEY (production_config_id) REFERENCES production_configs(id),
            FOREIGN KEY (cargo_id) REFERENCES cargos(id)
        )
    """)
    
    # Production output cargos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            production_config_id INTEGER,
            cargo_id TEXT,
            quantity INTEGER,
            FOREIGN KEY (production_config_id) REFERENCES production_configs(id),
            FOREIGN KEY (cargo_id) REFERENCES cargos(id)
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
                INSERT OR REPLACE INTO vehicles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                row.get("DeliveryBasePayment"),
                row.get("BodyDamageThreshold"),
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


def process_part_tuning(conn: sqlite3.Connection, json_files: List[Path]):
    """Extract tuning parameters from vehicle parts into the part_tuning EAV table."""
    cursor = conn.cursor()
    
    # Sub-struct definitions: struct_key -> (struct_type_label, fields_to_extract)
    TUNABLE_STRUCTS = {
        "SuspensionDamper": ("SuspensionDamper", [
            "BoundDampingRateMultiplier", "ReboundDampingRateMultiplier",
        ]),
        "SuspensionSpring": ("SuspensionSpring", [
            "SpringRateMultiplier",
        ]),
        "SuspensionRideHeight": ("SuspensionRideHeight", [
            "RideHeightChange",
        ]),
        "AntiRollBar": ("AntiRollBar", [
            "AntiRollBarRateMultiplier",
        ]),
        "BrakePad": ("BrakePad", [
            "HeatingMultiplier", "CoolingMultiplier", "FadeTemperature", "WearMultiplier",
        ]),
        "BrakePower": ("BrakePower", [
            "BrakePowerMultiplier",
        ]),
        "BrakeBalance": ("BrakeBalance", [
            "FrontMultiplier", "RearMultiplier",
        ]),
        "Turbocharger": ("Turbocharger", [
            "bIsValid", "BaseTorqueMultiplier", "TorqueMultiplier",
            "TurbineAspectRatio", "IntakePressureMultiplier",
            "HeatingMultiplier", "FuelConsumptionMultiplier", "TurbineWeight",
        ]),
        "Intake": ("Intake", [
            "Slope", "BaseRPMRatio", "IntakeSpeedEfficencyMultiplier",
        ]),
        "CoolantRadiator": ("CoolantRadiator", [
            "CoolingPower", "CoolantWaterInLiter",
        ]),
        "AngleKit": ("AngleKit", [
            "AngleIncreaseInDegree",
        ]),
        "WheelSpacer": ("WheelSpacer", [
            "Space",
        ]),
        "Winch": ("Winch", [
            "MaxForceKg", "MaxLength",
        ]),
        "FuelTank": ("FuelTank", [
            "FuelLiter",
        ]),
        "ItemInventory": ("ItemInventory", [
            "NumSlots",
        ]),
    }
    
    # Top-level numeric fields that vary per part (aero tuning)
    TOP_LEVEL_FIELDS = [
        "AirDragMultiplier", "TrailerAirDragMultiplier",
        "AeroLift", "FrontAeroLift", "RearAeroLift",
        "FrontDamageMultiplier",
    ]
    
    part_files = ["VehicleParts", "VehicleParts0", "Engines", "Transmissions",
                  "Wheels", "Suspensions", "BrakePads", "BrakePower", "BrakeBalance",
                  "FinalDriveRatio", "LSD", "AeroParts", "CargoBed", "Headlights", "UtilityParts"]
    
    insert_count = 0
    
    for json_file in json_files:
        if not any(json_file.name.startswith(pf) for pf in part_files):
            continue
        
        with open(json_file) as f:
            data = json.load(f)
        
        if data.get("Data", {}).get("Type") != "DataTable":
            continue
        
        for row in data["Data"]["Rows"]:
            part_id = row["RowName"]
            part_type = strip_enum(row.get("PartType", ""))
            
            # Extract sub-struct tuning values
            for struct_key, (struct_label, fields) in TUNABLE_STRUCTS.items():
                struct_data = row.get(struct_key)
                if not struct_data or not isinstance(struct_data, dict):
                    continue
                
                for field_name in fields:
                    value = struct_data.get(field_name)
                    if value is None:
                        continue
                    # Convert booleans to 0/1
                    if isinstance(value, bool):
                        value = 1 if value else 0
                    if isinstance(value, (int, float)):
                        cursor.execute("""
                            INSERT OR REPLACE INTO part_tuning
                            (part_id, struct_type, field_name, field_value)
                            VALUES (?, ?, ?, ?)
                        """, (part_id, struct_label, field_name, value))
                        insert_count += 1
                        
                        # Also store in part_type_values (handles duplicate RowNames)
                        if part_type:
                            cursor.execute("""
                                INSERT OR IGNORE INTO part_type_values
                                (part_type, struct_type, field_name, field_value)
                                VALUES (?, ?, ?, ?)
                            """, (part_type, struct_label, field_name, value))
            
            # Extract Tire physics data asset path as a string value
            tire_data = row.get("Tire")
            if tire_data and isinstance(tire_data, dict):
                tire_asset = tire_data.get("TirePhysicsDataAsset")
                if tire_asset and isinstance(tire_asset, dict):
                    path = tire_asset.get("Path", "")
                    if path:
                        # Store the asset name (last path component)
                        asset_name = path.split("/")[-1]
                        cursor.execute("""
                            INSERT OR REPLACE INTO part_tuning
                            (part_id, struct_type, field_name, field_value)
                            VALUES (?, 'Tire', 'TirePhysicsDataAsset', ?)
                        """, (part_id, hash(asset_name) % 1000000))  # numeric hash for REAL column
                
                dual = tire_data.get("bIsDualRearWheel")
                if dual is not None:
                    cursor.execute("""
                        INSERT OR REPLACE INTO part_tuning
                        (part_id, struct_type, field_name, field_value)
                        VALUES (?, 'Tire', 'bIsDualRearWheel', ?)
                    """, (part_id, 1 if dual else 0))
                    insert_count += 1
            
            # Extract top-level aero/numeric fields
            for field_name in TOP_LEVEL_FIELDS:
                value = row.get(field_name)
                if value is not None and isinstance(value, (int, float)):
                    cursor.execute("""
                        INSERT OR REPLACE INTO part_tuning
                        (part_id, struct_type, field_name, field_value)
                        VALUES (?, 'TopLevel', ?, ?)
                    """, (part_id, field_name, value))
                    insert_count += 1
                    
                    if part_type:
                        cursor.execute("""
                            INSERT OR IGNORE INTO part_type_values
                            (part_type, struct_type, field_name, field_value)
                            VALUES (?, 'TopLevel', ?, ?)
                        """, (part_type, field_name, value))
    
    conn.commit()
    type_values_count = cursor.execute("SELECT COUNT(*) FROM part_type_values").fetchone()[0]
    print(f"Inserted {insert_count} part tuning values, {type_values_count} part type values")


def process_blueprint_variants(conn: sqlite3.Connection, json_files: List[Path]):
    """Extract tire/LSD blueprint variant names from parsed blueprint JSONs.
    
    Tire variants (BasicTire_45, BasicTire_65) and LSD variants (1WayClutchPackLSD_50)
    are separate blueprint files in the pak. Their names encode tuning parameters
    that appear as suffixes in player part keys.
    """
    cursor = conn.cursor()
    variant_count = 0
    
    ASSET_TYPES = {
        "MTTirePhysicsDataAsset": "TirePhysics",
        "MTLSDDataAsset": "LSD",
    }
    
    for json_file in json_files:
        with open(json_file) as f:
            data = json.load(f)
        
        if data.get("Data", {}).get("Type") != "Blueprint":
            continue
        
        for export in data["Data"].get("Exports", []):
            export_class = export.get("Class", "")
            asset_type = ASSET_TYPES.get(export_class)
            if not asset_type:
                continue
            
            # ExportName is the base name (e.g. 'BasicTire' for BasicTire_65.uasset)
            base_name = export.get("ExportName", "")
            # Source asset filename is the variant name
            source = data.get("SourceAsset", "")
            variant_name = source.replace(".uasset", "")
            
            if base_name and variant_name:
                cursor.execute("""
                    INSERT OR REPLACE INTO blueprint_variants
                    (base_name, variant_name, asset_type)
                    VALUES (?, ?, ?)
                """, (base_name, variant_name, asset_type))
                variant_count += 1
    
    # Supplementary variants: stock tire/LSD values from live game data
    # that are delivered via hotfix patches NOT present in the main pak.
    # These are confirmed stock from observing hundreds of player vehicles.
    SUPPLEMENTARY_VARIANTS = [
        # Tire profile values observed in live data but missing from pak
        ("PerformanceTire", "PerformanceTire_15", "TirePhysics"),
        ("PerformanceTire", "PerformanceTire_25", "TirePhysics"),
        ("PerformanceTire", "PerformanceTire_30", "TirePhysics"),
        ("PerformanceTire", "PerformanceTire_46", "TirePhysics"),
    ]
    for base_name, variant_name, asset_type in SUPPLEMENTARY_VARIANTS:
        cursor.execute("""
            INSERT OR IGNORE INTO blueprint_variants
            (base_name, variant_name, asset_type)
            VALUES (?, ?, ?)
        """, (base_name, variant_name, asset_type))
        variant_count += 1
    
    # Supplementary vehicle_parts: stock parts from game updates not in DataTable.
    # Confirmed stock from observing hundreds of player vehicles.
    SUPPLEMENTARY_PARTS = []
    
    # RideHeight: DataTable has _-10 to _+10, game has up to _-20 / _+20
    for i in range(11, 21):
        SUPPLEMENTARY_PARTS.append((f"RideHeight_+{i}", "Suspension_RideHeight"))
        SUPPLEMENTARY_PARTS.append((f"RideHeight_-{i}", "Suspension_RideHeight"))
    
    # Spring: DataTable has 50-500, game has additional values up to 1000
    for v in [550, 600, 700, 800, 1000]:
        SUPPLEMENTARY_PARTS.append((f"Spring{v}", "Suspension_Spring"))
    
    # FinalDriveRatio: game encodes ratio as FD + str(ratio).replace('.', '_')
    # e.g. ratio 2.5 → FD2_5, ratio 0.55 → FD0_55, ratio 7.0 → FD7_0 or FD_7
    # DataTable RowNames use dot notation (FD_1.33) and are already in the DB.
    # Generate underscore-encoded variants for ratios 0.05 to 25.0 (step 0.05).
    for hundredths in range(5, 2505, 5):
        int_part = hundredths // 100
        frac_part = hundredths % 100
        if frac_part == 0:
            # Integer ratios appear in two formats
            SUPPLEMENTARY_PARTS.append((f"FD{int_part}_0", "FinalDriveRatio"))
            SUPPLEMENTARY_PARTS.append((f"FD_{int_part}", "FinalDriveRatio"))
        else:
            # Fractional: preserve leading zeros, strip trailing
            frac_str = f"{frac_part:02d}".rstrip('0')
            SUPPLEMENTARY_PARTS.append((f"FD{int_part}_{frac_str}", "FinalDriveRatio"))
    
    # Transmission: EF6 with opaque suffix observed in production
    SUPPLEMENTARY_PARTS.append(("EF6_4106", "Transmission"))
    supp_count = 0
    for part_id, part_type in SUPPLEMENTARY_PARTS:
        cursor.execute("""
            INSERT OR IGNORE INTO vehicle_parts (id, part_type)
            VALUES (?, ?)
        """, (part_id, part_type))
        supp_count += 1
    
    conn.commit()
    print(f"Inserted {variant_count} blueprint variants, {supp_count} supplementary parts")


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
                INSERT OR REPLACE INTO cargos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                row.get("PaymentSqrtRatio"),
                row.get("PaymentSqrtRatioMinCapcity"),
                row.get("MaxDamagePaymentMultiplier"),
                row.get("DamageBonusMultiplier"),
                row.get("ManualLoadingPayment"),
                row.get("MinDeliveryDistance"),
                row.get("MaxDeliveryDistance"),
                row.get("bTimer"),
                row.get("BaseTimeSeconds"),
                row.get("TimerBySpeedKPH"),
                row.get("TimerByRoadSpeedLimitRatio"),
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


def process_cargo_bed_specs(conn: sqlite3.Connection, json_files: List[Path]):
    """Process cargo bed parts to extract dimensions and capacity."""
    cursor = conn.cursor()
    
    for json_file in json_files:
        if not json_file.name.startswith("CargoBed") or json_file.name.startswith("CargoBedAttachments"):
            continue
            
        print(f"Processing cargo bed specs from {json_file.name}...")
        with open(json_file) as f:
            data = json.load(f)
        
        if data.get("Data", {}).get("Type") != "DataTable":
            continue
        
        for row in data["Data"]["Rows"]:
            part_id = row["RowName"]
            cargo_bed = row.get("CargoBed", {})
            
            if not cargo_bed:
                continue
            
            # Extract cargo space type
            space_type = strip_enum(cargo_bed.get("CargoSpaceType", ""))
            
            # Extract dimensions (in Unreal units = cm)
            cargo_size = cargo_bed.get("CargoSpaceSize", {})
            size_data = cargo_size.get("CargoSpaceSize", {})
            length_cm = size_data.get("X", 0)
            width_cm = size_data.get("Y", 0)
            height_cm = size_data.get("Z", 0)
            
            # Extract other properties
            dump_volume_kl = cargo_bed.get("DumpVolume", 0)
            fix_cargo = cargo_bed.get("bFixCargo", False)
            unlimited_height = cargo_bed.get("bUnlimitedHeight", False)
            
            cursor.execute("""
                INSERT OR REPLACE INTO cargo_bed_specs VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                part_id,
                space_type,
                length_cm,
                width_cm,
                height_cm,
                dump_volume_kl,
                fix_cargo,
                unlimited_height
            ))
    
    conn.commit()
    print(f"Inserted {cursor.execute('SELECT COUNT(*) FROM cargo_bed_specs').fetchone()[0]} cargo bed specs")


def process_vehicle_weights(conn: sqlite3.Connection, json_files: List[Path]):
    """Process vehicle blueprints to extract chassis mass."""
    cursor = conn.cursor()
    
    # Step 1: Build mapping from vehicle ID to blueprint filename
    print("Building vehicle-to-blueprint mapping...")
    vehicle_blueprint_map = {}  # vehicle_id -> blueprint_filename
    
    for row in cursor.execute("SELECT id, blueprint_path FROM vehicles WHERE blueprint_path IS NOT NULL"):
        vehicle_id, blueprint_path = row
        if blueprint_path:
            # Extract blueprint name from path
            # e.g., /Game/Cars/Models/Tuscan/Tuscan/Tuscan_C -> Tuscan
            parts = blueprint_path.split("/")
            if len(parts) >= 2:
                # Last part before _C is the blueprint name
                blueprint_name = parts[-1].replace("_C", "")
                vehicle_blueprint_map[vehicle_id] = blueprint_name
    
    print(f"Mapped {len(vehicle_blueprint_map)} vehicles to blueprint names")
    
    # Step 2: Build reverse mapping from blueprint filename to vehicle IDs
    blueprint_to_vehicles = {}  # blueprint_filename -> [vehicle_ids]
    for vehicle_id, blueprint_name in vehicle_blueprint_map.items():
        if blueprint_name not in blueprint_to_vehicles:
            blueprint_to_vehicles[blueprint_name] = []
        blueprint_to_vehicles[blueprint_name].append(vehicle_id)
    
    # Step 3: Process blueprint files
    for json_file in json_files:
        if not json_file.name.endswith("_parsed.json"):
            continue
            
        with open(json_file) as f:
            data = json.load(f)
        
        # Only process Blueprint types
        if data.get("Data", {}).get("Type") != "Blueprint":
            continue
        
        # Extract blueprint filename
        blueprint_name = json_file.stem.replace("_parsed", "")
        
        # Find matching vehicle(s) using the mapping
        matching_vehicles = blueprint_to_vehicles.get(blueprint_name, [])
        if not matching_vehicles:
            continue
        
        print(f"Processing vehicle weights from {json_file.name}...")
        
        # Extract all MassInKgOverride values from exports (chassis mass)
        chassis_mass = 0
        
        for export in data["Data"].get("Exports", []):
            props = export.get("Properties", {})
            
            # Check for BodyInstance with mass
            body_instance = props.get("BodyInstance")
            if isinstance(body_instance, dict):
                mass = body_instance.get("MassInKgOverride")
                if mass and mass > 0:
                    chassis_mass += mass
        
        if chassis_mass > 0:
            # Get blueprint path from first export
            blueprint_path = None
            if data["Data"].get("Exports"):
                first_export = data["Data"]["Exports"][0]
                blueprint_path = first_export.get("ExportName")
            
            # Insert weights for all matching vehicles
            for vehicle_id in matching_vehicles:
                cursor.execute("""
                    INSERT OR REPLACE INTO vehicle_weights VALUES (?, ?, ?)
                """, (vehicle_id, chassis_mass, blueprint_path))
    
    conn.commit()
    print(f"Inserted weights for {cursor.execute('SELECT COUNT(*) FROM vehicle_weights').fetchone()[0]} vehicles")


def process_delivery_points(conn: sqlite3.Connection, json_files: List[Path]):
    """Process delivery point blueprints to extract production configurations."""
    cursor = conn.cursor()
    
    for json_file in json_files:
        if not json_file.name.endswith("_parsed.json"):
            continue
            
        with open(json_file) as f:
            data = json.load(f)
        
        # Only process Blueprint types
        if data.get("Data", {}).get("Type") != "Blueprint":
            continue
        
        # Look for DeliveryPoint properties in exports
        for export in data["Data"].get("Exports", []):
            props = export.get("Properties", {})
            
            # Check for MissionPointType (indicates DeliveryPoint)
            mission_point_type = props.get("MissionPointType")
            if not mission_point_type:
                continue
            
            point_id = json_file.stem.replace("_parsed", "")
            
            print(f"Processing delivery point from {json_file.name}...")
            
            # Extract destination types
            dest_types = props.get("DestinationTypes", [])
            dest_types_json = json.dumps([strip_enum(d) for d in dest_types])
            
            cursor.execute("""
                INSERT OR REPLACE INTO delivery_points VALUES (?, ?, ?, ?, ?, ?)
            """, (
                point_id,
                strip_enum(mission_point_type),
                props.get("MaxPassiveDeliveries"),
                dest_types_json,
                export.get("ExportName"),
                json_file.name
            ))
            
            # Process production configs
            for idx, config in enumerate(props.get("ProductionConfigs", [])):
                cursor.execute("""
                    INSERT INTO production_configs 
                    (delivery_point_id, config_index, production_time_seconds, 
                     local_food_supply, production_speed_multiplier, 
                     store_input_cargo, is_hidden)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    point_id, idx,
                    config.get("ProductionTimeSeconds"),
                    config.get("LocalFoodSupply"),
                    config.get("ProductionSpeedMultiplier"),
                    config.get("bStoreInputCargo"),
                    config.get("bHidden")
                ))
                config_id = cursor.lastrowid
                
                # Process input cargos
                input_cargos = config.get("InputCargos", {})
                if isinstance(input_cargos, dict) and input_cargos.get("Entries"):
                    for entry in input_cargos["Entries"]:
                        cursor.execute("""
                            INSERT INTO production_inputs 
                            (production_config_id, cargo_id, quantity)
                            VALUES (?, ?, ?)
                        """, (config_id, entry.get("Key"), entry.get("Value")))
                
                # Process output cargos
                output_cargos = config.get("OutputCargos", {})
                if isinstance(output_cargos, dict) and output_cargos.get("Entries"):
                    for entry in output_cargos["Entries"]:
                        cursor.execute("""
                            INSERT INTO production_outputs 
                            (production_config_id, cargo_id, quantity)
                            VALUES (?, ?, ?)
                        """, (config_id, entry.get("Key"), entry.get("Value")))
    
    conn.commit()
    print(f"Inserted {cursor.execute('SELECT COUNT(*) FROM delivery_points').fetchone()[0]} delivery points")
    print(f"Inserted {cursor.execute('SELECT COUNT(*) FROM production_configs').fetchone()[0]} production configs")


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
    
    # View: vehicles with cargo space dimensions
    cursor.execute("""
        CREATE VIEW IF NOT EXISTS vehicles_with_cargo_space AS
        SELECT 
            v.id,
            v.name,
            v.vehicle_type,
            v.truck_class,
            cbs.cargo_space_type,
            ROUND(cbs.length_cm / 100, 1) as length_m,
            ROUND(cbs.width_cm / 100, 1) as width_m,
            ROUND(cbs.height_cm / 100, 1) as height_m,
            cbs.dump_volume_kl,
            ROUND((cbs.length_cm * cbs.width_cm * cbs.height_cm) / 1000000, 1) as volume_m3,
            cbs.fix_cargo,
            cbs.unlimited_height
        FROM vehicles v
        JOIN vehicle_default_parts vdp ON v.id = vdp.vehicle_id 
            AND vdp.slot LIKE 'CargoBed%'
        JOIN cargo_bed_specs cbs ON vdp.part_id = cbs.part_id
    """)
    
    # View: vehicles with full weight (chassis + default parts)
    cursor.execute("""
        CREATE VIEW IF NOT EXISTS vehicles_with_weight AS
        SELECT 
            v.id,
            v.name,
            v.vehicle_type,
            v.truck_class,
            v.cost,
            COALESCE(vw.chassis_mass_kg, 0) as chassis_mass_kg,
            COALESCE(pw.parts_weight_kg, 0) as parts_weight_kg,
            COALESCE(vw.chassis_mass_kg, 0) + COALESCE(pw.parts_weight_kg, 0) as total_weight_kg,
            COALESCE(pw.part_count, 0) as part_count
        FROM vehicles v
        LEFT JOIN vehicle_weights vw ON v.id = vw.vehicle_id
        LEFT JOIN (
            SELECT 
                vdp.vehicle_id,
                SUM(vp.mass_kg) as parts_weight_kg,
                COUNT(vp.id) as part_count
            FROM vehicle_default_parts vdp
            JOIN vehicle_parts vp ON vdp.part_id = vp.id
            WHERE vp.mass_kg IS NOT NULL AND vp.mass_kg > 0
            GROUP BY vdp.vehicle_id
        ) pw ON v.id = pw.vehicle_id
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
    process_part_tuning(conn, json_files)
    # Include blueprint JSONs from the blueprints/ subdirectory
    bp_dir = out_dir / "blueprints"
    bp_files = sorted(bp_dir.glob("*_parsed.json")) if bp_dir.exists() else []
    process_blueprint_variants(conn, json_files + bp_files)
    process_cargos(conn, json_files)
    
    # Phase 2: Cargo weights and bed specs
    print("\n=== Phase 2: Cargo Weights & Bed Specs ===")
    process_cargo_weights(conn, json_files)
    process_cargo_bed_specs(conn, json_files)
    process_vehicle_weights(conn, json_files)
    process_delivery_points(conn, json_files)
    
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
        ("Part Tuning Values", "SELECT COUNT(*) FROM part_tuning"),
        ("Cargos (Total)", "SELECT COUNT(*) FROM cargos"),
        ("Cargo Weights", "SELECT COUNT(*) FROM cargo_weights"),
        ("Default Parts", "SELECT COUNT(*) FROM vehicle_default_parts"),
        ("Vehicle Tags", "SELECT COUNT(*) FROM vehicle_tags"),
        ("Delivery Points", "SELECT COUNT(*) FROM delivery_points"),
        ("Production Configs", "SELECT COUNT(*) FROM production_configs"),
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
