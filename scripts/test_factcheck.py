from app.evaluator.factcheck import verify_claim

# (claim, labels that are acceptable)
S, C, U = "supported", "contradicted", "unverifiable"
CLAIMS = [
    ("Articles 323A and 323B were inserted by the 42nd Constitutional Amendment Act, 1976.", {S, U}),
    ("The Tenth Schedule was inserted by the 52nd Constitutional Amendment.", {S, U}),
    ("The 91st Amendment Act, 2003 removed the one-third split provision of the Tenth Schedule.", {S, U}),
    ("The Women's Reservation Act, 2023 is the Constitution (106th Amendment) Act.", {S, U}),
    ("The 73rd Amendment reserved one-third of seats for women in Panchayati Raj institutions.", {S, U}),
    ("Article 32 gives the right to move the Supreme Court for enforcement of fundamental rights.", {S, U}),
    ("The Tribunal Reforms Act was enacted in 2021.", {S, U}),
    ("The Representation of the People Act was enacted in 1951.", {S, U}),
    ("The Sevottam model has five modules.", {C, U}),
    ("Article 21 guarantees the right to vote.", {C, U}),
    ("Tribunals are not bound by the procedures of BNS and BNSS.", {C, U}),
    ("Hussainara Khatoon v. State of Bihar was decided in 1979.", {S, U}),   # may not be on the allowlist
]

bad_contradictions = 0
for claim, ok in CLAIMS:
    v = verify_claim(claim, use_cache=False)
    flag = "OK  " if v["label"] in ok else "FAIL"
    if v["label"] == C and C not in ok:
        bad_contradictions += 1
    print(f"{flag} {v['label']:<13} sources={len(v['sources'])}  {claim[:70]}")
    if v["label"] != U:
        print(f"       quote: {(v['quote'] or '')[:110]}")

print(f"\nFalse contradictions: {bad_contradictions} (must be 0)")