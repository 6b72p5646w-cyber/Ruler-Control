#!/usr/bin/env python3
"""Rebuild BC02 finite evidence, cross-contract gates and repository links."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def execute(script):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script)], cwd=ROOT,
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'{script}\n{result.stdout}\n{result.stderr}')
    return {'script':script, 'returncode':result.returncode, 'stdout':result.stdout.strip()}


def main():
    report_path = ROOT / 'docs/bc02_validation_report.json'
    report_path.write_text(json.dumps({'version':'BC02', 'status':'RUNNING', 'runtime_integrated':False}) + '\n')
    scripts = ['check_bc02_facilities.py', 'check_bc02_customer_routes.py', 'check_bc02_environment.py',
               'check_bc02_prerequisites.py', 'check_bc02_ads.py']
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(execute, scripts))
    for r in results:
        print(r['stdout'], flush=True)
    results.append(execute('check_bc02_contracts.py'))
    print(results[-1]['stdout'], flush=True)
    static = json.loads(execute('validate_content.py')['stdout'])
    if static['status'] != 'PASS':
        raise RuntimeError('repository static validation failed: ' + json.dumps(static, ensure_ascii=False))
    reports = []
    for name in ('facility','customer','environment','prerequisite','ad','contract'):
        path = ROOT / 'docs' / f'bc02_{name}_report.json'
        data = json.loads(path.read_text())
        rows = data.get('checks', data.get('cases', []))
        if not rows or not all(x['passed'] for x in rows):
            raise RuntimeError('failing or missing rows in ' + name)
        hashes = next((data[k] for k in ('inputs_sha256','input_sha256','source_sha256','hashes')
                       if isinstance(data.get(k), dict)), {})
        if not hashes:
            raise RuntimeError('missing input hashes in ' + name)
        for relative, expected in hashes.items():
            if sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
                raise RuntimeError('stale ' + name + ' report input: ' + relative)
        passed = data.get('passed', data.get('passed_count', data.get('assertion_count', len(rows))))
        reports.append({'name':name, 'path':str(path.relative_to(ROOT)), 'passed_assertions':passed,
                        'scenario_count':data.get('scenario_count'), 'scope':data.get('scope'),
                        'sha256':sha256(path.read_bytes()).hexdigest()})
    # Full content inventory covers indirect imports and old source pointers.
    # Reports/doc prose are outputs, not circular inputs to their own hashes.
    dependencies = sorted((ROOT / 'content').glob('*.json')) + sorted((ROOT / 'scripts').glob('*.py'))
    dependencies += sorted((ROOT / 'prototype').glob('*.py')) + sorted((ROOT / 'prototype').glob('*.mjs'))
    final = {'version':'BC02', 'baseline_commit':'dfd2e32eecb8fb4dc7dd3efa066cfa3817363788',
        'status':'PASS', 'runtime_integrated':False, 'passed_assertions':sum(x['passed_assertions'] for x in reports),
        'failed':0, 'reports':reports, 'commands':[r['script'] for r in results] + ['validate_content.py'],
        'repository_static_validation':{'status':static['status'], 'checks':static['checks'], 'scope':static['scope']},
        'counts_are_not_game_sessions':True,
        'proof_boundary':'BC02 source/action specifications, selected actual customer/environment routes and finite state/SQLite counterexamples. Pointer/coverage checks are included in assertion totals. Not a 105-AI client, full BC02 weekly balance, mobile validation or live ad service.',
        'codex_handoff':'docs/100_bc02_codex_start.md',
        'inputs_sha256':{str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in dependencies}}
    report_path.write_text(json.dumps(final, ensure_ascii=False, indent=2) + '\n')
    print(f"BC02 PASS: {final['passed_assertions']} finite/static assertions; repository links/content {static['checks']}; client false", flush=True)


if __name__ == '__main__':
    main()
