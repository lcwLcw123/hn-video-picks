"""Aggregate recommendation mentions into a per-video quality score.

Design goals (see docs/METHODOLOGY.md):
  * Count *people*, not comments: each HN account counts once per video (its strongest mention).
  * Reward independence: several recommendations inside the same thread are damped
    (1, 1/2, 1/3, ...), because people in one thread influence each other.
  * Reward durability: recommendations spread over many distinct years get a bonus.
  * Reward breadth: recommendations surfacing in threads on different topics get a bonus.
  * Popularity, recency and click-appeal (views, publish date, thumbnails) are NOT inputs.
"""
import math
from collections import defaultdict


def aggregate(mentions):
    """mentions: list of dicts with keys author, story_id, year, p, rec, topics.
    Returns dict of stats incl. 'score'."""
    recs = [m for m in mentions if m["rec"] and not m.get("own_thread")]
    best = {}
    for m in recs:  # one vote per account
        a = m["author"]
        if a not in best or m["p"] > best[a]["p"]:
            best[a] = m
    votes = list(best.values())
    by_thread = defaultdict(list)
    for m in votes:
        by_thread[m["story_id"]].append(m["p"])
    s = 0.0
    for ps in by_thread.values():
        for k, p in enumerate(sorted(ps, reverse=True), 1):
            s += p / k
    years = sorted({m["year"] for m in votes})
    topics = set()
    for m in votes:
        topics.update(m.get("topics") or [])
    n_years = len(years)
    score = s * (1 + 0.35 * math.log(n_years)) * (1 + 0.15 * math.log(1 + len(topics))) if votes else 0.0
    return {
        "score": round(score, 3),
        "recommenders": len(votes),
        "threads": len(by_thread),
        "years": years,
        "span": (years[-1] - years[0]) if years else 0,
        "topics": sorted(topics),
        "mentions": len(mentions),
        "citations": len([m for m in mentions if not m["rec"]]),
    }
