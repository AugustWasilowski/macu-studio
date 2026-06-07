#!/usr/bin/env python3
"""Stage 2: render ComfyUI master clips, one per unique (character|broll) key.

Idempotent: looks for the staged .zs.webp in clips/; if present, skips that key.
Usage: python3 stage_2_masters.py <slug>
"""
import sys, os, json, time, urllib.request, random, glob, shutil
sys.path.insert(0, os.path.dirname(__file__))
from lib import (episode_paths, load_manifest, ensure_dirs, COMFY_URL,
                 COMFY_OUT, COMFY_OUTPUT_ROOT, staged_master_webp, progress_tick)

STYLE_NEG_FALLBACK = (
    "shutterstock, watermark, text, caption, logo, color, colour, modern, "
    "smartphone, digital screen, hd, 4k, sharp, blurry, low quality, distorted, "
    "deformed, mutated, extra limbs, extra fingers"
)

def build_graph(prompt, negative, seed, prefix, w, h, frames, steps, cfg):
    return {
        "1": {"class_type":"ModelScopeT2VLoader","inputs":{
            "model_path":"text2video_pytorch_model.pth",
            "enable_attn":True,"enable_conv":True,
            "temporal_attn_strength":1.0,"temporal_conv_strength":1.0}},
        "2": {"class_type":"ModelScopeCLIPLoader","inputs":{"clip_name":"open_clip_pytorch_model.bin"}},
        "3": {"class_type":"VAELoader","inputs":{"vae_name":"vae-ft-mse-840000-ema-pruned.safetensors"}},
        "4": {"class_type":"CLIPTextEncode","inputs":{"text":prompt,"clip":["2",0]}},
        "5": {"class_type":"CLIPTextEncode","inputs":{"text":negative,"clip":["2",0]}},
        "6": {"class_type":"EmptyLatentImage","inputs":{"width":w,"height":h,"batch_size":frames}},
        "7": {"class_type":"KSampler","inputs":{
            "seed":seed,"steps":steps,"cfg":cfg,
            "sampler_name":"euler","scheduler":"normal","denoise":1.0,
            "model":["1",0],"positive":["4",0],"negative":["5",0],"latent_image":["6",0]}},
        "8": {"class_type":"VAEDecode","inputs":{"samples":["7",0],"vae":["3",0]}},
        "9": {"class_type":"SaveAnimatedWEBP","inputs":{
            "images":["8",0],"filename_prefix":prefix,
            "fps":8.0,"lossless":False,"quality":80,"method":"default"}},
    }

def post(path, body):
    r = urllib.request.Request(f"{COMFY_URL}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())

def get(path):
    with urllib.request.urlopen(f"{COMFY_URL}{path}", timeout=30) as r:
        return json.loads(r.read())

def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    style_suffix = m["style"]["suffix"]
    negative = m["style"].get("negative", STYLE_NEG_FALLBACK)
    cfg = m["comfyui"]
    W, H, FRAMES = cfg["width"], cfg["height"], cfg["frames"]
    STEPS, CFG = cfg["steps"], cfg["cfg"]

    # Discover unique (kind, key) from cues' shots
    unique = []
    seen = set()
    for cue in m["cues"]:
        for shot in cue["shots"]:
            if shot.get("kind") in ("character","broll"):
                k = (shot["kind"], shot["who"])
                if k not in seen:
                    seen.add(k); unique.append(k)

    jobs = []
    skipped = 0
    seed_updates = {}  # broll key -> {prompt, seed} for seeds we assign here (persist for determinism)
    for kind, key in unique:
        target = staged_master_webp(slug, key, kind)
        if os.path.exists(target):
            skipped += 1
            continue
        # Build prompt + seed
        if kind == "character":
            char = m["characters"][key]
            prompt = char["core"] + style_suffix
            seed = char["seed"]
            comfy_prefix = f"macu/{slug}/{key}_master"
        else:  # broll — value is a plain prompt string OR {"prompt", "seed"}
            bro = m["broll"][key]
            if isinstance(bro, dict):
                core = bro.get("prompt") or ""
                prompt = core + style_suffix
                seed = bro.get("seed")
                if seed is None:
                    seed = random.randint(1000, 9999)
                    seed_updates[key] = {"prompt": core, "seed": seed}
            else:
                prompt = bro + style_suffix
                seed = random.randint(1000, 9999)
                # Promote the plain-string broll to {prompt, seed} so this render is reproducible.
                seed_updates[key] = {"prompt": bro, "seed": seed}
            comfy_prefix = f"macu/{slug}/broll_{key}"
        jobs.append({"kind": kind, "key": key, "prompt": prompt, "seed": seed,
                     "prefix": comfy_prefix, "target": target})

    # Persist any seeds we just minted so re-renders (and cross-episode pulls) are
    # deterministic. We never back-populate old data — only seeds assigned this run.
    if seed_updates:
        for key, val in seed_updates.items():
            m["broll"][key] = val
        mpath = episode_paths(slug)["manifest"]
        tmp = mpath + ".tmp"
        with open(tmp, "w") as f:
            json.dump(m, f, indent=2, ensure_ascii=False)
        os.replace(tmp, mpath)
        print(f"[stage 2 masters] saved {len(seed_updates)} new broll seed(s): {', '.join(seed_updates)}")

    print(f"[stage 2 masters] {len(jobs)} to render, {skipped} cached")
    if not jobs:
        return {"rendered": 0, "skipped": skipped}

    start = time.time()
    for j in jobs:
        g = build_graph(j["prompt"], negative, j["seed"], j["prefix"], W, H, FRAMES, STEPS, CFG)
        try:
            resp = post("/prompt", {"prompt": g, "client_id": f"macu-{slug}"})
            j["pid"] = resp["prompt_id"]
        except Exception as e:
            # First gen may cold-load + time out the request but keep running.
            print(f"  WARN submit {j['key']}: {e}")
            j["pid"] = None
        print(f"  queued {j['key']:24} (kind={j['kind']}, seed={j['seed']}) pid={j.get('pid')}")

    # Watchdog: a crashed/restarted ComfyUI drops our queued prompts (queue goes empty)
    # and /history never reports them — the old loop then polled idle for the full hour
    # while holding the render lock. STALL_S bails early when ComfyUI is idle (empty
    # queue) AND nothing has completed for that long; a slow-but-progressing render keeps
    # resetting the clock (queue still busy), so only genuine stalls trip it. HARD_S is
    # the absolute ceiling regardless.
    STALL_S = 300
    HARD_S = 60 * 60

    def comfy_busy() -> bool:
        try:
            q = get("/queue")
            return bool(q.get("queue_running") or q.get("queue_pending"))
        except Exception:
            return False  # unreachable ComfyUI counts as not-busy → stall clock advances

    done = set()
    last_progress = time.time()
    while len(done) < len(jobs) and time.time() - start < HARD_S:
        time.sleep(6)
        before = len(done)
        for j in jobs:
            if j["key"] in done:
                continue
            if j.get("pid"):
                try:
                    hist = get(f"/history/{j['pid']}")
                except Exception:
                    continue
                e = hist.get(j["pid"])
                if e and e.get("status", {}).get("completed"):
                    files = (e.get("outputs", {}).get("9", {}).get("images")
                             or e.get("outputs", {}).get("9", {}).get("gifs") or [])
                    if files:
                        src = os.path.join(COMFY_OUT, slug, files[0]["filename"])
                        if not os.path.exists(src):
                            # ComfyUI puts it under output/<subfolder>/<filename>
                            src = os.path.join(COMFY_OUTPUT_ROOT,
                                                files[0]["subfolder"], files[0]["filename"])
                        shutil.copy2(src, j["target"])
                        done.add(j["key"])
                        print(f"  done {j['key']:24} +{round(time.time()-start,1)}s -> {j['target']}")
                        progress_tick(2, "masters", len(done) / len(jobs))
            else:
                # PID submission failed but cold-load probably still ran. Look for the file by prefix.
                pattern = "{}/{}/{}*.webp".format(COMFY_OUT, slug, os.path.basename(j["prefix"]))
                matches = sorted(glob.glob(pattern))
                if matches:
                    shutil.copy2(matches[-1], j["target"])
                    done.add(j["key"])
                    print(f"  done {j['key']:24} (recovered cold-load) -> {j['target']}")
                    progress_tick(2, "masters", len(done) / len(jobs))

        # Stall detection: reset the clock on any completion or while ComfyUI is working;
        # otherwise fail fast so the render lock isn't held by a dead ComfyUI.
        if len(done) > before or comfy_busy():
            last_progress = time.time()
        else:
            idle = time.time() - last_progress
            if idle > STALL_S:
                missing = [j["key"] for j in jobs if j["key"] not in done]
                raise RuntimeError(
                    f"[stage 2 masters] stalled — ComfyUI idle (empty queue) with no "
                    f"completions for {int(idle/60)}m; it likely crashed or was restarted. "
                    f"{len(done)}/{len(jobs)} done, missing: {missing}")
            print(f"  …waiting on ComfyUI — {len(done)}/{len(jobs)} done, "
                  f"idle {int(idle)}s/{STALL_S}s")

    if len(done) < len(jobs):
        missing = [j["key"] for j in jobs if j["key"] not in done]
        raise RuntimeError(f"[stage 2 masters] timeout after {int((time.time()-start)/60)}m, missing: {missing}")

    return {"rendered": len(jobs), "skipped": skipped,
            "wall_s": round(time.time()-start, 2)}

if __name__ == "__main__":
    main(sys.argv[1])
