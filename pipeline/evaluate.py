"""Evaluate the rule classifier against blind labels (data/eval/labels.jsonl).

The sample was stratified by the classifier's original prediction:
  P = random predicted-recommendation, N = random predicted-non-recommendation,
  B = extra borderline negatives (0.2 <= p < 0.5; error analysis only).
Weighted estimates use P and N with their population sizes. Items with even i are
the tuning ('dev') split, odd i the held-out 'test' split.
Usage: python3 pipeline/evaluate.py [dev|test|all] [--errors]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from classify import score_text, THRESHOLD

D = os.path.join(os.path.dirname(__file__), "..", "data", "eval")
POP = {"P": 9193, "N": 142459}  # stratum sizes at sampling time


def load():
    keys = {k["i"]: k for k in map(json.loads, open(os.path.join(D, "sample_keys.jsonl")))}
    labels = {l["i"]: l for l in map(json.loads, open(os.path.join(D, "labels.jsonl")))}
    return [dict(keys[i], label=labels[i]["label"], note=labels[i].get("note", "")) for i in sorted(labels)]


def predict(item):
    p, pos, neg = score_text(item["quote"])
    return p >= THRESHOLD and "自我推广" not in neg, p, pos, neg


def evaluate(items):
    n_in = {s: sum(1 for it in items if it["stratum"] == s) for s in POP}
    w = {s: POP[s] / n_in[s] if n_in[s] else 0 for s in POP}
    tp = fp = fn = tp_s = fn_s = 0.0
    pred_pos = 0
    raw_tp = raw_pp = 0
    for it in items:
        pred, *_ = predict(it)
        true_any = it["label"] in ("strong", "weak")
        if pred:
            raw_pp += 1; raw_tp += true_any
        if it["stratum"] not in POP:
            continue
        wt = w[it["stratum"]]
        if pred:
            pred_pos += wt
            if true_any: tp += wt
            else: fp += wt
            if it["label"] == "strong": tp_s += wt
        else:
            if true_any: fn += wt
            if it["label"] == "strong": fn_s += wt
    return {
        "n": len(items),
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "precision_strong": round(tp_s / (tp + fp), 3) if tp + fp else None,
        "recall_est": round(tp / (tp + fn), 3) if tp + fn else None,
        "recall_strong_est": round(tp_s / (tp_s + fn_s), 3) if tp_s + fn_s else None,
        "sample_precision_unweighted": round(raw_tp / raw_pp, 3) if raw_pp else None,
    }


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "test"
    items = load()
    if split == "dev": items = [i for i in items if i["i"] % 2 == 0]
    elif split == "test": items = [i for i in items if i["i"] % 2 == 1]
    print(split, json.dumps(evaluate(items), ensure_ascii=False))
    if "--errors" in sys.argv:
        for it in items:
            pred, p, pos, neg = predict(it)
            true_any = it["label"] in ("strong", "weak")
            if pred != true_any:
                kind = "FP" if pred else "FN"
                print(f"\n[{kind}] #{it['i']} label={it['label']} p={p:.2f} pos={pos} neg={neg} | {it['note']}\n  {it['quote'][:300]!r}")
    if "--save" in sys.argv:
        test = [i for i in load() if i["i"] % 2 == 1]
        r = evaluate(test); r["split"] = "held-out test (odd items)"
        r["strata"] = {}
        for s in "PNB":
            sub = [i for i in test if i["stratum"] == s]
            pp = [i for i in sub if predict(i)[0]]
            r["strata"][s] = {"n": len(sub), "pred_pos": len(pp), "pred_pos_true": sum(i["label"] != "no" for i in pp),
                              "pred_pos_strong": sum(i["label"] == "strong" for i in pp),
                              "true": sum(i["label"] != "no" for i in sub)}
        r["n_total_labeled"] = len(load())
        json.dump(r, open(os.path.join(D, "report.json"), "w"), indent=1)
