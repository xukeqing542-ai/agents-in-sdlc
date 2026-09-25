"""Local browser demo. Runs on 127.0.0.1 and uses only Python standard library."""
import csv
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent_demo import DATA, generate, retrieve, run

HTML='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>费用付款复核 Agent 演示</title>
<style>body{font:16px/1.6 system-ui;max-width:1000px;margin:30px auto;padding:0 20px;color:#243047}h1{font-size:26px}button{border:0;border-radius:8px;background:#155aa6;color:#fff;padding:10px 18px;margin:8px 4px;cursor:pointer}textarea,input{width:95%;padding:10px;border:1px solid #aaa;border-radius:6px}table{width:100%;border-collapse:collapse}td,th{text-align:left;border-bottom:1px solid #ddd;padding:7px}small{color:#666}.box{background:#f0f6fc;padding:15px;border-radius:8px}pre{white-space:pre-wrap;word-break:break-word}</style>
<h1>费用付款复核 Agent 原型</h1><p>个人作品：本地规则与制度检索。付款数据、制度均为演示材料；没有接入大模型。</p>
<h2>1 上传或运行演示 CSV</h2><input type="file" id="file" accept=".csv"><button onclick="sample()">运行240条演示数据</button><button onclick="upload()">分析所选CSV</button><small>字段：payment_id,order_id,invoice_id,amount,vendor；文件内容仅发送到本机服务。</small>
<div id="summary" class="box">尚未运行</div><h2>2 工具调用记录</h2><pre id="audit"></pre><h2>3 待人工复核清单</h2><button id="export" onclick="saveResult()" disabled>下载完整复核结果</button><div id="findings"></div>
<h2>4 查询演示制度</h2><input id="query" value="付款金额超过10000怎么办"><button onclick="ask()">检索条款</button><pre id="answer"></pre>
<script>
async function req(url,data){let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});return r.json()}
const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={missing_order:'订单编号缺失',missing_invoice:'发票号缺失',duplicate_invoice:'发票号重复',over_limit:'超出演示金额阈值',invalid_amount:'金额无效'};
let latestResult=null;
async function show(data){
  latestResult=null;document.querySelector('#export').disabled=true;
  if(data.error){document.querySelector('#summary').textContent=data.error;return}
  let x=data.result;
  if(x.status==='input_error'){
    let failure=x.audit_log[0].result;
    let missing=failure.missing.length?'缺少字段：'+failure.missing.join('、'):'请核对每行字段数';
    document.querySelector('#summary').textContent='输入未通过校验；'+missing+'。';
    document.querySelector('#audit').textContent=JSON.stringify(x.audit_log,null,2);
    document.querySelector('#findings').textContent='未处理付款记录。';return;
  }
  latestResult=x;document.querySelector('#export').disabled=false;
  document.querySelector('#summary').textContent=`输入 ${x.input_count} 条；待复核 ${x.findings.length} 条；批准状态：必须人工确认。`;
  document.querySelector('#audit').textContent=x.audit_log.map(a=>`${a.seq}. ${a.tool}: ${JSON.stringify(a.result)}`).join('\\n');
  document.querySelector('#findings').innerHTML='<table><tr><th>编号</th><th>异常与人工待核点</th><th>制度来源</th><th>状态</th></tr>'+x.findings.slice(0,30).map(f=>`<tr><td>${e(f.payment_id)}</td><td>${e(f.flags.map(flag=>names[flag]||flag).join('、'))}；请核对原始单据</td><td>${e(f.evidence.citation||'无依据，人工核实')}<br><small>${e(f.evidence.excerpt||'请人工核实依据')}</small></td><td>待人工复核</td></tr>`).join('')+'</table><small>页面展示前30条；点击上方按钮可下载本次完整结果。该页面不提供自动付款审批。</small>';
}
function saveResult(){if(!latestResult)return;let blob=new Blob([JSON.stringify(latestResult,null,2)],{type:'application/json'});let url=URL.createObjectURL(blob);let link=document.createElement('a');link.href=url;link.download='待人工复核结果.json';link.click();URL.revokeObjectURL(url)}
async function sample(){show(await req('/api/run',{sample:true}))}
async function upload(){let f=document.querySelector('#file').files[0];if(!f)return alert('请先选择CSV');show(await req('/api/run',{csv:await f.text()}))}
async function ask(){let x=await req('/api/retrieve',{query:document.querySelector('#query').value});document.querySelector('#answer').textContent=JSON.stringify(x,null,2)}
</script></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!='/': self.send_error(404);return
        data=HTML.encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>1_000_000: raise ValueError('文件大于1 MB，请拆分后重试')
            payload=json.loads(self.rfile.read(size))
            if self.path=='/api/retrieve': value=retrieve(str(payload.get('query','')))
            elif self.path=='/api/run':
                if payload.get('sample'):
                    with (DATA/'synthetic_payments.csv').open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
                else: rows=list(csv.DictReader(io.StringIO(str(payload.get('csv','')).lstrip('\ufeff'))))
                if len(rows)>5000: raise ValueError('最多处理5000条，请拆分文件')
                value={'result':run(rows)}
            else: self.send_error(404);return
            data=json.dumps(value,ensure_ascii=False).encode('utf-8');self.send_response(200)
        except (ValueError,TypeError,UnicodeError) as err:
            data=json.dumps({'error':str(err)},ensure_ascii=False).encode('utf-8');self.send_response(400)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

if __name__=='__main__':
    generate()
    print('打开 http://127.0.0.1:8765 ，按 Ctrl+C 结束')
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
