# Piper HAL — the synthetic / machine voice register (engine "piper", model "hal").
# CPU-only, tiny. The HAL-9000 voice is baked into the image at build time from
# Hugging Face (campwill/HAL-9000-Piper-TTS), so the container is self-contained —
# no model volume to mount, no runtime download.
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir "piper-tts[http]" huggingface-hub

# Bake the HAL-9000 voice (hal.onnx + hal.onnx.json) into /voices.
RUN python - <<'EOF'
from huggingface_hub import hf_hub_download
import os
voices_dir = "/voices"
os.makedirs(voices_dir, exist_ok=True)
for fn in ("hal.onnx", "hal.onnx.json"):
    hf_hub_download(repo_id="campwill/HAL-9000-Piper-TTS", filename=fn,
                    local_dir=voices_dir, local_dir_use_symlinks=False)
EOF

EXPOSE 5050

CMD ["python", "-m", "piper.http_server", "--host", "0.0.0.0", "--port", "5050", "--model", "/voices/hal.onnx"]
