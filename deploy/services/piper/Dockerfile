# Piper TTS — the synthetic/machine voice register (engine "piper") on :5050.
# CPU-only, tiny, self-contained (the voice is baked into the image at build time).
#
# DEFAULT voice is a permissively-licensed rhasspy/piper-voices model. To use the
# HAL-9000 voice instead, build with --build-arg PIPER_VOICE=hal (it's modeled on a
# copyrighted film character and comes from an unvetted repo — opt-in only; see
# NOTICE.md). PIPER_VOICE accepts "hal" or any rhasspy voice id like
# "en_US-lessac-medium" / "en_US-ryan-high".
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir "piper-tts[http]" huggingface-hub

ARG PIPER_VOICE=en_US-lessac-medium
ENV PIPER_VOICE=${PIPER_VOICE}

# Download the chosen voice into /voices and flatten to /voices/<base>.onnx(.json).
RUN python - <<'EOF'
import os, shutil
from huggingface_hub import hf_hub_download
voice = os.environ["PIPER_VOICE"]
os.makedirs("/voices", exist_ok=True)
if voice == "hal":
    repo, base = "campwill/HAL-9000-Piper-TTS", "hal"
    files = ["hal.onnx", "hal.onnx.json"]
else:
    # rhasspy/piper-voices layout: <lang>/<locale>/<speaker>/<quality>/<voice>.onnx
    lang, speaker, quality = voice.split("-")            # e.g. en_US-lessac-medium
    sub = f"{lang.split('_')[0]}/{lang}/{speaker}/{quality}"
    repo, base = "rhasspy/piper-voices", voice
    files = [f"{sub}/{voice}.onnx", f"{sub}/{voice}.onnx.json"]
for f in files:
    p = hf_hub_download(repo_id=repo, filename=f, local_dir="/voices")
    ext = ".onnx.json" if f.endswith(".onnx.json") else ".onnx"
    dst = f"/voices/{base}{ext}"
    if os.path.abspath(p) != os.path.abspath(dst):
        shutil.move(p, dst)
with open("/voices/MODEL", "w") as fh:
    fh.write(f"/voices/{base}.onnx")
print(f"baked voice: {base}")
EOF

EXPOSE 5050

# Serve whichever voice was baked in (path recorded in /voices/MODEL).
CMD ["sh", "-c", "python -m piper.http_server --host 0.0.0.0 --port 5050 --model \"$(cat /voices/MODEL)\""]
