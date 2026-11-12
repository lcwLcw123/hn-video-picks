"""Decide whether a comment *recommends* a linked YouTube video (vs. merely citing it).

Transparent, rule-based scorer. Each cue has a weight; the sum is squashed into
[0, 1]. We keep the matched cues so the website can show *why* a comment was
counted as a recommendation. Evaluated against a blind hand-labeled sample
(see tests/labeled_sample.jsonl and pipeline/evaluate.py).
"""
import math, re

def _c(p):
    return re.compile(p, re.I)

# (label, weight, regex) -- positive cues: the commenter vouches for the video
POSITIVE = [
    ("强烈推荐", 3.0, _c(r"\b(highly|strongly|heartily|warmly|wholeheartedly|really|definitely|absolutely)\s+recommend|can'?t recommend\b.{0,25}\benough|cannot recommend\b.{0,25}\benough|recommend\b.{0,20}\bhighly")),
    ("推荐", 2.0, _c(r"\b(i|i'd|i would|i'll|we|would|also|personally)\s+(also\s+)?recommend|\brecommended (watching|viewing|talk|video|lecture)|\bmy recommendation|\brecommend(ed)? (watching|this|the following|checking)|\bi recommend|\bcan recommend|\bi suggest|\bsuggest(ed)? watching")),
    ("必看", 3.0, _c(r"\bmust[- ](watch|see)\b|\brequired (viewing|watching)\b|\bessential (viewing|watching)\b|\ba must\b|\bshould be required\b")),
    ("值得看", 2.5, _c(r"\b(well |really |totally |definitely |very much |absolutely )?worth (a |the |your )?(watch|watching|look|viewing|time|hour|minutes?|\d+ minutes)\b")),
    ("值得一看", 2.5, _c(r"\bworth (checking|seeing|a look|it)\b")),
    ("最喜欢", 1.9, _c(r"\b(my|all[- ]time|personal) (absolute )?(favou?rite|fave)s?\b|\bone of (the|my) (best|favou?rite|greatest|most (interesting|influential|important|insightful|enlightening))\b|\bthe best (talk|lecture|explanation|video|introduction|intro|presentation|documentary|thing)\b")),
    ("强力赞美", 2.4, _c(r"\b(excellent|great|fantastic|brilliant|amazing|awesome|wonderful|superb|terrific|outstanding|fascinating|phenomenal|incredible|beautiful|lovely|classic|seminal|legendary|famous|insightful|enlightening|eye[- ]opening|mind[- ]?blowing|mind[- ]bending|illuminating|delightful|informative|entertaining|inspiring|underrated|good|nice|interesting|helpful|accessible|approachable)\s+([\w'-]+\s+){0,3}[\w-]*?(talk|lecture|video|series|explanation|explainer|intro|introduction|overview|presentation|documentary|keynote|course|tutorial|interview|demo|walkthrough|episode|channel|playlist|speech|discussion|debate|panel|primer|example|resource)s?\b")),
    ("影响深远", 2.5, _c(r"\b(changed (my|the way|how)|blew my mind|blown away|opened my eyes|life[- ]changing|eye[- ]opener|stuck with me|still think about|i think about (it|this) (often|a lot)|rewatch|re-watch|watched (it )?(several|multiple|many|countless|\d+) times|watch (it )?(every|once a) (year|few)|come back to (it|this))")),
    ("号召观看", 2.3, _c(r"\b(you|everyone|everybody|anyone|people)\s+(should|must|need to|ought to|have to)\s+(really\s+)?(watch|see|check)|\bdo yourself a favou?r\b|\bif you (haven'?t|have not|never)\s+(already\s+|yet\s+|ever\s+)?(seen|watched)|\bif you (haven'?t|have not)\b.{0,40}\b(seen|watched)\b|\bif you('ve| have) got (an hour|time|\d+ minutes)|\bif you have (an hour|time|\d+ minutes)|\bgo watch\b|\byou should\s*:|\byou will be amazed|\byou won\'?t regret|\bhighly suggest|\bi('d| would)? suggest (watching|this)|\bstrongly suggest\b")),
    ("值得关注", 1.6, _c(r"\bcheck out\b|\bcheck (this|it) out\b|\bhave a look at\b|\btake a look at\b|\bworth noting\b|\blook up\b")),
    ("讲得清楚", 1.5, _c(r"\b(explains?|explained|covers?|covered|demonstrates?|describes?|walks? through|goes (over|through)|breaks? down|lays? out)\b.{0,60}\b(well|clearly|nicely|beautifully|brilliantly|perfectly|better than|really)\b|\bbest explanation\b|\b(clear|clearest|great|good|better) explanation\b|\bexplains it (best|better|well)\b")),
    ("知识型内容", 0.6, _c(r"\b(talk|lecture|lectures|keynote|presentation|course|documentary|series|conference|seminar|interview|explanation|tutorial|walkthrough|tech talk|class|professor|prof\.)\b")),
    ("个人喜爱", 1.8, _c(r"\b(i (really |absolutely )?(love|loved|enjoy|enjoyed|adore|like|liked)) (this|that|the|his|her|their|watching)\b|\b(great|good|excellent|fantastic|awesome|amazing|fascinating|wonderful|brilliant) (stuff|watch|resource|content)\b|\b(really|truly|very|super|quite) (interesting|fascinating|good|great|informative|enlightening|insightful)\b|\bfound (it|this) (fascinating|interesting|helpful|useful|enlightening|insightful)|\bhelped me\b|\bblew me away|\bblown away|\bnever fails to|\bthis is (great|gold|excellent|fantastic|amazing|brilliant|wonderful|fascinating)\b|\bgold(mine)?\b|\bgem\b|\btreasure\b")),
    ("推荐列表", 1.0, _c(r"\b(here are|some of) (some|a few|my) (favou?rite|good|great|recommended)|\bfavou?rite (talks|lectures|videos|channels)\b|\btalks? (i|that i) (recommend|love)")),
]

# negative cues: linking but not vouching (citing, joking, self-promo, criticizing, asking)
NEGATIVE = [
    ("自我推广", -4.0, _c(r"\b(i made|i created|i recorded|i gave (a|this) talk|i did a (talk|video)|i presented|my (own )?(youtube )?(channel|video|talk|presentation|lecture)\b|shameless(ly)? plug|self[- ]plug|disclaimer:? (i|this is mine)|(our|my) (company|startup)'?s? (video|channel)|we made (a|this) video|i('ve| have) (made|recorded|uploaded|posted) (a|some) videos?|i('m| am) the (author|creator|speaker))")),
    ("负面评价", -3.0, _c(r"\b(terrible|awful|horrible|garbage|nonsense|misleading|cringe(y|worthy)?|clickbait|propaganda|debunk(ed|ing|s)?|bullshit|crap|painful to watch|hard to watch|unwatchable|don'?t (bother|watch)|waste of (time|an hour)|disappointing|overrated|pseudo-?science|so wrong|is wrong|factually incorrect|scam)\b")),
    ("出处引用", -1.5, _c(r"^\s*(source|sources|citation|ref|reference|via|context|link|video|relevant|related|obligatory|also|see|example|e\.g\.|here)\s*:|\bsource:|\bhere'?s (the|a) (clip|video|link|footage|recording|source)\b|\b(footage|clip|news report|news segment|livestream|stream|trailer|ad|commercial|advert)\b")),
    ("玩笑梗", -2.0, _c(r"\b(lol|lmao|rofl|(ha){2,}h?|(he){2,}|rickroll|rick ?roll|obligatory|reminds me of (this|the))\b|\bmandatory\b|\bnsfw\b")),
    ("提问", -1.5, _c(r"\?\s*(?:\[link\][\s.]*)*\Z|\b(does anyone|has anyone|anyone (know|seen|have)|can someone|what (do you|does everyone) think|any idea)\b")),
    ("音乐娱乐", -1.0, _c(r"\b(song|songs|music video|album|track|band|lyrics|remix|cover version|dance|parody|meme|cat video|funny video|sketch|skit|comedy|standup|stand-up)\b")),
]

BIAS = -2.2  # a bare link with no cue lands well below 0.5


def score_text(context):
    """Return (probability, matched_positive_labels, matched_negative_labels)."""
    pos, neg, s = [], [], BIAS
    for label, w, rx in POSITIVE:
        if rx.search(context):
            pos.append(label); s += w
    for label, w, rx in NEGATIVE:
        if rx.search(context):
            neg.append(label); s += w
    # very short comment that is basically just a link: almost never a recommendation
    words = len(re.findall(r"[A-Za-z]{2,}", context))
    if words < 6 and not pos:
        s -= 1.0
    p = 1 / (1 + math.exp(-s))
    return p, pos, neg


THRESHOLD = 0.5


def is_recommendation(context):
    p, _, neg = score_text(context)
    return p >= THRESHOLD and "自我推广" not in neg
