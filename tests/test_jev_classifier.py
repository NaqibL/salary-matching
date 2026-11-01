"""Jev classifier: payload shape, response parsing, fallbacks. No network."""

from __future__ import annotations

import json

import httpx

from mcf.lib.embeddings.jev_classifier import (
    OTHER_ROLE_KEY,
    ROLE_FAMILIES,
    ROLE_FAMILY_ID,
    JevClassifier,
    build_payload,
    parse_response,
    role_family_rows,
)


def _response(role="software_engineering", role_conf=0.9, score=2.0, tier_conf=0.8, cost=0.00007):
    return {
        "answers": {
            "role_family": {"choice": role, "confidence": role_conf},
            "seniority": {"score": score, "confidence": tier_conf},
        },
        "usage": {"cost": cost},
    }


def test_role_family_ids_are_stable_and_unique():
    ids = [ROLE_FAMILY_ID[k] for k, _, _ in ROLE_FAMILIES]
    assert ids == list(range(1, len(ROLE_FAMILIES) + 1))
    assert ROLE_FAMILY_ID[OTHER_ROLE_KEY] == 0
    rows = role_family_rows()
    assert len(rows) == len(ROLE_FAMILIES) + 1
    assert len({r[1] for r in rows}) == len(rows)


def test_payload_includes_position_levels_and_truncates():
    p = build_payload("Data Engineer", "x" * 10_000, ["Senior Executive"])
    assert p["state"]["employer_position_levels"] == ["Senior Executive"]
    assert len(p["state"]["job_description"]) == 6000
    assert set(p["questions"]) == {"role_family", "seniority"}
    assert p["questions"]["role_family"]["type"] == "choice"
    assert p["questions"]["seniority"]["type"] == "score"


def test_parse_maps_score_to_tier_and_keeps_confidences():
    r = parse_response(_response(score=2.4))
    assert r is not None
    assert r.role_key == "software_engineering"
    assert r.tier == "T3_Senior"
    assert r.role_conf == 0.9 and r.tier_conf == 0.8
    assert r.cost_usd == 0.00007


def test_parse_low_confidence_or_unknown_role_becomes_other():
    assert parse_response(_response(role_conf=0.3)).role_key == OTHER_ROLE_KEY
    assert parse_response(_response(role="astronaut")).role_key == OTHER_ROLE_KEY
    assert parse_response(_response(score=9)).tier == "T4_Management"
    assert parse_response(_response(score=-3)).tier == "T1_Entry"


def test_parse_malformed_returns_none():
    assert parse_response({}) is None
    assert parse_response({"answers": {"role_family": {}}}) is None


def test_classify_many_preserves_order_and_handles_failures():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        title = body["state"]["job_title"]
        calls.append(title)
        if title == "bad":
            return httpx.Response(400, text="nope")
        return httpx.Response(200, json=_response(role="fnb_hospitality", score=0.2))

    jev = JevClassifier(api_key="k", retries=0, transport=httpx.MockTransport(handler))
    out = jev.classify_many([("Chef", "cooks", None), ("bad", "x", None), ("Cook", "y", ["Fresh/entry level"])], workers=3)
    assert len(out) == 3
    assert out[0] is not None and out[0].role_key == "fnb_hospitality" and out[0].tier == "T1_Entry"
    assert out[1] is None
    assert out[2] is not None
    assert sorted(calls) == ["Chef", "Cook", "bad"]


def test_classify_skips_empty_input():
    jev = JevClassifier(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert jev.classify(None, None) is None
