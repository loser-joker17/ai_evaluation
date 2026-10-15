
import json

from app.evaluator.graph import evaluate_submission


# test_input_1 = {  # weak, generic
#     "question": (
#         "Discuss how social justice contributes to inclusive "
#         "development in India."
#     ),
#     "answer": (
#         "Social justice aims to reduce inequalities and provide "
#         "equal opportunities. Government initiatives in education, "
#         "healthcare and employment can help disadvantaged groups. "
#         "However, social discrimination and unequal access to "
#         "resources continue to create barriers. Inclusive development "
#         "requires effective implementation of welfare policies, "
#         "accountability and participation of marginalized communities."
#     ),
#     "subject": "GS Paper II",
#     "max_marks": 10,
#     "word_limit": 150,
# }

test_input_6 = {  # strong
    "question": (
        "Critically examine the role of Public Interest Litigation "
        "in strengthening access to justice in India."
    ),
    "answer": (
        "Public Interest Litigation (PIL) emerged when courts relaxed "
        "the rule of locus standi in cases like Hussainara Khatoon (1979) "
        "and S.P. Gupta (1981), opening the judiciary to the poor and "
        "marginalised.\n\n"
        "Contributions: Articles 32 and 226 allow courts to be approached "
        "through simple letters, which lowers the cost barrier. Courts "
        "expanded Article 21 to include speedy trial (Hussainara Khatoon) "
        "and the right to food (PUCL case). The Vishaka guidelines (1997) "
        "filled a legislative vacuum on workplace sexual harassment.\n\n"
        "Limitations: PIL is sometimes misused as 'publicity interest "
        "litigation', adding to case backlog. Continuing mandamus can "
        "blur the separation of powers, and compliance monitoring is "
        "weak.\n\n"
        "Way forward: courts should screen petitions for bona fides and "
        "impose costs on frivolous ones, following the guidelines in "
        "State of Uttaranchal v. Balwant Singh Chaufal (2010).\n\n"
        "Thus, PIL remains a vital tool for access to justice, but its "
        "credibility depends on disciplined use."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}

# test_input_3 = {  # average
#     "question": (
#         "Discuss the challenges faced by women in achieving political "
#         "representation in India and suggest measures to address them."
#     ),
#     "answer": (
#         "Women's political representation in India remains low despite "
#         "constitutional equality. The 73rd Amendment reserved one-third "
#         "of seats for women in Panchayati Raj institutions, which brought "
#         "many women into local politics. The Women's Reservation Act, "
#         "2023 extends one-third reservation to Parliament and state "
#         "assemblies, but it will apply only after delimitation.\n\n"
#         "Challenges include patriarchal social norms, lack of party "
#         "tickets, financial constraints and the problem of 'sarpanch "
#         "pati', where male relatives control the elected woman's "
#         "decisions. Violence and harassment during campaigns also "
#         "discourage participation.\n\n"
#         "Measures: political parties should give more tickets to women, "
#         "and training and awareness programmes can build the capacity of "
#         "women representatives."
#     ),
#     "subject": "GS Paper I",
#     "max_marks": 10,
#     "word_limit": 150,
# }

# test_input_4 = { #simultaneous elections
#     "question": (
#         "Discuss the relevance and challenges of holding simultaneous "
#         "elections in India. Would it strengthen federalism or undermine it?"
#     ),
#     "answer": (
#         "Simultaneous elections, also called One Nation One Election, "
#         "seek to synchronise Lok Sabha and State Assembly elections to "
#         "reduce financial costs, policy lags due to frequent MCC "
#         "imposition, and administrative disruption.\n\n"
#         "Relevance:\n"
#         "- Reduced cost and policy lag.\n"
#         "- Curbing populist schemes.\n"
#         "- Improved governance and policy continuity.\n"
#         "- More focus on development and less on elections.\n\n"
#         "Challenges:\n"
#         "- Constitutional amendments may be required, including changes "
#         "related to Articles 83, 172 and 356.\n"
#         "- States may oppose the idea.\n"
#         "- Local body elections are left out.\n"
#         "- Changes may be required in the Representation of the People Act, 1951.\n\n"
#         "Strengthening federalism:\n"
#         "- Enhances political stability.\n"
#         "- State issues may also be reflected in central elections.\n"
#         "- More time and energy can be devoted to developmental work.\n\n"
#         "Undermining federalism:\n"
#         "- National parties may override state parties with their narratives.\n"
#         "- State issues may be undermined by national agendas influencing "
#         "voter behaviour.\n"
#         "- The duration of a State Assembly may be reduced in case of dissolution.\n\n"
#         "Although a great vision, implementation of ONOE must accommodate "
#         "all federal stakeholders through consultation, deliberation and "
#         "participation in the national interest, not for political benefit."
#     ),
#     "subject": "GS Paper II",
#     "max_marks": 10,
#     "word_limit": 150,
# }
# test_input_5 = {  # Tribunals
#     "question": (
#         "The role of tribunals in India has expanded but concerns about "
#         "their independence and effectiveness persist. Critically evaluate "
#         "the current tribunal system in light of recent judicial and "
#         "legislative developments."
#     ),
#     "answer": (
#         "Tribunals are quasi-judicial institutions added through the "
#         "provisions of Articles 323A and 323B by the 42nd Constitutional "
#         "Amendment Act, 1976, for fields such as taxation, administration, "
#         "environment and more.\n\n"
#         "Role of Tribunals:\n"
#         "- Their role has expanded with LPG reforms and neoliberal policies.\n"
#         "- They deal with specific types of cases, e.g., the National Green "
#         "Tribunal for environmental cases.\n"
#         "- They help ease the judiciary's workload.\n\n"
#         "The Tribunal Reforms Act, 2021 raised greater concerns regarding "
#         "tribunals.\n\n"
#         "Tribunals are not bound by the procedures of BNS and BNSS, making "
#         "them unfairly inclined towards [unclear].\n\n"
#         "Challenges to Independence and Efficiency:\n"
#         "- Abolition and merger of tribunals have led to reduced specificity "
#         "and case overload.\n"
#         "- L. Chandra Kumar Case: The Supreme Court mentioned that appeals "
#         "to High Courts are available, reducing the purpose of tribunals, "
#         "as they cannot function as a binding verdict.\n"
#         "- Unfulfilled vacancies, infrastructure lags, the technical nature "
#         "of cases and unsuitable appointees have further reduced efficiency.\n\n"
#         "Conclusion / Way Forward:\n"
#         "There is a need to check and oversee the effectiveness of tribunals, "
#         "using modern technology such as e-Tribunals and AI."
#     ),
#     "subject": "GS Paper II",
#     "max_marks": 10,
#     "word_limit": 150,
# }
test_input_1 = { #Constitutional morality
    "question": (
        '"Constitutional morality acts as both a restraint and an enabler '
        'in a democratic society." Critically examine this statement in '
        'the context of recent judicial interpretations in India.'
    ),
    "answer": (
        "Constitutional morality refers to adherence to values of equality, "
        "liberty, justice, fraternity and more as enshrined in the Indian "
        "Constitution.\n\n"
        "As a Restraint:\n"
        "- Limits power of state and the rule of majoritarianism in a "
        "democracy, that may undermine rights of individuals and especially "
        "minorities.\n"
        "- Navtej Singh Johar Case - SC decriminalized homosexuality, "
        "emphasizing that popular morality cannot override constitutional "
        "morality.\n"
        "- Sabarimala Case - Court put an end to discriminatory practices "
        "against women with respect to temple entry.\n\n"
        "As an Enabler:\n"
        "- It empowers vulnerable sections and individuals to ensure "
        "opportunity for development, dignity and justice.\n"
        "- Joseph Shine Case - Adultery was decriminalized "
        "(equality, justice and dignity).\n"
        "- Shayara Bano Case - Triple Talaq (Talaq-e-Biddat) was declared "
        "unconstitutional (constitutional morality over religious freedom), "
        "as discriminatory.\n\n"
        "In a heterogeneous society like India, constitutional morality "
        "acts as both a safeguard and a guiding light to better our society "
        "and legislations in line with modern humanistic, developmental "
        "and equitable principles."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}


test_input_2 = {# elections_in_India
    "question": (
        "Discuss the relevance and challenges of holding simultaneous "
        "elections in India. Would it strengthen federalism or undermine it?"
    ),
    "answer": (
        "Simultaneous elections, also called as One Nation One Election, "
        "seek to synchronise Lok Sabha and State Assembly elections to "
        "reduce financial costs, policy lags due to frequent MCC imposition "
        "and administrative disruption.\n\n"
        "Relevance:\n"
        "- Reduced cost.\n"
        "- Reduced policy lag.\n"
        "- Curbing populist schemes.\n"
        "- Improved governance.\n"
        "- More focus on development and less on elections.\n"
        "- Policy continuity.\n\n"
        "Challenges:\n"
        "- Many constitutional amendments, like Articles 83, 172 and 356.\n"
        "- States are not happy with the idea.\n"
        "- Local body elections are left out.\n"
        "- Changes required in the RPA Act, 1951.\n\n"
        "Simultaneous Elections and Federalism:\n\n"
        "Strengthen:\n"
        "- Enhance political stability.\n"
        "- State issues to be reflected in central elections also.\n"
        "- Cooperative federalism can be enhanced as more time and energy "
        "can be given to developmental work.\n\n"
        "Undermine:\n"
        "- National parties may override state parties with narratives.\n"
        "- State issues may be undermined due to national agendas "
        "influencing voter behaviour.\n"
        "- Reduced duration of State Assembly in case of dissolution.\n\n"
        "Although a great vision, implementation efforts of ONOE must "
        "satisfy all federal stakeholders through consultation, deliberations "
        "and participation for national interest and not political benefit."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}


test_input_3 = { #tribunals
    "question": (
        "The role of tribunals in India has expanded but concerns about "
        "their independence and effectiveness persist. Critically evaluate "
        "the current tribunal system in light of recent judicial and "
        "legislative developments."
    ),
    "answer": (
        "Tribunals are quasi-judicial institutions added as the provisions "
        "of Articles 323A and 323B by the 42nd Constitutional Amendment "
        "Act, 1976, for fields like taxation, administration, environment "
        "and more.\n\n"
        "Role of tribunals have expanded with LPG reforms and neoliberal "
        "policies, specified nature of the cases it undertakes "
        "(e.g. Green Tribunal for environmental cases) and easing "
        "judiciary load.\n\n"
        "The Tribunal Reforms Act, 2021 raised greater concerns to tribunals.\n\n"
        "Tribunals are not bound by procedures of BNS and BNSS, making "
        "them unfairly inclined towards [unclear].\n\n"
        "Challenges to Independence and Efficiency:\n"
        "- Abolition and merger of various tribunals has led to reduced "
        "specificity and case overload.\n"
        "- L. Chandra Kumar Case - SC mentioned appeal to High Court "
        "available, reducing the purpose of tribunals as it cannot "
        "function as a binding verdict.\n"
        "- Unfulfilled vacancies, infrastructure lags, technical nature "
        "of cases and unsuitable appointees further reduced efficiency.\n\n"
        "Therefore, there is a need to check and oversee effectiveness "
        "of tribunals, using modern technology like e-Tribunals and AI."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}


test_input_4 = { #anti-defection
    "question": (
        "In light of increasing defections and political instability, "
        "do you think the Tenth Schedule of the Constitution needs a "
        "relook? Suggest reforms for strengthening anti-defection law."
    ),
    "answer": (
        "10th Schedule, inserted by 52nd Constitutional Amendment, seeks "
        "to curb political defection and horse trading (corrupt practices) "
        "in legislators (Parliament and State Assemblies).\n\n"
        "Relevance and Achievements:\n"
        "- Increased political stability and accountability.\n"
        "- Increased relevance of party whips.\n"
        "- Reduced corruption.\n"
        "- Reduction in individual defections.\n\n"
        "But recent events in Maharashtra State Assembly have highlighted "
        "the need to relook the 10th Schedule and issues with it.\n\n"
        "Challenges with ADL:\n"
        "- Reduced individual standing against party standing.\n"
        "- Bulk defections are allowed (2/3rd members), leading to reduced "
        "political stability as seen in Maharashtra recently.\n"
        "- Non-application to local bodies.\n"
        "- Speaker/Chairman, to act as the final authority, can be partisan.\n\n"
        "Suggested Reforms:\n"
        "- Powers may be shared between Speaker and Election Commission "
        "for more impartiality.\n"
        "- Merger parameter to be made more holistic.\n"
        "- Time-bound decision making by the Speaker.\n"
        "- Written statements of reasons and rationale behind verdict.\n"
        "- Enhancing intra-party democracy by forming an Anti-Defection "
        "Committee instead of only whips."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}


test_input_5 = { #Sevottam_model
    "question": (
        '"The success of good governance lies in citizen-centric '
        'administration." Examine the significance of the Sevottam model '
        'in this context.'
    ),
    "answer": (
        "Good governance in a democracy requires administration to be "
        "ethical, efficient, responsive and considerate to the needs and "
        "grievances of citizens.\n\n"
        "Ethical, efficient and citizen-centric administration leads to "
        "good governance.\n\n"
        "Sevottam Model was developed by the Department of Administrative "
        "Reforms and Public Grievances, ensuring a citizen-centric "
        "framework for ethical service delivery.\n\n"
        "Means and Significance of Sevottam:\n"
        "- Citizen Charter.\n"
        "- Grievance Redressal Mechanism.\n"
        "- Service Delivery/Efficiency.\n"
        "- Accountability and transparency.\n"
        "- Citizen empowerment.\n\n"
        "Sevottam requires internal shift in working model, attitude "
        "towards services and working culture towards citizens.\n\n"
        "Challenges:\n"
        "- No legal mandate, uniformity and clarity towards Citizen Charter.\n"
        "- High pending cases of grievance redressal.\n"
        "- Low digital literacy in both appointees and citizens.\n"
        "- Lack of awareness.\n"
        "- Weak monitoring and implementation.\n\n"
        "Way Forward:\n"
        "- Legal mandate, clear rules and guidelines.\n"
        "- One-stop helpline number for all government departments.\n"
        "- Sevottam officers to be appointed to integrate functions of "
        "Information Officer, CVC and Lokayukta.\n\n"
        "Although a great vision, Sevottam requires structural changes "
        "to make services more accessible to the public."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}

test_input_7 = {  # Right to Vote and Right to Contest Elections
    "question": (
        "In a democracy like India, the right to vote and the right to "
        "contest elections are important tools for citizens to express "
        "their dissent and fight for their rights against the state. "
        "Discuss the nature and scope of these rights."
    ),
    "answer": (
        "In a democracy like India,\n\n"
        "Right to vote and Right to contest elections become a powerful "
        "tool which could be exercised by people in order to express "
        "their dissent and to fight for their own rights against the state.\n\n"
        "Nature and Scope of the Right to vote\n\n"
        "1) Constitutional Guarantee :- According to Art 326 of the "
        "Constitution it is a right of every citizen to get registered "
        "as an elector in the Rolls.\n\n"
        "2) Legal Meaning → laws like ROP Act 1950 and ROP Act 1951 ensure "
        "that officials and institutions would be present for the citizens "
        "to get empowered their right to vote.\n\n"
        "3) Institutional Governance – Election Commission of India and "
        "States make sure that the person are able to get their voting rights.\n\n"
        "Nature and Restrictions → However few exceptions, barring people "
        "to get register in the rolls is :-\n\n"
        "→ Unsound mind.\n\n"
        "→ Committed an offence under laws like IPC or Food Adulteration Act.\n\n"
        "→ Less than 18 years of age.\n\n"
        "→ Not a citizen of India.\n\n"
        "Nature and scope of Right to Contest elections.\n\n"
        "1) Legal Meaning → ROP, 1951 (Section 8) ensures that everyone "
        "in the nation has right to contest elections, if they are fit "
        "to represent their constituency.\n\n"
        "2) Scope → For Lok Sabha anyone from the nation (citizen of India, "
        "25 years age) can contest from their respective, while for R-S "
        "the rules are similar just the age is 35 years.\n\n"
        "3) Restrictions – For Declaration, the table explains the "
        "restrictions, while others are listed in Section 123 of the ROP, 1951.\n\n"
        "Hence these both rights if exercised judiciously could ensure "
        "free and fair elections in India."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}
test_input_8 = {  # Fifth Industrial Revolution and Governance
    "question": (
        "The emergence of Fifth Industrial Revolution is likely to "
        "transform governance from a digital service-delivery model "
        "to a more intelligent, responsive, and citizen-centric system. "
        "Comment."
    ),
    "answer": (
        "Fifth Industrial Revolution in governance is expected to "
        "transform the Indian government into more citizen-centric "
        "model in the future and will also increase the efficiency "
        "of governance as well.\n\n"
        "Transforming governance through 5th IR\n\n"
        "Intelligent system\n\n"
        "1) 5th IR will help to use the resources judiciously and "
        "will be able to generate huge returns.\n\n"
        "2) Effective delivery of public services in the digital era "
        "could be ensured.\n\n"
        "3) Growth penetration could be ensured by the digital era "
        "in 5th IR, making intelligence to innovate in many spheres.\n\n"
        "Citizen Centric System\n\n"
        "1) Accountability would be ensured if every people would be "
        "able to exercise the power with their own.\n\n"
        "2) Last mile delivery of the public services would be ensured. "
        "Eg. Gram Suvidha App.\n\n"
        "3) Citizen oriented democratic model with the initiatives like "
        "Bhashini AI, vernacular languages would be made available "
        "in governance.\n\n"
        "Responsive system\n\n"
        "1) Democratic mindset rather than Bureaucratic mindset would "
        "also help the citizen.\n\n"
        "2) Responsiveness towards people would be ensured through "
        "transparent and intelligence system being developed. "
        "Eg. Sabha initiative.\n\n"
        "Democratizing public services and ensuring governance that "
        "is citizen centric is a key feature of 5th IR and such "
        "And Hence would achieve the meaning of decentralization."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}

test_input_9 = { #multipolar
    "question": (
        "For India, a multipolar world order would also mean a "
        "multipolar Asia. Comment."
    ),
    "answer": (
        "India has always remained against Bipolar world order and "
        "always remained towards multipolarity in the world with "
        "equitable sharing of resources and growing together.\n\n"

        "How Multipolar world order could ensure multipolar Asia.\n\n"

        "1) Rule Based order - Through multipolarity, rules could "
        "be enforced against the coercive nations that defy Rules "
        "(eg China’s coercive nature against the PCA ruling in the "
        "South China Sea).\n\n"

        "2) Supply Chain Resilience - India’s supply chain would "
        "also be ensured that would also benefit South Asia and "
        "South East Asia, and could ensure peaceful Asia, ensuring "
        "multipolar Asia.\n\n"

        "3) Institutional Autonomy -> Powerful institutions like "
        "G20, UN or QUAD could function more powerfully in a "
        "multipolar world which could ensure growth of all in Asia "
        "and other parts as well.\n\n"

        "4) Comverging diverse objectives:-\n"
        "India wants -> World: Bipolar, Asia: Multipolar, "
        "South: Unipolar.\n"
        "China wants -> World: Bipolar, Asia: Unipolar, "
        "South: Multipolar.\n\n"

        "Hence multipolar world could also ensure the convergence "
        "of multi-view points of both the nations in Asia.\n\n"

        "5) Reducing Chinese dominancy -> India could also ensure "
        "to counteract with the help of western powers, the "
        "dominance of China.\n\n"

        "Hence for India to be a first multipolar Asia, it is "
        "necessary to ensure multipolarity in the world."
    ),
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
}

if __name__ == "__main__":
    try:
        result = evaluate_submission(test_input_8)

        print("\n========== EVALUATION RESULT ==========\n")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        print("\n========== BASIC VALIDATION ==========\n")
        print("Status:", result["status"])

        if result["status"] == "success":
            scores = result["dimension_scores"]

            print(
                "Raw total:", result["raw_total_score"],
                "| Final:", result["total_score"], "/", result["max_marks"],
            )
            print("Number of dimensions:", len(scores))

            for s in scores:
                print(s["dimension"], s["raw_level"], "->", s["final_level"], "|", s["cap_note"], "|", s["audit_note"])

            af = result["answer_features"]
            print("  intro:", af["has_introduction"], "| conclusion:", af["has_conclusion"])
            for n in af["feature_notes"]:
                print("  note:", n)
            assert len(scores) == 5
            assert abs(result["raw_total_score"] - sum(i["score"] for i in scores)) < 0.05
            assert result["total_score"] * 2 == int(result["total_score"] * 2)
            assert 0 <= result["total_score"] <= result["max_marks"]

            print("Score validation: PASS")
            print("Feedback consistency:", result["feedback_consistent"])
        else:
            print("Errors:", result["errors"])

    except Exception as exc:
        print("Evaluation test failed:", repr(exc))
        raise