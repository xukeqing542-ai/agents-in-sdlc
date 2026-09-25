"""Evaluate twenty hand-authored cases separate from agent_demo.generate()."""
import csv
import json
from pathlib import Path
from agent_demo import run

data = Path(__file__).resolve().parent / 'data'
rows = list(csv.DictReader((data / 'holdout_20.csv').open(encoding='utf-8', newline='')))
expected = json.loads((data / 'holdout_20_expected.json').read_text(encoding='utf-8'))
result = run(rows)
observed = {finding['payment_id']:finding['flags'] for finding in result['findings']}
details = []
for row in rows:
    payment_id = row['payment_id']
    want = expected[payment_id]
    got = observed.get(payment_id, [])
    details.append({'payment_id':payment_id, 'expected':want, 'observed':got, 'match':want == got})
summary = {
    'source':'20 hand-authored synthetic cases, separate from generator; not a blind real-world sample',
    'case_count':len(rows), 'exact_flag_match_count':sum(d['match'] for d in details),
    'all_pending_human_review':all(f['review_status']=='pending_human_review' for f in result['findings']),
    'limitations':['Cases were authored after viewing the prototype rules',
                   'No model output is evaluated', 'No enterprise or customer data'],
    'details':details,
}
assert len(rows) == len(expected) == 20
(data / 'holdout_20_result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k != 'details'},ensure_ascii=False,indent=2))
