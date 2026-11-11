from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_pt1_candidate_manifest import validate


def _fixture(tmp_path):
    (tmp_path / 'evals').mkdir()
    (tmp_path / 'pdfs').mkdir()
    pdf = tmp_path / 'pdfs' / 'paper.pdf'
    pdf.write_bytes(b'public fixture bytes')
    gold = tmp_path / 'evals' / 'gold.jsonl'
    gold.write_text('', encoding='utf-8')
    schema = tmp_path / 'evals' / 'schema.json'
    schema.write_text(json.dumps({'title': 'PaperTrail PT-1 manually annotated question'}), encoding='utf-8')
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    sources = [{
        'doi': f'10.1/{i}', 'license': 'CC BY 4.0', 'paper_split': 'development_seen',
        'annotation_status': '待人工标注', 'local_pdf': 'pdfs/paper.pdf', 'pdf_sha256': sha,
    } for i in range(3)]
    manifest = tmp_path / 'evals' / 'manifest.json'
    manifest.write_text(json.dumps({
        'source_count': 3, 'sources': sources, 'gold_file': 'evals/gold.jsonl',
        'gold_file_sha256': hashlib.sha256(b'').hexdigest(), 'gold_schema': 'evals/schema.json',
    }), encoding='utf-8')
    return manifest, pdf


def test_current_candidate_manifest_passes():
    assert validate() == []


def test_candidate_manifest_rejects_pdf_hash_tampering(tmp_path):
    manifest, pdf = _fixture(tmp_path)
    pdf.write_bytes(b'tampered fixture bytes')

    issues = validate(manifest, tmp_path)

    assert sum('PDF hash mismatch' in issue for issue in issues) == 3
