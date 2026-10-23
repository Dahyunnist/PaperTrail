"""Compare extractive citation mapping on PT7/PT8/PT10/PT11 development groups only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.gold import _normalize_excerpt
from papertrail import qa
from papertrail.qa import _validate_quote, ask
from papertrail.s1_index import open_database

GROUPS = ("pt7", "pt8", "pt10", "pt11")
MODES = ("bm25", "bm25_expanded")
DATE = "20261023"


def _gold(group: str) -> list[dict[str, Any]]:
    path = ROOT / "evals" / f"{group}-development-gold-{DATE}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _evaluate(group: str, mode: str) -> dict[str, Any]:
    database = ROOT / ".local" / f"{group}-development.sqlite3"
    artifact = ROOT / ".local" / f"{group}-development.vectors.joblib"
    conn = open_database(database)
    output = []
    totals = {"answerable_questions": 0, "gold_pages": 0, "cited_gold_pages": 0,
              "gold_phrases_contained": 0, "exact_gold_quotes": 0,
              "displayed_citations": 0, "source_validation_failures": 0, "model_calls": 0}
    try:
        for item in _gold(group):
            if item["abstain"]:
                continue
            result = ask(database, item["question"], limit=5, mode=mode, generate=False,
                         artifact=artifact)
            totals["model_calls"] += result["model_budget"]["calls"]
            totals["answerable_questions"] += 1
            cited = [claim["evidence"] for claim in result["claims"]]
            page_hits = phrase_hits = exact_hits = 0
            page_rows = []
            page_cache: dict[tuple[str, int, str], str] = {}
            for gold in item["evidence"]:
                matches = [row for row in cited if row.get("sha256") == gold["sha256"]
                           and row.get("pdf_page") == gold["pdf_page"]]
                phrase = _normalize_excerpt(gold["quote"])
                contained = any(phrase in _normalize_excerpt(row.get("quote", "")) for row in matches)
                exact = any(phrase == _normalize_excerpt(row.get("quote", "")) for row in matches)
                page_hits += int(bool(matches))
                phrase_hits += int(contained)
                exact_hits += int(exact)
                page_rows.append({"sha256": gold["sha256"], "pdf_page": gold["pdf_page"],
                                  "page_cited": bool(matches), "gold_phrase_contained": contained,
                                  "exact_gold_quote": exact})
            validation = []
            for citation in cited:
                path = Path(citation["path"])
                valid = citation.get("text_origin", "native_text") == "native_text" and _validate_quote(
                    str(path), citation["sha256"], citation["pdf_page"], citation["quote"], page_cache)
                validation.append(valid)
            failures = sum(not valid for valid in validation)
            totals["gold_pages"] += len(item["evidence"])
            totals["cited_gold_pages"] += page_hits
            totals["gold_phrases_contained"] += phrase_hits
            totals["exact_gold_quotes"] += exact_hits
            totals["displayed_citations"] += len(cited)
            totals["source_validation_failures"] += failures
            output.append({"id": item["id"], "gold_pages": page_rows,
                           "displayed_citations": len(cited),
                           "citation_source_valid": validation,
                           "model_calls": result["model_budget"]["calls"]})
    finally:
        conn.close()
    return {"group_id": f"{group}-public-development-{DATE}", "mode": mode,
            "totals": totals, "questions": output}


def main() -> None:
    def no_model_calls(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("development citation comparison must not call a model")

    qa.chat_json = no_model_calls
    groups = [_evaluate(group, mode) for group in GROUPS for mode in MODES]
    totals = {mode: {key: sum(row["totals"][key] for row in groups if row["mode"] == mode)
                     for key in next(row["totals"].keys() for row in groups if row["mode"] == mode)}
              for mode in MODES}
    report = {
        "schema_version": 1,
        "dataset_role": "development_diagnostic",
        "scope": {"groups": list(GROUPS), "questions": "answerable only", "model_calls": 0},
        "modes": totals,
        "groups": groups,
        "limitations": [
            "仅 PT7/PT8/PT10/PT11 开发题；结果不代表语义正确率或盲测表现。",
            "生成关闭；输出是可核验摘录，不是模型综合后的答案 claim。",
            "黄金短语为片段；完全相等衡量边界吻合，不等于引文合法性。",
        ],
    }
    path = ROOT / "evals" / f"pt7-pt8-pt10-pt11-claim-map-{DATE}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "modes": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
