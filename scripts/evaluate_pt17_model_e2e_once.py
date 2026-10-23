"""Run the frozen PT17 CC BY paper-disjoint holdout once under the master budget."""
from __future__ import annotations
import argparse, hashlib, inspect, json, os, sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from papertrail import qa
from papertrail.local_llm import _max_request_cost
from papertrail.qa import _validate_quote
PREREG=ROOT/'evals/pt17-model-e2e-prereg-20261023.json'
GOLD=ROOT/'evals/pt17-heldout-gold-20261023.jsonl'
DATABASE=ROOT/'.local/pt17-heldout.sqlite3'
LEDGER=ROOT/'.local/pt-master-usage.json'
OUTPUT=ROOT/'evals/pt17-model-e2e-20261023.json'
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def prompt_sha()->str:
 names=('_plan_subquestions','_screen_evidence','_synthesize_local','_hosted_json_prompt')
 return hashlib.sha256('\n'.join(f'{n}\n{inspect.getsource(getattr(qa,n))}' for n in names).encode()).hexdigest()
def evidence_rows(claims:list[dict[str,Any]])->list[dict[str,Any]]:
 out=[];seen=set()
 for c in claims:
  for e in [c.get('evidence'),*(c.get('support_evidence') or [])]:
   if not isinstance(e,dict):continue
   key=(e.get('sha256'),e.get('pdf_page'),e.get('quote'))
   if key not in seen:seen.add(key);out.append(e)
 return out
def main()->None:
 ap=argparse.ArgumentParser();ap.add_argument('--run-once',action='store_true');args=ap.parse_args()
 if not args.run_once:raise SystemExit('必须显式使用 --run-once；未调用模型')
 pre=json.loads(PREREG.read_text(encoding='utf-8'))
 if pre['status']!='preregistered_not_run' or OUTPUT.exists():raise SystemExit('PT17 不是首次运行状态；拒绝调用')
 checks={'gold_sha256':sha(GOLD),'database_sha256':sha(DATABASE),'source_manifest_sha256':sha(ROOT/'evals/pt17-heldout-source-manifest-20261023.json'),'source_config_sha256':sha(ROOT/'evals/pt17-heldout-sources.yaml'),'selection_sha256':sha(ROOT/'evals/pt17-heldout-selection.jsonl'),'runner_sha256':sha(Path(__file__)),'prompt_sha256':prompt_sha(),'qa_sha256':sha(ROOT/'papertrail/qa.py'),'local_llm_sha256':sha(ROOT/'papertrail/local_llm.py'),'retrieval_sha256':sha(ROOT/'papertrail/retrieval.py'),'index_sha256':sha(ROOT/'papertrail/s1_index.py')}
 if checks!=pre['locked_hashes']:raise SystemExit('PT17 冻结文件或代码哈希不符；未调用模型')
 if not os.environ.get('DEEPSEEK_API_KEY'):raise SystemExit('缺少 API 凭据；未调用模型')
 ledger=json.loads(LEDGER.read_text(encoding='utf-8'));baseline=float(pre['budget_gate']['master_spent_before_usd']);cap=float(pre['budget_gate']['master_cap_usd']);stage_cap=float(pre['budget_gate']['stage_cap_usd'])
 if ledger['spent_upper_bound_usd']!=baseline or ledger['cap_usd']!=cap:raise SystemExit('主账本起点已变化；未调用模型')
 if baseline+stage_cap>cap:raise SystemExit('阶段预算超出主账；未调用模型')
 os.environ.update(PAPERTRAIL_LLM_PROVIDER='openai-compatible',PAPERTRAIL_LLM_MODEL=pre['locked_config']['model'],PAPERTRAIL_OPENAI_BASE_URL=pre['locked_config']['base_url'],PAPERTRAIL_LLM_BUDGET_FILE=str(LEDGER),PAPERTRAIL_LLM_BUDGET_USD=str(cap),PAPERTRAIL_RETRIEVAL_MODE=pre['locked_config']['retrieval_mode'],PAPERTRAIL_EVIDENCE_LIMIT=str(pre['locked_config']['evidence_limit']))
 real_chat=qa.chat_json;calls=0;reserved=0.0;results=[];failure=None
 def gated(model:str,system:str,prompt:str,**kwargs:Any)->dict[str,Any]:
  nonlocal calls,reserved
  chars=len(system)+len(prompt)+len('\nReturn a valid JSON object only.')
  if chars>pre['budget_gate']['prompt_char_limit_per_call']:raise RuntimeError('单请求字符数超限；未发送')
  cost=_max_request_cost(chars);current=json.loads(LEDGER.read_text(encoding='utf-8'));charged=float(current['spent_upper_bound_usd'])-baseline
  if calls+1>pre['budget_gate']['max_calls'] or max(charged,reserved)+cost>stage_cap or float(current['spent_upper_bound_usd'])+cost>cap:
   raise RuntimeError('PT17 费用门禁拦截请求；未发送')
  calls+=1;reserved=round(reserved+cost,8)
  return real_chat(model,system,prompt,**kwargs)
 qa.chat_json=gated
 items=[json.loads(x) for x in GOLD.read_text(encoding='utf-8').splitlines() if x.strip()]
 src={s['local_pdf_sha256']:ROOT/s['local_pdf'] for s in pre['sources']};
 try:
  for item in items:
   result=qa.ask(DATABASE,item['question'],limit=pre['locked_config']['evidence_limit'],mode=pre['locked_config']['retrieval_mode'],generate=True)
   cited=evidence_rows(result.get('claims',[]));valid=[];cache={}
   for e in cited:
    path=src.get(e.get('sha256'))
    valid.append(bool(path and _validate_quote(str(path),e['sha256'],e['pdf_page'],e.get('quote',''),cache)))
   gold=item['evidence'];gold_pages=[(e['sha256'],e['pdf_page']) for e in gold];got=[(e.get('sha256'),e.get('pdf_page')) for e in cited]
   normalize=qa._normalize_excerpt
   page_hits=phrase_hits=exact=0
   for g in gold:
    matches=[e for e in cited if e.get('sha256')==g['sha256'] and e.get('pdf_page')==g['pdf_page']]
    page_hits+=int(bool(matches));phrase=normalize(g['quote'])
    phrase_hits+=int(any(phrase in normalize(e.get('quote','')) for e in matches))
    exact+=int(any(phrase==normalize(e.get('quote','')) for e in matches))
   results.append({'id':item['id'],'question_type':item['question_type'],'gold_abstain':item['abstain'],'status':result['status'],'claims':[c['text'] for c in result.get('claims',[])],
    'coverage_complete':result.get('coverage_complete'),'coverage_gaps':result.get('coverage_gaps',[]),
    'gold_evidence_slots':len(gold),'gold_pages_cited':page_hits,'gold_phrases_contained':phrase_hits,'exact_gold_quotes':exact,
    'displayed_citations':len(cited),'all_displayed_citations_source_valid':all(valid) if valid else None,
    'retrieval_diagnostics':(result.get('usage') or {}).get('_diagnostics',{}),
    'citations':[{'sha256':e.get('sha256'),'pdf_page':e.get('pdf_page'),'quote':e.get('quote')} for e in cited]})
 except Exception as exc:failure=f'{type(exc).__name__}: {str(exc)[:220]}'
 finally:qa.chat_json=real_chat
 after=json.loads(LEDGER.read_text(encoding='utf-8'));charged=round(float(after['spent_upper_bound_usd'])-baseline,8)
 metrics={'questions_total':len(items),'questions_completed':len(results),'answerable_questions':sum(not x['abstain'] for x in items),'unanswerable_questions':sum(x['abstain'] for x in items),
  'gold_evidence_slots':sum(x['gold_evidence_slots'] for x in results),'gold_pages_cited':sum(x['gold_pages_cited'] for x in results),'gold_phrases_contained':sum(x['gold_phrases_contained'] for x in results),'exact_gold_quotes':sum(x['exact_gold_quotes'] for x in results),
  'unanswerable_abstentions':sum(x['gold_abstain'] and x['status']=='abstained' for x in results),'all_displayed_citations_source_valid':all(x['all_displayed_citations_source_valid'] for x in results if x['displayed_citations'])}
 report={'schema_version':1,'status':'completed_once_human_review_pending' if len(results)==len(items) and not failure else 'incomplete_once_human_review_pending','dataset_role':pre['dataset_role'],'preregistration':PREREG.name,'locked_hashes':pre['locked_hashes'],'metrics':metrics,'limitations':pre['limitations'],'human_review':{'status':'pending_independent_human_review','runtime_model_review_is_not_independent':True},'model_usage':{'api_calls':calls,'summed_request_reserves_usd':reserved,'charged_upper_bound_usd':charged,'master_spent_after_usd':after['spent_upper_bound_usd'],'master_remaining_after_usd':round(cap-float(after['spent_upper_bound_usd']),8),'stage_cap_usd':stage_cap},'failure':failure,'results':results}
 OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'output':str(OUTPUT),'status':report['status'],'metrics':metrics,'model_usage':report['model_usage'],'failure':failure},ensure_ascii=False,indent=2))
 if failure or len(results)!=len(items):raise SystemExit(1)
if __name__=='__main__':main()
