"""Loopback-only Flask learning workspace for PaperTrail S5."""

from __future__ import annotations

import hmac
import json
import secrets
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, jsonify, make_response, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

import yaml

from .audit import _hash
from .compare import add_gap_candidate, compare_papers, comparison_report, label_evidence
from .qa import ask, conversation_history
from .s1_index import open_database
from .jobs import enqueue_index, get_job
from .workspace import (create_note, dashboard_stats, delete_note, ensure_workspace_schema,
                        library_documents, list_uploads, remove_upload, search_notes, study_report,
                        register_upload, update_upload)


def create_app(database: Path | str = Path(".local/papertrail.sqlite3"),
               upload_root: Path | str | None = None,
               sources_config: Path | str | None = None,
               selection_manifest: Path | str | None = None) -> Flask:
    database = Path(database).resolve()
    upload_root = Path(upload_root).resolve() if upload_root else database.parent / "uploads"
    project_root = Path(__file__).resolve().parent.parent
    sources_config = Path(sources_config).resolve() if sources_config else project_root / "configs" / "sources.example.yaml"
    selection_manifest = Path(selection_manifest).resolve() if selection_manifest else project_root / "configs" / "s1-pilot.jsonl"
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=100 * 1024 * 1024,
                      DATABASE=database, UPLOAD_ROOT=upload_root, CSRF_ENABLED=True)

    @app.before_request
    def csrf_guard() -> None:
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        if request.method == "POST" and app.config["CSRF_ENABLED"]:
            token = session.get("_csrf", "")
            if not token or not hmac.compare_digest(token, request.form.get("_csrf", "")):
                abort(400, "表单令牌无效，请刷新页面后重试。")

    @app.get("/")
    def home() -> str:
        conn = open_database(app.config["DATABASE"])
        try:
            ensure_workspace_schema(conn)
            recent = [dict(row) for row in conn.execute(
                "SELECT c.conversation_id,c.title,c.updated_at,COUNT(t.turn_id) AS turns "
                "FROM qa_conversations c LEFT JOIN qa_turns t ON t.conversation_id=c.conversation_id "
                "GROUP BY c.conversation_id ORDER BY c.updated_at DESC LIMIT 8")]
        finally:
            conn.close()
        conversation_id = request.args.get("conversation_id", "")
        comparison_id = request.args.get("comparison_id", "")
        return render_template(
            "index.html", csrf_token=session["_csrf"], stats=dashboard_stats(app.config["DATABASE"]),
            documents=library_documents(app.config["DATABASE"]), uploads=list_uploads(app.config["DATABASE"]),
            notes=search_notes(app.config["DATABASE"], request.args.get("note_q", "")),
            note_query=request.args.get("note_q", ""), recent_conversations=recent,
            conversation_id=conversation_id,
            turns=conversation_history(app.config["DATABASE"], conversation_id) if conversation_id else [],
            comparison=comparison_report(app.config["DATABASE"], comparison_id) if comparison_id else None,
            can_load_config=sources_config.is_file() and selection_manifest.is_file(),
        )

    @app.post("/index-selected")
    def index_selected() -> Any:
        if not sources_config.is_file() or not selection_manifest.is_file():
            flash("没有找到已配置的来源清单。", "warning")
            return redirect(url_for("home") + "#library")
        try:
            job_id = enqueue_index(app.config["DATABASE"], sources_config, selection_manifest)
            flash(f"索引任务已排队：{job_id}。可通过 /jobs/{job_id} 查看进度。", "success")
        except (ValueError, OSError) as exc:
            flash(f"读取配置文献失败：{exc}", "warning")
        return redirect(url_for("home") + "#library")

    @app.get("/jobs/<job_id>")
    def index_job(job_id: str) -> Any:
        job = get_job(app.config["DATABASE"], job_id)
        return (jsonify(job), 200) if job else (jsonify({"error": "job_not_found"}), 404)

    @app.post("/ask")
    def ask_question() -> Any:
        try:
            result = ask(app.config["DATABASE"], request.form.get("question", ""),
                         request.form.get("conversation_id") or None,
                         limit=5, mode="bm25")
            flash("已保存本轮问题与逐条核验的原文摘录。" if result["claims"] else
                  "未找到通过文件版本和页码核验的证据，系统已拒答。", "success" if result["claims"] else "warning")
            return redirect(url_for("home", conversation_id=result["conversation_id"]) + "#assistant")
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("home") + "#assistant")

    @app.post("/notes")
    def add_note() -> Any:
        try:
            create_note(app.config["DATABASE"], request.form.get("concept", ""),
                        request.form.get("body", ""))
            flash("个人笔记已保存，与论文原文证据分开存放。", "success")
        except ValueError as exc:
            flash(str(exc), "warning")
        return redirect(url_for("home") + "#notes")

    @app.post("/notes/<note_id>/delete")
    def remove_note(note_id: str) -> Any:
        flash("个人笔记已删除。" if delete_note(app.config["DATABASE"], note_id) else "没有找到该笔记。")
        return redirect(url_for("home") + "#notes")

    @app.post("/uploads")
    def upload_pdf() -> Any:
        file = request.files.get("pdf")
        if file is None or not file.filename:
            flash("请选择一个 PDF 文件。", "warning")
            return redirect(url_for("home") + "#library")
        original_name = secure_filename(Path(file.filename).name)
        if not original_name or Path(original_name).suffix.casefold() != ".pdf":
            flash("目前只接受 PDF 文件。", "warning")
            return redirect(url_for("home") + "#library")
        upload_root = app.config["UPLOAD_ROOT"]
        upload_root.mkdir(parents=True, exist_ok=True)
        upload_id = secrets.token_hex(16)
        stored_path = (upload_root / f"{upload_id}.pdf").resolve()
        if not stored_path.is_relative_to(upload_root):
            abort(400)
        file.save(stored_path)
        with stored_path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                stored_path.unlink(missing_ok=True)
                flash("文件内容不像有效 PDF，未加入索引。", "warning")
                return redirect(url_for("home") + "#library")
        sha256 = _hash(stored_path)
        register_upload(app.config["DATABASE"], upload_id, sha256, original_name, stored_path)
        root_config = upload_root.parent / f"upload-sources-{upload_id}.yaml"
        root_config.write_text(yaml.safe_dump({"roots": [{"id": "user_uploads", "path": str(upload_root)}]},
                                               allow_unicode=True), encoding="utf-8")
        manifest = upload_root.parent / f"upload-{upload_id}.jsonl"
        manifest.write_text(json.dumps({"root_id": "user_uploads", "file_name": stored_path.name,
            "relative_path": stored_path.name, "sha256": sha256, "kind": "pdf",
            "source_type": "original_pdf"}, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            update_upload(app.config["DATABASE"], upload_id, "queued", "")
            job_id = enqueue_index(app.config["DATABASE"], root_config, manifest, upload_id)
            flash(f"PDF 已安全保存，后台索引任务已排队：{job_id}。", "success")
        except Exception as exc:
            update_upload(app.config["DATABASE"], upload_id, "failed", f"{type(exc).__name__}: {exc}")
            flash("PDF 已保存，但索引失败；可以在下方删除后重试。", "warning")
        return redirect(url_for("home") + "#library")

    @app.post("/uploads/<upload_id>/delete")
    def delete_uploaded_pdf(upload_id: str) -> Any:
        try:
            removed = remove_upload(app.config["DATABASE"], upload_id, app.config["UPLOAD_ROOT"])
            flash("个人上传 PDF 已删除。" if removed else "没有找到该上传文件。", "success" if removed else "warning")
        except (ValueError, OSError) as exc:
            flash(f"无法删除上传文件：{exc}", "warning")
        return redirect(url_for("home") + "#library")

    @app.post("/compare")
    def run_comparison() -> Any:
        try:
            result = compare_papers(app.config["DATABASE"], request.form.get("topic", ""),
                                   request.form.get("claim", ""), 8)
            flash(f"已找到 {result['paper_count']} 篇论文的候选证据；立场尚未分类。", "success")
            return redirect(url_for("home", comparison_id=result["comparison_id"]) + "#compare")
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("home") + "#compare")

    @app.post("/compare/evidence/<evidence_id>/label")
    def annotate_evidence(evidence_id: str) -> Any:
        comparison_id = request.form.get("comparison_id", "")
        try:
            label_evidence(app.config["DATABASE"], evidence_id,
                           request.form.get("label", "unclear"), request.form.get("rationale", ""))
            flash("证据标签和理由已保存为人工判断。", "success")
        except ValueError as exc:
            flash(str(exc), "warning")
        return redirect(url_for("home", comparison_id=comparison_id) + "#compare")

    @app.post("/compare/gaps")
    def save_gap() -> Any:
        comparison_id = request.form.get("comparison_id", "")
        ids = request.form.getlist("evidence_id")
        try:
            add_gap_candidate(app.config["DATABASE"], comparison_id,
                              request.form.get("note", ""), ids)
            flash("研究空白候选已保存，状态为待复核。", "success")
        except ValueError as exc:
            flash(str(exc), "warning")
        return redirect(url_for("home", comparison_id=comparison_id) + "#compare")

    @app.get("/reports/study.json")
    def export_report() -> Any:
        payload = json.dumps(study_report(app.config["DATABASE"]), ensure_ascii=False, indent=2)
        response = make_response(payload)
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        response.headers["Content-Disposition"] = "attachment; filename=papertrail-study-report.json"
        return response

    @app.errorhandler(413)
    def too_large(_: Any) -> Any:
        flash("PDF 超过 100 MB 上传上限。", "warning")
        return redirect(url_for("home") + "#library")

    return app


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="在本机启动 PaperTrail 学习助手")
    parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    parser.add_argument("--upload-root", type=Path)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    create_app(args.db, args.upload_root, args.sources, args.selection).run(host="127.0.0.1", port=args.port,
                                              debug=False, threaded=True)


if __name__ == "__main__":
    main()
