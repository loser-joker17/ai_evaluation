import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from app.retrieval.corpus import search_corpus

from app.llm import llm

load_dotenv()
WEB_MODE = "always"  

# Official or near-official sources only. Check each domain still serves what you need.
TRUSTED_DOMAINS = [
    "indiacode.nic.in",
    "legislative.gov.in",
    "sci.gov.in",
    "prsindia.org",
    "pib.gov.in",
    "darpg.gov.in",
    "eci.gov.in",
    "loksabha.nic.in",
    "rajyasabha.nic.in",
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


def _cache_key(claim: str) -> str:
    return hashlib.sha1(_squash(claim).encode()).hexdigest()


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

def search_evidence(query: str, max_results: int = 4) -> list[dict]:
    sources = [
        {"url": s["url"], "text": s["text"], "tier": "notes"}
        for s in search_corpus(query, k=3)
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
- A claim that is partly right but imprecise is "unverifiable", not "contradicted".
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


def verify_claim(claim: str, query: str | None = None, use_cache: bool = True) -> dict:
    cache = _load_cache() if use_cache else {}
    key = _cache_key(claim)
    if key in cache:
        return cache[key]

    sources = search_evidence(query or claim)
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

def fact_check(answer: str) -> tuple[list[dict], list[str]]:
    """Extract checkable claims and verify each. Returns (verifications, evidence_gaps)."""
    verifications, gaps = [], []
    for c in extract_claims(answer):
        try:
            v = verify_claim(c["claim"], c["query"])
        except Exception as exc:                      # one failed search must not stop the rest
            gaps.append(f"Could not check: \"{c['claim'][:70]}\" ({type(exc).__name__}).")
            continue
        verifications.append(v)
        if not v["found_sources"]:
            gaps.append(f"No official source found for: \"{c['claim'][:70]}\".")
    return verifications, gaps