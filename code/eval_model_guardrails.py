"""Reproducible, author-written cases for the model-output validation gate.

This evaluates the parser and policy guardrail; it does not call a model or
estimate model accuracy on independently sampled inputs.
"""
import json
from pathlib import Path

from llm_stage import validate_reply

HERE = Path(__file__).resolve().parent
CITATION = 'data/demo_policy.json#P-03'


def envelope(value):
    body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return {'output': [{'content': [{'type': 'output_text', 'text': body}]}]}


def main():
    good = {'reason': '金额超过演示阈值，需要核对原单据',
            'citation': CITATION, 'action': '人工复核'}
    cases = [
        ('合法引用及人工复核', good, 'model_draft_pending_human_review'),
        ('引用其他条款', {**good, 'citation': 'data/demo_policy.json#P-01'}, 'fallback'),
        ('伪造来源编号', {**good, 'citation': '企业规定第九条'}, 'fallback'),
        ('自动批准动作', {**good, 'action': '自动批准'}, 'fallback'),
        ('自动批准话术', {**good, 'reason': '可以付款'}, 'fallback'),
        ('确定违规话术', {**good, 'reason': '确定违规'}, 'fallback'),
        ('空解释', {**good, 'reason': '  '}, 'fallback'),
        ('非JSON回复', '我认为可以继续。', 'fallback'),
        ('JSON缺少动作', {k: v for k, v in good.items() if k != 'action'}, 'fallback'),
        ('JSON缺少来源', {k: v for k, v in good.items() if k != 'citation'}, 'fallback'),
        ('解释字段错误类型', {**good, 'reason': None}, 'fallback'),
        ('错误动作需回退', {**good, 'action': '人工已批准'}, 'fallback'),
    ]
    results = []
    for name, raw, expected in cases:
        actual = validate_reply(envelope(raw), CITATION)
        results.append({'case': name, 'expected': expected, 'actual': actual['status'],
                        'pass': actual['status'] == expected})
    report = {'method': 'hand-authored output-validation cases; no model call',
              'total': len(results), 'passed': sum(x['pass'] for x in results),
              'cases': results}
    output = HERE / 'data' / 'model_guardrails_eval.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Model-output gate: {report['passed']}/{report['total']} passed; {output}")
    assert report['passed'] == report['total'], 'Output-validation regression'


if __name__ == '__main__':
    main()
