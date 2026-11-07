"""Fetch only the 5,000 model.svg drawings out of the CubiCasa5K zip on Zenodo (about 44 MB
instead of 5.5 GB), one file per plan into data/raw/cubicasa5k/svg/. Resumable: re-run to
pick up anything that failed. CC BY-NC-SA 4.0; kept out of the repository."""
from __future__ import annotations

import os
import struct
import sys
import threading
import time
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from remote_zip import RangeFile  # noqa: E402

URL = "https://zenodo.org/records/2613548/files/cubicasa5k.zip?download=1"


def main(out: str = "data/raw/cubicasa5k/svg"):
    f = RangeFile(URL, block=1 << 16)
    members = [i for i in zipfile.ZipFile(f).infolist() if i.filename.endswith("model.svg")]
    os.makedirs(out, exist_ok=True)

    def path(m):
        return os.path.join(out, m.filename.replace("cubicasa5k/", "").replace("/model.svg", "")
                            .replace("/", "__") + ".svg")

    todo = [m for m in members if not os.path.exists(path(m))]
    print(f"{len(members)} drawings, {len(todo)} to fetch", flush=True)
    lock, last = threading.Lock(), [0.0]

    def throttle():  # Zenodo allows 133 requests a minute
        with lock:
            wait = last[0] + 0.47 - time.time()
            if wait > 0:
                time.sleep(wait)
            last[0] = time.time()

    def get(m):
        # one request: the local header, its name and extra field (guessed generously), the data
        throttle()
        blob = f._get(m.header_offset, min(f.size, m.header_offset + 30 + 512 + m.compress_size))
        n, e = struct.unpack("<HH", blob[26:30])
        start = 30 + n + e
        raw = blob[start:start + m.compress_size]
        if len(raw) < m.compress_size:
            throttle()
            raw = f._get(m.header_offset + start, m.header_offset + start + m.compress_size)
        return zlib.decompress(raw, -15) if m.compress_type == 8 else raw

    def save(m):
        try:
            data = get(m)
        except Exception as e:  # skipped; a re-run picks it up
            return str(e)[:80]
        with open(path(m), "wb") as fo:
            fo.write(data)
        return None

    errors = 0
    with ThreadPoolExecutor(4) as pool:
        for i, err in enumerate(pool.map(save, todo)):
            errors += err is not None
            if i % 250 == 0:
                print(i, "errors", errors, flush=True)
    print("done, errors", errors, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
