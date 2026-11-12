"""Join aggregates + YouTube metadata + mentions into the static site's JSON files.

site/data/index.json      compact list for browsing / filtering
site/data/v/<id>.json     full "why recommended" detail per video
site/data/meta.json       dataset stats + classifier evaluation
"""
import gzip, json, os, re, shutil, sys, time
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from enrich_youtube import load_cache

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site", "data")

NON_KNOWLEDGE = {"Music", "Comedy", "Gaming", "Pets & Animals", "Entertainment", "Sports"}
# HN recommendation cues that say "this is something you learn from"
LEARNING_CUES = {"知识型内容", "讲得清楚"}
KNOWLEDGE_TITLE = re.compile(r"\b(talk|lecture|keynote|conference|documentary|explained|explains?|how|why|what|history|story|interview|course|lesson|introduction|intro|science|theory|engineering|programming|math|physics|tutorial|seminar|panel|debate|demo|war stories|economics|problem|analysis|essay|gdc|defcon|def con|sxsw|ted|tedx|ccc|c3|postmortem|post-mortem|deep dive|behind|making of|busted|truth|stats|statistics|machine learning|file ?systems?|software|computer|hardware|algorithm|the hard parts)\b|\b\d{4}\b.*\b(talk|conf)", re.I)


MUSIC_HINT = re.compile(r"official (music )?video|\(official|lyrics?\b|\bfeat\.|\bft\.|remix|full album|music video|\(audio\)|official audio|\blive at\b|\bcover\)|\bunplugged\b|\bconcerto\b|\bsymphony\b|\bsonata\b|trailer\b|\bfunny\b|\bprank|\bmeme\b", re.I)
MUSIC_CHANNEL = re.compile(r"vevo$| - topic$|records$|\bmusic$", re.I)


def kind_of(meta, recs=()):
    """'knowledge' unless the video looks like music/comedy/gaming/entertainment for its own sake.
    Uploader categories are unreliable (many great talks are filed under Gaming/Entertainment),
    so non-knowledge categories are overridden by the title or by what HN recommenders said."""
    cat = meta.get("category")
    learn = sum(1 for m in recs if LEARNING_CUES & set(m.get("pos", [])))
    if cat in NON_KNOWLEDGE:
        if KNOWLEDGE_TITLE.search(meta.get("title") or "") or learn >= 2 or (recs and learn / len(recs) >= 0.4):
            return "knowledge"
        return "other"
    if not cat:  # no watch-page data: fall back to title/channel heuristics
        if MUSIC_HINT.search(meta.get("title") or "") or MUSIC_CHANNEL.search(meta.get("channel") or ""):
            return "other"
        return "knowledge"
    return "knowledge"


STRONG_CUES = {"强烈推荐", "必看", "值得看", "值得一看", "最喜欢", "影响深远", "号召观看", "讲得清楚"}


def quote_rank(m):
    """Which recommendation to feature: explicit endorsement first, then readable length, then strength."""
    strong = len(STRONG_CUES & set(m["pos"]))
    n = len(m["quote"])
    readable = 1 if 60 <= n <= 450 else 0
    single = 1 if m.get("n_videos", 1) == 1 else 0
    return (-min(strong, 2), -readable, -single, -m["p"], m["t"])


def best_sentence(quote, limit=260):
    """Trim a quote to a readable snippet: prefer sentences carrying the endorsement."""
    q = re.sub(r"\s+", " ", quote).strip()
    if len(q) <= limit:
        return q
    cut = q[:limit]
    dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:dot + 1] if dot > limit * 0.5 else cut.rstrip() + "…")


def main():
    stats = json.load(open(os.path.join(DATA, "videos_stats.json")))
    yt = load_cache()
    want = set(stats)
    mentions = defaultdict(list)
    for line in gzip.open(os.path.join(DATA, "mentions.jsonl.gz"), "rt"):
        m = json.loads(line)
        if m["vid"] in want:
            mentions[m["vid"]].append(m)
    if os.path.exists(os.path.join(SITE, "v")):
        shutil.rmtree(os.path.join(SITE, "v"))
    os.makedirs(os.path.join(SITE, "v"), exist_ok=True)
    index = []
    for vid, st in stats.items():
        meta = yt.get(vid, {})
        ms = sorted(mentions[vid], key=lambda m: m["t"])
        recs = [m for m in ms if m["rec"] and not m.get("own_thread")]
        # strongest mention per author, ordered by strength, for the "why" quotes
        seen, quotes = set(), []
        for m in sorted(recs, key=quote_rank):
            if m["author"] in seen:
                continue
            seen.add(m["author"]); quotes.append(m)
        top = quotes[0] if quotes else None
        avail = meta.get("available")
        title = meta.get("title")
        item = {
            "id": vid, "t": title, "c": meta.get("channel"), "cat": meta.get("category"),
            "d": meta.get("duration"), "pub": (meta.get("published") or "")[:4] or None,
            "s": st["score"], "r": st["recommenders"], "th": st["threads"], "y": st["years"],
            "tp": st["topics"], "ci": st["citations"],
            "a": 1 if avail else 0, "k": kind_of(meta, quotes) if avail else "other",
            "q": {"x": best_sentence(top["quote"]), "u": top["author"], "yr": top["year"], "id": top["cid"]} if top else None,
        }
        index.append(item)
        detail = dict(item)
        detail["desc"] = meta.get("description")
        detail["recs"] = [{"id": m["cid"], "u": m["author"], "t": m["t"], "st": m["story_id"],
                           "stt": m["story_title"], "x": m["quote"], "p": m["p"], "cues": m["pos"],
                           "tp": m["topics"], "ai": m.get("llm")} for m in sorted(quotes, key=lambda m: m["t"])]
        detail["cites"] = [{"id": m["cid"], "u": m["author"], "t": m["t"], "stt": m["story_title"],
                            "x": best_sentence(m["quote"], 200), "neg": m["neg"]}
                           for m in ms if not m["rec"]][:40]
        json.dump(detail, open(os.path.join(SITE, "v", vid + ".json"), "w"), ensure_ascii=False, separators=(",", ":"))
    index.sort(key=lambda i: -i["s"])
    json.dump(index, open(os.path.join(SITE, "index.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    summary = json.load(open(os.path.join(DATA, "build_summary.json")))
    ev_path = os.path.join(DATA, "eval", "report.json")
    summary["eval"] = json.load(open(ev_path)) if os.path.exists(ev_path) else None
    llm_ev = os.path.join(DATA, "llm", "eval_report.json")
    summary["llm_eval"] = json.load(open(llm_ev)) if os.path.exists(llm_ev) else None
    summary["listed"] = len(index)
    summary["listed_available"] = sum(i["a"] for i in index)
    summary["exported_at"] = int(time.time())
    summary["repo"] = os.environ.get("SITE_REPO", "lcwLcw123/hn-video-picks")
    json.dump(summary, open(os.path.join(SITE, "meta.json"), "w"), ensure_ascii=False, indent=1)
    print({k: summary[k] for k in ("listed", "listed_available")})


if __name__ == "__main__":
    main()
