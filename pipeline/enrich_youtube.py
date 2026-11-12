"""Fetch YouTube metadata for candidate videos (no API key needed).

- oEmbed: title, channel, availability (401/404 => private/removed).
- Watch page (gzip): category, duration, publish date, view count, short description.
Results are cached in data/youtube_cache.jsonl so reruns only fetch new IDs.
Usage: python3 pipeline/enrich_youtube.py data/candidates.json [--no-pages] [--retry-pages]
       YOUTUBE_API_KEY=... python3 pipeline/enrich_youtube.py data/candidates.json [--refresh-all]
         (preferred: official Data API, ~48 requests for 2,400 videos)
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


# Standard YouTube category IDs (videoCategories.list, regionCode=US)
CATEGORIES = {"1": "Film & Animation", "2": "Autos & Vehicles", "10": "Music", "15": "Pets & Animals",
              "17": "Sports", "19": "Travel & Events", "20": "Gaming", "22": "People & Blogs", "23": "Comedy",
              "24": "Entertainment", "25": "News & Politics", "26": "Howto & Style", "27": "Education",
              "28": "Science & Technology", "29": "Nonprofits & Activism"}


def iso_duration(s):
    """'PT1H2M3S' -> 3723 seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return None
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def api_record(item):
    """One item of videos.list (part=snippet,contentDetails,statistics,status) -> cache record."""
    sn, cd, st = item.get("snippet", {}), item.get("contentDetails", {}), item.get("statistics", {})
    status = item.get("status", {})
    return {
        "id": item["id"], "title": sn.get("title"), "channel": sn.get("channelTitle"),
        "channel_url": f"https://www.youtube.com/channel/{sn['channelId']}" if sn.get("channelId") else None,
        "available": status.get("privacyStatus", "public") != "private", "src": "api",
        "category": CATEGORIES.get(sn.get("categoryId"), sn.get("categoryId")),
        "duration": iso_duration(cd.get("duration")), "published": (sn.get("publishedAt") or "")[:10] or None,
        "views": int(st["viewCount"]) if st.get("viewCount") else None,
        "description": (sn.get("description") or "")[:400], "page": True,
    }


def main_api(ids, key, refresh_all=False):
    """YouTube Data API v3: 50 videos per request, 1 quota unit each (free quota: 10,000/day).
    Videos missing from the response are deleted/private -> available=False."""
    cache = load_cache()
    todo = [v for v in ids if refresh_all or v not in cache or not cache[v].get("page")]
    print(f"{len(ids)} ids, {len(todo)} to fetch via API ({(len(todo) + 49) // 50} requests)", flush=True)
    with open(CACHE, "a") as f:
        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            url = ("https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,statistics,status"
                   f"&maxResults=50&id={','.join(batch)}&key={urllib.parse.quote(key)}")
            try:
                data = json.loads(_open_once(url))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")[:300]
                sys.exit(f"YouTube API error {e.code}: {body}")
            found = {it["id"]: api_record(it) for it in data.get("items", [])}
            for vid in batch:
                rec = found.get(vid) or {"id": vid, "available": False, "status": 404, "src": "api"}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {i + len(batch)}/{len(todo)}", flush=True)


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
    key = os.environ.get("YOUTUBE_API_KEY")
    if key:
        main_api(ids, key, refresh_all="--refresh-all" in sys.argv)
        sys.exit(0)
    main(ids, retry_pages="--retry-pages" in sys.argv, want_page="--no-pages" not in sys.argv,
         workers=4 if "--no-pages" in sys.argv else 2)
