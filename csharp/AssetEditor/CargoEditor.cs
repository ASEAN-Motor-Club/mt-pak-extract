using System;
using System.Collections.Generic;
using System.Linq;
using UAssetAPI;
using UAssetAPI.ExportTypes;
using UAssetAPI.PropertyTypes.Objects;
using UAssetAPI.PropertyTypes.Structs;
using UAssetAPI.UnrealTypes;

namespace AssetEditor
{
    /// <summary>
    /// Provides methods for editing cargo definitions in the Cargos DataTable.
    /// </summary>
    public static class CargoEditor
    {
        /// <summary>
        /// Add a new cargo to the Cargos DataTable asset.
        /// </summary>
        public static void AddCargo(UAsset asset, CargoConfig config)
        {
            // Find the DataTable export
            var dataTableExport = asset.Exports.OfType<DataTableExport>().FirstOrDefault();
            if (dataTableExport == null)
            {
                throw new InvalidOperationException("No DataTable export found in asset");
            }
            
            // Check if cargo already exists
            if (dataTableExport.Table.Data.Any(row => row.Name.Value.Value == config.CargoId))
            {
                throw new InvalidOperationException($"Cargo '{config.CargoId}' already exists. Use modify-cargo to update it.");
            }
            
            Console.WriteLine($"Adding cargo: {config.CargoId}");
            
            // Create new struct row
            var newRow = new StructPropertyData(FName.FromString(asset, config.CargoId))
            {
                StructType = FName.FromString(asset, "MTCargoRow")
            };
            
            // Build property list
            var properties = new List<PropertyData>();
            
            // String properties
            properties.Add(new StrPropertyData(FName.FromString(asset, "Name")) { Value = FString.FromString(config.Name) });
            properties.Add(new NamePropertyData(FName.FromString(asset, "CargoType")) { Value = FName.FromString(asset, $"EMTCargoType::{config.CargoType}") });
            // TODO: ActorClass requires proper FSoftObjectPath construction - defer to Phase 2
            // properties.Add(new SoftObjectPropertyData(FName.FromString(asset, "ActorClass")) { Value = ... });
            
            // Numeric properties
            properties.Add(new IntPropertyData(FName.FromString(asset, "VolumeSize")) { Value = config.VolumeSize });
            properties.Add(new IntPropertyData(FName.FromString(asset, "PaymentPer1Km")) { Value = config.PaymentPer1Km });
            properties.Add(new FloatPropertyData(FName.FromString(asset, "PaymentPer1KmMultiplierByMaxWeight")) { Value = config.PaymentPer1KmMultiplierByMaxWeight });
            properties.Add(new Int64PropertyData(FName.FromString(asset, "BasePayment")) { Value = config.BasePayment });
            properties.Add(new FloatPropertyData(FName.FromString(asset, "PaymentSqrtRatio")) { Value = config.PaymentSqrtRatio });
            properties.Add(new IntPropertyData(FName.FromString(asset, "PaymentSqrtRatioMinCapcity")) { Value = config.PaymentSqrtRatioMinCapacity });
            properties.Add(new FloatPropertyData(FName.FromString(asset, "MaxDamagePaymentMultiplier")) { Value = config.MaxDamagePaymentMultiplier });
            properties.Add(new FloatPropertyData(FName.FromString(asset, "DamageBonusMultiplier")) { Value = config.DamageBonusMultiplier });
            properties.Add(new IntPropertyData(FName.FromString(asset, "ManualLoadingPayment")) { Value = config.ManualLoadingPayment });
            properties.Add(new IntPropertyData(FName.FromString(asset, "MinDeliveryDistance")) { Value = config.MinDeliveryDistance });
            properties.Add(new IntPropertyData(FName.FromString(asset, "MaxDeliveryDistance")) { Value = config.MaxDeliveryDistance });
            properties.Add(new IntPropertyData(FName.FromString(asset, "BaseTimeSeconds")) { Value = config.BaseTimeSeconds });
            properties.Add(new FloatPropertyData(FName.FromString(asset, "TimerBySpeedKPH")) { Value = config.TimerBySpeedKPH });
            properties.Add(new FloatPropertyData(FName.FromString(asset, "TimerByRoadSpeedLimitRatio")) { Value = config.TimerByRoadSpeedLimitRatio });
            properties.Add(new IntPropertyData(FName.FromString(asset, "Fragile")) { Value = config.Fragile });
            properties.Add(new IntPropertyData(FName.FromString(asset, "SpawnProbability")) { Value = config.SpawnProbability });
            properties.Add(new IntPropertyData(FName.FromString(asset, "NumCargoMin")) { Value = config.NumCargoMin });
            properties.Add(new IntPropertyData(FName.FromString(asset, "NumCargoMax")) { Value = config.NumCargoMax });
            
            // Boolean properties
            properties.Add(new BoolPropertyData(FName.FromString(asset, "bTimer")) { Value = config.HasTimer });
            properties.Add(new BoolPropertyData(FName.FromString(asset, "bAllowStacking")) { Value = config.AllowStacking });
            properties.Add(new BoolPropertyData(FName.FromString(asset, "bUseDamage")) { Value = config.UseDamage });
            properties.Add(new BoolPropertyData(FName.FromString(asset, "bDepcreated")) { Value = config.IsDeprecated });
            
            // Weight range struct
            var weightRangeStruct = new StructPropertyData(FName.FromString(asset, "WeightRange"))
            {
                StructType = FName.FromString(asset, "Vector2D"),
                Value = new List<PropertyData>
                {
                    new Vector2DPropertyData(FName.FromString(asset, "WeightRange")) { Value = new FVector2D(config.WeightRange.Min, config.WeightRange.Max) }
                }
            };
            properties.Add(weightRangeStruct);
            
            // Cargo space types array
            var spaceTypesArray = new ArrayPropertyData(FName.FromString(asset, "CargoSpaceTypes"))
            {
                ArrayType = FName.FromString(asset, "EnumProperty"),
                Value = config.CargoSpaceTypes
                    .Select(type => new EnumPropertyData() { Value = FName.FromString(asset, $"EMTCargoSpaceType::{type}") })
                    .ToArray<PropertyData>()
            };
            properties.Add(spaceTypesArray);
            
            // Assign properties to row
            newRow.Value = properties;
            
            // Add row to table
            dataTableExport.Table.Data.Add(newRow);
            
            Console.WriteLine($"✓ Added cargo '{config.CargoId}' with {properties.Count} properties");
        }
        
        /// <summary>
        /// List all cargos in the DataTable.
        /// </summary>
        public static void ListCargos(UAsset asset)
        {
            var dataTableExport = asset.Exports.OfType<DataTableExport>().FirstOrDefault();
            if (dataTableExport == null)
            {
                throw new InvalidOperationException("No DataTable export found in asset");
            }
            
            Console.WriteLine($"Cargos in DataTable: {dataTableExport.Table.Data.Count}");
            Console.WriteLine();
            
            foreach (var row in dataTableExport.Table.Data)
            {
                var name = row.Value.FirstOrDefault(p => p.Name.Value.Value == "Name") as StrPropertyData;
                var cargoType = row.Value.FirstOrDefault(p => p.Name.Value.Value == "CargoType") as NamePropertyData;
                
                Console.WriteLine($"  - {row.Name.Value.Value}");
                if (name != null) Console.WriteLine($"      Name: {name.Value}");
                if (cargoType != null) Console.WriteLine($"      Type: {cargoType.Value?.Value?.Value}");
            }
        }
    }
}
