"""Optional model explanation stage. Never approves payments. Live mode requires your own API key."""
import argparse
import json
import os
import urllib.error
import urllib.request

from agent_demo import DATA, retrieve

ENDPOINT='https://api.openai.com/v1/responses'

def make_prompt(finding):
    evidence=finding['evidence']
    if evidence['status']!='found' or not evidence['citation']:
        return None
    return ('你是财务复核辅助工具。只依据下方演示条款解释已由规则发现的异常；不能批准付款、'
            '认定违规或补充条款中没有的规定。仅输出JSON：'
            '{"reason":"一句话原因","citation":"原样来源编号","action":"人工复核"}。\n'
            f'付款编号：{finding["payment_id"]}\n异常标签：{finding["flags"]}\n金额：{finding["amount"]}\n'
            f'演示条款：{evidence["excerpt"]}\n来源编号：{evidence["citation"]}')

def validate_reply(response, citation):
    chunks=[part.get('text','') for item in response.get('output',[]) for part in item.get('content',[])
            if part.get('type')=='output_text']
    try:
        value=json.loads(''.join(chunks).strip())
        if (value.get('citation')!=citation or value.get('action')!='人工复核'
                or not isinstance(value.get('reason'),str) or not value['reason'].strip()
                or any(s in value['reason'] for s in ('可以付款','自动批准','确定违规'))):
            raise ValueError('来源或动作不符合要求')
        return {'status':'model_draft_pending_human_review', 'reason':value['reason'][:240],
                'citation':citation,'action':'人工复核'}
    except (json.JSONDecodeError,ValueError,AttributeError):
        return {'status':'fallback','reason':'模型回复不符合引用或动作约束，需人工复核',
                'citation':citation,'action':'人工复核'}

def live_explain(finding):
    prompt=make_prompt(finding)
    if prompt is None:return {'status':'no_evidence','reason':'缺少演示制度依据，需人工复核'}
    key=os.environ.get('OPENAI_API_KEY')
    model=os.environ.get('OPENAI_MODEL')
    if not key or not model:raise RuntimeError('请在本机设置 OPENAI_API_KEY 和 OPENAI_MODEL 环境变量')
    body=json.dumps({'model':model,'input':prompt,'store':False},ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(ENDPOINT,data=body,headers={
        'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=35) as resp:
            response=json.load(resp)
    except urllib.error.HTTPError as err:
        raise RuntimeError('模型接口返回 HTTP '+str(err.code)) from err
    return validate_reply(response,finding['evidence']['citation'])

def self_test():
    with (DATA/'run_output.json').open(encoding='utf-8') as f:finding=json.load(f)['findings'][0]
    citation=finding['evidence']['citation']
    mock={'output':[{'content':[{'type':'output_text','text':json.dumps({
        'reason':'订单编号缺失，应人工核实','citation':citation,'action':'人工复核'},ensure_ascii=False)}]}]}
    assert validate_reply(mock,citation)['status']=='model_draft_pending_human_review'
    mock['output'][0]['content'][0]['text']='{"reason":"可以付款","citation":"无来源","action":"自动批准"}'
    assert validate_reply(mock,citation)['status']=='fallback'
    print('离线测试通过：合法引用可解析；来源错误或要求自动批准时回退。未请求大模型。')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['dry-run','live']);p.add_argument('--payment',default='PAY-0001')
    args=p.parse_args()
    if args.mode=='dry-run':self_test()
    else:
        with (DATA/'run_output.json').open(encoding='utf-8') as f:findings=json.load(f)['findings']
        target=next((f for f in findings if f['payment_id']==args.payment),None)
        if not target:raise SystemExit('没有找到待复核付款编号')
        print(json.dumps(live_explain(target),ensure_ascii=False,indent=2))
