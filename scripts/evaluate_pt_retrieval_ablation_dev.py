"""No-model retrieval ablations for PT7/PT8/PT10/PT11 public development groups."""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.gold import _normalize_excerpt
from papertrail import qa
from papertrail.retrieval import retrieve
from papertrail.qa import _sentences, _term_overlap, _validate_quote
from papertrail.s1_index import open_database

GROUPS = ("pt7", "pt8", "pt10", "pt11")
DATE = "20261023"
LIMITS = (20, 40, 80)
STOPWORDS = qa.QUESTION_STOPWORDS


def _gold(group: str) -> list[dict[str, Any]]:
    path = ROOT / "evals" / f"{group}-development-gold-{DATE}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[\w]+", text.casefold())
            if term not in STOPWORDS and len(term) > 1}


def _target_result(rows: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for target in item["evidence"]:
        key = (target["sha256"], target["pdf_page"])
        page_ranks = [index + 1 for index, row in enumerate(rows)
                      if (row["sha256"], row["pdf_page"]) == key]
        phrase = _normalize_excerpt(target["quote"])
        chunk_ranks = [index + 1 for index, row in enumerate(rows)
                       if row["sha256"] == target["sha256"]
                       and row["pdf_page"] == target["pdf_page"]
                       and phrase in _normalize_excerpt(row["text"])]
        results.append({"sha256": key[0], "pdf_page": key[1],
                        "page_candidate_rank": page_ranks[0] if page_ranks else None,
                        "gold_phrase_chunk_rank": chunk_ranks[0] if chunk_ranks else None,
                        "page_hit": bool(page_ranks), "gold_phrase_chunk_hit": bool(chunk_ranks)})
    return results


def _metadata_rerank(question: str, rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    terms = _terms(question)
    rescored = []
    for row in rows:
        title_matches = len(terms & _terms(row["title"]))
        section_matches = len(terms & _terms(row["section"]))
        score = row["rank_score"] + 0.001 * section_matches + 0.0005 * title_matches
        rescored.append((score, row))
    return [row for _, row in sorted(rescored, key=lambda pair: pair[0], reverse=True)[:limit]]


def _unique_pages(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    results = []
    seen: set[tuple[str, int | None]] = set()
    for row in rows:
        key = row["sha256"], row["pdf_page"]
        if key in seen:
            continue
        seen.add(key)
        results.append(row)
        if len(results) >= limit:
            break
    return results


def _citation_result(claims: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for target in item["evidence"]:
        key = (target["sha256"], target["pdf_page"])
        citations = [claim["evidence"] for claim in claims
                     if (claim["evidence"]["sha256"], claim["evidence"]["pdf_page"]) == key]
        phrase = _normalize_excerpt(target["quote"])
        result.append({"sha256": key[0], "pdf_page": key[1],
                       "page_cited": bool(citations),
                       "gold_phrase_contained": any(
                           phrase in _normalize_excerpt(row["quote"]) for row in citations)})
    return result


def _extractive_select(question: str, rows: list[dict[str, Any]], limit: int,
                       title_weight: int = 2, minimum_overlap: int | None = None,
                       diversity: str | None = None
                       ) -> list[dict[str, Any]]:
    query_terms = {term for term in re.findall(r"[\w]+", question.casefold())
                   if term not in STOPWORDS and len(term) > 1}
    if minimum_overlap is None:
        minimum_overlap = 0 if not query_terms else (2 if len(query_terms) >= 3 else 1)
    candidates = []
    for rank, row in enumerate(rows, 1):
        if row.get("text_origin", "native_text") != "native_text" or row["pdf_page"] is None:
            continue
        for sentence in _sentences(row["text"]):
            sentence_terms = set(re.findall(r"[\w]+", sentence.casefold()))
            overlap = _term_overlap(query_terms, sentence_terms)
            if not query_terms or overlap < minimum_overlap:
                continue
            title_terms = set(re.findall(r"[\w]+", row["title"].casefold()))
            title_overlap = _term_overlap(query_terms, title_terms)
            candidates.append((overlap + title_weight * title_overlap, rank,
                               row, sentence))
    candidates.sort(key=lambda item: (-item[0], item[1], len(item[3])))
    if diversity in {"paper", "page"}:
        groups: dict[Any, list[tuple[int, int, dict[str, Any], str]]] = {}
        for candidate in candidates:
            row = candidate[2]
            key = ((row["paper_id"], row["sha256"]) if diversity == "paper"
                   else (row["sha256"], row["pdf_page"]))
            groups.setdefault(key, []).append(candidate)
        candidates = [group[offset] for offset in range(max(map(len, groups.values()), default=0))
                      for group in groups.values() if offset < len(group)]
    page_cache: dict[tuple[str, int, str], str] = {}
    seen: set[tuple[str, int, str]] = set()
    paper_counts: dict[tuple[str, str], int] = {}
    selected = []
    for _, _, row, quote in candidates:
        key = (row["sha256"], row["pdf_page"], quote)
        paper_key = (row["paper_id"], row["sha256"])
        if key in seen or paper_counts.get(paper_key, 0) >= 2:
            continue
        if not _validate_quote(row["path"], row["sha256"], row["pdf_page"], quote, page_cache):
            continue
        seen.add(key)
        paper_counts[paper_key] = paper_counts.get(paper_key, 0) + 1
        selected.append({"evidence": {"sha256": row["sha256"],
                                      "pdf_page": row["pdf_page"], "quote": quote}})
        if len(selected) >= limit:
            break
    return selected


def _phrase_candidate_trace(question: str, rows: list[dict[str, Any]],
                           item: dict[str, Any]) -> list[dict[str, Any]]:
    query_terms = {term for term in re.findall(r"[\w]+", question.casefold())
                   if term not in STOPWORDS and len(term) > 1}
    threshold = 0 if not query_terms else (2 if len(query_terms) >= 3 else 1)
    ranked = []
    for result_rank, row in enumerate(rows, 1):
        if row.get("text_origin", "native_text") != "native_text" or row["pdf_page"] is None:
            continue
        for sentence in _sentences(row["text"]):
            terms = set(re.findall(r"[\w]+", sentence.casefold()))
            overlap = _term_overlap(query_terms, terms)
            if not query_terms or overlap < threshold:
                continue
            title_terms = set(re.findall(r"[\w]+", row["title"].casefold()))
            score = overlap + 2 * _term_overlap(query_terms, title_terms)
            ranked.append((score, result_rank, row, sentence, overlap))
    ranked.sort(key=lambda row: (-row[0], row[1], len(row[3])))
    trace = []
    for target in item["evidence"]:
        phrase = _normalize_excerpt(target["quote"])
        matches = [(index + 1, row) for index, row in enumerate(ranked)
                   if row[2]["sha256"] == target["sha256"]
                   and row[2]["pdf_page"] == target["pdf_page"]
                   and phrase in _normalize_excerpt(row[3])]
        all_phrase_spans = []
        for source_rank, source in enumerate(rows, 1):
            if source["sha256"] != target["sha256"] or source["pdf_page"] != target["pdf_page"]:
                continue
            all_phrase_spans.extend(sentence for sentence in _sentences(source["text"])
                                    if phrase in _normalize_excerpt(sentence))
        trace.append({"sha256": target["sha256"], "pdf_page": target["pdf_page"],
                      "phrase_sentence_in_top80_chunks": bool(all_phrase_spans),
                      "phrase_candidate_eligible": bool(matches),
                      "best_phrase_candidate_rank": matches[0][0] if matches else None,
                      "best_phrase_candidate_retrieval_rank": matches[0][1][1] if matches else None,
                      "best_phrase_candidate_overlap": matches[0][1][4] if matches else None,
                      "best_phrase_candidate_score": matches[0][1][0] if matches else None,
                      "best_phrase_candidate_quote": matches[0][1][3] if matches else None})
    return trace


def _run_question(group: str, item: dict[str, Any]) -> dict[str, Any]:
    database = ROOT / ".local" / f"{group}-development.sqlite3"
    candidates: dict[str, Any] = {}
    for mode in ("bm25", "bm25_expanded"):
        for limit in LIMITS:
            rows = retrieve(database, item["question"], limit, "original_pdf", mode)
            candidates[f"{mode}@{limit}"] = _target_result(rows, item)
    expanded_pool = retrieve(database, item["question"], 80, "original_pdf", "bm25_expanded")
    candidates["metadata_rerank_expanded80_to20"] = _target_result(
        _metadata_rerank(item["question"], expanded_pool, 20), item)
    candidates["page_unique_expanded80_to20"] = _target_result(
        _unique_pages(expanded_pool, 20), item)
    phrase_trace = _phrase_candidate_trace(item["question"], expanded_pool, item)

    extractive_variants = {}
    for mode, depth in (("bm25", 20), ("bm25_expanded", 20),
                        ("bm25_expanded", 40), ("bm25_expanded", 80)):
        rows = retrieve(database, item["question"], depth, "original_pdf", mode)
        label = f"{mode}_depth{depth}_title2_min2_limit5"
        extractive_variants[label] = _citation_result(
            _extractive_select(item["question"], rows, 5, 2), item)
        if mode == "bm25_expanded" and depth in (20, 80):
            extractive_variants[f"{mode}_depth{depth}_title0_min2_limit5"] = _citation_result(
                _extractive_select(item["question"], rows, 5, 0), item)
            extractive_variants[f"{mode}_depth{depth}_title2_min1_limit5"] = _citation_result(
                _extractive_select(item["question"], rows, 5, 2, 1), item)
            extractive_variants[f"{mode}_depth{depth}_paper_roundrobin"] = _citation_result(
                _extractive_select(item["question"], rows, 5, 2, diversity="paper"), item)
            extractive_variants[f"{mode}_depth{depth}_page_roundrobin"] = _citation_result(
                _extractive_select(item["question"], rows, 5, 2, diversity="page"), item)
            if depth == 80:
                extractive_variants[f"{mode}_depth{depth}_title2_min2_limit8"] = _citation_result(
                    _extractive_select(item["question"], rows, 8, 2), item)

    original_retrieve = qa.retrieve
    citation_variants = {}
    try:
        for mode in ("bm25", "bm25_expanded"):
            qa.retrieve = original_retrieve
            result = qa.ask(database, item["question"], limit=5, mode=mode,
                            generate=False, conversation_id=f"ablation-{uuid.uuid4()}")
            citation_variants[f"ask_{mode}_limit5"] = _citation_result(result["claims"], item)
    finally:
        qa.retrieve = original_retrieve
    return {"id": item["id"], "question": item["question"],
            "question_type": item["question_type"], "targets": len(item["evidence"]),
            "candidates": candidates, "citations": citation_variants,
            "extractive_selection": extractive_variants,
            "phrase_selection_trace_at_expanded80": phrase_trace}


def main() -> None:
    def forbid_model(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("retrieval ablation must not call a model")

    qa.chat_json = forbid_model
    groups = []
    for group in GROUPS:
        group_items = [item for item in _gold(group) if not item["abstain"]]
        groups.append({"group_id": group, "questions": [
            _run_question(group, item) for item in group_items]})
    cases = [question for group in groups for question in group["questions"]]
    totals: dict[str, dict[str, int]] = {}
    for question in cases:
        for family in ("candidates", "citations", "extractive_selection"):
            for variant, targets in question[family].items():
                stats = totals.setdefault(variant, {"gold_pages": 0, "page_hits": 0,
                                                     "gold_phrases": 0,
                                                     "gold_phrase_chunks": 0})
                stats["gold_pages"] += len(targets)
                stats["page_hits"] += sum(row.get("page_hit", row.get("page_cited", False))
                                          for row in targets)
                stats["gold_phrases"] += len(targets)
                stats["gold_phrase_chunks"] += sum(
                    row.get("gold_phrase_chunk_hit", row.get("gold_phrase_contained", False))
                    for row in targets)
    report = {
        "schema_version": 1,
        "dataset_role": "development_diagnostic",
        "scope": {"groups": list(GROUPS), "answerable_questions": len(cases),
                  "gold_pages": sum(question["targets"] for question in cases),
                  "model_calls": 0},
        "variants": totals,
        "groups": groups,
        "methods": {
            "bm25_and_expanded": "Native retrieval functions; page and exact gold-phrase-containing chunk rank recorded.",
            "candidate_depth": "Direct retrieval and simulated extractive selection tested depths 20/40/80; actual QA run confirms mode-specific output.",
            "metadata_rerank": "Expanded top-80 rescored with section lexical overlap 0.001 and title overlap 0.0005 per token.",
            "page_unique": "Expanded top-80 collapsed to first-ranked unique SHA/page pairs before top-20 recall.",
            "metadata_scope": "Every variant retains original_pdf source-type filter; no gold paper/title is used to filter candidates.",
        },
        "limitations": ["仅使用公开开发组；不读取 PT15、PT9、PT12 或冻结 gold。",
                        "候选召回和 extractive phrase containment 不代表语义正确率。",
                        "metadata_rerank 权重是诊断性对照，未经新数据验证。"],
    }
    output = ROOT / "evals/pt7-pt8-pt10-pt11-retrieval-ablation-20261023.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "scope": report["scope"],
                      "variants": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
