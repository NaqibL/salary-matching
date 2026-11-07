"""Candidate tier inference from neighbour Jev tiers (SGSAL-022 C7). No network/DB."""

from mcf.matching.service import infer_candidate_tier


def test_majority_tier_wins():
    assert infer_candidate_tier(["T3_Senior", "T3_Senior", "T2_Junior"]) == "T3_Senior"


def test_ties_go_to_the_more_junior_tier():
    assert infer_candidate_tier(["T1_Entry", "T2_Junior"]) == "T1_Entry"
    assert infer_candidate_tier(["T4_Management", "T3_Senior"]) == "T3_Senior"


def test_unknown_and_missing_tiers_are_ignored():
    assert infer_candidate_tier([None, "bogus", "T2_Junior"]) == "T2_Junior"
    assert infer_candidate_tier([]) is None
    assert infer_candidate_tier([None, "bogus"]) is None
