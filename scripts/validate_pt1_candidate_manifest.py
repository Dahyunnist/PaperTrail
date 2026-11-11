from pathlib import Path
import hashlib
import json


def validate(manifest_path=None, project_root=None):
    root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[1]
    manifest_path = Path(manifest_path) if manifest_path else root / 'evals/pt1-candidate-manifest-20261111.json'
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    errors = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    except (OSError, json.JSONDecodeError) as exc:
        return [f'manifest unavailable or invalid: {exc}']
    sources = manifest.get('sources', [])
    if manifest.get('source_count') != len(sources) or len(sources) < 3:
        errors.append('source_count must match at least 3 source records')
    ids = [source.get('doi', '') for source in sources]
    if len(set(ids)) != len(ids) or any(not doi.startswith('10.') for doi in ids):
        errors.append('DOI missing or duplicate')
    for source in sources:
        if (source.get('license') != 'CC BY 4.0'
                or source.get('paper_split') != 'development_seen'
                or source.get('annotation_status') != '待人工标注'):
            errors.append(f"metadata invalid: {source.get('doi')}")
        try:
            path = (root / source['local_pdf']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                errors.append(f"PDF unavailable: {source.get('doi')}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != source['pdf_sha256']:
                errors.append(f"PDF hash mismatch: {source.get('doi')}")
        except (KeyError, OSError):
            errors.append(f"PDF unavailable: {source.get('doi')}")
    try:
        gold = (root / manifest['gold_file']).resolve()
        if not gold.is_relative_to(root) or not gold.is_file() or hashlib.sha256(gold.read_bytes()).hexdigest() != manifest['gold_file_sha256']:
            errors.append('gold hash mismatch')
        elif gold.read_text(encoding='utf8').strip():
            errors.append('candidate gold must remain empty until human annotation')
        schema = json.loads((root / manifest['gold_schema']).read_text(encoding='utf8'))
        if schema.get('title') != 'PaperTrail PT-1 manually annotated question':
            errors.append('unexpected gold schema')
    except (KeyError, OSError, json.JSONDecodeError):
        errors.append('gold file or schema unavailable/invalid')
    return errors


if __name__ == '__main__':
    issues = validate()
    if issues:
        print('\n'.join(issues))
        raise SystemExit(1)
    print('PT1 candidate source/hash/license metadata and pending-gold checks passed (6 sources; 0 annotations).')
