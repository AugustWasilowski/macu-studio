FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip \
        git ffmpeg libgl1 libglib2.0-0 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3.12 -m venv /opt/venv --system-site-packages
ENV PATH=/opt/venv/bin:$PATH

# Torch first (CUDA 12.6 build), then ComfyUI's requirements.
# ComfyUI source itself is bind-mounted at runtime under /workspace, so the
# image stays slim and "always-latest" is a `git pull` on the host.
RUN /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install \
        --index-url https://download.pytorch.org/whl/cu126 \
        torch torchvision torchaudio

# Entrypoint reinstalls /workspace/requirements.txt on every start so a host
# `git pull` of new ComfyUI deps takes effect on next `docker compose restart`.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /workspace
EXPOSE 8188

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"]
