using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace AssetEditor
{
    /// <summary>
    /// Represents production configuration for a factory delivery point.
    /// </summary>
    public class ProductionConfig
    {
        public string FactoryBlueprint { get; set; } = "";
        public List<ProductionRecipe> ProductionConfigs { get; set; } = new();
        
        /// <summary>
        /// Load from YAML file
        /// </summary>
        public static ProductionConfig LoadFromYaml(string path)
        {
            var deserializer = new DeserializerBuilder()
                .WithNamingConvention(PascalCaseNamingConvention.Instance)
                .Build();
            
            var yaml = File.ReadAllText(path);
            return deserializer.Deserialize<ProductionConfig>(yaml);
        }
    }
    
    public class ProductionRecipe
    {
        public Dictionary<string, int> Inputs { get; set; } = new();
        public Dictionary<string, int> Outputs { get; set; } = new();
        public int TimeSeconds { get; set; } = 10;
        public float SpeedMultiplier { get; set; } = 1.0f;
        public float LocalFoodSupply { get; set; } = 0;
        public bool StoreInputCargo { get; set; } = false;
        public bool IsHidden { get; set; } = false;
    }
}
