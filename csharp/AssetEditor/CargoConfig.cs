using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace AssetEditor
{
    /// <summary>
    /// Represents a cargo definition with all 29+ fields from the Cargos DataTable.
    /// </summary>
    public class CargoConfig
    {
        // Primary identity
        public string CargoId { get; set; } = "";
        public string Name { get; set; } = "";
        
        // Type and classification
        public string CargoType { get; set; } = "Regular";
        public int VolumeSize { get; set; } = 1;
        
        // Weight
        public WeightRange WeightRange { get; set; } = new();
        
        // Payment
        public int PaymentPer1Km { get; set; } = 0;
        public float PaymentPer1KmMultiplierByMaxWeight { get; set; } = 1.0f;
        public int BasePayment { get; set; } = 0;
        public float PaymentSqrtRatio { get; set; } = 0;
        public int PaymentSqrtRatioMinCapacity { get; set; } = 0;
        public float MaxDamagePaymentMultiplier { get; set; } = 0.9f;
        public float DamageBonusMultiplier { get; set; } = 0;
        public int ManualLoadingPayment { get; set; } = 0;
        
        // Delivery constraints
        public int MinDeliveryDistance { get; set; } = 0;
        public int MaxDeliveryDistance { get; set; } = 0;
        
        // Timer
        public bool HasTimer { get; set; } = false;
        public int BaseTimeSeconds { get; set; } = 0;
        public float TimerBySpeedKPH { get; set; } = 0;
        public float TimerByRoadSpeedLimitRatio { get; set; } = 0;
        
        // Actor references
        public string ActorClass { get; set; } = "";
        
        // Cargo space types
        public List<string> CargoSpaceTypes { get; set; } = new();
        
        // Behavior flags
        public bool AllowStacking { get; set; } = false;
        public bool UseDamage { get; set; } = false;
        public int Fragile { get; set; } = 0;
        
        // Spawning
        public int SpawnProbability { get; set; } = 100;
        public int NumCargoMin { get; set; } = 1;
        public int NumCargoMax { get; set; } = 1;
        
        // Status
        public bool IsDeprecated { get; set; } = false;
        
        /// <summary>
        /// Load from YAML file
        /// </summary>
        public static CargoConfig LoadFromYaml(string path)
        {
            var deserializer = new DeserializerBuilder()
                .WithNamingConvention(PascalCaseNamingConvention.Instance)
                .Build();
            
            var yaml = File.ReadAllText(path);
            return deserializer.Deserialize<CargoConfig>(yaml);
        }
        
        /// <summary>
        /// Save to YAML file (for reference/templates)
        /// </summary>
        public void SaveToYaml(string path)
        {
            var serializer = new SerializerBuilder()
                .WithNamingConvention(PascalCaseNamingConvention.Instance)
                .Build();
            
            var yaml = serializer.Serialize(this);
            File.WriteAllText(path, yaml);
        }
    }
    
    public class WeightRange
    {
        public float Min { get; set; } = 0;
        public float Max { get; set; } = 0;
    }
}
