from app.evaluator.scoring import allocation_caps
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
    both = compute_caps({"has_conclusion": False}, 320, 150, "over_limit")
    note = both["structure_presentation"][1]
    assert "double" in note and "No concluding" in note

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
    (3.7, 3.75), (3.8, 3.75), (3.3, 3.25), (3.5, 3.5),
    (3.79, 3.75), (3.62, 3.5), (3.63, 3.75), (0.0, 0.0), (9.9, 10.0),
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
    # Low levels use the same fraction for 15 and 20 marks, so they scale with the marks.
    fifteen = sum(s["score"] for s in finalize(raw(2), 15).values())
    twenty = sum(s["score"] for s in finalize(raw(2), 20).values())
    assert abs(fifteen - 0.75 * twenty) < 0.1


def test_fifteen_mark_levels_3_to_5_are_stricter():
    # 15-mark answers are stricter than 20-mark ones at levels 3-5.
    from app.evaluator.scoring import level_fraction
    for level in (3, 4, 5):
        assert level_fraction(level, 15) < level_fraction(level, 20)


def test_ten_mark_table_is_narrow_and_ordered():
    # 10-mark table: each level a clear step above the one below, and a narrow range
    # (examiners' 10-mark marks fall in about 3.5-5/10).
    from app.evaluator.scoring import level_fraction
    f = [level_fraction(lv, 10) for lv in range(6)]
    assert all(b > a for a, b in zip(f, f[1:]))
    assert f[5] - f[2] <= 0.2

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


def test_moderately_over_limit_does_not_cap_structure():
    res = finalize(raw(4), status="over_limit")
    assert res["structure_presentation"]["final_level"] == 4
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
    assert "coverage_balance" not in caps
    assert "structure_presentation" not in caps
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
    assert "Double-check" in by["content_substantiation"]["improvement"]
    assert "unverified" not in (by["content_substantiation"]["cap_note"] or "")
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


def test_well_over_limit_caps_structure_at_4():
    assert compute_caps({"has_conclusion": True}, 255, 150, "over_limit")["structure_presentation"][0] == 4


def test_double_limit_caps_structure_at_3():
    assert compute_caps({"has_conclusion": True}, 320, 150, "over_limit")["structure_presentation"][0] == 3


def test_analysis_expectation():
    from app.evaluator.scoring import analysis_expectation
    assert analysis_expectation("Elaborate on the significance") == "descriptive"
    assert analysis_expectation("Describe") == "descriptive"
    assert analysis_expectation("Identify and discuss") == "balanced"   # discuss outranks identify
    assert analysis_expectation("Critically examine") == "judgement"
    assert analysis_expectation("Critically analyse") == "judgement"   # weigh both sides, then a verdict
    assert analysis_expectation("To what extent has it succeeded?") == "judgement"
    assert analysis_expectation("Do you agree? Discuss.") == "judgement"
    assert analysis_expectation("Analyze") == "analytical"
    assert analysis_expectation("Discuss") == "balanced"
    assert analysis_expectation("") == "balanced"
    assert analysis_expectation(None) == "balanced"


def test_cap_keeps_judge_feedback_when_not_binding():
    # Judge already below the coverage cap: its own reasoning must survive.
    low = finalize(raw(2, improvement="Name the specific reforms."), status="under_limit")
    cov = low["coverage_balance"]
    assert cov["final_level"] == 2
    assert cov["justification"].startswith("reason") and "Also:" in cov["justification"]
    assert cov["improvement"] == "Name the specific reforms."
    # Judge above the cap: the cap text explains the lowered level.
    high = finalize(raw(4), status="under_limit")["coverage_balance"]
    assert high["final_level"] == 3 and high["justification"].startswith("Level lowered from 4 to 3")

# ------------------------------------------------- length and allocation

def test_required_mechanisms_scale_with_word_limit():
    from app.evaluator.scoring import required_mechanisms
    assert required_mechanisms(None) == 2
    assert required_mechanisms(150) == 2
    assert required_mechanisms(250) == 3
    caps = compute_caps({"has_conclusion": True, "mechanisms_explained": 2}, 240, 250, "within_limit")
    assert caps["analysis_depth"][0] == 3 and "250-word" in caps["analysis_depth"][1]
    assert "analysis_depth" not in compute_caps(
        {"has_conclusion": True, "mechanisms_explained": 2}, 140, 150, "within_limit")


def test_compute_allocation_shares_and_order():
    from app.evaluator.features import compute_allocation
    blocks = ["Intro line here.", "need " * 40, "bottleneck " * 30, "law " * 30, "Thus done."]
    labels = ["intro", "other", "P1", "P2", "conclusion"]
    a = compute_allocation(blocks, labels, ["bottlenecks", "legislations"])
    assert a["unasked_share"] == 0.4 and a["parts_in_order"] is True
    assert [p["share"] for p in a["part_word_share"]] == [0.3, 0.3]
    b = compute_allocation(blocks, ["intro", "other", "P2", "P1", "conclusion"], ["x", "y"])
    assert b["parts_in_order"] is False
    bad = compute_allocation(blocks, ["intro", "P1"], ["x", "y"])
    assert bad["part_word_share"] == [] and "not measured" in bad["note"]
    assert compute_allocation(blocks, ["intro", "P9", "P1", "P2", "conclusion"], ["x", "y"])["note"]


def test_allocation_caps():
    from app.evaluator.scoring import allocation_caps
    ok = {"part_word_share": [{"part": "a", "share": 0.5}, {"part": "b", "share": 0.45}],
          "unasked_share": 0.05, "parts_in_order": True}
    assert allocation_caps(ok) == {}
    thin = {**ok, "part_word_share": [{"part": "a", "share": 0.85}, {"part": "b", "share": 0.15}]}
    assert allocation_caps(thin)["relevance"][0] == 3
    unasked = {**ok, "unasked_share": 0.38}
    assert "did not ask" in allocation_caps(unasked)["relevance"][1]
    order = {**ok, "parts_in_order": False}
    assert allocation_caps(order)["structure_presentation"][0] == 3
    # Old cached features without allocation fields: no caps.
    assert allocation_caps({"has_conclusion": True}) == {}


def test_directive_type_uses_question_when_directive_is_generic():
    from app.evaluator.scoring import directive_type
    q = "To what extent can the rise of 'Kidfluencers' be seen as a reflection of changing family structures?"
    assert directive_type("Examine", q) == "judgement"
    assert directive_type("Analyze", q) == "judgement"    # "to what extent" in the question outranks it
    assert directive_type("", "Highlight the salient differences.") == "descriptive"


def test_mechanism_cap_only_where_explanation_is_asked():
    feats = {"has_conclusion": True, "mechanisms_explained": 0}
    assert "analysis_depth" in compute_caps(feats, 140, 150, "within_limit", "Discuss")
    assert "analysis_depth" in compute_caps(feats, 140, 150, "within_limit", "Analyze")
    assert "analysis_depth" not in compute_caps(feats, 140, 150, "within_limit", "To what extent")
    assert "analysis_depth" not in compute_caps(feats, 140, 150, "within_limit", "Highlight")
    assert "analysis_depth" not in compute_caps(
        feats, 140, 150, "within_limit", "Examine", "Do you agree with this view?")


def test_every_rubric_explains_specific_points():
    from app.evaluator.scoring import ANALYSIS_LEVELS
    assert set(ANALYSIS_LEVELS) == {"analytical", "judgement", "balanced", "descriptive"}
    for text in ANALYSIS_LEVELS.values():
        assert "specific point even without a why-sentence" in text
    assert "Do not lower this dimension for missing causal mechanisms" in ANALYSIS_LEVELS["judgement"]


def test_directive_kind_uses_every_directive():
    from app.evaluator.demands import directive_kind, find_directives
    assert directive_kind("", "What is floriculture? How is it helpful in boosting exports?") == "descriptive"
    assert directive_kind("", "What are REEs? Discuss the implications.") == "balanced"
    assert directive_kind("Examine", "To what extent can X be seen as Y?") == "judgement"
    assert directive_kind("", "Critically analyse the scheme.") == "judgement"
    assert directive_kind("", "Analyze.") == "analytical"
    keys = [f["key"] for f in find_directives("Critically examine the procedure.")]
    assert keys == ["critically"]                        # not also "examine"
    # "State" as a noun and "What is your opinion" are not directives of their own
    assert "define" not in [f["key"] for f in find_directives("What is your opinion? Give reasons.")]
    assert find_directives("The British Indian State changed.") == []


def test_build_demands_numbers_parts_and_directive_needs():
    from app.evaluator.demands import build_demands
    q = "What are the objectives of IBC? To what extent has it been successful?"
    d = build_demands(q, {"question_parts": ["objectives of IBC", "extent of success"], "directive": ""})
    ids = [x["id"] for x in d]
    assert ids[:2] == ["Q1", "Q2"]
    assert any(x["source"] == "directive" for x in d)
    assert all(x["cap"] is None for x in d if x["source"] == "directive")   # feedback only
    # no question_parts: the question itself is Q1
    assert build_demands("Discuss X.", {})[0] == {"id": "Q1", "text": "Discuss X.", "source": "question", "cap": None}


def test_demand_caps():
    from app.evaluator.demands import build_demands, demand_caps
    q = "Explain X. What are its consequences? To what extent has it worked?"
    d = build_demands(q, {"question_parts": ["explain X", "consequences", "extent"]})
    assert demand_caps(d, []) == {}                      # old saved runs: no caps
    caps = demand_caps(d, [{"id": "Q2", "status": "missing"}])
    assert caps["coverage_balance"][0] == 3 and caps["relevance"][0] == 3
    assert "consequences" in caps["coverage_balance"][1]
    caps = demand_caps(d, [{"id": "Q1", "status": "missing"}, {"id": "Q2", "status": "missing"}])
    assert caps["coverage_balance"][0] == 2
    assert demand_caps(d, [{"id": "Q3", "status": "thin"}])["coverage_balance"][0] == 3
    verdict = next(x["id"] for x in d if "verdict" in x["text"])
    assert demand_caps(d, [{"id": verdict, "status": "missing"}]) == {}    # feedback only
    c = build_demands("Critically examine the scheme.", {"question_parts": ["the scheme"]})
    both = next(x["id"] for x in c if "merits" in x["text"])
    assert demand_caps(c, [{"id": both, "status": "missing"}])["analysis_depth"][0] == 3
    # feedback-only directive demands never cap; unknown ids are ignored
    assert demand_caps(d, [{"id": "Q1", "status": "covered"}, {"id": "Z9", "status": "missing"}]) == {}


def test_finalize_applies_demand_caps():
    from app.evaluator.demands import build_demands
    items = [{"dimension": dim, "score": 5, "justification": "ok",
              "evidence_from_answer": [], "improvement": "None"}
             for dim in ("relevance", "content_substantiation", "analysis_depth",
                         "coverage_balance", "structure_presentation")]
    d = build_demands("Q?", {"question_parts": ["part one", "part two"]})
    final, issues = finalize_scores(items, {"has_conclusion": True}, 140, 150, 10, "within_limit",
                                    demands=d, demand_check=[{"id": "Q2", "status": "missing"}])
    levels = {x["dimension"]: x["final_level"] for x in final}
    assert levels["coverage_balance"] == 3 and levels["relevance"] == 3


def test_meta_parts_are_not_question_parts():
    from app.evaluator.demands import is_meta_part, build_demands
    k = ("To what extent can the rise of 'Kidfluencers' be seen as a reflection of changing "
         "family structures and parental aspirations in Indian society?")
    assert is_meta_part("Make a reasoned assessment of the extent to which this rise reflects", k)
    assert is_meta_part("Analyse the relationship between the rise and the changes", k)
    assert is_meta_part("State whether you agree or disagree with the statement.", "Do you agree?")
    assert not is_meta_part("Identify changes in family structures", k)
    e = "Under what conditions can Emergency be proclaimed? What are the consequences?"
    assert not is_meta_part("Consequences while in force", e)
    assert is_meta_part("Challenges faced by associations", "In what ways do associations contribute?")
    assert not is_meta_part("Provide suitable examples", "Explain with suitable examples.")
    ids = [d["text"] for d in build_demands(k, {"question_parts": [
        "Identify changes in family structures", "Make a reasoned assessment of the extent"]})]
    assert "Make a reasoned assessment of the extent" not in ids


def test_allocation_ignores_meta_parts():
    feats = {"part_word_share": [
        {"part": "Identify changes in family structures", "share": 0.5},
        {"part": "Identify parental aspirations", "share": 0.5},
        {"part": "Make a reasoned assessment of the extent", "share": 0.0},
    ]}
    assert "relevance" not in allocation_caps(feats, "To what extent can X be seen as Y?")


def test_demand_caps_replay_uses_current_rules():
    from app.evaluator.demands import demand_caps
    q = "To what extent can X be seen as Y?"
    saved = [  # as saved by an earlier run: an invented part and an old verdict cap
        {"id": "Q1", "text": "Identify Y", "source": "question", "cap": None},
        {"id": "Q2", "text": "Make a reasoned assessment of the extent", "source": "question", "cap": None},
        {"id": "D1", "text": "a clear, reasoned verdict on the extent or view asked",
         "source": "directive", "cap": "analysis_depth"},
    ]
    check = [{"id": "Q1", "status": "covered"}, {"id": "Q2", "status": "missing"},
             {"id": "D1", "status": "missing"}]
    assert demand_caps(saved, check, q) == {}


def test_incomplete_answer_is_scaled_by_share_written():
    full, _ = finalize_scores(
        raw_items=raw(3), features=FEATURES, word_count=100, word_limit=150,
        max_marks=10, word_limit_status="within_limit", answer=ANSWER,
    )
    frag, _ = finalize_scores(
        raw_items=raw(3), features=FEATURES, word_count=38, word_limit=150,
        max_marks=10, word_limit_status="under_limit", answer=ANSWER,
    )
    t_full = sum(d["score"] for d in full)
    t_frag = sum(d["score"] for d in frag)
    assert t_frag == pytest.approx(t_full * 38 / 75, abs=0.05)
    by = {d["dimension"]: d for d in frag}
    assert "Incomplete answer" in by["coverage_balance"]["improvement"]


def test_answer_at_half_the_limit_is_not_scaled():
    a, _ = finalize_scores(raw_items=raw(3), features=FEATURES, word_count=75, word_limit=150,
                           max_marks=10, word_limit_status="under_limit", answer=ANSWER)
    b, _ = finalize_scores(raw_items=raw(3), features=FEATURES, word_count=140, word_limit=150,
                           max_marks=10, word_limit_status="within_limit", answer=ANSWER)
    assert sum(d["score"] for d in a) == pytest.approx(sum(d["score"] for d in b), abs=0.01)


def test_invented_sub_parts_are_not_question_parts():
    from app.evaluator.demands import is_meta_part
    q = ("'Operation Sindoor' signals a strategic evolution in India's approach to "
         "cross-border terrorism. Analyze.")
    assert is_meta_part("Contrast these features with India's previous responses to "
                        "cross-border terrorism (e.g. surgical strikes, Balakot).", q)
    assert is_meta_part("Explain the strategic evolution implied: shift in doctrine, "
                        "escalation management, international messaging.", q)
    k = ("To what extent can the rise of 'Kidfluencers' be seen as a reflection of changing "
         "family structures and parental aspirations in Indian society?")
    assert not is_meta_part("Identify key changes in Indian family structures", k)
    c = ("What do you understand by the term 'crisis of conscience'? Describe an incident. "
         "How did you deal with it?")
    assert not is_meta_part("Explain the steps taken to resolve or cope with the crisis.", c)
    e = "Distinguish between empathy and compassion. Why are they foundational values?"
    assert not is_meta_part("Highlight the key differences between the two concepts.", e)


def test_duplicate_dimension_keeps_first_entry():
    items = raw(3) + [dict(raw(5)[0])]          # the judge repeated one dimension
    scores, issues = finalize_scores(raw_items=items, features=FEATURES, word_count=100,
                                     word_limit=150, max_marks=10,
                                     word_limit_status="within_limit", answer=ANSWER)
    assert not issues and len(scores) == 5
    assert all(s["raw_level"] == 3 for s in scores)


def test_missing_dimension_is_still_rejected():
    scores, issues = finalize_scores(raw_items=raw(3)[:4], features=FEATURES, word_count=100,
                                     word_limit=150, max_marks=10,
                                     word_limit_status="within_limit", answer=ANSWER)
    assert scores == [] and issues


def test_backup_used_when_main_model_returns_nothing():
    from app.llm import _StructuredWithBackup

    class Empty:
        def invoke(self, *a, **k):
            return None

    class Good:
        def invoke(self, *a, **k):
            return "ok"

    assert _StructuredWithBackup(Empty(), Good(), "b").invoke("x") == "ok"
