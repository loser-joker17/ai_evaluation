"""What a question demands, and code caps when the answer leaves a demand out.

1. Directives. Every directive word in the question is found (a question often has two,
   e.g. "Define X and discuss Y"), each with what UPSC expects from it. The judge sees
   this list, so it judges the answer against what was asked, not a generic standard.

2. Demand check. The judge is given numbered demands:
     Q1, Q2 ...  the parts the question explicitly asks (from the question analysis)
     D1, D2 ...  demands implied by the directives (e.g. "to what extent" needs the
                 other side and a verdict)
   and returns covered / thin / missing for each. The code then caps levels:
     a question part missing  -> coverage and relevance at most 3 (2+ missing: coverage 2)
     a question part thin     -> coverage at most 3
     a key directive demand missing (other side, verdict, definition, comparison on
       both sides) -> the dimension that demand belongs to, at most 3
   The judge only reports what it sees; the code decides the cap, so the rule is applied
   the same way every time, and the feedback names the missing demand.

Old saved runs have no demand check, so --replay is unaffected by section 2.
"""
import re

# Priority when a question has several directives: the most demanding one decides
# which analysis rubric is used.
KIND_PRIORITY = ("judgement", "analytical", "balanced", "descriptive")

# (key, regex, kind, what it demands, implied demands)
# implied demand: (text, dimension to cap if missing, or None for feedback only)
# For "to what extent / do you agree / assess / comment" the other side and the verdict
# are feedback only (cap None): examiners accept a short "however / other factors" part
# and a position implied by the conclusion, and still give such answers top marks
# (ForumIAS GS-1 Kidfluencers 6.75/15, GS-4 parenting bias 5/10).
_JUDGE_SIDES = ("points on the other side (limitations, gaps or arguments against), "
                "even briefly", None)
_JUDGE_VERDICT = ("a position or verdict on the extent or view asked (it may be implied "
                  "by the conclusion)", None)

DIRECTIVES = [
    ("critically", r"\bcritically\s+(?:examine|analy[sz]e|evaluate|comment|discuss|assess)\b", "judgement",
     "weigh both merits and demerits, point out gaps or contradictions, and reach a fair, "
     "balanced judgement (a mature middle path); praise alone or criticism alone loses marks",
     [("both merits and demerits (gaps, flaws or limitations as well as strengths)", "analysis_depth"),
      ("a balanced, reasoned conclusion", None)]),
    ("to what extent", r"\bto what extent\b|\bhow far\b|\bto what degree\b", "judgement",
     "explore how far the statement holds: arguments for and against, ending with how much "
     "you agree",
     [_JUDGE_SIDES, _JUDGE_VERDICT]),
    ("do you agree", r"\bdo you agree\b|\byour (?:opinion|view)\b|\bdo you think\b", "judgement",
     "take a clear position and support it, acknowledging the other view",
     [_JUDGE_SIDES, ("a position on the view (it may be implied by the conclusion)", None)]),
    ("evaluate", r"\bevaluate\b|\bassess\b|\bappraise\b", "judgement",
     "judge the value, success or impact on evidence: achievements and shortfalls, then a "
     "reasoned verdict",
     [("evidence of both achievements and shortfalls", None), _JUDGE_VERDICT]),
    ("comment", r"\bcomment\b|\bjustif(?:y|ied)\b", "judgement",
     "state a clear view on the statement and support it with reasons, facts or examples",
     [("a view on the statement, supported by reasons or facts", None)]),
    ("analyse", r"\banaly[sz]e\b", "analytical",
     "break the topic into its parts and examine how they relate: causes, effects and "
     "implications",
     [("causes, effects or implications explained, not only listed", None)]),
    ("explain", r"\bexplain\b|\baccount for\b|\bwhy\b", "balanced",
     "clarify the details, causes and effects or the working mechanism",
     []),
    ("discuss", r"\bdiscuss\b", "balanced",
     "a multi-dimensional view covering the relevant aspects, ending with a brief balanced "
     "conclusion or way forward",
     [("more than one dimension of the issue", None)]),
    ("suggest", r"\bsuggest\b|\bpropose\b|\brecommend\b|\bway forward\b|"
                r"\bwhat (?:steps|measures)\b|\bhow (?:can|should|could)\b|\bwhat can (?:one|be|we)\b",
     "balanced",
     "concrete, workable measures tied to the problems identified",
     [("specific, workable measures (not only general intentions)", None)]),
    ("examine", r"\bexamine\b|\breview\b|\binvestigate\b", "balanced",
     "a close look at the issue, testing its assumptions, evidence and arguments",
     []),
    ("compare", r"\bcompare\b|\bcontrast\b|\bdistinguish\b|\bdifferentiate\b|\bdifferences?\s+between\b",
     "descriptive",
     "similarities and/or differences on common parameters, ideally point-wise or as a table",
     [("points for each side on common parameters", "coverage_balance")]),
    ("define", r"\bdefine\b|\bwhat do you understand by\b|\bmeaning of\b|\bwhat (?:is|are) (?!the\b|its\b|their\b|your\b)(?:[\w'()\-]+\s?){1,6}\?", "descriptive",
     "a clear, precise and concise meaning of the term or concept",
     [("a precise definition or meaning of the term asked", "coverage_balance")]),
    ("elaborate", r"\belaborate\b|\belucidate\b", "descriptive",
     "expand the statement with detailed arguments, data or context",
     []),
    ("illustrate", r"\billustrate\b|\bwith (?:suitable |relevant )?examples\b", "descriptive",
     "make the points with concrete examples, case studies, data or diagrams",
     [("concrete examples", "content_substantiation")]),
    ("enumerate", r"\benumerate\b|\blist\b|\benlist\b|\boutline\b|\bidentify\b",
     "descriptive",
     "clean, point-wise, structured points without long prose",
     []),
    ("describe", r"\bdescribe\b|\bhighlight\b|\btrace\b|\bbring out\b", "descriptive",
     "specific, well-illustrated points on what is asked",
     []),
]
_COMPILED = [(k, re.compile(rx, re.I), kind, demand, implied) for k, rx, kind, demand, implied in DIRECTIVES]


def find_directives(*texts) -> list[dict]:
    """All directives in the texts, in order of first appearance, without duplicates.
    "critically examine" is reported once (as critically), not also as "examine"."""
    text = " ".join(str(t or "") for t in texts)
    found, taken = [], []
    for key, rx, kind, demand, implied in _COMPILED:
        for m in rx.finditer(text):
            if any(s <= m.start() < e for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            if all(f["key"] != key for f in found):
                found.append({"key": key, "kind": kind, "demand": demand,
                              "implied": implied, "pos": m.start()})
    return sorted(found, key=lambda f: f["pos"])


def question_directives(question: str = "", directive: str = "") -> list[dict]:
    """Directives written in the question. The extracted directive (from the question
    analysis model) is used only when the question text has none, because the model
    sometimes reduces "to what extent ..." to a generic "Examine"."""
    return find_directives(question) or find_directives(directive)


def directive_kind(directive="", question="") -> str:
    """Which analysis rubric applies: the most demanding directive found decides."""
    kinds = {f["kind"] for f in question_directives(question, directive)}
    for k in KIND_PRIORITY:
        if k in kinds:
            return k
    return "balanced"


def directive_guide(question: str, directive: str = "") -> str:
    """Prompt text: what each directive in this question demands."""
    # Only directives actually written in the question. A directive guessed by the
    # question-analysis model is never turned into extra demands.
    found = find_directives(question)
    if not found:
        return ("THIS QUESTION HAS NO DIRECTIVE WORD (such as discuss, examine, critically "
                "analyse). Judge the answer only against the questions it asks (listed in the "
                "demand check). Do not expect a way forward, challenges, both sides or a verdict "
                "unless the question itself asks for them.")
    lines = ["WHAT THE QUESTION'S DIRECTIVES DEMAND (judge the answer against these):"]
    for f in found:
        lines.append(f'- "{f["key"]}": {f["demand"]}.')
    if len(found) > 1:
        lines.append("- This question combines several directives: every one of them must be "
                     "answered. A directive that gets no treatment is a missing demand.")
    if any(f["kind"] == "judgement" for f in found):
        lines.append("- For these judgement directives a stance may be implied by the "
                     "conclusion (a summing-up or a solution), and a short 'however / other "
                     "factors' paragraph counts as the other side. Do not lower relevance or "
                     "coverage_balance because an explicit verdict sentence is missing; at most "
                     "mention it in the improvement text.")
    lines.append("- Do not ask for anything a directive does not demand (for example, causal "
                 "mechanisms for a 'to what extent' or 'highlight' question).")
    return "\n".join(lines)


# Parts the question-analysis model sometimes adds that the question does not ask as a
# part of its own: the directive restated as a task ("State whether you agree", "Make a
# reasoned assessment of the extent", "Analyse the relationship" for a question that never
# says analyse) or a side the question does not mention ("Identify limitations" for
# "assess the potential of X"). They are handled, softly, by the directive demands; as
# question parts they were penalised up to three times (part share, demand check, directive).
_META_PART_RX = re.compile(
    r"agree or disagree|whether (?:you|one) agree|\byour (?:stance|position|view|opinion)\b|"
    r"\b(?:verdict|stance)\b|reasoned (?:assessment|judg|conclusion|verdict)|"
    r"overall (?:assessment|judg|verdict|evaluation)|assessment of the extent|"
    r"(?:state|give|take|provide|offer|make|reach|arrive at|express) (?:a |an |the |your )?"
    r"(?:clear )?(?:position|judg(?:e)?ment|conclusion|opinion)",
    re.I,
)
_SIDE_WORDS = {
    "limitation": "limitation", "challenge": "challenge", "drawback": "drawback",
    "shortcoming": "shortcoming", "criticism": "critic", "concern": "concern",
    "counter": "counter", "gap": "gap", "example": "example", "case stud": "case stud",
    "way forward": "way forward", "measure": "measure", "suggest": "suggest",
    "recommend": "recommend", "definition": "defin", "define": "defin",
    "empirical": "empirical", "data": "data", "evidence": "evidence",
}


# A "question part" the question text does not support: the question-analysis model
# sometimes breaks a one-line question ("... Analyze.") into detailed sub-parts of its
# own ("identify features (scale, targets, domains)", "contrast with previous
# responses"). Answers were then capped for "missing" parts nobody asked for.
# A part is ungrounded when most of its content words never appear in the question.
# Questions that already ask several things (2+ question marks, lettered sub-parts as in
# case studies) are left alone: there the parts come straight from the question.
_GENERIC_WORDS = set("""
identify explain discuss describe analyze analyse examine evaluate assess elaborate highlight
provide propose suggest list enumerate state outline trace illustrate interpret relate link
justify comment critically critical give present bring mention cite show demonstrate
key main major principal various certain specific relevant important significant suitable
concrete role nature scope concept concepts idea statement claim phenomenon question answer
context light view aspect aspects factor factors issue issues current recent overall broader
each both these those this that their there which with from into about such more most also
other others between within without india indian country nation ways help helps through
across being been have will would could should difference differences distinction similarities
two three following given above taken
""".split())


def _content_words(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z-]+", text.lower().replace("\u2019", "'").replace("'s", ""))
    return [w for w in words if len(w) >= 4 and w not in _GENERIC_WORDS]


def is_grounded_part(part: str, question: str) -> bool:
    if not question:
        return True
    if question.count("?") >= 2 or re.search(r"(?:^|\n)\s*[a-e][.)]\s", question):
        return True
    words = _content_words(part)
    if len(words) < 3:
        return True
    q_stems = {w[:5] for w in re.findall(r"[a-z][a-z-]+", question.lower())}
    hits = sum(w[:5] in q_stems for w in words)
    return hits / len(words) >= 0.34


def is_meta_part(part: str, question: str = "") -> bool:
    """True if a 'question part' is really the directive restated, adds a side or
    element the question text never mentions, or is mostly words the question never uses."""
    p, q = str(part or "").lower(), str(question or "").lower()
    if not p:
        return False
    if _META_PART_RX.search(p):
        return True
    if re.match(r"\s*analy[sz]e\b", p) and q and not re.search(r"\banaly[sz]", q):
        return True
    if q:
        for word, stem in _SIDE_WORDS.items():
            if word in p and stem not in q:
                return True
        if not is_grounded_part(part, question):
            return True
    return False


def build_demands(question: str, question_analysis: dict | None) -> list[dict]:
    """Numbered demands for the judge to check. Q = asked by the question, D = implied
    by a directive. 'cap' is the dimension capped at 3 when a D demand is missing."""
    qa = question_analysis if isinstance(question_analysis, dict) else {}
    parts = [str(p).strip() for p in (qa.get("question_parts") or []) if str(p).strip()]
    parts = [p for p in parts if not is_meta_part(p, question)]
    if not parts:
        parts = [question.strip()]
    demands = [{"id": f"Q{i}", "text": p, "source": "question", "cap": None}
               for i, p in enumerate(parts[:6], 1)]
    n = 0
    seen = set()
    for f in find_directives(question):    # written in the question only, never guessed
        for text, cap in f["implied"]:
            if text in seen:
                continue
            seen.add(text)
            n += 1
            demands.append({"id": f"D{n}", "text": text, "source": "directive", "cap": cap})
    return demands


def demand_block(demands: list[dict]) -> str:
    """Prompt text: the demand check the judge must fill in."""
    if not demands:
        return ""
    lines = ["DEMAND CHECK (fill demand_check with exactly one entry per id below):"]
    lines += [f"{d['id']}: {d['text']}" for d in demands]
    lines += [
        "For each id set status:",
        '  "covered" - the answer gives this at least one clear, specific treatment',
        '  "thin"    - only a passing, one-line or generic mention',
        '  "missing" - the answer does not address it at all',
        "evidence: a short exact quote from the answer for covered/thin, empty for missing.",
        "Judge only what is written. A demand the question did not ask is not listed here, so",
        "do not mark the answer down elsewhere for it. Use this check when you set relevance",
        "and coverage_balance, and name any missing or thin demand in the improvement text.",
    ]
    return "\n".join(lines)


def _short(text: str, n: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


def _current_cap(text: str):
    """The cap the CURRENT directive table gives an implied demand (saved runs may carry
    an older cap; --replay should apply today's rules)."""
    for _k, _rx, _kind, _demand, implied in DIRECTIVES:
        for t, cap in implied:
            if t == text:
                return cap
    return None


def demand_caps(demands: list[dict] | None, demand_check: list | None,
                question: str = "") -> dict[str, tuple[int, str]]:
    """Caps from the judge's demand check. No check (old saved runs) -> no caps.
    Question parts that only restate the directive (see is_meta_part) never cap, and
    directive demands use the current table's cap, so saved runs replay under today's rules."""
    if not demands or not demand_check:
        return {}
    demands = [
        {**d, "cap": _current_cap(d["text"])} if d.get("source") == "directive" else d
        for d in demands
        if not (d.get("source") == "question" and is_meta_part(d.get("text", ""), question))
    ]
    by_id = {d["id"]: d for d in demands}
    status = {}
    for item in demand_check:
        get = item.get if isinstance(item, dict) else (lambda k, _i=item: getattr(_i, k, None))
        did, st = str(get("id") or "").strip().upper(), str(get("status") or "").strip().lower()
        if did in by_id and st in ("covered", "thin", "missing"):
            status[did] = st

    caps: dict[str, tuple[int, str]] = {}

    def add(dim, level, note):
        if dim in caps:
            caps[dim] = (min(caps[dim][0], level), f"{caps[dim][1]} {note}")
        else:
            caps[dim] = (level, note)

    q_missing = [by_id[i] for i, s in status.items() if s == "missing" and by_id[i]["source"] == "question"]
    q_thin = [by_id[i] for i, s in status.items() if s == "thin" and by_id[i]["source"] == "question"]
    if q_missing:
        names = "; ".join(f'"{_short(d["text"])}"' for d in q_missing)
        add("coverage_balance", 2 if len(q_missing) >= 2 else 3,
            f"The question asks for {names}, which the answer does not address.")
        add("relevance", 3, f"Part of the question is not answered: {names}.")
    if q_thin:
        names = "; ".join(f'"{_short(d["text"])}"' for d in q_thin)
        add("coverage_balance", 3, f"Only a brief mention of {names}; give it proper treatment.")
    for i, s in status.items():
        d = by_id[i]
        if s == "missing" and d["source"] == "directive" and d["cap"]:
            add(d["cap"], 3, f"The directive needs {d['text']}, which is missing.")
    return caps

def answered_share(demands: list[dict] | None, demand_check: list | None,
                   question: str = "") -> tuple[float | None, dict]:
    """Share of the question's own parts the answer deals with: covered = 1, thin = 0.5,
    missing = 0, averaged over the question parts (directive demands and meta parts are
    left out). None when there is no check (old saved runs) or no question parts."""
    if not demands or not demand_check:
        return None, {}
    parts = {d["id"]: d for d in demands
             if d.get("source") == "question" and not is_meta_part(d.get("text", ""), question)}
    status = {}
    for item in demand_check:
        get = item.get if isinstance(item, dict) else (lambda k, _i=item: getattr(_i, k, None))
        did, st = str(get("id") or "").strip().upper(), str(get("status") or "").strip().lower()
        if did in parts and st in ("covered", "thin", "missing"):
            status[did] = st
    if not status:
        return None, {}
    value = {"covered": 1.0, "thin": 0.5, "missing": 0.0}
    share = sum(value[s] for s in status.values()) / len(status)
    return share, {parts[i]["text"]: s for i, s in status.items()}