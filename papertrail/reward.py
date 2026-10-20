"""Human-rated QA trajectory export and transparent reward calculation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .s1_index import open_database
from .qa import _ensure_qa_schema

RATING_BASE = {"correct": 1.0, "partially_correct": 0.5, "incorrect": -1.0,
               "abstention_correct": 0.5, "abstention_wrong": -0.5}


def rate_trajectory(database: Path, turn_id: str, rating: str, note: str = "") -> dict[str, Any]:
    if rating not in RATING_BASE:
        raise ValueError(f"rating must be one of {', '.join(RATING_BASE)}")
    conn = open_database(database)
    try:
        _ensure_qa_schema(conn)
        row = conn.execute("SELECT * FROM qa_trajectories WHERE turn_id=?", (turn_id,)).fetchone()
        if not row:
            raise ValueError("找不到该 QA 轨迹")
        total = row["total_claims"]
        rejected = row["rejected_claims"]
        grounding = max(0.0, 1 - rejected / total) if total else 1.0
        latency_penalty = min(row["latency_ms"] / 60_000, 0.1)
        reward = RATING_BASE[rating] * grounding - latency_penalty
        components = {"human_rating_base": RATING_BASE[rating], "claim_grounding_ratio": grounding,
                      "latency_penalty": latency_penalty, "formula": "base * grounding_ratio - latency_penalty"}
        rated_at = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE qa_trajectories SET user_rating=?,user_note=?,reward=?,reward_json=?,rated_at=? WHERE turn_id=?",
                     (rating, note[:1000], reward, json.dumps(components), rated_at, turn_id))
        conn.commit()
        return {"turn_id": turn_id, "rating": rating, "reward": reward, "components": components}
    finally:
        conn.close()


def trajectory_rows(database: Path) -> list[dict[str, Any]]:
    conn = open_database(database)
    try:
        _ensure_qa_schema(conn)
        rows = conn.execute("SELECT q.*,t.question,t.answer,t.retrieval_mode,t.context_query "
                            "FROM qa_trajectories q JOIN qa_turns t USING(turn_id) ORDER BY q.created_at").fetchall()
        output = []
        for row in rows:
            claims = conn.execute("SELECT ordinal,claim_text,evidence_json FROM qa_claims WHERE turn_id=? ORDER BY ordinal",
                                  (row["turn_id"],)).fetchall()
            output.append({**dict(row), "retrieval": json.loads(row["retrieval_json"]),
                           "evidence_refs": json.loads(row["evidence_json"]),
                           "usage": json.loads(row["usage_json"]) if row["usage_json"] else None,
                           "reward_components": json.loads(row["reward_json"]) if row["reward_json"] else None,
                           "claims": [{"ordinal": claim["ordinal"], "text": claim["claim_text"],
                                       "evidence": json.loads(claim["evidence_json"])} for claim in claims]})
        for row in output:
            for key in ("retrieval_json", "evidence_json", "usage_json", "reward_json"):
                row.pop(key, None)
        return output
    finally:
        conn.close()


def export_trajectories(database: Path, output: Path) -> int:
    rows = trajectory_rows(database)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return len(rows)
