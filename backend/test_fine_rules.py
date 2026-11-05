"""The fine suggestions must match the website's traffic rules page.  cd backend && python -m pytest -q"""
import re
from pathlib import Path

import fine_rules

RULES_TS = (Path(__file__).parent.parent / "web" / "lib" / "rules.ts").read_text(encoding="utf-8")


def _rule_block(rule_id: str) -> str:
    m = re.search(r'id: "%s".*?\n  \},' % re.escape(rule_id), RULES_TS, re.S)
    assert m, f"rule {rule_id} not on the rules page"
    return m.group(0)


def test_every_offence_maps_to_a_rule_on_the_page_with_the_same_law_and_maximum():
    import accounts
    assert set(fine_rules.FINE_RULES) == accounts.CASE_TYPES     # every reportable event type has a law
    for etype, law in fine_rules.FINE_RULES.items():
        block = _rule_block(law["rule_id"])
        assert f'penalty: "{law["penalty"]}"' in block, etype
        fine = re.search(r"fineBdt: \{[^}]*max: ([\d_]+)", block)
        assert fine and int(fine.group(1).replace("_", "")) == law["max_bdt"], etype
        assert law["max_bdt"] <= accounts.MAX_FINE_BDT
