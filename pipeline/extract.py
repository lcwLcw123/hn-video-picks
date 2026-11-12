"""Parse HN comment HTML: plain text, YouTube video IDs, and the text around each link."""
import html, re

YT_PATTERNS = [
    r"(?:https?://|//|\b)(?:www\.|m\.|music\.)?youtube\.com/watch\?(?:[^\s\"'<>]*?&(?:amp;)?)?v=([A-Za-z0-9_-]{11})",
    r"(?:https?://|//|\b)(?:www\.|m\.)?youtube\.com/(?:embed|v|shorts|live)/([A-Za-z0-9_-]{11})",
    r"(?:https?://|//|\b)(?:www\.)?youtube-nocookie\.com/embed/([A-Za-z0-9_-]{11})",
    r"(?:https?://|//|\b)youtu\.be/([A-Za-z0-9_-]{11})",
]
YT_RE = re.compile("|".join(YT_PATTERNS), re.I)
TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r'<a\s+href="([^"]*)"[^>]*>.*?</a>', re.I | re.S)


def to_text(comment_html):
    """HN comment HTML -> plain text, with links replaced by their href."""
    s = comment_html or ""
    s = HREF_RE.sub(lambda m: " " + html.unescape(m.group(1)) + " ", s)
    s = re.sub(r"<p>", "\n\n", s, flags=re.I)
    s = TAG_RE.sub("", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", s).strip()


def video_ids(text):
    """Ordered unique YouTube IDs in text."""
    seen, out = set(), []
    for m in YT_RE.finditer(text):
        vid = next(g for g in m.groups() if g)
        if vid not in seen:
            seen.add(vid); out.append(vid)
    return out


def link_spans(text):
    """[(video_id, start, end)] for every YouTube link occurrence."""
    return [(next(g for g in m.groups() if g), m.start(), m.end()) for m in YT_RE.finditer(text)]


def strip_urls(text):
    return re.sub(r"(?:https?://|\b(?:www\.)?youtu)\S+", "[link]", text)


def context_for(text, vid, width=280):
    """Text near the first occurrence of vid (URLs replaced), for cue detection and quoting."""
    spans = [s for s in link_spans(text) if s[0] == vid]
    if not spans:
        return strip_urls(text)[:width * 2]
    _, a, b = spans[0]
    # take the paragraph containing the link plus the previous paragraph
    before = text[:a]
    para_start = before.rfind("\n\n")
    prev_start = before.rfind("\n\n", 0, max(para_start, 0)) if para_start > 0 else -1
    start = max(prev_start, 0, a - width * 2)
    after = text[b:]
    para_end = after.find("\n\n")
    end = b + (para_end if 0 <= para_end < width * 2 else min(len(after), width))
    return strip_urls(text[start:end]).strip()
