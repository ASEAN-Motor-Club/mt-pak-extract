# Custom Model Workflow for MotorTown Cargo

The current toolchain (UAssetAPI + repak) allows **editing existing assets** but not **creating new 3D models or blueprints**. Here's the workflow for custom cargo models:

## Option 1: Reuse Existing Blueprints (Recommended)

**Simplest approach** - Reference an existing cargo blueprint:

```yaml
ActorClass: /Game/Objects/Mission/Delivery/CheeseBox/CheeseBox
```

**Available blueprints** (from existing cargo data):
- `CheeseBox`, `CheesePallet` - Dairy products
- `BottleBox`, `BottlePallete` - Bottled goods
- `OrangeBox`, `AppleBox`, `CarrotBox` - Produce
- `SmallBox`, `BoxPallete_01/02/03` - Generic boxes
- `GroceryBox`, `GroceryBag` - Food items
- `Container_20ft/30ft/40ft` - Shipping containers

This approach works immediately with no additional tools.

---

## Option 2: Create Custom Blueprint (Advanced)

To create a **fully custom** cargo model (ButterBox with butter branding):

### Requirements
1. **Unreal Engine 5.5** (same version as MotorTown)
2. **3D modeling software** (Blender, Maya, etc.)
3. **MotorTown SDK/modding kit** (if available from developers)

### Workflow
```
1. Model the cargo in Blender
   └─> Export as FBX

2. Import FBX into Unreal Engine 5.5 project
   └─> Create StaticMesh asset

3. Create Blueprint actor
   ├─> Add StaticMeshComponent
   ├─> Set collision (for physics)
   ├─> Add BodyInstance (mass properties)
   └─> Save as /Game/Mods/ButterBox/ButterBox.uasset

4. Extract the .uasset/.uexp using repak

5. Reference in cargo config:
   ActorClass: /Game/Mods/ButterBox/ButterBox

6. Repack all modified assets into mod PAK
```

### Challenges
- **No modding SDK**: MotorTown may not have official UE5 project/SDK for modders
- **Reverse engineering**: Would need to recreate project structure
- **Collision/physics**: Blueprint must match game's cargo handling system
- **Performance**: Custom models need LODs, proper collision meshes

---

## Option 3: Hybrid Approach (Practical)

**Reuse blueprint structure**, modify materials only:

1. Extract existing `CheeseBox.uasset` blueprint
2. Copy to `ButterBox.uasset`
3. In UE5, swap material references to butter-themed textures
4. Export and repack

This requires UE5 but avoids full 3D modeling.

---

## Recommendation

For **initial modding**:
- ✅ Use existing blueprints (CheeseBox works great for Butter)
- ✅ Focus on gameplay (production configs, pricing, delivery) 
- ❌ Defer custom models until official modding support

The gameplay impact of custom production chains (Butter from Milk) is **much more significant** than visual differences between CheeseBox and a hypothetical ButterBox.

---

## Future: Blueprint Cloning

A future enhancement to this toolchain could add:
```csharp
BlueprintEditor.CloneCargo(
    source: "CheeseBox",
    target: "ButterBox", 
    nameSuffix: "_Butter"
);
```

This would copy the blueprint structure without needing UE5, but material/mesh references would still point to cheese assets.
