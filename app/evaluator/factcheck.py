import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from app.retrieval import corpus as _corpus
from app.retrieval.corpus import paper_from_subject, search_corpus

from app.llm import llm

load_dotenv()
WEB_MODE = "always"  

# Official or near-official sources only. Check each domain still serves what you need.
TRUSTED_DOMAINS = [
    # --- GS-1: History, Art & Culture, Geography ---
    "indiaculture.gov.in",   # Ministry of Culture (Schemes, archives, festivals)
    "ccrtindia.gov.in",      # Centre for Cultural Resources and Training (Definitive art & culture monographs)
    "gsi.gov.in",            # Geological Survey of India (Mineral resources, geographic mapping)
    "mausam.imd.gov.in",     # India Meteorological Department (Monsoon updates, climate trends)

    # --- GS-2: Polity, Governance, Constitution & IR ---
    "indiacode.gov.in",      # Updated from indiacode.nic.in due to site migration
    "legislative.gov.in",    # Ministry of Law & Justice (Acts, central bills)
    "sci.gov.in",            # Supreme Court of India (Landmark judgements, constitutional benches)
    "prsindia.org",          # PRS Legislative Research (Simplified bill summaries & legislative briefs)
    "pib.gov.in",            # Press Information Bureau (Official press releases & PIB Fact Check)
    "darpg.gov.in",          # Administrative Reforms & Public Grievances (e-Gov, ARC reports)
    "eci.gov.in",            # Election Commission of India (Electoral data, model code of conduct)
    "loksabha.nic.in",       # Parliament of India - Lok Sabha portal
    "rajyasabha.nic.in",     # Parliament of India - Rajya Sabha portal
    
    # --- GS-3: Economy, Budget, Banking & Science ---
    "incometaxindia.gov.in", # Central Board of Direct Taxes updates
    "indiabudget.gov.in",    # Union Budget documents & annual Economic Survey
    "rbi.org.in",            # Reserve Bank of India (Monetary policy, financial stability reports)
    "mospi.gov.in",          # Ministry of Statistics & Programme Implementation (GDP, CPI, IIP data)
    "dea.gov.in",            # Department of Economic Affairs (Capital markets, external debt reports)
    "niti.gov.in",           # NITI Aayog (Policy indices, state rankings, SDG tracking dashboards)
    "isro.gov.in",           # Indian Space Research Organisation (Space missions, satellite data)

    # --- GS-3: Environment, Forest & Climate Change ---
    "moef.gov.in",           # Ministry of Environment, Forest and Climate Change (Forest surveys, wildlife census)
    "cpcb.nic.in",           # Central Pollution Control Board (AQI data, environmental regulations)
    "wii.gov.in",            # Wildlife Institute of India (Endangered species, conservation statuses)
]


MAX_CLAIMS = 5
MIN_CLAIM_WORDS = 4
CACHE_PATH = Path("data/cache/factcheck.json")

_client = None


# ------------------------------------------------------------ schemas

class ExtractedClaim(BaseModel):
    claim: str = Field(description="Exact words from the answer, at least 4 words")
    query: str = Field(description="Short web search query to check this claim")


class ExtractedClaims(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


class Verdict(BaseModel):
    label: Literal["supported", "contradicted", "unverifiable"]
    quote: str | None = None   # exact passage copied from a SOURCE
    explanation: str


# ------------------------------------------------------------ helpers

def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _tavily():
    global _client
    if _client is None:
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            raise RuntimeError("TAVILY_API_KEY is missing. Check your .env file.")
        from tavily import TavilyClient
        _client = TavilyClient(api_key=key)
    return _client


def _corpus_version() -> str:
    """Changes whenever the notes index or the tag manifest changes, so a verdict cached
    before the corpus grew is not reused."""
    parts = []
    for f in (_corpus.CACHE_FILE, _corpus.MANIFEST_FILE):
        try:
            st = f.stat()
            parts.append(f"{st.st_size}:{int(st.st_mtime)}")
        except OSError:
            parts.append("none")
    return "|".join(parts)


def _cache_key(claim: str, papers: list[str] | None = None) -> str:
    raw = f"{_squash(claim)}||{','.join(papers or [])}||{_corpus_version()}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


# ----------------------------------------------------- claim extraction

def extract_claims(answer: str) -> list[dict]:
    structured = llm.with_structured_output(ExtractedClaims)

    prompt = f"""
You select checkable factual claims from a UPSC answer. You do NOT judge them.

ANSWER:
{answer}

List up to {MAX_CLAIMS} claims that can be checked against an official source:
claims about a named case, judgment, Article, Act, Amendment, committee,
scheme, year or number, and what each of them says or did.

For each claim:
- claim: copy the sentence or phrase WORD FOR WORD from the answer
  (at least {MIN_CLAIM_WORDS} words).
- query: a short web search query (under 12 words) to check it.

Do NOT include: opinions, reform suggestions, generic statements, predictions,
or sentences with no named legal or institutional fact.
Prefer claims that look doubtful or surprising over obvious ones.
If there are none, return an empty list.
"""
    raw = structured.invoke(prompt).model_dump()["claims"]

    haystack = _squash(answer)
    seen: set[str] = set()
    claims: list[dict] = []
    for c in raw:
        text = (c.get("claim") or "").strip()
        key = _squash(text)
        if len(text.split()) < MIN_CLAIM_WORDS or key in seen or key not in haystack:
            continue
        seen.add(key)
        claims.append({"claim": text, "query": (c.get("query") or text)[:200]})
    return claims[:MAX_CLAIMS]


# ------------------------------------------------------------ search

def search_evidence(query: str, max_results: int = 4, papers: list[str] | None = None) -> list[dict]:
    extra = {"papers": papers} if papers else {}     # a paper filter falls back to all notes if empty
    sources = [
        {"url": s["url"], "text": s["text"], "tier": "notes"}
        for s in search_corpus(query, k=3, **extra)
    ]
    if WEB_MODE == "always" or not sources:
        try:
            res = _tavily().search(
                query=query, include_domains=TRUSTED_DOMAINS, max_results=max_results
            )
            sources += [
                {"url": r["url"], "text": r.get("content", ""), "tier": "official"}
                for r in res.get("results", [])
                if r.get("content")
            ]
        except Exception:
            if not sources:
                raise
    return sources

# ------------------------------------------------------- verification

def _judge(claim: str, sources: list[dict]) -> tuple[str, str | None, str, bool]:
    context = "\n\n".join(
        f"[{i}] ({s['tier']}) {s['url']}\n{s['text']}" for i, s in enumerate(sources)
    )
    prompt = f"""
Decide whether the SOURCES support or contradict the CLAIM.

CLAIM: {claim}

SOURCES (tier "official" = government or court websites; tier "notes" = study notes):
{context}

RULES:
- Use ONLY the sources. Ignore your own memory.
- "supported" or "contradicted" requires an exact quote copied from a source.
- If the sources do not address this specific claim, or you are unsure,
  answer "unverifiable".
- A claim that is partly right but imprecise (rounded, approximate, loosely
  worded) is "unverifiable", not "contradicted".
- Exception: a specific number, rate, year, name or attribution that a source
  states differently IS "contradicted", even if the rest of the claim is right
  (e.g. claim "corporate tax cut to 25%", source "reduced to 22%").
- "contradicted" only if a source directly states something incompatible.
- Study notes can be simplified or wrong, so prefer an official source for
  any contradiction.
- explanation: one sentence.
"""
    v = llm.with_structured_output(Verdict).invoke(prompt)

    label, note_only = v.label, False
    if label != "unverifiable":
        pool = _squash(" ".join(s["text"] for s in sources))
        if not v.quote or _squash(v.quote) not in pool:
            label = "unverifiable"
            v.explanation = "The judge's quote was not found in the retrieved text."
    if label == "contradicted":
        official = _squash(" ".join(s["text"] for s in sources if s["tier"] == "official"))
        if _squash(v.quote) not in official:
            label, note_only = "unverifiable", True   # only study notes disagree
    return label, v.quote, v.explanation, note_only


def verify_claim(claim: str, query: str | None = None, use_cache: bool = True,
                 papers: list[str] | None = None) -> dict:
    cache = _load_cache() if use_cache else {}
    key = _cache_key(claim, papers)
    if key in cache:
        return cache[key]

    sources = search_evidence(query or claim, **({"papers": papers} if papers else {}))
    official_urls = [s["url"] for s in sources if s["tier"] == "official"]
    result = {
        "claim": claim, "query": query or claim, "label": "unverifiable",
        "quote": None, "explanation": "",
        # Only official URLs are exposed. Study-notes names never reach student feedback.
        "sources": official_urls,
        "notes_used": sum(1 for s in sources if s["tier"] == "notes"),
        "found_sources": bool(sources),
        "note_disagrees": False,
    }

    if sources:
        label, quote, why, note_only = _judge(claim, sources)

        # A false "contradicted" is the worst failure, so confirm it a second time
        # with the sources in reverse order.
        if label == "contradicted":
            label2 = _judge(claim, list(reversed(sources)))[0]
            if label2 != "contradicted":
                label, why = "unverifiable", "Contradiction was not confirmed on recheck."

        result.update(
            label=label,
            quote=quote if label != "unverifiable" else None,
            explanation=why,
            note_disagrees=note_only,
        )

    if use_cache:
        cache[key] = result
        _save_cache(cache)
    return result

def fact_check(answer: str, subject: str | None = None) -> tuple[list[dict], list[str]]:
    """Extract checkable claims and verify each. Returns (verifications, evidence_gaps)."""
    verifications, gaps = [], []
    paper = paper_from_subject(subject)               # "GS-2" -> "GS2"; None if not recognised
    extra = {"papers": [paper]} if paper else {}
    for c in extract_claims(answer):
        try:
            v = verify_claim(c["claim"], c["query"], **extra)
        except Exception as exc:                      # one failed search must not stop the rest
            gaps.append(f"Could not check: \"{c['claim'][:70]}\" ({type(exc).__name__}).")
            continue
        verifications.append(v)
        if not v["found_sources"]:
            gaps.append(f"No official source found for: \"{c['claim'][:70]}\".")
    return verifications, gaps