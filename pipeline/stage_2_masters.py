#!/usr/bin/env python3
"""Stage 2: render ComfyUI master clips, one per unique (character|broll) key.

Idempotent: looks for the staged .zs.webp in clips/; if present, skips that key.
Usage: python3 stage_2_masters.py <slug>
"""
import sys, os, json, time, threading, urllib.request, urllib.error, urllib.parse, random, glob, shutil, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from lib import (episode_paths, load_manifest, ensure_dirs, COMFY_URL,
                 COMFY_OUT, COMFY_OUTPUT_ROOT, staged_master_webp, progress_tick)

# Masters backend selector. Episodes default to zeroscope text-to-video; an episode
# whose comfyui.workflow names a WAN i2v graph renders its CHARACTER shots image-to-
# video, seeded from stills/<key>.png (b-roll stays t2v). See plan: WAN i2v masters.
WAN_I2V_WORKFLOW = "wan21_i2v"


def _masters_backend(m):
    return "wan_i2v" if (m.get("comfyui") or {}).get("workflow") == WAN_I2V_WORKFLOW else "zeroscope"


# WAN i2v master clips are cached by a sidecar hash (not just file existence) so a
# changed seed still / prompt / seed re-renders — mirrors vo/.cache.json + .hf_cache.json.
MASTERS_CACHE = ".masters_cache.json"


def _masters_cache_path(clips_dir):
    return os.path.join(clips_dir, MASTERS_CACHE)


def _load_masters_cache(clips_dir):
    try:
        d = json.loads(Path(_masters_cache_path(clips_dir)).read_text())
        return dict(d.get("masters") or {}) if d.get("version") == 1 else {}
    except Exception:
        return {}


def _save_masters_cache(clips_dir, entries):
    p = _masters_cache_path(clips_dir)
    Path(p + ".tmp").write_text(json.dumps({"version": 1, "masters": entries},
                                           indent=2, sort_keys=True))
    os.replace(p + ".tmp", p)


def _i2v_hash(prompt, seed, still_path, w, h, frames, steps):
    import hf_cache
    sha = hf_cache.file_sha(Path(still_path)) if os.path.exists(still_path) else None
    payload = {"prompt": prompt, "seed": seed, "still": sha, "workflow": WAN_I2V_WORKFLOW,
               "w": w, "h": h, "frames": frames, "steps": steps}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()[:16]

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


def _download_view(filename, subfolder, target):
    """Pull a ComfyUI output file over its HTTP /view API into `target`.
    Works regardless of where the ComfyUI install put its output dir — no shared
    filesystem assumed (the docker bind-mount path and a native install's output
    root differ; this is the install-agnostic path)."""
    q = urllib.parse.urlencode({"filename": filename,
                                "subfolder": subfolder or "", "type": "output"})
    with urllib.request.urlopen(f"{COMFY_URL}/view?{q}", timeout=120) as r, \
         open(target, "wb") as out:
        shutil.copyfileobj(r, out)


def _collect_output(file_meta, target, slug):
    """Stage one completed ComfyUI output file at `target`, install-agnostically.
    Tries the configured local-filesystem paths first (docker bind-mount or a
    same-box install where MACU_COMFY_OUT/MACU_COMFY_OUTPUT_ROOT point at the real
    output dir), then a recursive glob by basename, then falls back to fetching the
    bytes over ComfyUI's HTTP /view API. The /view fallback is what lets a NATIVE
    ComfyUI install (whose output root isn't the docker mount path) collect cleanly
    with no env tuning. Returns True on success, False if the file can't be found
    anywhere — never raises, so one un-collectable shot can't crash the whole stage
    after a multi-hour render (SSA-126)."""
    fn = file_meta.get("filename")
    if not fn:
        return False
    sub = file_meta.get("subfolder") or ""
    for src in (os.path.join(COMFY_OUT, slug, fn),
                os.path.join(COMFY_OUTPUT_ROOT, sub, fn)):
        if os.path.exists(src):
            shutil.copy2(src, target)
            return True
    hits = sorted(glob.glob(os.path.join(COMFY_OUTPUT_ROOT, "**", fn), recursive=True))
    if hits:
        shutil.copy2(hits[0], target)
        return True
    try:
        _download_view(fn, sub, target)
        return os.path.exists(target) and os.path.getsize(target) > 0
    except Exception as e:
        print(f"  WARN /view fetch failed for {fn}: {e}")
        return False

def main(slug):
    """Local zeroscope masters + (concurrently) Higgsfield cloud shots.

    Cloud shots (kind higgsfield/lipsync) run in a thread via stage_2b_cloud —
    they're network-bound while ComfyUI is GPU-bound, so the wall-clock is
    max(local, cloud), not the sum. Zero cloud shots in the manifest ⇒ behavior
    is byte-identical to the local-only stage. A cloud failure fails the stage,
    but only AFTER the local loop and every other in-flight cloud job finish
    (each success is cached in clips/.hf_cache.json, so a re-run resumes)."""
    import hf_cache
    import stage_2b_cloud
    cloud_box: dict = {}
    cloud_err: list = []
    cloud_thread = None
    if any(True for _ in hf_cache.cloud_shots(load_manifest(slug))):
        def _cloud():
            try:
                cloud_box.update(stage_2b_cloud.main(slug))
            except Exception as e:
                cloud_err.append(e)
        cloud_thread = threading.Thread(target=_cloud, name=f"stage2b-{slug}", daemon=True)
        cloud_thread.start()
    try:
        out = _local_main(slug)
    finally:
        if cloud_thread:
            cloud_thread.join()
    if cloud_err:
        raise cloud_err[0]
    out.update(cloud_box)
    return out


def _local_main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    style_suffix = m["style"]["suffix"]
    negative = m["style"].get("negative", STYLE_NEG_FALLBACK)
    cfg = m["comfyui"]
    W, H, FRAMES = cfg["width"], cfg["height"], cfg["frames"]
    STEPS, CFG = cfg["steps"], cfg["cfg"]
    backend = _masters_backend(m)
    ep_base = p["base"]
    mcache = _load_masters_cache(p["clips"])

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
        # Under the WAN backend BOTH character and b-roll shots animate from a z-image
        # seed still — no zeroscope anywhere, so a clean WAN+z-image install (no
        # ModelScope/zeroscope custom node) renders the whole episode self-contained.
        use_i2v = (backend == "wan_i2v" and kind in ("character", "broll"))
        # Zeroscope: existence is the cache (skip BEFORE building prompt so a cached
        # b-roll never mints/persists a fresh seed). i2v hashes inputs, so it builds
        # the prompt first (characters carry a fixed seed — no minting side effect).
        if not use_i2v and os.path.exists(target):
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
        if use_i2v:
            still = f"{ep_base}/stills/{key}.png"
            h = _i2v_hash(prompt, seed, still, W, H, FRAMES, STEPS)
            if os.path.exists(target) and mcache.get(key) == h:
                skipped += 1
                continue
            if not os.path.exists(still):
                raise RuntimeError(
                    f"[stage 2 masters] WAN i2v {kind} '{key}' needs a seed still at "
                    f"stills/{key}.png — run generate_stills first (it renders z-image "
                    f"stills for every character AND b-roll key under the wan_i2v backend).")
            jobs.append({"kind": kind, "key": key, "prompt": prompt, "seed": seed,
                         "prefix": comfy_prefix, "target": target,
                         "i2v": True, "still": still, "hash": h})
        else:
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
    import stage_2b_cloud  # reuse _comfy_upload / _bind_workflow for the i2v path
    for j in jobs:
        if j.get("i2v"):
            # WAN image-to-video: upload the seed still, bind wan21_i2v (its own tuned
            # negative stays — don't pass the zeroscope negative), submit. SaveAnimatedWEBP
            # output → same fetch path as zeroscope. Fails loud on a non-WAN ComfyUI.
            j["out_node"] = "400"
            try:
                img_name = stage_2b_cloud._comfy_upload(Path(j["still"]))
                graph, out_node = stage_2b_cloud._bind_workflow(
                    "wan21_i2v", prompt=j["prompt"], image=img_name, seed=j["seed"],
                    num_frames=FRAMES, width=W, height=H, steps=STEPS,
                    filename_prefix=j["prefix"])
                j["out_node"] = out_node
                resp = post("/prompt", {"prompt": graph, "client_id": f"macu-i2v-{slug}"})
                j["pid"] = resp["prompt_id"]
            except urllib.error.HTTPError as e:
                raise RuntimeError(
                    f"[stage 2 masters] WAN i2v '{j['key']}': ComfyUI rejected the workflow "
                    f"({e.code}): {e.read().decode()[:300]} — are the talking-head models + "
                    f"WanVideoWrapper/VHS/KJNodes installed (--with-talking-head)?")
            except Exception as e:
                print(f"  WARN submit {j['key']}: {e}")
                j["pid"] = None
        else:
            j["out_node"] = "9"
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
    fetch_failed = {}   # key -> filename: completed in ComfyUI but output couldn't be located
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
                    on = j.get("out_node", "9")
                    files = (e.get("outputs", {}).get(on, {}).get("images")
                             or e.get("outputs", {}).get(on, {}).get("gifs") or [])
                    if files:
                        # Completed in ComfyUI — stop polling this shot either way; a
                        # failed FETCH is reported after the loop, NOT a hard crash here
                        # (so it can't kill a multi-hour render at collection — SSA-126).
                        if _collect_output(files[0], j["target"], slug):
                            if j.get("i2v"):
                                mcache[j["key"]] = j["hash"]; _save_masters_cache(p["clips"], mcache)
                            print(f"  done {j['key']:24} +{round(time.time()-start,1)}s -> {j['target']}")
                        else:
                            fetch_failed[j["key"]] = files[0].get("filename")
                            print(f"  !! {j['key']:24} rendered but output not collectable "
                                  f"(filename={files[0].get('filename')})")
                        done.add(j["key"])
                        progress_tick(2, "masters", len(done) / len(jobs))
            else:
                # PID submission failed but cold-load probably still ran. Look for the file by
                # prefix under the configured output dir, then anywhere under the output root
                # (a native install writes outside the docker mount path — SSA-126).
                base = os.path.basename(j["prefix"])
                matches = sorted(glob.glob("{}/{}/{}*.webp".format(COMFY_OUT, slug, base)))
                if not matches:
                    matches = sorted(glob.glob("{}/**/{}*.webp".format(COMFY_OUTPUT_ROOT, base),
                                               recursive=True))
                if matches:
                    shutil.copy2(matches[-1], j["target"])
                    done.add(j["key"])
                    if j.get("i2v"):
                        mcache[j["key"]] = j["hash"]; _save_masters_cache(p["clips"], mcache)
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

    if fetch_failed:
        # Every shot rendered, but some outputs couldn't be located on disk OR fetched
        # over /view. That's an output-path/config problem, not a render failure — say so
        # clearly (the old code hard-crashed on the first one mid-collection — SSA-126).
        raise RuntimeError(
            f"[stage 2 masters] {len(fetch_failed)}/{len(jobs)} shots rendered in ComfyUI but "
            f"their output files couldn't be collected: {fetch_failed}. Point MACU_COMFY_OUT / "
            f"MACU_COMFY_OUTPUT_ROOT at this ComfyUI's real output dir, or confirm COMFY_URL "
            f"({COMFY_URL}) can serve /view. Re-run stage 2 to retry (staged shots are cached).")

    return {"rendered": len(jobs), "skipped": skipped,
            "wall_s": round(time.time()-start, 2)}

if __name__ == "__main__":
    main(sys.argv[1])
