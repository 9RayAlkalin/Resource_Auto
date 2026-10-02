import hashlib
import json
import os
import random
import string
import threading
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

sample = string.ascii_lowercase + string.digits

THREADS = 32
CHUNK_RETRIES = 5

print_lock = threading.Lock()


class DownloadCancelled(Exception):
    """Raised when a download is aborted via stop_check."""


def taptap(appid: int):
    uid = uuid.uuid4()
    #VN_CODE = 206012000, 281001004
    X_UA = "V=1&PN=TapTap&VN_CODE=281001004&LOC=CN&LANG=zh_CN&CH=default&UID=%s" % uid

    req = urllib.request.Request(
        "https://api.taptapdada.com/app/v2/detail-by-id/%d?X-UA=%s" % (appid, urllib.parse.quote(X_UA)),
        headers={"User-Agent": "okhttp/3.12.1"}
    )
    with urllib.request.urlopen(req) as response:
        r = json.load(response)
    apkid = r["data"]["download"]["apk_id"]

    nonce = "".join(random.sample(sample, 5))
    t = int(time.time())
    byte = "X-UA=%s&end_point=d1&id=%d&node=%s&nonce=%s&time=%sPeCkE6Fu0B10Vm9BKfPfANwCUAn5POcs" % (X_UA, apkid, uid, nonce, t)
    md5 = hashlib.md5(byte.encode()).hexdigest()
    body = "sign=%s&node=%s&time=%s&id=%d&nonce=%s&end_point=d1" % (md5, uid, t, apkid, nonce)

    req = urllib.request.Request(
        "https://api.taptapdada.com/apk/v1/detail?X-UA=" + urllib.parse.quote(X_UA),
        body.encode(),
        {"User-Agent": "okhttp/3.12.1"}
    )
    with urllib.request.urlopen(req) as response:
        return json.load(response)


def _open(url: str, start: int = None, end: int = None):
    headers = {"User-Agent": "okhttp/3.12.1"}
    if start is not None:
        headers["Range"] = f"bytes={start}-{end}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)


def _download_chunk(url: str, path: str, start: int, end: int, progress: dict, stop_check=None):
    """Download bytes [start, end] into path at offset start, with retries.

    Each thread uses its own file handle (no shared fd), because os.pwrite
    is unavailable on Windows. Chunks are disjoint, so no locking is needed.
    """
    for attempt in range(CHUNK_RETRIES):
        if stop_check is not None and stop_check():
            raise DownloadCancelled()
        try:
            with _open(url, start, end) as resp, open(path, "r+b") as f:
                f.seek(start)
                while True:
                    if stop_check is not None and stop_check():
                        raise DownloadCancelled()
                    data = resp.read(256 * 1024)
                    if not data:
                        break
                    f.write(data)
                    with print_lock:
                        progress["done"] += len(data)
            return
        except Exception as e:
            if attempt == CHUNK_RETRIES - 1:
                raise
            with print_lock:
                print(f"\nchunk {start}-{end} failed ({e}), retry {attempt + 1}")
            time.sleep(1 + attempt)


def download_mt(url: str, path: str, threads: int = THREADS, progress_cb=None, stop_check=None):
    """Multi-threaded download using HTTP Range requests.

    progress_cb: optional callable(pct: int, done: int, total: int)
    stop_check: optional callable() -> bool; when it returns True the download
        aborts with KeyboardInterrupt-like CancelledError.
    """
    with _open(url) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        accept_ranges = resp.headers.get("Accept-Ranges", "none").lower() != "none"

    if total == 0 or not accept_ranges:
        print("server does not support range requests, falling back to single thread")
        done = 0
        with _open(url) as resp, open(path, "wb") as f:
            while True:
                if stop_check is not None and stop_check():
                    raise DownloadCancelled()
                data = resp.read(256 * 1024)
                if not data:
                    break
                f.write(data)
                done += len(data)
                if progress_cb is not None and total > 0:
                    progress_cb(done * 100 // total, done, total)
        if progress_cb is not None:
            progress_cb(100, done, total)
        return

    chunk = (total + threads - 1) // threads
    ranges = [(i, min(i + chunk - 1, total - 1)) for i in range(0, total, chunk)]
    progress = {"done": 0}

    def show_progress():
        while True:
            with print_lock:
                pct = progress["done"] * 100 // total
                print(f"\r{pct:3d}%  {progress['done'] / 1048576:.1f}/{total / 1048576:.1f} MB", end="")
            if progress_cb is not None:
                progress_cb(pct, progress["done"], total)
            if progress["done"] >= total or (stop_check is not None and stop_check()):
                print()
                return
            time.sleep(0.5)

    t = threading.Thread(target=show_progress, daemon=True)
    t.start()

    tmp = path + ".part"
    try:
        with open(tmp, "wb") as f:
            f.truncate(total)
        with ThreadPoolExecutor(max_workers=len(ranges)) as pool:
            futures = [pool.submit(_download_chunk, url, tmp, s, e, progress, stop_check) for s, e in ranges]
            for fut in futures:
                fut.result()
    except DownloadCancelled:
        print(f"\ncancelled: {tmp}")
        with print_lock:
            progress["done"] = total  # 让 show_progress 线程退出
        t.join(timeout=2)
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    t.join()
    os.replace(tmp, path)
    if progress_cb is not None:
        progress_cb(100, total, total)
    print(f"saved: {path} ({total / 1048576:.1f} MB)")


# Phigros app id = 165287
if __name__ == "__main__":
    r = taptap(165287)
    version = r["data"]["apk"]["version_name"]
    print(r["data"]["apk"]["download"])
    download_mt(r["data"]["apk"]["download"], f"Phigros_{version}.apk")
    print("finished!")
