"""Company name variants: one key per organisation, whatever the spelling on the ad.

Job ads name the same organisation several ways: upper case or mixed, with or without the
legal form ("Pte. Ltd.", "Limited", "LLP"), with or without a place qualifier ("(Singapore)",
"(S)", "Singapore Branch", "Asia Pacific"). ``name_key`` reduces a name to the part that
identifies the organisation, so those spellings share a key and can be shown as one company.

Deliberately conservative: only the legal form and a trailing place qualifier are dropped.
Words that distinguish sister companies ("Holdings", "Group", "Services", "International",
"Trains" vs "Buses") are kept, so separate legal entities of one brand stay separate.
"""

from __future__ import annotations

import re

# Legal-form words, dropped from the end of a name.
_LEGAL = frozenset(
    "pte pvt private ltd limited llp llc lp inc incorporated corp corporation co company "
    "sdn bhd plc gmbh pty".split()
)
# Trailing place qualifiers, longest first. "s" only arrives here from "(S)" / "(S'pore)".
_PLACE_TAILS: tuple[tuple[str, ...], ...] = (
    ("singapore", "branch"),
    ("asia", "pacific"),
    ("singapore",),
    ("apac",),
    ("asia",),
    ("sg",),
)
# A place word after one of these is part of the name itself ("Bank of Singapore").
_CONNECTORS = frozenset({"of", "and", "for", "at", "in", "the", "de", "la"})
_MIN_KEY_CHARS = 3
_MAX_ACRONYM_CHARS = 3


def _tokens(name: str) -> list[str]:
    s = name.lower()
    s = re.sub(r"\(\s*s(?:'?pore)?\s*\)", " singapore ", s)  # "(S)", "(S'pore)"
    s = s.replace("&", " and ")
    s = re.sub(r"[.,'’`\"]", "", s)
    s = re.sub(r"[^a-z0-9*+@#]+", " ", s)
    return s.split()


def _strip_legal(toks: list[str]) -> list[str]:
    out = list(toks)
    while len(out) > 1:
        if out[-3:] == ["limited", "liability", "partnership"] and len(out) > 3:
            out = out[:-3]
        elif out[-1] in _LEGAL:
            out.pop()
        else:
            break
    return out


def _strip_place(toks: list[str]) -> list[str]:
    for tail in _PLACE_TAILS:
        n = len(tail)
        if len(toks) > n and tuple(toks[-n:]) == tail and toks[-n - 1] not in _CONNECTORS:
            return toks[:-n]
    return toks


def name_key(name: str | None) -> str:
    """Key shared by spelling variants of one organisation; "" for an unusable name."""
    toks = _tokens(name or "")
    if not toks:
        return ""
    if len(toks) > 1 and toks[0] == "the":
        toks = toks[1:]
    strict = _strip_legal(toks)
    cur = strict
    for _ in range(4):  # "X Co., Ltd. (Singapore Branch) Pte Ltd" needs a few passes
        nxt = _strip_legal(_strip_place(cur))
        if nxt == cur:
            break
        cur = nxt
    # Dropping the place left too little to identify anyone: a bare acronym ("AMT (Singapore)"
    # and "AMT" are often unrelated firms), a two-letter stub, or only connectors. Keep the
    # place in the key then, so only identical legal names merge.
    if cur != strict and (
        len("".join(cur)) < _MIN_KEY_CHARS
        or (len(cur) == 1 and len(cur[0]) <= _MAX_ACRONYM_CHARS)
        or all(t in _CONNECTORS for t in cur)
    ):
        cur = strict
    return " ".join(cur)


def _looks_shouty(name: str) -> bool:
    letters = [c for c in name if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.9


def pick_display_name(candidates: list[dict]) -> str:
    """The name to show for a group of spelling variants.

    Each candidate is ``{"name", "is_canonical", "active", "total"}``. An existing cleaned
    (canonical) name wins; then the spelling with the most open ads, then the most ads ever,
    then a mixed-case spelling over an all-capitals one, then the shortest.
    """
    best = min(
        candidates,
        key=lambda c: (
            not c.get("is_canonical"),
            -int(c.get("active") or 0),
            -int(c.get("total") or 0),
            _looks_shouty(c["name"]),
            len(c["name"]),
            c["name"],
        ),
    )
    return best["name"]
