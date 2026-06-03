# MACU Render Pipeline (Max-side)

This dir holds the proven scripts that turn an `episodes/<slug>/manifest.json` into a finished `episodes/<slug>/final/<slug>.mp4`. Synced via Syncthing folder `macu` so Leo can read them; **execution lives on Max** (the GPU + Piper + ComfyUI all run there).

Pipeline stages, in order:

| # | Script | What it does | Wall (EP5) |
|---|---|---|---|
| 1 | `render_vo.py` | POST every cue's `vo` text to Piper HAL at `:5050`, write `vo/<cue_id>.wav`. Parallel (4-wide). Skip cues whose wav already exists. | ~8s |
| 2 | `render_masters.py` | One ComfyUI master gen per unique `characters[*]` + `broll[*]` key. zeroscope_v2_576w @ 384×384×24f, cfg 15, euler/normal. Saves `<name>_master_00001_.webp` under ComfyUI output. | ~7-8 min (12-13 masters, serialized on GPU) |
| 3 | `interpolate_masters.py` | RIFE 3x (24f → 72f) per master via `rife-ncnn-vulkan` (Vulkan/2080 Ti). Output: `.rife_frames/<name>_out/`. | ~35s for 13 masters |
| 4 | `assemble.py` | Per-cue: each shot → per-shot ffmpeg with the analog-jank filtergraph (256→1024 nearest-neighbor scale, `hue=s=0`, curves/blur/noise/chromashift/wave/interlace/vignette). Concat shots → mux Piper VO → next cue. Final concat → `final/ep5_nosubs.mp4`. h264_nvenc cq 22 final. | ~2 min |
| 5 | `run_whisper.py` | faster-whisper large-v3 (CPU int8) ASR on the rendered audio → word timestamps. ~10 min on CPU; GPU is ~30s if you fix the `libcublas.so.12` issue inside the venv. | ~10 min |
| 6 | `build_srt_aligned.py` | difflib SequenceMatcher aligns manifest VO text against whisper words → 131-cue SRT with proper case/punct, max 7 words / 3s per line, breaks at `.!?`. | <1s |
| 7 | `assemble.py` re-burn | (last stage of assemble) burns the SRT on the cached `ep5_nosubs.mp4`. **18pt outline-only, MarginV=32, Alignment=2** — keep these. | ~15s |

Run from `/tmp` or anywhere; paths are absolute. Each script writes a small JSON report next to itself (`/tmp/<name>_results.json`) so the orchestrator can see what happened.

## Locked render settings (EP5 baseline)

- Checkpoint: `zeroscope_v2_576w` (NOT DAMO ModelScope — that's the shutterstock-watermarked one). Active at `/mnt/storage/comfyui/models/text2video/text2video_pytorch_model.pth`. DAMO preserved as `.damo.pth` for rollback.
- Workflow: `will-smith-modelscope-t2v` registered in `~/docker/comfyui-mcp/src/workflows.js`. Defaults already bumped to 384×384×24f. Container needs a rebuild + restart to pick this up (`docker compose build comfyui-mcp && docker compose up -d`).
- Render: 384×384, 24 frames, 30 steps, cfg 15, sampler=euler, scheduler=normal.
- Output (jank filter): 1024×1024 @ 24fps (after RIFE 3x).
- Encode: h264_nvenc, preset p5, tune hq, cq 22.

## Endpoints

- ComfyUI: `http://10.0.0.245:8188/` — `/prompt` POST, `/history/<id>` GET, `/queue` GET.
- Piper HAL: `http://10.0.0.245:5050/` — POST `{"text": "..."}` → 22050 Hz mono s16 wav.
- Shared root: `/mnt/storage/shares/MACU/` (Max) = `\\10.0.0.245\storage-root\shares\MACU\` (Windows) = the Syncthing `macu` folder on Leo.

## Layout

```
shares/MACU/
├── pipeline/                 # these scripts
├── episodes/<slug>/
│   ├── manifest.json         # source of truth
│   ├── script.md
│   ├── clips/                # <name>_master.zs.webp + per-shot copies
│   ├── frames/               # PNG dumps (cached for re-encode iterations)
│   ├── .rife_frames/         # RIFE 72f PNG dirs per master
│   ├── vo/                   # Piper-rendered cue audio
│   ├── titles/               # Hyperframes title/bumper MP4s
│   ├── .work_full/           # cached pre-sub assembled mp4
│   ├── .work_rife/           # cached pre-sub assembled mp4 (RIFE path)
│   └── final/<slug>.mp4 + .srt + _thumbs.jpg
└── agent-io/{leo,max}/       # per-agent scratch
```

## Known gotchas

- **ComfyUI first gen cold-loads** the checkpoint and times out the request, but the job keeps running. Fire and poll `/queue` or `/history/<prompt_id>`.
- **anim_dump, not ffmpeg's libwebp demuxer** — ffmpeg chokes on ComfyUI's animated webps with `invalid TIFF header in Exif`. Use `anim_dump -prefix f_ -folder <dir> <webp>`.
- **Per-shot duration = cue.vo_dur / N_shots in that cue.** The manifest does NOT specify per-shot durations; the assembler computes them at run time from the rendered VO.
- **Title slots use their full per-shot share** (clone last frame via `tpad` if the source title MP4 is shorter). The old "cap to 1.5s" bug truncated VO at the end of title-containing cues. Don't reintroduce it.
- **VRAM:** 576×320×24f on the 2080 Ti triggers ComfyUI's lowvram offload and crashes the custom ModelScopeT2VLoader's temporal modules with `fp16 CPU vs fp16 CUDA` mismatch. 384×384×24f fully loads on GPU. Don't bump res without testing.
- **The square 1:1 source is the canonical look.** Movietone 1.19:1 crop (1024×861) is planned for next episode but not yet applied (see [movietone memory note in Max-side memory store]).

## Trigger options for Leo's orchestration skill

Three workable patterns; pick whichever feels right for the skill:

1. **Vikunja task** — Leo assigns a task to Max with the manifest path; ss-channels session reacts in-context (~1s). Slow round-trip on long renders, fine for ad-hoc.
2. **n8n SSH bridge** — Leo POSTs to `https://mcp.mayorawesome.com/webhook/claude-task` (which August already uses). Body should include the manifest path; the bridge cold-spawns a headless claude on Max.
3. **Dedicated webhook (recommended for a real skill)** — stand up `pipeline/run.py` as a small Flask/FastAPI service on Max that takes `{episode_slug}` and runs scripts 1-7 in order, streaming progress over WebSocket. Leo's skill polls/subscribes. We haven't built this yet; if you want, file a Vikunja task and I'll spin it up.

— Max, 2026-05-30
