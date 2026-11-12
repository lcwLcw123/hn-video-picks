"""Fetch YouTube metadata for candidate videos (no API key needed).

- oEmbed: title, channel, availability (401/404 => private/removed).
- Watch page (gzip): category, duration, publish date, view count, short description.
Results are cached in data/youtube_cache.jsonl so reruns only fetch new IDs.
Usage: python3 pipeline/enrich_youtube.py data/candidates.json
"""
import gzip, json, os, re, sys, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from net import CTX, UA

CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "youtube_cache.jsonl")
lock = threading.Lock()
_pause = {"until": 0.0, "backoff": 60.0}
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


def fetch_one(vid):
    rec = {"id": vid}
    try:
        o = json.loads(_open("https://www.youtube.com/oembed?format=json&url=" +
                             urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")))
        rec.update(title=o.get("title"), channel=o.get("author_name"), channel_url=o.get("author_url"), available=True)
    except urllib.error.HTTPError as e:
        rec.update(available=False, status=e.code)
        if e.code not in (400, 401, 403, 404):
            rec["transient"] = True
        return rec
    except Exception as e:
        rec.update(available=None, error=str(e)[:100], transient=True)
        return rec
    try:
        page = _open(f"https://www.youtube.com/watch?v={vid}&hl=en")
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
    except Exception as e:
        rec["page_error"] = str(e)[:100]
        rec["transient"] = True  # retry the page next run
    return rec


def load_cache():
    out = {}
    if os.path.exists(CACHE):
        for line in open(CACHE):
            r = json.loads(line)
            if not r.get("transient"):
                out[r["id"]] = r
    return out


def main(ids, workers=2):
    cache = load_cache()
    todo = [v for v in ids if v not in cache]
    print(f"{len(ids)} ids, {len(todo)} to fetch", flush=True)
    with open(CACHE, "a") as f, ThreadPoolExecutor(workers) as ex:
        for i, rec in enumerate(ex.map(fetch_one, todo)):
            with lock:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} {rec.get('title')!r} {rec.get('category')}", flush=True)


if __name__ == "__main__":
    ids = json.load(open(sys.argv[1]))
    main(ids)
