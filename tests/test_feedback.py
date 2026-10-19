"""Feedback grounding: the checks that run after the feedback model writes its text."""
from app.evaluator.demands import (
    demand_caps,
    is_cross_cutting_part,
    is_meta_part,
    is_premise_part,
)
from app.evaluator.feedback import (
    claims_match,
    clean_feedback,
    drop_supported,
    length_statement,
    score_band,
    _answer_feature_context,
    _is_gs4,
)
from app.evaluator.scoring import allocation_caps

KIDS = ("To what extent can the rise of 'Kidfluencers' be seen as a reflection of changing "
        "family structures and parental aspirations in Indian society?")
PROPERTY = ("The evolution of property rights in India reflects an intricate relationship that "
            "exists between individual rights and public welfare. Discuss this statement with "
            "the help of relevant constitutional provisions and case laws.")


# ------------------------------------------------ cross-cutting and premise parts

def test_cross_cutting_parts():
    assert is_cross_cutting_part("Support the discussion with relevant constitutional provisions")
    assert is_cross_cutting_part("Cite relevant case laws")
    assert is_cross_cutting_part("Illustrate with suitable examples")
    assert not is_cross_cutting_part("Discuss the evolution of property rights")
    assert not is_cross_cutting_part("Provide a way forward")
    assert not is_cross_cutting_part("Give examples of how SHGs empower women")


def test_premise_part():
    assert is_premise_part("Describe the rise of Kidfluencers", KIDS)
    assert is_premise_part("Identify the rise of Kidfluencers in Indian society", KIDS)
    assert not is_premise_part("Explain how the rise reflects changing family structures", KIDS)
    assert not is_premise_part("Discuss the growth of MSMEs",
                               "Discuss the growth of MSMEs in India and the challenges they face.")


def test_cross_cutting_part_gets_no_share_cap_or_demand_cap():
    features = {"part_word_share": [
        {"part": "Discuss the evolution of property rights", "share": 0.5},
        {"part": "Explain the relationship between individual rights and public welfare", "share": 0.5},
        {"part": "Support the discussion with relevant constitutional provisions", "share": 0.0},
    ]}
    assert allocation_caps(features, PROPERTY) == {}
    assert is_meta_part("Support the discussion with relevant constitutional provisions", PROPERTY)

    demands = [{"id": "Q1", "text": "Describe the rise of Kidfluencers", "source": "question", "cap": None},
               {"id": "Q2", "text": "Explain how the rise reflects changing family structures",
                "source": "question", "cap": None}]
    check = [{"id": "Q1", "status": "missing"}, {"id": "Q2", "status": "covered"}]
    assert demand_caps(demands, check, KIDS) == {}


# ------------------------------------------------ supported claims

def test_supported_concern_dropped():
    concerns = [{"claim": "India suspended the Indus Waters Treaty after Pahalgam"},
                {"claim": "Article 300A was added by the 42nd Amendment"}]
    verifs = [{"claim": "India suspended the Indus Waters Treaty in April 2025", "label": "supported"},
              {"claim": "Article 300A was added by the 42nd Amendment", "label": "unverifiable"}]
    left = drop_supported(concerns, verifs)
    assert [c["claim"] for c in left] == ["Article 300A was added by the 42nd Amendment"]
    assert claims_match("Saturation principle of scheme beneficiaries",
                        "PM Modi's Saturation Principle of scheme beneficiaries")


def _clean(fb, **kw):
    args = dict(answer="India suspended the Indus Waters Treaty. Article 300A protects property.",
                question=PROPERTY, word_count=169, word_limit=150, max_marks=10, total_score=4.25)
    args.update(kw)
    return clean_feedback(fb, **args)


def test_doubt_about_supported_claim_removed():
    fb = {"strengths": [], "improvement_suggestions": [], "overall_feedback": "",
          "weaknesses": ["The suspension of the Indus Waters Treaty may be inaccurate; verify it.",
                         "The analysis of land reforms is thin."]}
    out, notes = _clean(fb, supported_claims=["India suspended the Indus Waters Treaty"])
    assert out["weaknesses"] == ["The analysis of land reforms is thin."]
    assert notes


# ------------------------------------------------ length and figures

def test_full_length_answer_not_called_brief():
    fb = {"strengths": [], "improvement_suggestions": [], "overall_feedback": "",
          "weaknesses": ["The answer is very brief and lacks depth.",
                         "Land reforms are not linked to Article 31A."]}
    out, _ = _clean(fb)
    assert out["weaknesses"] == ["Land reforms are not linked to Article 31A."]
    # a genuinely short answer may still be called short
    out, _ = _clean(fb, word_count=60)
    assert len(out["weaknesses"]) == 2


def test_invented_figures_removed_but_articles_kept():
    fb = {"strengths": [], "weaknesses": [], "overall_feedback": "",
          "improvement_suggestions": [
              "Include accurate figures (e.g., public debt ~90% of GDP) and the trend of the ratio.",
              "India's debt is 90% of GDP, so mention it.",
              "Add Articles 14, 21 and 19(1)(g) and the 44th Amendment to the discussion.",
              "Mention the Kesavananda Bharati case (1973).",
          ]}
    out, notes = _clean(fb)
    s = out["improvement_suggestions"]
    assert s[0] == "Include accurate figures and the trend of the ratio."
    assert "Add Articles 14, 21 and 19(1)(g) and the 44th Amendment to the discussion." in s
    assert not any("90%" in x for x in s)
    assert not any("1973" in x for x in s)   # a year not in the answer
    assert len(notes) == 3


def test_numbers_from_answer_allowed_and_none_strings_dropped():
    fb = {"strengths": ["None", ""], "weaknesses": ["Article 300A is cited but not explained."],
          "improvement_suggestions": [], "overall_feedback": "Solid. The answer scores 4.25/10."}
    out, _ = _clean(fb)
    assert out["strengths"] == []
    assert out["weaknesses"] == ["Article 300A is cited but not explained."]
    assert out["overall_feedback"] == "Solid. The answer scores 4.25/10."


def test_gs4_reference_not_dismissed():
    fb = {"strengths": [], "improvement_suggestions": [], "overall_feedback": "",
          "weaknesses": ["Quoting Gandhi's talisman is irrelevant to the case.",
                         "The options lack merits and demerits."]}
    out, _ = _clean(fb, gs4=True, word_count=240, word_limit=250, max_marks=20, total_score=7.5)
    assert out["weaknesses"] == ["The options lack merits and demerits."]
    assert _is_gs4("GS Paper IV", "") and _is_gs4("GS4", "") and not _is_gs4("GS Paper II", "")


# ------------------------------------------------ prompt context

def test_length_statement_and_band():
    assert "13% over" in length_statement(169, 150)
    assert "do NOT call it brief" in length_statement(169, 150)
    assert "incomplete" in length_statement(40, 150)
    assert score_band(7.0, 15)[0] == "good"
    assert score_band(2.0, 10)[0] == "weak"
    assert score_band(6.0, 10)[0] == "excellent"


def test_feature_context_uses_real_keys():
    text = _answer_feature_context({"mechanisms_explained": 3, "addresses_all_question_parts": True,
                                    "relevant_point_count": 7})
    assert "unknown" not in text
    assert ": 3" in text and ": True" in text and ": 7" in text


# ------------------------------------------------ second round (compare_feedback run 2)

def test_unconfirmed_claim_not_called_fictional():
    fb = {"strengths": [], "improvement_suggestions": [
              "Clarify Article 39 and remove the fictional 2024 case to eliminate factual errors.",
              "Expand the analysis of Kesavananda Bharati."],
          "overall_feedback": "",
          "weaknesses": [
              "The 2024 Property Owners' Association case may be inaccurate; verify it.",
              "The answer contains factual inaccuracies about Article 39.",
              "The claim that 50% of women are anaemic is incorrect; NFHS-5 states 57%."]}
    out, _ = _clean(fb, confirmed_claims=["50% of women are anemic (NFHS-5)"], extra_numbers="57%",
                    answer="50% of women are anemic. Property Owners' Association case 2024.")
    assert out["improvement_suggestions"] == ["Expand the analysis of Kesavananda Bharati."]
    assert len(out["weaknesses"]) == 2
    assert "may be inaccurate" in out["weaknesses"][0]
    assert "incorrect" in out["weaknesses"][1]   # confirmed by an official source: kept


def test_weakness_count_follows_band_keeping_factual_ones():
    weak = [f"Point {c} lacks depth." for c in "abcdef"] + ["The 29% figure may be inaccurate; verify it."]
    fb = {"strengths": [], "improvement_suggestions": [], "overall_feedback": "", "weaknesses": weak}
    out, _ = _clean(fb, band="good", answer="Debt is 29% of GDP.")
    assert len(out["weaknesses"]) == 3
    assert any("29%" in w for w in out["weaknesses"])


def test_dimension_notes_cleaned_but_cap_figures_kept():
    from app.evaluator.feedback import clean_dimension_notes
    dims = [{"dimension": "content_substantiation",
             "improvement": "Replace the 29% figure with the correct ratio (~70% as of 2023). "
                            "Add the FRBM review committee.",
             "justification": "None"},
            {"dimension": "coverage_balance", "cap_note": "Incomplete answer: 38 words (about 25%).",
             "improvement": "Incomplete answer: 38 words (about 25%). Attempt every part.",
             "justification": "Level lowered from 4 to 2."}]
    out = clean_dimension_notes(dims, answer="Debt is 29% of GDP.", question="Discuss.", extra_numbers="",
                                word_count=38, word_limit=150, max_marks=10, total_score=2.0)
    assert "70" not in out[0]["improvement"] and "2023" not in out[0]["improvement"]
    assert out[0]["improvement"].endswith("Add the FRBM review committee.")
    assert out[0]["justification"] == ""
    assert out[1]["improvement"] == "Incomplete answer: 38 words (about 25%). Attempt every part."
    assert out[1]["justification"] == "Level lowered from 4 to 2."


def test_concern_keeps_one_neutral_line():
    fb = {"strengths": [], "improvement_suggestions": [], "overall_feedback": "",
          "weaknesses": ["The 2024 Property Owners' Association case is not a recognised judgment."]}
    out, _ = _clean(fb, concerns=[{"claim": "Property Owners' Association case 2024"}])
    assert out["weaknesses"] == ['The claim "Property Owners\' Association case 2024" may be '
                                 'inaccurate; verify it against the original source before using it.']
