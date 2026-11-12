"""raw HN comments -> per-mention classification -> per-video aggregates.

Outputs:
  data/mentions.jsonl   every (comment, video) pair with classifier output
  data/videos_stats.json  aggregates for videos with >= MIN_RECOMMENDERS
  data/candidates.json  video IDs to enrich via YouTube
"""
import glob, gzip, json, os, sys, time
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from extract import to_text, video_ids, context_for, strip_urls
from classify import score_text, THRESHOLD
from topics import tag
from score import aggregate

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
MIN_RECOMMENDERS = 2
LLM_RESULTS = os.path.join(ROOT, "llm", "results_borderline.jsonl")
LLM_P = {"strong": 0.85, "weak": 0.6}  # weight of a recommendation found only by the LLM second opinion
LLM = {}  # (cid, vid) -> {"label", "reason"}; filled by load_llm()


def load_llm(path=LLM_RESULTS):
    LLM.clear()
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            LLM[(r["cid"], r["vid"])] = {"label": r["label"], "reason": r["reason"]}
    return len(LLM)


def _lines(path):
    try:
        with gzip.open(path, "rt") as f:
            yield from f
    except (EOFError, OSError):  # interrupted final gzip member
        return


def load_raw():
    seen = {}
    for path in glob.glob(os.path.join(ROOT, "raw", "comments_*.jsonl.gz")):
        for line in _lines(path):
            try:
                h = json.loads(line)
            except ValueError:  # truncated last line after an interrupted run
                continue
            seen[h["objectID"]] = h
    return list(seen.values())


def mentions_from_comment(h):
    text = to_text(h.get("comment_text"))
    vids = video_ids(text)
    if not vids:
        return []
    story_url = h.get("story_url") or ""
    head = strip_urls(text[:220])
    out = []
    for vid in vids:
        ctx = context_for(text, vid)
        # list-style comments ("My favourite talks: ...") put the vouching in the intro
        cue_text = ctx if head[:80] in ctx else head + "\n" + ctx
        p, pos, neg = score_text(cue_text)
        if len(vids) > 6:  # link dumps: keep the signal but trust each item a bit less
            p *= 0.85
        rec = p >= THRESHOLD and "自我推广" not in neg
        llm = LLM.get((h["objectID"], vid))
        if llm and not rec and llm["label"] in LLM_P and "自我推广" not in neg:
            rec, p = True, max(p, LLM_P[llm["label"]])
        t = h["created_at_i"]
        out.append({
            "vid": vid, "cid": h["objectID"], "author": h.get("author") or "?",
            "t": t, "year": time.gmtime(t).tm_year,
            "story_id": h.get("story_id"), "story_title": h.get("story_title") or "",
            "own_thread": vid in story_url,
            "p": round(p, 3), "rec": rec, "pos": pos, "neg": neg,
            "n_videos": len(vids), "quote": ctx[:600], "llm": llm,
            "topics": tag(h.get("story_title") or ""),
        })
    return out


def main():
    raw = load_raw()
    print(f"{len(raw)} unique comments; {load_llm()} LLM second opinions loaded", flush=True)
    by_vid = defaultdict(list)
    n = 0
    with gzip.open(os.path.join(ROOT, "mentions.jsonl.gz"), "wt") as f:
        for h in raw:
            for m in mentions_from_comment(h):
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
                by_vid[m["vid"]].append(m)
                n += 1
    print(f"{n} mentions of {len(by_vid)} distinct videos", flush=True)
    stats = {}
    for vid, ms in by_vid.items():
        a = aggregate(ms)
        if a["recommenders"] >= MIN_RECOMMENDERS:
            stats[vid] = a
    order = sorted(stats, key=lambda v: -stats[v]["score"])
    json.dump({v: stats[v] for v in order}, open(os.path.join(ROOT, "videos_stats.json"), "w"), ensure_ascii=False)
    json.dump(order, open(os.path.join(ROOT, "candidates.json"), "w"))
    n_rec = sum(1 for ms in by_vid.values() for m in ms if m["rec"])
    n_llm = sum(1 for ms in by_vid.values() for m in ms if m["rec"] and m.get("llm"))
    summary = {"comments": len(raw), "mentions": n, "videos": len(by_vid), "rec_mentions": n_rec,
               "llm_judged": len(LLM), "llm_added": n_llm,
               "candidates": len(order), "built_at": int(time.time())}
    json.dump(summary, open(os.path.join(ROOT, "build_summary.json"), "w"), indent=1)
    print(summary)


if __name__ == "__main__":
    main()
