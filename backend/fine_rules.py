"""Which law an AI-flagged event breaks, and its maximum fine: Road Transport Act 2018 (Act No. 47 of 2018).

The same rules (by `rule_id`) are on the website's traffic rules page (web/lib/rules.ts); test_fine_rules.py
checks that the two agree. These are legal MAXIMUMS: police or a court set the actual fine. RoadWatch only
suggests the rule; a reviewer and then police/admin confirm every case and amount (nothing is fined automatically).
"""
from __future__ import annotations

# event type -> the rule it breaks
FINE_RULES: dict[str, dict] = {
    "wrong_way": {
        "rule_id": "wrong-way", "rule": "49(1)(ঘ)", "penalty": "92(1)", "max_bdt": 10_000,
        "en": "Wrong-way driving", "bn": "উল্টো পথে গাড়ি চালানো",
    },
    "bus_midroad_stop": {
        "rule_id": "parking", "rule": "47", "penalty": "90", "max_bdt": 5_000,
        "en": "Stopping to pick up or drop passengers outside a designated stop",
        "bn": "নির্ধারিত স্থান ছাড়া যাত্রী ওঠানামার জন্য থামানো",
    },
    "u_turn": {   # an illegal U-turn breaks a sign or signal (no U-turn sign, divider, police signal)
        "rule_id": "signals", "rule": "42", "penalty": "85", "max_bdt": 10_000,
        "en": "Illegal U-turn against a traffic sign or signal", "bn": "ট্রাফিক সাইন বা সংকেত অমান্য করে ইউ-টার্ন",
    },
}


def for_event(event_type: str | None) -> dict | None:
    r = FINE_RULES.get(event_type or "")
    return dict(r) if r else None
