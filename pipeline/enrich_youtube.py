"""Fetch YouTube metadata for candidate videos (no API key needed).

- oEmbed: title, channel, availability (401/404 => private/removed).
- Watch page (gzip): category, duration, publish date, view count, short description.
Results are cached in data/youtube_cache.jsonl so reruns only fetch new IDs.
Usage: python3 pipeline/enrich_youtube.py data/candidates.json [--no-pages] [--retry-pages]
"""
import gzip, json, os, re, sys, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from net import CTX, UA

CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "youtube_cache.jsonl")
lock = threading.Lock()
_pause = {"until": 0.0, "backoff": 60.0}
_yt_down = {"until": 0.0}
DELAY = 0.8  # seconds between requests per worker


class RateLimited(Exception):
    pass


def _open(url, tries=6):
    for _ in range(tries):
        wait = _pause["until"] - time.time()
        if wait > 0:
            time.sleep(wait)
        time.sleep(DELAY)
        try:
            return _open_once(url)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            with lock:  # global pause, doubling each time we get throttled
                if _pause["until"] < time.time():
                    _pause["until"] = time.time() + _pause["backoff"]
                    print(f"  429 -> pausing {_pause['backoff']:.0f}s", flush=True)
                    _pause["backoff"] = min(_pause["backoff"] * 2, 900)
    raise RateLimited(url)


def _open_once(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                                               "Accept-Encoding": "gzip", "Cookie": "CONSENT=YES+1"})
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        _pause["backoff"] = max(60.0, _pause["backoff"] * 0.9)
        return data.decode("utf-8", "replace")


def _field(pat, s):
    m = re.search(pat, s)
    return m.group(1) if m else None


def _oembed(vid):
    """Title/channel/availability. Falls back to noembed.com (an oEmbed proxy) when
    youtube.com itself is unreachable from this network."""
    yurl = f"https://www.youtube.com/watch?v={vid}"
    try:
        if time.time() < _yt_down["until"]:
            raise ConnectionError("youtube.com recently unreachable")
        o = json.loads(_open("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(yurl), tries=2))
        return o, "youtube"
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        if not isinstance(e, ConnectionError):
            _yt_down["until"] = time.time() + 600  # circuit breaker: skip youtube.com for 10 min
        o = json.loads(_open("https://noembed.com/embed?url=" + urllib.parse.quote(yurl)))
        if "error" in o:
            code = int(re.match(r"\d+", o["error"]).group()) if re.match(r"\d+", o["error"]) else 404
            raise urllib.error.HTTPError(yurl, code, o["error"], None, None)
        return o, "noembed"


def fetch_one(vid, want_page=True):
    rec = {"id": vid}
    try:
        o, src = _oembed(vid)
        rec.update(title=o.get("title"), channel=o.get("author_name"), channel_url=o.get("author_url"),
                   available=True, src=src)
    except urllib.error.HTTPError as e:
        rec.update(available=False, status=e.code)
        if e.code not in (400, 401, 403, 404):
            rec["transient"] = True
        return rec
    except Exception as e:
        rec.update(available=None, error=str(e)[:100], transient=True)
        return rec
    if not want_page or time.time() < _yt_down["until"]:
        return rec
    try:
        page = _open(f"https://www.youtube.com/watch?v={vid}&hl=en", tries=2)
        cat = _field(r'"category":"([^"]+)"', page)
        rec["category"] = cat.replace("\\u0026", "&") if cat else None
        ls = _field(r'"lengthSeconds":"(\d+)"', page)
        rec["duration"] = int(ls) if ls else None
        rec["published"] = (_field(r'"publishDate":"([^"]+)"', page) or "")[:10] or None
        vc = _field(r'"viewCount":"(\d+)"', page)
        rec["views"] = int(vc) if vc else None
        desc = _field(r'"shortDescription":"((?:[^"\\]|\\.)*)"', page)
        if desc:
            try:
                desc = json.loads('"' + desc + '"')
            except Exception:
                pass
            rec["description"] = desc[:400]
        rec["page"] = True
    except Exception as e:
        rec["page_error"] = str(e)[:100]  # kept; `--retry-pages` refetches these later
    return rec


def load_cache():
    out = {}
    if os.path.exists(CACHE):
        for line in open(CACHE):
            r = json.loads(line)
            if not r.get("transient"):
                out[r["id"]] = r
    return out


def main(ids, workers=2, retry_pages=False, want_page=True):
    cache = load_cache()
    todo = [v for v in ids if v not in cache or
            (retry_pages and cache[v].get("available") and not cache[v].get("page"))]
    print(f"{len(ids)} ids, {len(todo)} to fetch", flush=True)
    with open(CACHE, "a") as f, ThreadPoolExecutor(workers) as ex:
        for i, rec in enumerate(ex.map(lambda v: fetch_one(v, want_page), todo)):
            with lock:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} {rec.get('title')!r} {rec.get('category')}", flush=True)


if __name__ == "__main__":
    ids = json.load(open(sys.argv[1]))
    main(ids, retry_pages="--retry-pages" in sys.argv, want_page="--no-pages" not in sys.argv,
         workers=4 if "--no-pages" in sys.argv else 2)
