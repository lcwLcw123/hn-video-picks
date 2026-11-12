"""Crawl Hacker News comments that mention YouTube via the public HN Algolia API.

Algolia caps any single query at 1000 retrievable hits, so we walk time
windows and recursively split any window that has more than 1000 hits.
Output: data/raw/comments_<query>.jsonl.gz (one hit per line, deduped by objectID).
Re-running is incremental: windows already fetched are recorded in a state file.
"""
import gzip, json, os, sys, time, urllib.parse
sys.path.insert(0, os.path.dirname(__file__))
from net import get

API = "https://hn.algolia.com/api/v1/search_by_date"
ATTRS = "objectID,author,comment_text,created_at_i,story_id,story_title,story_url,parent_id,points"
ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
START = 1160418111  # first HN item (Oct 2006)


def fetch(query, lo, hi, retries=5):
    params = {
        "query": query, "tags": "comment", "hitsPerPage": 1000,
        "attributesToRetrieve": ATTRS, "attributesToHighlight": "",
        "numericFilters": f"created_at_i>={lo},created_at_i<{hi}",
        "typoTolerance": "false",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    return get(url, retries=retries)


def crawl(query, end=None):
    end = end or int(time.time())
    slug = query.replace(".", "_").replace("/", "_")
    out_path = os.path.join(ROOT, f"comments_{slug}.jsonl.gz")
    state_path = os.path.join(ROOT, f"state_{slug}.json")
    done = json.load(open(state_path)) if os.path.exists(state_path) else []
    done_set = {tuple(w) for w in done}
    os.makedirs(ROOT, exist_ok=True)
    # initial windows: one per quarter
    step = 86400 * 91
    stack = [(t, min(t + step, end)) for t in range(START, end, step)][::-1]
    n_req = 0
    while stack:
        lo, hi = stack.pop()
        if (lo, hi) in done_set:
            continue
        d = fetch(query, lo, hi)
        n_req += 1
        if d["nbHits"] > 1000 and hi - lo > 60:
            mid = (lo + hi) // 2
            stack.extend([(mid, hi), (lo, mid)])
            continue
        with gzip.open(out_path, "at") as out:  # one complete gzip member per window
            for h in d["hits"]:
                out.write(json.dumps(h) + "\n")
        done.append([lo, hi]); done_set.add((lo, hi))
        json.dump(done, open(state_path, "w"))
        print(f"{query} {time.strftime('%Y-%m-%d', time.gmtime(lo))} hits={len(d['hits'])} req={n_req}", flush=True)
        time.sleep(0.25)


if __name__ == "__main__":
    for q in sys.argv[1:] or ["youtube.com", "youtu.be"]:
        crawl(q)
