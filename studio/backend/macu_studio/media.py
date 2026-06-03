"""File streaming helpers with HTTP Range support for video."""
from __future__ import annotations
import mimetypes, os
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse


CHUNK = 1024 * 1024


def stream_file(request: Request, path: Path, *, content_type: str | None = None) -> StreamingResponse:
    if not path.exists():
        raise HTTPException(404, f"not found: {path.name}")
    size = path.stat().st_size
    ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    range_header = request.headers.get("range") or request.headers.get("Range")

    start, end = 0, size - 1
    status = 200
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(size),
        "Content-Type": ctype,
        "Cache-Control": "no-cache",
    }
    if range_header and range_header.startswith("bytes="):
        try:
            spec = range_header.split("=", 1)[1]
            s, e = spec.split("-", 1)
            start = int(s) if s else 0
            end = int(e) if e else size - 1
        except Exception:
            raise HTTPException(416, "invalid range")
        if start >= size:
            raise HTTPException(416, "range out of bounds")
        end = min(end, size - 1)
        length = end - start + 1
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(length)

    def gen():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                buf = f.read(min(CHUNK, remaining))
                if not buf:
                    break
                remaining -= len(buf)
                yield buf

    return StreamingResponse(gen(), status_code=status, headers=headers, media_type=ctype)
