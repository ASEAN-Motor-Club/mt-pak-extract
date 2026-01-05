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
    /// Provides methods for editing production configurations in factory blueprints.
    /// </summary>
    public static class ProductionEditor
    {
        /// <summary>
        /// Add production configurations to a factory blueprint.
        /// Uses clone-and-modify approach for reliability.
        /// </summary>
        public static void AddProductionConfigs(UAsset asset, ProductionConfig config)
        {
            // Find the Default__*_C export (CDO - Class Default Object)
            var cdoExport = asset.Exports
                .OfType<NormalExport>()
                .FirstOrDefault(e => e.ObjectName.Value.Value.StartsWith("Default__"));
            
            if (cdoExport == null)
            {
                throw new InvalidOperationException("No Default export found in blueprint");
            }
            
            Console.WriteLine($"Found CDO: {cdoExport.ObjectName.Value.Value}");
            
            // Find existing ProductionConfigs array
            var productionConfigsProp = cdoExport.Data
                .FirstOrDefault(p => p.Name.Value.Value == "ProductionConfigs") as ArrayPropertyData;
            
            if (productionConfigsProp == null || productionConfigsProp.Value.Length == 0)
            {
                throw new InvalidOperationException("No existing ProductionConfigs found to clone. Asset must have at least one config.");
            }
            
            Console.WriteLine($"Current production configs: {productionConfigsProp.Value.Length}");
            
            // Clone the first existing config as template
            var templateConfig = productionConfigsProp.Value[0] as StructPropertyData;
            if (templateConfig == null)
            {
                throw new InvalidOperationException("Failed to access template production config");
            }
            
            // Convert existing array to list for modification
            var configsList = productionConfigsProp.Value.ToList();
            
            // Add each new recipe by cloning template and modifying
            foreach (var recipe in config.ProductionConfigs)
            {
                var newConfig = (StructPropertyData)templateConfig.Clone();
                ModifyProductionConfig(asset, newConfig, recipe);
                configsList.Add(newConfig);
                
                var inputStr = string.Join(", ", recipe.Inputs.Select(kv => $"{kv.Key}:{kv.Value}"));
                var outputStr = string.Join(", ", recipe.Outputs.Select(kv => $"{kv.Key}:{kv.Value}"));
                Console.WriteLine($"✓ Added recipe: [{inputStr}] -> [{outputStr}] ({recipe.TimeSeconds}s)");
            }
            
            // Update array
            productionConfigsProp.Value = configsList.ToArray();
            Console.WriteLine($"Total production configs: {configsList.Count}");
        }
        
        private static void ModifyProductionConfig(UAsset asset, StructPropertyData config, ProductionRecipe recipe)
        {
            var props = config.Value as List<PropertyData>;
            if (props == null) return;
            
            // Update InputCargos map
            var inputCargos = props.FirstOrDefault(p => p.Name.Value.Value == "InputCargos") as MapPropertyData;
            if (inputCargos != null)
            {
                inputCargos.Value.Clear();
                foreach (var cargo in recipe.Inputs)
                {
                    var key = new NamePropertyData() { Value = FName.FromString(asset, cargo.Key) };
                    var value = new IntPropertyData() { Value = cargo.Value };
                    inputCargos.Value[key] = value;
                }
            }
            
            // Update OutputCargos map
            var outputCargos = props.FirstOrDefault(p => p.Name.Value.Value == "OutputCargos") as MapPropertyData;
            if (outputCargos != null)
            {
                outputCargos.Value.Clear();
                foreach (var cargo in recipe.Outputs)
                {
                    var key = new NamePropertyData() { Value = FName.FromString(asset, cargo.Key) };
                    var value = new IntPropertyData() { Value = cargo.Value };
                    outputCargos.Value[key] = value;
                }
            }
            
            // Update numeric properties
            SetIntProperty(props, "ProductionTimeSeconds", recipe.TimeSeconds);
            SetFloatProperty(props, "LocalFoodSupply", recipe.LocalFoodSupply);
            SetFloatProperty(props, "ProductionSpeedMultiplier", recipe.SpeedMultiplier);
            
            // Update boolean properties
            SetBoolProperty(props, "bStoreInputCargo", recipe.StoreInputCargo);
            SetBoolProperty(props, "bHidden", recipe.IsHidden);
        }
        
        private static void SetIntProperty(List<PropertyData> props, string name, int value)
        {
            var prop = props.FirstOrDefault(p => p.Name.Value.Value == name) as IntPropertyData;
            if (prop != null) prop.Value = value;
        }
        
        private static void SetFloatProperty(List<PropertyData> props, string name, float value)
        {
            var prop = props.FirstOrDefault(p => p.Name.Value.Value == name) as FloatPropertyData;
            if (prop != null) prop.Value = value;
        }
        
        private static void SetBoolProperty(List<PropertyData> props, string name, bool value)
        {
            var prop = props.FirstOrDefault(p => p.Name.Value.Value == name) as BoolPropertyData;
            if (prop != null) prop.Value = value;
        }
        
        private static StructPropertyData BuildProductionConfigStruct(UAsset asset, ProductionRecipe recipe)
        {
            // Array items don't need a property name - use the struct name instead
            var configStruct = new StructPropertyData()
            {
                StructType = FName.FromString(asset, "MTProductionConfig"),
                Value = new List<PropertyData>()
            };
            
            var properties = (List<PropertyData>)configStruct.Value;
            
            // InputCargos map
            properties.Add(BuildCargoMap(asset, "InputCargos", recipe.Inputs));
            
            // OutputCargos map
            properties.Add(BuildCargoMap(asset, "OutputCargos", recipe.Outputs));
            
            // InputCargoTypes (empty map)
            properties.Add(new MapPropertyData(FName.FromString(asset, "InputCargoTypes"))
            {
                KeyType = FName.FromString(asset, "EnumProperty"),
                ValueType = FName.FromString(asset, "IntProperty"),
                Value = new TMap<PropertyData, PropertyData>()
            });
            
            // OutputCargoTypes (empty map)
            properties.Add(new MapPropertyData(FName.FromString(asset, "OutputCargoTypes"))
            {
                KeyType = FName.FromString(asset, "EnumProperty"),
                ValueType = FName.FromString(asset, "IntProperty"),
                Value = new TMap<PropertyData, PropertyData>()
            });
            
            // Empty GameplayTagQuery structs
            properties.Add(BuildEmptyGameplayTagQuery(asset, "InputCargoGameplayTagQuery"));
            properties.Add(BuildEmptyGameplayTagQuery(asset, "OutputCargoRowGameplayTagQuery"));
            
            // Numeric properties
            properties.Add(new IntPropertyData(FName.FromString(asset, "ProductionTimeSeconds")) { Value = recipe.TimeSeconds });
            properties.Add(new FloatPropertyData(FName.FromString(asset, "LocalFoodSupply")) { Value = recipe.LocalFoodSupply });
            properties.Add(new FloatPropertyData(FName.FromString(asset, "ProductionSpeedMultiplier")) { Value = recipe.SpeedMultiplier });
            
            // Boolean properties
            properties.Add(new BoolPropertyData(FName.FromString(asset, "bStoreInputCargo")) { Value = recipe.StoreInputCargo });
            properties.Add(new BoolPropertyData(FName.FromString(asset, "bHidden")) { Value = recipe.IsHidden });
            
            return configStruct;
        }
        
        private static MapPropertyData BuildCargoMap(UAsset asset, string propertyName, Dictionary<string, int> cargos)
        {
            var map = new MapPropertyData(FName.FromString(asset, propertyName))
            {
                KeyType = FName.FromString(asset, "NameProperty"),
                ValueType = FName.FromString(asset, "IntProperty"),
                Value = new TMap<PropertyData, PropertyData>()
            };
            
            foreach (var cargo in cargos)
            {
                // Map entries don't need a property name - use the key/value directly
                var key = new NamePropertyData() { Value = FName.FromString(asset, cargo.Key) };
                var value = new IntPropertyData() { Value = cargo.Value };
                map.Value[key] = value;
            }
            
            return map;
        }
        
        private static StructPropertyData BuildEmptyGameplayTagQuery(UAsset asset, string propertyName)
        {
            return new StructPropertyData(FName.FromString(asset, propertyName))
            {
                StructType = FName.FromString(asset, "GameplayTagQuery"),
                Value = new List<PropertyData>
                {
                    new BytePropertyData(FName.FromString(asset, "TokenStreamVersion")) { Value = 0 },
                    new ArrayPropertyData(FName.FromString(asset, "TagDictionary"))
                    {
                        ArrayType = FName.FromString(asset, "NameProperty"),
                        Value = new PropertyData[0]
                    },
                    new ArrayPropertyData(FName.FromString(asset, "QueryTokenStream"))
                    {
                        ArrayType = FName.FromString(asset, "ByteProperty"),
                        Value = new PropertyData[0]
                    },
                    new TextPropertyData(FName.FromString(asset, "UserDescription")) { Value = null },
                    new TextPropertyData(FName.FromString(asset, "AutoDescription")) { Value = null }
                }
            };
        }
        
        /// <summary>
        /// List all production configs in a factory blueprint.
        /// </summary>
        public static void ListProductionConfigs(UAsset asset)
        {
            var cdoExport = asset.Exports
                .OfType<NormalExport>()
                .FirstOrDefault(e => e.ObjectName.Value.Value.StartsWith("Default__"));
            
            if (cdoExport == null)
            {
                Console.WriteLine("No Default export found");
                return;
            }
            
            var configsProp = cdoExport.Data
                .FirstOrDefault(p => p.Name.Value.Value == "ProductionConfigs") as ArrayPropertyData;
            
            if (configsProp == null)
            {
                Console.WriteLine("No ProductionConfigs found");
                return;
            }
            
            Console.WriteLine($"Production Configs: {configsProp.Value.Length}");
            Console.WriteLine();
            
            for (int i = 0; i < configsProp.Value.Length; i++)
            {
                var config = configsProp.Value[i] as StructPropertyData;
                if (config == null) continue;
                
                Console.WriteLine($"Config {i + 1}:");
                
                // Extract inputs
                var inputs = GetCargoMap(config, "InputCargos");
                if (inputs.Any())
                    Console.WriteLine($"  Inputs: {string.Join(", ", inputs.Select(kv => $"{kv.Key}:{kv.Value}"))}");
                
                // Extract outputs
                var outputs = GetCargoMap(config, "OutputCargos");
                if (outputs.Any())
                    Console.WriteLine($"  Outputs: {string.Join(", ", outputs.Select(kv => $"{kv.Key}:{kv.Value}"))}");
                
                // Time
                var time = GetIntProperty(config, "ProductionTimeSeconds");
                if (time.HasValue)
                    Console.WriteLine($"  Time: {time}s");
                
                Console.WriteLine();
            }
        }
        
        private static Dictionary<string, int> GetCargoMap(StructPropertyData config, string mapName)
        {
            var result = new Dictionary<string, int>();
            var props = config.Value as List<PropertyData>;
            if (props == null) return result;
            
            var mapProp = props.FirstOrDefault(p => p.Name.Value.Value == mapName) as MapPropertyData;
            if (mapProp == null) return result;
            
            foreach (var entry in mapProp.Value)
            {
                var keyName = (entry.Key as NamePropertyData)?.Value?.Value?.Value;
                var valueInt = (entry.Value as IntPropertyData)?.Value;
                
                if (keyName != null && valueInt.HasValue)
                    result[keyName] = valueInt.Value;
            }
            
            return result;
        }
        
        private static int? GetIntProperty(StructPropertyData config, string propName)
        {
            var props = config.Value as List<PropertyData>;
            return (props?.FirstOrDefault(p => p.Name.Value.Value == propName) as IntPropertyData)?.Value;
        }
    }
}
