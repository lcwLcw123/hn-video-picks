"""Second opinion from Claude on comments the rule classifier scored just below the cutoff.

The rules are tuned for precision; they miss mildly worded recommendations
("nice video about it"). Here Claude re-reads borderline comments and labels each
strong / weak / no with a short reason. Runs through the Message Batches API (50% cheaper).

Usage (needs ANTHROPIC_API_KEY in the environment; the key is never written to disk):
  python3 pipeline/llm_rejudge.py eval          # 300 blind-labeled comments -> agreement report
  python3 pipeline/llm_rejudge.py borderline    # ~5,900 borderline comments -> data/llm/judgments.jsonl
  python3 pipeline/llm_rejudge.py borderline --dry-run   # show count + cost estimate only
A submitted batch id is saved, so re-running after an interruption resumes polling instead of resubmitting.
"""
import gzip, json, os, sys, time
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(ROOT, "llm")
MODEL = os.environ.get("REJUDGE_MODEL", "claude-opus-5-5")
BORDERLINE_P = 0.2  # rule probability floor for the borderline set (cutoff is 0.5)

SYSTEM = """You judge Hacker News comments that contain a YouTube link.

Decide whether the commenter is RECOMMENDING the linked video - vouching that it is worth someone's time to watch (quality, value, insight) - as opposed to merely linking it.

Labels:
- "strong": explicit endorsement ("great talk", "highly recommend", "worth watching", "one of my favorites", "if you haven't seen it, watch this", "best explanation of X").
- "weak": offered as a useful resource to learn from, with mild or implicit endorsement ("This talk covers it well", "Good intro here:", "Linus explains his reasoning in this talk:").
- "no": not a recommendation - citing evidence or a source, news clip or raw footage, joke/meme, music or entertainment for its own sake, the commenter's own video (self-promotion), criticism of the video, a question, a neutral pointer with no endorsement ("here's the video", "[link] for the lazy"), or too ambiguous to tell.

In the excerpt, every URL is replaced by [link]. If several links appear, judge the endorsement for the YouTube link the excerpt is about; in a list such as "my favourite talks: ...", the intro applies to each item.

Reply with JSON only: "label" and "reason", where reason is at most 20 Chinese characters explaining the decision."""

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["strong", "weak", "no"]},
        "reason": {"type": "string"},
    },
    "required": ["label", "reason"],
    "additionalProperties": False,
}


def user_msg(story_title, quote, n_videos=1):
    extra = f"\n(This comment links {n_videos} YouTube videos.)" if n_videos > 1 else ""
    return f"Thread title: {story_title or '(unknown)'}{extra}\n\nComment excerpt:\n{quote[:1500]}"


def items_eval():
    keys = [json.loads(l) for l in open(os.path.join(ROOT, "eval", "sample_keys.jsonl"))]
    return [{"key": f"eval-{k['i']}", "i": k["i"], "story_title": k["story_title"], "quote": k["quote"]} for k in keys]


def items_borderline():
    """Rule-negative mentions with p >= BORDERLINE_P, only for videos that at least two
    different people mentioned (otherwise one more vote can't put a video on the list)."""
    by_vid = defaultdict(list)
    for line in gzip.open(os.path.join(ROOT, "mentions.jsonl.gz"), "rt"):
        m = json.loads(line)
        if not m.get("own_thread"):
            by_vid[m["vid"]].append(m)
    out = []
    for vid, ms in by_vid.items():
        if len({m["author"] for m in ms}) < 2:
            continue
        for m in ms:
            if not m["rec"] and m["p"] >= BORDERLINE_P and "自我推广" not in m["neg"]:
                out.append({"key": f"{m['cid']}-{vid}", "cid": m["cid"], "vid": vid,
                            "story_title": m["story_title"], "quote": m["quote"], "n_videos": m.get("n_videos", 1)})
    return out


def estimate(items):
    chars = sum(len(SYSTEM) + len(it["quote"][:1500]) + len(it["story_title"] or "") + 80 for it in items)
    tok_in = chars / 3.5
    tok_out = len(items) * 250  # JSON + low-effort thinking, rough
    price_in, price_out = 4.0, 20.0  # $/MTok for claude-opus-5-5; batch = 50% off
    usd = (tok_in * price_in + tok_out * price_out) / 1e6 * 0.5
    return int(tok_in), int(tok_out), usd


def run(name, items, dry_run=False):
    os.makedirs(OUT, exist_ok=True)
    state_path = os.path.join(OUT, f"batch_{name}.json")
    result_path = os.path.join(OUT, f"results_{name}.jsonl")
    tin, tout, usd = estimate(items)
    print(f"{name}: {len(items)} comments, ~{tin:,} input / ~{tout:,} output tokens, est. ${usd:.2f} (model {MODEL}, batch pricing)")
    if dry_run:
        return None
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    by_key = {it["key"]: it for it in items}
    if os.path.exists(state_path):
        batch_id = json.load(open(state_path))["id"]
        print(f"resuming batch {batch_id}")
    else:
        system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
        reqs = [Request(custom_id=it["key"], params=MessageCreateParamsNonStreaming(
                    model=MODEL, max_tokens=2048, system=system,
                    output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                    messages=[{"role": "user", "content": user_msg(it["story_title"], it["quote"], it.get("n_videos", 1))}]))
                for it in items]
        batch = client.messages.batches.create(requests=reqs)
        batch_id = batch.id
        json.dump({"id": batch_id, "n": len(items), "model": MODEL, "created": int(time.time())}, open(state_path, "w"))
        print(f"submitted batch {batch_id}")

    while True:
        b = client.messages.batches.retrieve(batch_id)
        c = b.request_counts
        print(f"  {b.processing_status}: processing={c.processing} succeeded={c.succeeded} errored={c.errored}", flush=True)
        if b.processing_status == "ended":
            break
        time.sleep(30)

    n_ok = n_bad = 0
    usage = {"input": 0, "output": 0, "cache_read": 0}
    with open(result_path, "w") as f:
        for r in client.messages.batches.results(batch_id):
            it = by_key.get(r.custom_id)
            if it is None:
                continue
            if r.result.type != "succeeded":
                n_bad += 1
                continue
            msg = r.result.message
            usage["input"] += msg.usage.input_tokens
            usage["output"] += msg.usage.output_tokens
            usage["cache_read"] += msg.usage.cache_read_input_tokens or 0
            if msg.stop_reason == "refusal":
                n_bad += 1
                continue
            text = next((blk.text for blk in msg.content if blk.type == "text"), "")
            try:
                out = json.loads(text)
            except ValueError:
                n_bad += 1
                continue
            rec = {k: it[k] for k in ("key", "cid", "vid", "i") if k in it}
            rec.update(label=out["label"], reason=out["reason"][:60], model=MODEL)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_ok += 1
    print(f"{n_ok} judged, {n_bad} failed/refused -> {result_path}")
    print(f"tokens: input {usage['input']:,} (cache read {usage['cache_read']:,}), output {usage['output']:,}")
    return result_path


def report_eval(result_path):
    """Compare Claude with the blind labels; headline numbers on the held-out (odd) split."""
    sys.path.insert(0, os.path.dirname(__file__))
    from evaluate import load, predict
    gold = {it["i"]: it for it in load()}
    llm = {r["i"]: r for r in map(json.loads, open(result_path))}
    rep = {}
    for split, mod in (("dev", 0), ("test", 1)):
        ids = [i for i in gold if i % 2 == mod and i in llm]
        agree = sum(llm[i]["label"] == gold[i]["label"] for i in ids)
        pos = lambda lab: lab in ("strong", "weak")
        tp = sum(pos(llm[i]["label"]) and pos(gold[i]["label"]) for i in ids)
        pp = sum(pos(llm[i]["label"]) for i in ids)
        ap = sum(pos(gold[i]["label"]) for i in ids)
        # the combined system the site uses: rules, plus Claude on rule-negatives with p >= floor
        def combined(i):
            rule_pos, p, *_ = predict(gold[i])
            if rule_pos:
                return True
            return p >= BORDERLINE_P and pos(llm[i]["label"])
        ctp = sum(combined(i) and pos(gold[i]["label"]) for i in ids)
        cpp = sum(combined(i) for i in ids)
        rtp = sum(predict(gold[i])[0] and pos(gold[i]["label"]) for i in ids)
        rpp = sum(predict(gold[i])[0] for i in ids)
        rep[split] = {
            "n": len(ids), "exact_agreement": round(agree / len(ids), 3),
            "llm_precision": round(tp / pp, 3) if pp else None, "llm_recall": round(tp / ap, 3) if ap else None,
            "rules_precision": round(rtp / rpp, 3) if rpp else None, "rules_recall_in_sample": round(rtp / ap, 3) if ap else None,
            "combined_precision": round(ctp / cpp, 3) if cpp else None, "combined_recall_in_sample": round(ctp / ap, 3) if ap else None,
        }
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    json.dump(dict(rep, model=MODEL, borderline_p=BORDERLINE_P), open(os.path.join(OUT, "eval_report.json"), "w"), indent=1)
    print("note: 'recall_in_sample' is within the stratified sample (borderline-heavy), not population recall.")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    dry = "--dry-run" in sys.argv
    if what == "eval":
        path = run("eval", items_eval(), dry)
        if path:
            report_eval(path)
    elif what == "borderline":
        run("borderline", items_borderline(), dry)
    else:
        sys.exit(__doc__)
