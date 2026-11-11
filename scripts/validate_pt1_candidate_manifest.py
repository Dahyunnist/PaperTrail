from pathlib import Path
import json,hashlib,sys
root=Path(__file__).resolve().parents[1]
def validate():
 m=json.loads((root/'evals/pt1-candidate-manifest-20261111.json').read_text(encoding='utf8')); errors=[]
 if m.get('source_count')!=3 or len(m.get('sources',[]))!=3:errors.append('source_count must be 3')
 ids=[s.get('doi') for s in m.get('sources',[])]
 if len(set(ids))!=len(ids) or any(not x.startswith('10.') for x in ids):errors.append('DOI missing or duplicate')
 for s in m.get('sources',[]):
  if s.get('license')!='CC BY 4.0' or s.get('paper_split')!='development_seen' or s.get('annotation_status')!='待人工标注':errors.append(f"metadata invalid: {s.get('doi')}")
  p=(root/s['local_pdf']).resolve()
  if not p.is_relative_to(root) or not p.is_file():errors.append(f"PDF unavailable: {s['doi']}")
  elif hashlib.sha256(p.read_bytes()).hexdigest()!=s['pdf_sha256']:errors.append(f"PDF hash mismatch: {s['doi']}")
 gold=root/m['gold_file']
 if not gold.is_file() or hashlib.sha256(gold.read_bytes()).hexdigest()!=m['gold_file_sha256']:errors.append('gold hash mismatch')
 if gold.read_text(encoding='utf8').strip():errors.append('candidate gold must remain empty until human annotation')
 schema=json.loads((root/m['gold_schema']).read_text(encoding='utf8'))
 if schema.get('title')!='PaperTrail PT-1 manually annotated question':errors.append('unexpected gold schema')
 return errors
if __name__=='__main__':
 issues=validate()
 if issues:print('\n'.join(issues));raise SystemExit(1)
 print('PT1 candidate source/hash/license metadata and pending-gold checks passed (3 sources; 0 annotations).')
