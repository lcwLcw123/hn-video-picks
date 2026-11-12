"""Tiny HTTP helper with a CA bundle that works on python.org macOS builds and CI."""
import json, os, ssl, sys, time, urllib.request

def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        if os.path.exists("/etc/ssl/cert.pem"):
            return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
        return ssl.create_default_context()

CTX = _ctx()
UA = "Mozilla/5.0 (hn-video-picks research crawler)"

def get(url, retries=5, timeout=60, headers=None, as_json=True):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en"}
    h.update(headers or {})
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                data = r.read()
                return json.loads(data) if as_json else data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):
                raise
            last = e
        except Exception as e:
            last = e
        wait = 2 ** i * 2
        print(f"  retry {i+1} after {last}; sleep {wait}s", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"failed {url}: {last}")
