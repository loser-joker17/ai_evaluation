import pytest

from app.evaluator.scoring import (
    EXPECTED_DIMENSIONS,
    evidence_ok,
    finalize_scores,
    dimension_max,
    round_marks,
    compute_caps,
    verify_concerns,
)
from app.evaluator.features import (
    split_sentences,
    verify_conclusion,
    verify_introduction,
)


ANSWER = "Alpha beta gamma delta. Epsilon zeta eta theta."
FEATURES = {"has_introduction": True, "has_conclusion": True}

def test_compute_caps():
    assert compute_caps({"has_conclusion": True}, 100, 150, "within_limit") == {}
    assert "structure_presentation" in compute_caps({"has_conclusion": False}, 100, 150, "within_limit")
    assert "coverage_balance" in compute_caps({"has_conclusion": True}, 40, 150, "under_limit")
    both = compute_caps({"has_conclusion": False}, 200, 150, "over_limit")
    note = both["structure_presentation"][1]
    assert "exceeds" in note and "No concluding" in note

def raw(levels, evidence=None, improvement="None"):
    ev = ["Alpha beta gamma delta."] if evidence is None else evidence
    return [
        {
            "dimension": d,
            "score": levels[d] if isinstance(levels, dict) else levels,
            "justification": "reason",
            "evidence_from_answer": ev,
            "improvement": improvement,
        }
        for d in sorted(EXPECTED_DIMENSIONS)
    ]


def finalize(items, max_marks=10, status="within_limit", answer=ANSWER):
    scores, issues = finalize_scores(
        raw_items=items, features=FEATURES, word_count=100, word_limit=150,
        max_marks=max_marks, word_limit_status=status, answer=answer,
    )
    assert not issues
    return {s["dimension"]: s for s in scores}


# ---------------------------------------------------------- rounding

@pytest.mark.parametrize("raw_total,expected", [
    (3.7, 3.5), (3.8, 4.0), (3.3, 3.0), (3.5, 3.5),
    (3.79, 3.5), (0.0, 0.0), (9.9, 10.0),
])
def test_round_marks(raw_total, expected):
    assert round_marks(raw_total, 10) == expected


# ----------------------------------------------------------- ceiling

def test_all_fives_never_exceed_ceiling():
    res = finalize(raw(5))
    assert sum(s["score"] for s in res.values()) <= 7.51


def test_dimension_maxes_add_up():
    assert abs(sum(dimension_max(d, 10) for d in EXPECTED_DIMENSIONS) - 10) < 0.01
    assert abs(sum(dimension_max(d, 15) for d in EXPECTED_DIMENSIONS) - 15) < 0.01


def test_fifteen_mark_scale_is_larger():
    ten = sum(s["score"] for s in finalize(raw(3), 10).values())
    fifteen = sum(s["score"] for s in finalize(raw(3), 15).values())
    assert abs(fifteen - 1.5 * ten) < 0.1


# ------------------------------------------------------------- audit

def test_fabricated_evidence_downgrades_level_5():
    res = finalize(raw(5, evidence=["This sentence is not in the answer."]))
    assert all(s["final_level"] <= 3 for s in res.values())
    assert all(s["audit_note"] for s in res.values())


def test_level_5_with_listed_improvement_drops_to_4():
    res = finalize(raw(5, improvement="Add more examples."))
    assert all(s["final_level"] <= 4 for s in res.values())


def test_level_4_without_evidence_drops_to_3():
    res = finalize(raw(4, evidence=[]))
    assert all(s["final_level"] <= 3 for s in res.values())


def test_low_levels_are_not_audited():
    res = finalize(raw(2, evidence=[]))
    assert all(s["final_level"] == 2 and s["audit_note"] is None for s in res.values())


def test_over_limit_caps_structure_only():
    res = finalize(raw(4), status="over_limit")
    assert res["structure_presentation"]["final_level"] == 3
    assert res["relevance"]["final_level"] == 4


# ---------------------------------------------------- evidence match

def test_evidence_ok_ignores_case_quotes_spacing_and_ellipsis():
    assert evidence_ok('"alpha  BETA gamma..."', ANSWER)
    assert evidence_ok("Alpha beta ... gamma delta", ANSWER)
    assert evidence_ok("Alphabeta gamma delta.", ANSWER)   # missing space


def test_evidence_ok_rejects_unknown_text():
    assert not evidence_ok("Something completely different", ANSWER)
    assert not evidence_ok("", ANSWER)


# ----------------------------------------------------- feature checks

def test_sentence_split_keeps_case_names_together():
    s = split_sentences("The court in S.P. Gupta (1981) relaxed standing. It helped the poor.")
    assert len(s) == 2


def test_section_label_is_not_a_conclusion():
    s = split_sentences(
        "Women's representation remains low in India today. "
        "Challenges include patriarchy and money.\n\n"
        "Measures: parties should give more tickets to women."
    )
    ok, _, note = verify_conclusion("Measures: parties should give more tickets to women.", s)
    assert not ok and note


def test_closing_sentence_with_marker_is_a_conclusion():
    s = split_sentences("Intro sentence is right here. Body point is made here. "
                        "Thus, the tool remains vital for justice.")
    ok, _, _ = verify_conclusion("Thus, the tool remains vital for justice.", s)
    assert ok


def test_conclusion_must_be_near_the_end():
    s = split_sentences("Intro sentence is right here. Thus, the middle claim is made here. "
                        "Another body point follows now. One more body point follows.")
    ok, _, _ = verify_conclusion("Thus, the middle claim is made here.", s)
    assert not ok


def test_label_is_not_an_introduction():
    s = split_sentences("Challenges: patriarchy and money matter here. Body point two is here.")
    ok, _, _ = verify_introduction("Challenges: patriarchy and money matter here.", s)
    assert not ok

def test_level_5_needs_substantial_quotes():
    answer = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu."
    short = ["Alpha beta", "gamma delta", "zeta eta"]
    long = [
        "Alpha beta gamma delta epsilon zeta eta theta",
        "beta gamma delta epsilon zeta eta theta iota",
        "gamma delta epsilon zeta eta theta iota kappa",
    ]
    items_short = [{"dimension": "relevance", "score": 5,
                    "evidence_from_answer": short, "improvement": "None"}]
    items_long = [{"dimension": "relevance", "score": 5,
                   "evidence_from_answer": long, "improvement": "None"}]

    from app.evaluator.scoring import audit_item
    assert audit_item(items_short[0], answer)[0] == 4
    assert audit_item(items_long[0], answer)[0] == 5

def test_compute_caps_analysis_and_overlimit():
    caps = compute_caps({"has_conclusion": True, "mechanisms_explained": 1}, 100, 150, "within_limit")
    assert caps["analysis_depth"][0] == 3
    caps = compute_caps({"has_conclusion": True, "mechanisms_explained": 3}, 200, 150, "over_limit")
    assert caps["coverage_balance"][0] == 4
    assert "analysis_depth" not in caps

def test_verify_concerns_filters():
    answer = "Bulk defections are allowed when two thirds of members defect together."
    good = {"claim": "Bulk defections are allowed when two thirds", "issue": "x", "confidence": "high"}
    low = {**good, "confidence": "medium"}
    fake = {"claim": "This sentence is not in the answer at all", "issue": "x", "confidence": "high"}
    short = {"claim": "Bulk defections", "issue": "x", "confidence": "high"}
    out = verify_concerns([good, low, fake, short, good], answer)
    assert len(out) == 1


def test_concerns_cap_content_substantiation():
    concerns = [{"claim": "Alpha beta gamma delta", "issue": "x", "confidence": "high"}]
    scores, _ = finalize_scores(
        raw_items=raw(5), features=FEATURES, word_count=100, word_limit=150,
        max_marks=10, word_limit_status="within_limit", answer=ANSWER,
        factual_concerns=concerns,
    )
    by = {s["dimension"]: s for s in scores}
    assert by["content_substantiation"]["final_level"] <= 3
    assert "possible factual" in by["content_substantiation"]["cap_note"]
    assert by["relevance"]["final_level"] > 3

def test_confirmed_errors_cap_content():
    confirmed = [{"claim": "Alpha beta gamma delta", "sources": ["https://x"], "quote": "q"}]
    scores, _ = finalize_scores(
        raw_items=raw(5), features=FEATURES, word_count=100, word_limit=150,
        max_marks=10, word_limit_status="within_limit", answer=ANSWER,
        confirmed_errors=confirmed,
    )
    by = {s["dimension"]: s for s in scores}
    assert by["content_substantiation"]["final_level"] <= 3
    assert "contradicted by official sources" in by["content_substantiation"]["cap_note"]