from copy import deepcopy

from scripts.validate_pt1_annotation_slice import FIELDS, validate


def _draft():
    return [{"task_id": f"PT1-H00{i}", "candidate_question": "candidate",
             "status": "draft", "source": {"pdf_path": "pending", "pdf_sha256": "pending",
             "evidence_page": "pending", "evidence_locator": "pending"},
             "adjudication": "pending", "annotations": []} for i in range(1, 6)]


def _gold():
    row = _draft()[0]
    row.update(status="gold", adjudication="resolved")
    row["source"] = {"pdf_path": "local.pdf", "pdf_sha256": "a" * 64,
                     "evidence_page": 1, "evidence_locator": "section heading"}
    row["annotations"] = [{**{field: "filled" for field in FIELDS},
                           "annotator": person, "independent": True}
                          for person in ("A", "B")]
    return [row, *_draft()[1:]]


def test_five_pending_cases_are_valid_drafts():
    assert validate(_draft()) == []


def test_complete_human_adjudicated_case_can_be_gold():
    assert validate(_gold()) == []


def test_gold_rejects_pending_source_location():
    rows = _gold()
    rows[0]["source"]["pdf_sha256"] = "pending"
    assert any("source locator incomplete" in issue for issue in validate(rows))


def test_gold_requires_two_distinct_independent_annotators():
    rows = _gold()
    rows[0]["annotations"][1]["annotator"] = "A"
    assert any("two distinct annotators" in issue for issue in validate(rows))
    rows = _gold()
    rows[0]["annotations"][1]["independent"] = False
    assert any("independent annotations incomplete" in issue for issue in validate(rows))


def test_gold_requires_adjudication_and_rejects_unknown_status():
    rows = _gold()
    rows[0]["adjudication"] = "pending"
    assert any("adjudication unresolved" in issue for issue in validate(rows))
    rows = _draft()
    rows[0]["status"] = "accepted"
    assert any("status must be draft or gold" in issue for issue in validate(rows))
