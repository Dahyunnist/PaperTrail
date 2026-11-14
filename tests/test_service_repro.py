from pathlib import Path

from papertrail.cli import _parser
from papertrail.s1_index import open_database
from papertrail.web import create_app


ROOT = Path(__file__).resolve().parents[1]


def test_s5_synthetic_workspace_smoke_has_local_search_and_no_model(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERTRAIL_LLM_MODEL", "")
    app = create_app(tmp_path / "workspace.sqlite3", tmp_path / "uploads",
                     allow_local_dev_principal=True)
    app.config.update(TESTING=True)
    open_database(tmp_path / "workspace.sqlite3").close()
    client = app.test_client()

    assert client.get("/").status_code == 200
    response = client.get("/api/search?q=synthetic+needle")
    assert response.status_code == 200
    assert response.get_json() == {"results": []}
    assert client.get("/api/evidence/" + "a" * 64 + "/1").status_code == 404


def test_readme_reproduction_commands_match_available_cli_and_fixtures():
    parser = _parser()
    subcommands = parser._subparsers._group_actions[0].choices
    assert {"web", "mcp", "compare", "compare-label", "compare-gap", "compare-report"} <= set(subcommands)
    assert (ROOT / "evals/fixtures/pt3-synthetic/sources.yaml").is_file()
    assert (ROOT / "evals/pt3-synthetic-gold-20261023.jsonl").is_file()
    assert "scripts/verify_pt3_report.py" in (ROOT / "docs/demo-5-minutes.md").read_text(encoding="utf-8")


def test_web_and_mcp_local_demo_identity_requires_explicit_flag():
    parser = _parser()
    web_default = parser.parse_args(["web"])
    mcp_default = parser.parse_args(["mcp"])
    assert web_default.allow_local_dev_principal is False
    assert mcp_default.allow_local_dev_principal is False
    assert parser.parse_args(["web", "--allow-local-dev-principal"]).allow_local_dev_principal
    assert parser.parse_args(["mcp", "--allow-local-dev-principal"]).allow_local_dev_principal
