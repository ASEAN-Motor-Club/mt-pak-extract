import unreal, json, os
out=r'C:\Users\freeman\masked_png'
os.makedirs(out,exist_ok=True)
entries=json.load(open(r'C:\Users\freeman\masked_entries.json'))
for e in entries:
    name=e['instance'].rsplit('/',1)[-1].replace('MI_C1_','')
    for kind,key in [('base','base'),('emis','emissive')]:
        tp=e[key]
        if kind=='emis' and tp==e['base']: continue
        t=unreal.load_asset(tp)
        if t is None:
            print('MISSING',name,kind,tp,flush=True); continue
        unreal.AssetToolsHelpers.get_asset_tools().export_assets([tp],out)
    print('EXPORTED',name,flush=True)
print('PNG_EXPORT_DONE',flush=True)
