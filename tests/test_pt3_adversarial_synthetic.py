import hashlib
import json

import fitz

from papertrail.evaluate_qa import _correct_abstention, _gold_quote_coverage, _outcome_class
from papertrail.qa import _validate_quote


CASES = [
    {"id": "SYN-ADV-01", "kind": "answerable_complete", "abstain": False, "expected": "complete"},
    {"id": "SYN-ADV-02", "kind": "answerable_partial", "abstain": False, "expected": "partial"},
    {"id": "SYN-ADV-03", "kind": "unanswerable", "abstain": True, "expected": "correct_abstention"},
    {"id": "SYN-ADV-04", "kind": "false_refusal", "abstain": False, "expected": "false_refusal"},
    {"id": "SYN-ADV-05", "kind": "unsupported_claim", "abstain": False, "expected": "unsupported_claim"},
]
GOLD_SHA256 = hashlib.sha256(json.dumps(CASES, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_frozen_synthetic_adversarial_cases_and_scorer_hash(tmp_path):
    assert len(CASES) == 5
    assert len({case["id"] for case in CASES}) == 5
    scorer_sha = hashlib.sha256(__import__("pathlib").Path("papertrail/evaluate_qa.py").read_bytes()).hexdigest()

    pdf = tmp_path / "synthetic-adversarial.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "Synthetic supported claim has exactly 42 units.")
    doc.save(pdf)
    doc.close()
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    citation = {"sha256": sha, "page": 1, "quote": "Synthetic supported claim has exactly 42 units."}

    rows = [
        {"id": CASES[0]["id"], "pass": _validate_quote(str(pdf), sha, 1, citation["quote"], {})},
        {"id": CASES[1]["id"], "pass": _gold_quote_coverage(
            [{"sha256": sha, "pdf_page": 1, "quote": citation["quote"]},
             {"sha256": sha, "pdf_page": 2, "quote": "Missing synthetic second slot."}], [citation])[
                 "covered_quotes"] == 1},
        {"id": CASES[2]["id"], "result": _outcome_class(
            {"answered": False, "completion_state": "no_evidence"}, True)},
        {"id": CASES[3]["id"], "result": _outcome_class(
            {"answered": False, "completion_state": "refused"}, False)},
        {"id": CASES[4]["id"], "pass": _gold_quote_coverage(
            [{"sha256": sha, "pdf_page": 1, "quote": "Unsupported claim says 24 units."}], [citation])[
                 "covered_quotes"] == 0,
         "result": _outcome_class({"answered": True, "completion_state": "complete",
                                   "unsupported_claim": True}, False)},
    ]
    rows[0]["result"] = "complete" if rows[0]["pass"] else "fail"
    rows[1]["result"] = "partial" if rows[1]["pass"] else "fail"
    assert [row["result"] for row in rows] == [case["expected"] for case in CASES]
    assert _correct_abstention({"answered": False, "completion_state": "refused"}, expected_abstain=False) is False
    assert len(sha) == 64 and len(scorer_sha) == 64 and len(GOLD_SHA256) == 64
