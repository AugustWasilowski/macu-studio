#!/usr/bin/env python3
"""Render the 11 missing masters: 8 characters + 3 broll. zeroscope @ 384x384x24f.
Skip safe (have safe_master) and empty_room (have c09_s1 from slice)."""
import json, time, urllib.request, random

COMFY = "http://10.0.0.245:8188"
W, H, FRAMES, STEPS, CFG = 384, 384, 24, 30, 15.0

STYLE_SUFFIX = (
    ", black and white, grainy vintage analog television footage, 1970s broadcast, "
    "retro futurism, low resolution, washed out, soft focus"
)
NEGATIVE = (
    "shutterstock, watermark, text, caption, logo, color, colour, modern, "
    "smartphone, digital screen, hd, 4k, sharp, blurry, low quality, distorted, "
    "deformed, mutated, extra limbs, extra fingers"
)

MANIFEST = "/mnt/storage/shares/MACU/episodes/ep5/manifest.json"
with open(MANIFEST) as f:
    m = json.load(f)

# Characters we need (skip safe — have safe_master)
SKIP_CHARS = {"safe"}
SKIP_BROLL = {"empty_room"}  # c09_s1 already on disk

JOBS = []
for name, c in m["characters"].items():
    if name in SKIP_CHARS: continue
    JOBS.append({"key": name, "kind": "char", "prefix": f"macu/ep5/{name}_master",
                 "prompt_core": c["core"], "seed": c["seed"]})
for name, core in m["broll"].items():
    if name in SKIP_BROLL: continue
    JOBS.append({"key": name, "kind": "broll", "prefix": f"macu/ep5/broll_{name}",
                 "prompt_core": core, "seed": random.randrange(2**32)})

print(f"queuing {len(JOBS)} jobs:")
for j in JOBS:
    print(f"  {j['kind']:5} {j['key']:14} seed={j['seed']}")

def build(prompt, seed, prefix):
    return {
        "1": {"class_type":"ModelScopeT2VLoader","inputs":{
            "model_path":"text2video_pytorch_model.pth",
            "enable_attn":True,"enable_conv":True,
            "temporal_attn_strength":1.0,"temporal_conv_strength":1.0}},
        "2": {"class_type":"ModelScopeCLIPLoader","inputs":{"clip_name":"open_clip_pytorch_model.bin"}},
        "3": {"class_type":"VAELoader","inputs":{"vae_name":"vae-ft-mse-840000-ema-pruned.safetensors"}},
        "4": {"class_type":"CLIPTextEncode","inputs":{"text":prompt,"clip":["2",0]}},
        "5": {"class_type":"CLIPTextEncode","inputs":{"text":NEGATIVE,"clip":["2",0]}},
        "6": {"class_type":"EmptyLatentImage","inputs":{"width":W,"height":H,"batch_size":FRAMES}},
        "7": {"class_type":"KSampler","inputs":{
            "seed":seed,"steps":STEPS,"cfg":CFG,
            "sampler_name":"euler","scheduler":"normal","denoise":1.0,
            "model":["1",0],"positive":["4",0],"negative":["5",0],"latent_image":["6",0]}},
        "8": {"class_type":"VAEDecode","inputs":{"samples":["7",0],"vae":["3",0]}},
        "9": {"class_type":"SaveAnimatedWEBP","inputs":{
            "images":["8",0],"filename_prefix":prefix,
            "fps":8.0,"lossless":False,"quality":80,"method":"default"}},
    }

def post(p,b):
    r = urllib.request.Request(f"{COMFY}{p}", data=json.dumps(b).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())

def get(p):
    with urllib.request.urlopen(f"{COMFY}{p}", timeout=30) as r:
        return json.loads(r.read())

start = time.time()
for j in JOBS:
    full = j["prompt_core"] + STYLE_SUFFIX
    g = build(full, j["seed"], j["prefix"])
    r = post("/prompt", {"prompt": g, "client_id":"ssa87-full"})
    j["pid"] = r["prompt_id"]
    print(f"queued {j['prefix']} pid={j['pid']}", flush=True)

done = {}
while len(done) < len(JOBS) and time.time()-start < 40*60:
    time.sleep(6)
    for j in JOBS:
        if j["pid"] in done: continue
        try: hist = get(f"/history/{j['pid']}")
        except: continue
        e = hist.get(j["pid"])
        if not e: continue
        st = e.get("status",{})
        if st.get("completed"):
            files = e.get("outputs",{}).get("9",{}).get("images",[]) or e.get("outputs",{}).get("9",{}).get("gifs",[])
            done[j["pid"]] = {**j, "files": files, "elapsed_s": round(time.time()-start,1)}
            print(f"done {j['key']:14} ({len(done)}/{len(JOBS)}) +{done[j['pid']]['elapsed_s']}s", flush=True)
        elif st.get("status_str") == "error":
            done[j["pid"]] = {**j, "error": st}
            print(f"ERROR {j['key']}: {st}", flush=True)

out = {"jobs": list(done.values()), "total_elapsed_s": round(time.time()-start,1)}
with open("/tmp/masters_results.json","w") as f:
    json.dump(out, f, indent=2)
print(f"\nWrote /tmp/masters_results.json")
