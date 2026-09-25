"""Archive three assistant-authored responses from the current conversation and evaluate them.

This script does not call a model API. It records the exact prompt constructed by the
prototype and responses generated in the accompanying interactive AI session.
"""
import csv
import hashlib
import json
from pathlib import Path

from agent_demo import run
from llm_stage import make_prompt, validate_reply

root = Path(__file__).resolve().parent
with (root/'data/holdout_20.csv').open(encoding='utf-8',newline='') as f:
    findings = {x['payment_id']:x for x in run(list(csv.DictReader(f)))['findings']}

# These response strings were written by the AI in this conversation as answers
# to the exact prompt saved below. They are not outputs from llm_stage.py live.
responses = {
  'H02': {'reason':'H02 的付款金额超过演示阈值 10000 元，应核对原始单据后交人工复核。',
          'citation':'data/demo_policy.json#P-03','action':'人工复核'},
  'H03': {'reason':'H03 缺少订单编号，演示条款要求补齐订单信息并提交人工复核。',
          'citation':'data/demo_policy.json#P-01','action':'人工复核'},
  'H06': {'reason':'H06 的发票号与先前付款记录重复，需人工核对票据及付款背景。',
          'citation':'data/demo_policy.json#P-02','action':'人工复核'},
}

records=[]
for payment_id, answer in responses.items():
    finding=findings[payment_id]
    prompt=make_prompt(finding)
    output=json.dumps(answer,ensure_ascii=False)
    envelope={'output':[{'content':[{'type':'output_text','text':output}]}]}
    check=validate_reply(envelope,finding['evidence']['citation'])
    records.append({'payment_id':payment_id,'input':finding,'prompt':prompt,'raw_response':output,
                    'response_sha256':hashlib.sha256(output.encode()).hexdigest(),
                    'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                    'format_and_citation_check':check['status']=='model_draft_pending_human_review',
                    'review_status':check['action']})

result={'method':'interactive assistant-authored responses archived with prompts; no API request IDs',
        'scope':'three controlled test records from holdout_20.csv',
        'checked':len(records),'passed':sum(x['format_and_citation_check'] for x in records),
        'limitation':'This is not an independent or blinded model API benchmark.',
        'records':records}
(root/'data/chat_output_trace.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
assert result['checked']==result['passed']==3
print(json.dumps({'checked':result['checked'],'passed':result['passed'],'method':result['method']},ensure_ascii=False))
