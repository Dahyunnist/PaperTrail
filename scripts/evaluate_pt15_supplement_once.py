"""Run one cost-gated, non-blind PT15 addendum over the two skipped items."""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from papertrail import qa
from papertrail.local_llm import _max_request_cost
from papertrail.qa import _validate_quote, ask
PRE=ROOT/'evals/pt15-supplement-prereg-20261023.json'
GOLD=ROOT/'evals/pt15-heldout-gold-20261023.jsonl'
LEDGER=ROOT/'.local/pt-master-usage.json'
REPORT=ROOT/'evals/pt15-supplement-20261023.json'
def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->None:
 ap=argparse.ArgumentParser();ap.add_argument('--run-once',action='store_true');args=ap.parse_args()
 pre=json.loads(PRE.read_text(encoding='utf-8'))
 db=ROOT/pre['supplement_database']
 if sha(GOLD)!=pre['gold_sha256'] or sha(ROOT/pre['source_database'])!=pre['source_database_sha256'] or sha(db)!=pre['supplement_database_sha256']:
  raise SystemExit('冻结题集或索引哈希不符')
 if sha(ROOT/'papertrail/qa.py')!=pre['qa_sha256'] or sha(ROOT/'papertrail/local_llm.py')!=pre['local_llm_sha256']:
  raise SystemExit('问答代码哈希不符')
 if REPORT.exists() or pre['status']!='preregistered_not_run': raise SystemExit('补测已运行或状态不允许')
 ledger=json.loads(LEDGER.read_text(encoding='utf-8'))
 baseline=float(pre['baseline_spent_usd']); stage_cap=float(pre['stage_cap_usd'])
 if ledger['spent_upper_bound_usd']!=baseline or ledger['cap_usd']!=pre['master_cap_usd']:
  raise SystemExit('账本起点已变化；本次补测不调用')
 if baseline+stage_cap>float(ledger['cap_usd']): raise SystemExit('阶段上限超过总账；不调用')
 items=[json.loads(x) for x in GOLD.read_text(encoding='utf-8').splitlines() if x.strip()]
 items=[x for x in items if x['id'] in pre['question_ids']]
 if [x['id'] for x in items]!=pre['question_ids']: raise SystemExit('冻结题目不匹配')
 if not args.run_once:
  for item in items:
   r=ask(db,item['question'],limit=5,mode='bm25',generate=False)
   print(json.dumps({'id':item['id'],'status':r.get('status'),'claims':[c.get('text','') for c in r.get('claims',[])],'retrieved_evidence':[c.get('evidence') for c in r.get('claims',[]) if c.get('evidence')]},ensure_ascii=False))
  print('dry_run: no model calls')
  return
 if not os.environ.get('DEEPSEEK_API_KEY'): raise SystemExit('缺少 API 凭据；未调用模型')
 os.environ.update(PAPERTRAIL_LLM_PROVIDER='openai-compatible',PAPERTRAIL_LLM_MODEL=pre['locked_config']['model'],PAPERTRAIL_OPENAI_BASE_URL=pre['locked_config']['base_url'],PAPERTRAIL_LLM_BUDGET_FILE=str(LEDGER),PAPERTRAIL_LLM_BUDGET_USD=str(pre['master_cap_usd']),PAPERTRAIL_RETRIEVAL_MODE='bm25',PAPERTRAIL_EVIDENCE_LIMIT='5')
 real=qa.chat_json;calls=0;reserved=0.0;results=[];failure=None
 def gated(model:str,system:str,prompt:str,**kwargs:Any)->dict[str,Any]:
  nonlocal calls,reserved
  cost=_max_request_cost(len(system)+len(prompt)+len('\nReturn a valid JSON object only.'))
  current=json.loads(LEDGER.read_text(encoding='utf-8'))
  if len(system)+len(prompt)>pre['max_request_chars']: raise RuntimeError('请求字符数超限；未发送')
  if calls+1>pre['max_calls'] or max(reserved,current['spent_upper_bound_usd']-baseline)+cost>stage_cap or current['spent_upper_bound_usd']+cost>pre['master_cap_usd']:
   raise RuntimeError('补测预算门禁拦截；请求未发送')
  calls+=1;reserved=round(reserved+cost,8)
  return real(model,system,prompt,**kwargs)
 qa.chat_json=gated
 try:
  for item in items:
   result=ask(db,item['question'],limit=5,mode='bm25',generate=True)
   claims=result.get('claims',[]);evidence=[]
   for claim in claims:
    for row in [claim.get('evidence'),*(claim.get('support_evidence') or [])]:
     if isinstance(row,dict): evidence.append(row)
   valid=[]
   for row in evidence:
    src=next((s for s in pre['sources'] if s['local_pdf_sha256']==row.get('sha256')),None)
    valid.append(bool(src and _validate_quote(str(ROOT/src['local_pdf']),row['sha256'],row['pdf_page'],row.get('quote',''),{})))
   gold_pages=[(e['sha256'],e['pdf_page']) for e in item['evidence']]
   got_pages=[(e.get('sha256'),e.get('pdf_page')) for e in evidence]
   results.append({'id':item['id'],'status':result.get('status'),'claims':[c.get('text','') for c in claims],
    'gold_abstain':item['abstain'],'gold_pages_cited':sum(any(p==g for p in got_pages) for g in gold_pages),
    'gold_pages_total':len(gold_pages),'displayed_citations':len(evidence),'citation_validity':valid,
    'all_citations_source_valid':all(valid) if valid else None,
    'citations':[{'sha256':e.get('sha256'),'pdf_page':e.get('pdf_page'),'quote':e.get('quote')} for e in evidence]})
 except Exception as exc: failure=f'{type(exc).__name__}: {str(exc)[:200]}'
 finally: qa.chat_json=real
 after=json.loads(LEDGER.read_text(encoding='utf-8'))
 report={'schema_version':1,'status':'completed_once_nonblind_addendum' if len(results)==len(items) and not failure else 'incomplete_once_nonblind_addendum',
  'dataset_role':pre['dataset_role'],'preregistration':PRE.name,'question_ids':pre['question_ids'],'results':results,'failure':failure,
  'model_usage':{'api_calls':calls,'summed_request_reserves_usd':reserved,'charged_upper_bound_usd':round(after['spent_upper_bound_usd']-baseline,8),'master_spent_after_usd':after['spent_upper_bound_usd'],'master_remaining_after_usd':round(after['cap_usd']-after['spent_upper_bound_usd'],8),'stage_cap_usd':stage_cap}}
 REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'output':str(REPORT),'status':report['status'],'usage':report['model_usage'],'failure':failure},ensure_ascii=False,indent=2))
 if failure or len(results)!=len(items): raise SystemExit(1)
if __name__=='__main__':main()
