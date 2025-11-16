# src/streaming/sse_utils.py
import requests
from typing import Iterator

def sse_client(url: str, timeout: int = None) -> Iterator[str]:
    """
    Minimal SSE client generator using requests.
    Yields decoded lines. Stops when the special token [[STREAM_END]] appears.
    """
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw:
                continue
            try:
                line = raw.decode("utf-8")
            except Exception:
                line = raw.decode(errors="replace")
            yield line
            if "[[STREAM_END]]" in line:
                break
