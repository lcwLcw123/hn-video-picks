"""Keyword taxonomy used to tag HN thread titles and video titles with broad topics."""
import re

TOPICS = {
    "编程与软件": r"program|programm|code|coding|software|compiler|language|python|rust|golang|\bgo\b|javascript|typescript|java\b|haskell|lisp|clojure|scheme|erlang|elixir|c\+\+|\bc\b|git\b|linux|unix|kernel|database|sql|postgres|api|web|browser|framework|react|emacs|vim|devops|debug|algorithm|data structure|open source|github|functional|concurrency|distributed|refactor|testing|architecture",
    "AI 与机器学习": r"\bai\b|artificial intelligence|machine learning|\bml\b|neural|deep learning|\bllm|gpt|transformer|openai|chatgpt|reinforcement|computer vision|robot|anthropic|claude|diffusion",
    "数学": r"math|mathemat|theorem|proof|algebra|geometry|calculus|topology|prime|number theory|statistics|probability|equation|fourier|category theory|logic|godel|gödel",
    "物理与太空": r"physic|quantum|relativity|einstein|particle|cosmolog|astronom|space|nasa|rocket|spacex|orbit|planet|mars|moon|telescope|black hole|universe|galaxy|satellite|apollo",
    "硬件与电子": r"hardware|cpu|gpu|chip|semiconductor|transistor|electronic|circuit|fpga|arduino|raspberry|microcontroller|risc|x86|arm\b|intel|amd|nvidia|silicon|keyboard|solder|oscilloscope|retro ?comput|6502|z80",
    "安全与隐私": r"security|hack|exploit|vulnerab|encrypt|crypto(graphy)?\b|privacy|surveillance|nsa|malware|password|cyber|attack|breach",
    "历史": r"histor|ancient|medieval|war\b|wwii|world war|empire|century|1[0-8][0-9]{2}s\b|archaeolog|civilization",
    "商业与创业": r"startup|founder|business|company|ceo|venture|vc\b|investor|y combinator|\byc\b|market|sales|management|career|hiring|job\b|remote work|productiv|entrepreneur",
    "经济与金融": r"econom|finance|money|inflation|bank|bitcoin|crypto ?currenc|stock|tax|wealth|price|trade|monetary|debt|gdp",
    "生物与医学": r"biolog|medic|health|disease|cancer|brain|neuro|dna|gene|evolution|virus|covid|vaccine|drug|sleep|diet|nutrition|cell|protein|aging",
    "心理与哲学": r"psycholog|philosoph|mind|conscious|happiness|meaning|ethic|moral|thinking|cognit|behavio|motivation|attention|habit|stoic",
    "工程与制造": r"engineer|manufactur|machin|factory|3d print|cnc|bridge|aviation|aircraft|plane|car\b|cars\b|tesla|engine|nuclear|reactor|material|metal|build|construction|ship",
    "能源与气候": r"energy|solar|battery|climate|carbon|oil|electric|grid|wind|power plant|fusion|emission|weather",
    "设计与创意": r"design|ux\b|user interface|\bui\b|typograph|font|art\b|music|film|animation|photograph|game design|creative|writing|book",
    "社会与政策": r"politic|government|law\b|legal|court|police|policy|regulation|democra|election|education|school|university|city|cities|urban|housing|transit|society|culture|media|journal",
    "游戏": r"\bgame|gaming|nintendo|speedrun|minecraft|doom|quake|playstation|xbox",
}
_RX = {k: re.compile(r"\b(?:" + v + ")", re.I) for k, v in TOPICS.items()}


def tag(text, limit=3):
    text = text or ""
    hits = [(k, len(rx.findall(text))) for k, rx in _RX.items()]
    hits = [h for h in hits if h[1] > 0]
    hits.sort(key=lambda h: -h[1])
    return [k for k, _ in hits[:limit]]
