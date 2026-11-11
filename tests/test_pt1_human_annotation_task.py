import csv
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_pt1_human_annotation_task import TASK, validate


def test_annotation_template_has_40_unannotated_prompts():
    assert validate() == []


def test_annotation_template_rejects_prefilled_gold(tmp_path):
    target = tmp_path / "task.csv"
    shutil.copyfile(TASK, target)
    with target.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    rows[0]["answerability"] = "可答"
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    issues = validate(target)

    assert any("gold/annotation field must remain blank" in issue for issue in issues)
