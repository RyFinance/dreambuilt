"""Read members of a zip on a web server without downloading the whole archive
(HTTP range requests; the central directory first, then only the files asked for)."""
from __future__ import annotations

import io
import urllib.request


class RangeFile(io.RawIOBase):
    def __init__(self, url: str, block: int = 1 << 20):
        self.url, self.block, self.pos = url, block, 0
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req) as r:
            self.size = int(r.headers["Content-Length"])
        self.cache: dict[int, bytes] = {}

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def _get(self, start: int, end: int) -> bytes:
        """One byte range, retried (home connections drop long reads)."""
        import time
        out = b""
        for attempt in range(8):
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={start + len(out)}-{end - 1}"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    while len(out) < end - start:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        out += chunk
                if len(out) >= end - start:
                    return out
            except Exception:
                time.sleep(1 + attempt)
        raise IOError(f"could not read bytes {start}-{end} of {self.url}")

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        if n > self.block:  # big reads go straight through
            data = self._get(self.pos, self.pos + n)
        else:
            b0 = self.pos // self.block
            b1 = (self.pos + n - 1) // self.block
            parts = []
            for b in range(b0, b1 + 1):
                if b not in self.cache:
                    if len(self.cache) > 64:
                        self.cache.clear()
                    self.cache[b] = self._get(b * self.block, min(self.size, (b + 1) * self.block))
                parts.append(self.cache[b])
            buf = b"".join(parts)
            off = self.pos - b0 * self.block
            data = buf[off:off + n]
        self.pos += len(data)
        return data

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)
