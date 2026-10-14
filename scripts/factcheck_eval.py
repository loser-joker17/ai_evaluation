"""Fact-check test set with known answers. Run from the project root:

    python scripts\\factcheck_eval.py --limit 6          # quick look (first 6 claims)
    python scripts\\factcheck_eval.py                    # all claims in data/factcheck_eval.json
    python scripts\\factcheck_eval.py --paper "GS Paper I"
    python scripts\\factcheck_eval.py --ablate           # run every claim twice: with notes and WITHOUT notes
    python scripts\\factcheck_eval.py --only gs3_f1,gs3_t2

The claims live in data/factcheck_eval.json (created automatically on the first run; edit it freely).
Each claim:
    {"id": "gs3_t1", "paper": "GS Paper III", "truth": "true" | "false", "claim": "...", "query": "optional short search query"}

Outcomes
  true claim : confirmed (supported) | missed (unverifiable) | FALSE ALARM (contradicted, or notes disagree)
  false claim: caught (contradicted, or notes disagree) | missed (unverifiable) | WRONGLY SUPPORTED
A false alarm on a true claim is the worst result: it would mislead a student. Aim for zero.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EVAL_FILE = Path("data/factcheck_eval.json")

STARTER_CLAIMS = [
    {"id": "gs2_t1", "paper": "GS Paper II", "truth": "true", "claim": "Articles 323A and 323B were inserted by the 42nd Constitutional Amendment Act, 1976."},
    {"id": "gs2_t2", "paper": "GS Paper II", "truth": "true", "claim": "The Tenth Schedule was inserted by the 52nd Constitutional Amendment."},
    {"id": "gs2_t3", "paper": "GS Paper II", "truth": "true", "claim": "The 91st Amendment Act, 2003 removed the one-third split provision of the Tenth Schedule."},
    {"id": "gs2_t4", "paper": "GS Paper II", "truth": "true", "claim": "The Women's Reservation Act, 2023 is the Constitution (106th Amendment) Act."},
    {"id": "gs2_t5", "paper": "GS Paper II", "truth": "true", "claim": "The 73rd Amendment reserved one-third of seats for women in Panchayati Raj institutions."},
    {"id": "gs2_t6", "paper": "GS Paper II", "truth": "true", "claim": "Article 32 gives the right to move the Supreme Court for enforcement of fundamental rights."},
    {"id": "gs2_t7", "paper": "GS Paper II", "truth": "true", "claim": "The Tribunal Reforms Act was enacted in 2021."},
    {"id": "gs2_t8", "paper": "GS Paper II", "truth": "true", "claim": "The Representation of the People Act was enacted in 1951."},
    {"id": "gs2_f1", "paper": "GS Paper II", "truth": "false", "claim": "The Sevottam model has five modules."},
    {"id": "gs2_f2", "paper": "GS Paper II", "truth": "false", "claim": "Article 21 guarantees the right to vote."},
    {"id": "gs2_f3", "paper": "GS Paper II", "truth": "false", "claim": "Tribunals are not bound by the procedures of BNS and BNSS."},
    {"id": "gs2_t9", "paper": "GS Paper II", "truth": "true", "claim": "Hussainara Khatoon v. State of Bihar was decided in 1979."},
    {"id": "gs1_t1", "paper": "GS Paper I", "truth": "true", "claim": "The Battle of Plassey was fought in 1757."},
    {"id": "gs1_t2", "paper": "GS Paper I", "truth": "true", "claim": "The Tropic of Cancer passes through eight Indian states."},
    {"id": "gs1_t3", "paper": "GS Paper I", "truth": "true", "claim": "Rajaraja I built the Brihadeeswara temple at Thanjavur."},
    {"id": "gs1_f1", "paper": "GS Paper I", "truth": "false", "claim": "The Battle of Buxar was fought in 1757."},
    {"id": "gs1_f2", "paper": "GS Paper I", "truth": "false", "claim": "The Tropic of Cancer passes through ten Indian states."},
    {"id": "gs1_f3", "paper": "GS Paper I", "truth": "false", "claim": "The Permanent Settlement was introduced by Lord Wellesley in 1793."},
    {"id": "gs3_t1", "paper": "GS Paper III", "truth": "true", "claim": "The Reserve Bank of India was established in 1935."},
    {"id": "gs3_t2", "paper": "GS Paper III", "truth": "true", "claim": "GST came into effect in India on 1 July 2017."},
    {"id": "gs3_t3", "paper": "GS Paper III", "truth": "true", "claim": "MGNREGA guarantees 100 days of wage employment per rural household in a year."},
    {"id": "gs3_f1", "paper": "GS Paper III", "truth": "false", "claim": "The Reserve Bank of India was established in 1949."},
    {"id": "gs3_f2", "paper": "GS Paper III", "truth": "false", "claim": "GST came into effect in India on 1 April 2017."},
    {"id": "gs3_f3", "paper": "GS Paper III", "truth": "false", "claim": "The repo rate is the rate at which commercial banks lend short-term funds to the RBI."},
    {"id": "gs4_t1", "paper": "GS Paper IV", "truth": "true", "claim": "Kohlberg proposed three levels of moral development."},
    {"id": "gs4_t2", "paper": "GS Paper IV", "truth": "true", "claim": "The Nolan Committee formulated seven principles of public life."},
    {"id": "gs4_t3", "paper": "GS Paper IV", "truth": "true", "claim": "The Second Administrative Reforms Commission's fourth report is titled Ethics in Governance."},
    {"id": "gs4_f1", "paper": "GS Paper IV", "truth": "false", "claim": "Kohlberg proposed five levels of moral development."},
    {"id": "gs4_f2", "paper": "GS Paper IV", "truth": "false", "claim": "The Nolan Committee formulated twelve principles of public life."},
    {"id": "gs4_f3", "paper": "GS Paper IV", "truth": "false", "claim": "Emotional intelligence was first proposed by Kohlberg."},
]

OUT_FILE = Path("data/benchmark/results/factcheck_eval.json")


def classify(truth: str, v: dict) -> str:
    label, notes_disagree = v.get("label"), bool(v.get("note_disagrees"))
    if truth == "true":
        if label == "contradicted" or notes_disagree:
            return "FALSE ALARM"
        return "confirmed" if label == "supported" else "missed"
    if label == "supported":
        return "WRONGLY SUPPORTED"
    return "caught" if (label == "contradicted" or notes_disagree) else "missed"


def run(claims, verify, paper_of, label):
    rows = []
    for c in claims:
        paper = paper_of(c.get("paper"))
        kw = {"papers": [paper]} if paper else {}
        try:
            v = verify(c["claim"], c.get("query"), use_cache=False, **kw)
        except Exception as exc:
            print(f"  [error] {c['id']}: {type(exc).__name__}: {exc}")
            continue
        outcome = classify(c["truth"], v)
        rows.append({"id": c["id"], "paper": c.get("paper"), "truth": c["truth"], "label": v["label"],
                     "note_disagrees": v.get("note_disagrees"), "notes_used": v.get("notes_used"),
                     "official": len(v.get("sources", [])), "outcome": outcome})
        print(f"  {outcome:<18} {v['label']:<13} notes={v.get('notes_used')} official={len(v.get('sources', []))}"
              f"  [{c['id']}] {c['claim'][:62]}")
    print(f"\n--- {label} ---")
    summarise(rows)
    return rows


def summarise(rows):
    def n(truth, *outs):
        return sum(1 for r in rows if r["truth"] == truth and r["outcome"] in outs)

    t, f = sum(r["truth"] == "true" for r in rows), sum(r["truth"] == "false" for r in rows)
    print(f"True claims  ({t}): confirmed {n('true', 'confirmed')} | missed {n('true', 'missed')} | "
          f"FALSE ALARMS {n('true', 'FALSE ALARM')}   <- must be 0")
    print(f"False claims ({f}): caught {n('false', 'caught')} | missed {n('false', 'missed')} | "
          f"WRONGLY SUPPORTED {n('false', 'WRONGLY SUPPORTED')}   <- must be 0")
    for p in sorted({r["paper"] or "-" for r in rows}):
        sub = [r for r in rows if (r["paper"] or "-") == p]
        print(f"  {p:<14} n={len(sub):<3} confirmed {sum(r['outcome'] == 'confirmed' for r in sub)} | "
              f"caught {sum(r['outcome'] == 'caught' for r in sub)} | "
              f"bad {sum(r['outcome'] in ('FALSE ALARM', 'WRONGLY SUPPORTED') for r in sub)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--paper", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ablate", action="store_true", help="also run with the notes search switched off")
    args = ap.parse_args()

    import app.evaluator.factcheck as fc
    from app.retrieval.corpus import paper_from_subject

    if not EVAL_FILE.exists():                       # first run: create the editable claims file
        EVAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        EVAL_FILE.write_text(json.dumps(STARTER_CLAIMS, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Created {EVAL_FILE} with {len(STARTER_CLAIMS)} starter claims (edit it to add your own).")
    claims = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    if args.only:
        claims = [c for c in claims if c["id"] in set(args.only.split(","))]
    if args.paper:
        claims = [c for c in claims if c.get("paper") == args.paper]
    if args.limit:
        claims = claims[:args.limit]
    if not claims:
        raise SystemExit("No claims selected.")

    result = {"with_notes": run(claims, fc.verify_claim, paper_from_subject, "WITH notes")}
    if args.ablate:
        original = fc.search_corpus
        fc.search_corpus = lambda query, k=3, **kw: []
        try:
            result["without_notes"] = run(claims, fc.verify_claim, paper_from_subject, "WITHOUT notes")
        finally:
            fc.search_corpus = original
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nSaved {OUT_FILE}")


if __name__ == "__main__":
    main()