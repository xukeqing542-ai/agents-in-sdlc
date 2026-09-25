"""Local, deterministic expense review Agent prototype. No LLM or company data."""
import argparse
import csv
import json
import html
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
POLICY = [
    {'id':'P-01','title':'单据完整性（演示制度）','text':'费用付款记录必须包含付款编号、订单编号、发票号及付款金额；订单编号缺失时提交人工复核。'},
    {'id':'P-02','title':'重复票据（演示制度）','text':'同一发票号出现多次付款记录，应标记重复票据风险，并由人工核对，不得自动认定违规。'},
    {'id':'P-03','title':'金额阈值（演示制度）','text':'本演示单笔付款金额超过10000元时应提示金额超限并转人工审核；此阈值仅用于合成数据演示。'},
    {'id':'P-04','title':'人工审批（演示制度）','text':'系统仅输出风险提示和证据。付款批准及违规认定必须由授权审核人员作出。'},
]

def generate():
    """Create synthetic input and a separately stored answer key."""
    DATA.mkdir(exist_ok=True)
    rows, truth = [], []
    for i in range(1,241):
        kind = 'missing_order' if i<=25 else 'duplicate_invoice' if i<=50 else 'over_limit' if i<=76 else 'normal'
        invoice = f'INV-{i-25:04}' if kind=='duplicate_invoice' else f'INV-{i:04}'
        rows.append({'payment_id':f'PAY-{i:04}', 'order_id':'' if kind=='missing_order' else f'ORD-{i:04}',
                     'invoice_id':invoice, 'amount':'15000' if kind=='over_limit' else '1200',
                     'vendor':f'供应商{i%12:02}'})
        truth.append({'payment_id':f'PAY-{i:04}','label':kind})
    for name, data in [('synthetic_payments.csv',rows),('answer_key.csv',truth)]:
        with (DATA/name).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=data[0]); w.writeheader(); w.writerows(data)
    (DATA/'demo_policy.json').write_text(json.dumps(POLICY,ensure_ascii=False,indent=2),encoding='utf-8')

def tokens(s):
    s=''.join(str(s).lower().split())
    return {s[i:i+n] for n in (2,3) for i in range(max(0,len(s)-n+1))}

def retrieve(query):
    """Char ngram retrieval with citation and an abstention threshold."""
    q=tokens(query)
    scored=[]
    for section in POLICY:
        t=tokens(section['title']+' '+section['text'])
        score=len(q&t)/max(1,len(q))
        scored.append((score,section))
    score,section=max(scored,key=lambda x:x[0])
    if score < .16:
        return {'status':'no_evidence','message':'未找到足够依据，需人工核实','citation':None,'score':round(score,3)}
    return {'status':'found','title':section['title'],'excerpt':section['text'],
            'citation':f'data/demo_policy.json#{section["id"]}','score':round(score,3)}

def run(rows):
    log=[]
    def step(name, information):
        log.append({'seq':len(log)+1,'tool':name,'result':information})
    needed={'payment_id','order_id','invoice_id','amount','vendor'}
    missing=needed-set(rows[0]) if rows else needed
    malformed=[i+1 for i,r in enumerate(rows) if any(r.get(k) is None for k in needed)]
    if missing or malformed:
        step('validate_schema',{'ok':False,'missing':sorted(missing),'malformed_rows':malformed[:20]})
        return {'status':'input_error','audit_log':log,'findings':[]}
    step('validate_schema',{'ok':True,'rows':len(rows)})
    invoice_count=Counter(r['invoice_id'].strip() for r in rows if r['invoice_id'].strip())
    step('index_invoices',{'unique':len(invoice_count)})
    findings=[]
    seen_invoices=set()
    for row in rows:
        labels=[]
        if not row['order_id'].strip(): labels.append('missing_order')
        invoice=row['invoice_id'].strip()
        if not invoice: labels.append('missing_invoice')
        elif invoice in seen_invoices: labels.append('duplicate_invoice')
        if invoice: seen_invoices.add(invoice)
        try:
            amount=Decimal(row['amount'])
            if not amount.is_finite() or amount<0: labels.append('invalid_amount')
            elif amount>10000: labels.append('over_limit')
        except (InvalidOperation, ValueError): labels.append('invalid_amount')
        if labels:
            query={'missing_order':'订单编号缺失 单据完整性','missing_invoice':'发票号缺失 单据完整性',
                   'duplicate_invoice':'重复发票号 票据重复',
                   'over_limit':'付款金额超过10000 金额阈值','invalid_amount':'金额字段异常'}[labels[0]]
            findings.append({'payment_id':row['payment_id'],'flags':labels,'amount':row['amount'],
                             'evidence':retrieve(query),'review_status':'pending_human_review'})
    step('detect_exceptions',{'flagged':len(findings),'kinds':dict(Counter(x for f in findings for x in f['flags']))})
    step('retrieve_policy',{'cited':sum(f['evidence']['status']=='found' for f in findings),
                            'no_evidence':sum(f['evidence']['status']!='found' for f in findings)})
    step('human_review_gate',{'decision':'pending','auto_approval':False})
    step('export_report',{'findings':len(findings),'audit_events':len(log)+1})
    return {'status':'completed_pending_human_review','input_count':len(rows),'findings':findings,
            'audit_log':log,'policy_is_synthetic':True,'llm_used':False}

def evaluate():
    generate()
    with (DATA/'synthetic_payments.csv').open(encoding='utf-8-sig',newline='') as f: result=run(list(csv.DictReader(f)))
    with (DATA/'answer_key.csv').open(encoding='utf-8-sig',newline='') as f: truth={r['payment_id'] for r in csv.DictReader(f) if r['label']!='normal'}
    flagged={f['payment_id'] for f in result['findings']}
    tp=len(flagged&truth); fp=len(flagged-truth); fn=len(truth-flagged)
    cases=[('订单编号缺失 单据完整性','P-01'),('重复发票号 票据重复','P-02'),
           ('付款金额超过10000 金额阈值','P-03'),('谁能批准付款 人工审批','P-04'),
           ('火星轨道电梯宇宙辐射','none')]
    retrieved=[{'query':q,'expected':expected,'actual':(v:=retrieve(q))['citation'] or 'none','pass':
                (v['citation'] or 'none').endswith(expected) if expected!='none' else v['status']=='no_evidence'} for q,expected in cases]
    metrics={'dataset':'240 synthetic payments / 76 rule-seeded positives','true_positives':tp,'false_positives':fp,
             'false_negatives':fn,'precision':round(tp/(tp+fp),4),'recall':round(tp/(tp+fn),4),
             'retrieval_pass':sum(x['pass'] for x in retrieved),'retrieval_total':len(retrieved),
             'manual_review_gate':all(f['review_status']=='pending_human_review' for f in result['findings']),
             'tool_order':[a['tool'] for a in result['audit_log']], 'limitations':
             '合成样本由相同规则构造，指标只证明演示流程运行；制度为演示文本，未接入LLM或企业系统。'}
    assert metrics['manual_review_gate'] and result['audit_log'][-2]['tool']=='human_review_gate'
    assert run([{'payment_id':'1'}])['status']=='input_error'
    assert all(x['pass'] for x in retrieved), retrieved
    # Separately authored edge cases; never used to construct detection rules or tune the retrieval threshold.
    edge=[
        {'payment_id':'E1','order_id':'O1','invoice_id':'A','amount':'10000','vendor':'甲'},
        {'payment_id':'E2','order_id':'','invoice_id':'B','amount':'100','vendor':'甲'},
        {'payment_id':'E3','order_id':'O3','invoice_id':'A','amount':'100','vendor':'甲'},
        {'payment_id':'E4','order_id':'O4','invoice_id':'C','amount':'10000.01','vendor':'乙'},
        {'payment_id':'E5','order_id':'O5','invoice_id':'','amount':'200','vendor':'乙'},
        {'payment_id':'E6','order_id':'O6','invoice_id':'F','amount':'NaN','vendor':'乙'},
        {'payment_id':'E7','order_id':'O7','invoice_id':'G','amount':'-1','vendor':'乙'},
    ]
    edge_result=run(edge)
    expected={'E2','E3','E4','E5','E6','E7'}
    actual={x['payment_id'] for x in edge_result['findings']}
    assert actual==expected,(actual,expected)
    metrics['edge_cases']='7条独立边界输入，6条应提示，6条提示；10000元边界保持正常'
    (DATA/'edge_cases.json').write_text(json.dumps({'input':edge,'expected':sorted(expected),'actual':sorted(actual),'pass':actual==expected},ensure_ascii=False,indent=2),encoding='utf-8')
    (DATA/'run_output.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (DATA/'evaluation.json').write_text(json.dumps({'metrics':metrics,'retrieval_cases':retrieved},ensure_ascii=False,indent=2),encoding='utf-8')
    body=''.join('<tr><td>'+html.escape(f['payment_id'])+'</td><td>'+html.escape(', '.join(f['flags']))+'</td><td>'+html.escape(str(f['evidence']['citation']))+'</td><td>待人工复核</td></tr>' for f in result['findings'][:20])
    audit=''.join('<li>'+str(a['seq'])+'. '+html.escape(a['tool'])+'：'+html.escape(json.dumps(a['result'],ensure_ascii=False))+'</li>' for a in result['audit_log'])
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>费用复核 Agent 运行报告</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:48px auto;color:#243047;padding:0 20px}h1{font-size:26px}h2{margin-top:34px;color:#17456d}.stats{display:flex;gap:12px;flex-wrap:wrap}.stats b{border:1px solid #c5d5e2;background:#f3f8fc;border-radius:8px;padding:16px}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}small{color:#666}li{margin:8px 0}</style><h1>费用付款复核 Agent 运行报告</h1><p>徐苛清｜个人作品｜合成数据及演示制度</p><div class="stats"><b>输入 240 条</b><b>待复核 76 条</b><b>检索用例 5/5</b><b>审批状态：待人工复核</b></div><p><strong>边界：</strong>规则设计与数据生成一致，评测不能证明真实业务准确率。本原型不含大模型调用与企业数据。</p><h2>工具调用轨迹</h2><ol>'''+audit+'''</ol><h2>异常清单（前20项）</h2><table><tr><th>付款编号</th><th>异常</th><th>演示制度引用</th><th>处理状态</th></tr>'''+body+'''</table><p><small>全量记录见 data/run_output.json；原始数据和答案见 data 目录。</small></p></html>'''
    (ROOT/'运行报告.html').write_text(page,encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['evaluate','run'])
    args=parser.parse_args()
    if args.command=='evaluate':evaluate()
    else:
        with (DATA/'synthetic_payments.csv').open(encoding='utf-8-sig',newline='') as f: print(json.dumps(run(list(csv.DictReader(f))),ensure_ascii=False,indent=2))
