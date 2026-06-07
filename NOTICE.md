# Third-party components & licenses

MACU Studio orchestrates a number of third-party models, fonts, and tools that it
downloads or bundles. This file records what they are and the licensing terms the
maintainer is aware of. **It is informational, not legal advice** — verify upstream
before any commercial or broad redistribution. Where a term is marked "see upstream,"
consult the linked source.

## Models (downloaded by `deploy/fetch-models.sh`, not bundled)

| Component | Source | License (as understood) |
|---|---|---|
| zeroscope_v2_576w unet (`text2video_pytorch_model.pth`) | `cerspense/zeroscope_v2_576w` (HF) | CreativeML OpenRAIL-M — commercial use permitted under the use-based restrictions |
| DAMO ModelScope VAE + CLIP + config (`VQGAN_autoencoder.pth`, `open_clip_pytorch_model.bin`, `configuration.json`) | `ali-vilab/modelscope-damo-text-to-video-synthesis` (HF) | **CC-BY-NC-4.0 — NON-COMMERCIAL.** This is the binding constraint on the video stack for commercial use; source a permissive VAE/CLIP to lift it. |
| qwen2.5 (shot-list LLM) | `qwen2.5:7b-instruct-q4_K_M` via Ollama | Qwen LICENSE (Tongyi Qianwen) — see upstream |

## Voices

| Component | Source | Notes |
|---|---|---|
| HAL-9000 Piper voice (default, baked into the Piper image) | `campwill/HAL-9000-Piper-TTS` (HF) | Voice modeled on a copyrighted film character, from an unvetted community repo. **Treat as non-redistributable / opt-in.** For an unencumbered default, switch to a `rhasspy/piper-voices` model and gate HAL behind a build arg. |

## Fonts (bundled in `deploy/assets/fonts/`)

| Component | Author | License |
|---|---|---|
| Better VCR (`BetterVCR.ttf`) | artdzyk / PAWFONT | SIL Open Font License (OFL) — redistribution permitted; keep this attribution and ship the OFL text alongside the font. |

## Services & tools (run in Docker or invoked as CLIs)

| Component | Source | License (as understood) |
|---|---|---|
| ComfyUI | `Comfy-Org/ComfyUI` | GPL-3.0 |
| ComfyUI_ModelScopeT2V node | `ExponentialML/ComfyUI_ModelScopeT2V` | see upstream |
| OmniVoice Studio | `ghcr.io/debpalash/omnivoice-studio` (+ in-repo patches) | see upstream |
| Piper TTS | `rhasspy/piper` | MIT |
| faster-whisper | `SYSTRAN/faster-whisper` (CTranslate2) | MIT |
| rife-ncnn-vulkan | `nihui/rife-ncnn-vulkan` | MIT |
| HyperFrames CLI | `heygen-com/hyperframes` | see upstream |
| Ollama | `ollama/ollama` | MIT |

## This project's own license

Not yet chosen. Until a `LICENSE` file is added, default copyright applies (all
rights reserved). For a self-hosted web app that bundles GPL (ComfyUI), AGPL-3.0 or
GPL-3.0 are the conventional defensible choices — but this is the maintainer's call.
