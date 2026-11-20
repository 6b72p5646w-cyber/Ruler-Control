#!/usr/bin/env python3
"""Rebuild all BC01 evidence with one command, preserving honest scope labels."""
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
    return {'script': script, 'returncode': result.returncode, 'stdout': result.stdout.strip()}


def main(verify_reports_only=False):
    # The linked summary exists during a clean first build, but never claims
    # success until all behavior and repository-link checks have completed.
    (ROOT / 'docs/bc01_validation_report.json').write_text(json.dumps(
        {'version': 'BC01', 'status': 'RUNNING', 'runtime_integrated': False}) + '\n')
    scripts = ['check_bc01_facilities.py', 'check_bc01_director.py', 'check_bc01_map.py', 'check_bc01_campaign.py']
    if verify_reports_only:
        results = []
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(execute, scripts))
    for row in results:
        print(row['stdout'], flush=True)
    if not verify_reports_only:
        results.append(execute('check_bc01_p0.py'))
        print(results[-1]['stdout'], flush=True)
    legacy_static = execute('validate_content.py')
    legacy_json = json.loads(legacy_static['stdout'])
    if legacy_json['status'] != 'PASS':
        raise RuntimeError('repository content/link validation failed')
    reports = []
    for name in ('facility', 'director', 'map', 'campaign', 'p0'):
        path = ROOT / 'docs' / f'bc01_{name}_report.json'
        data = json.loads(path.read_text())
        passed = data.get('passed', data.get('counts', {}).get('passed'))
        failed = data.get('failed', data.get('counts', {}).get('failed', data.get('total', passed) - passed))
        if failed or not all(c['passed'] for c in data['checks']):
            raise RuntimeError(name + ' contains a failing check')
        hashes = data.get('inputs_sha256', data.get('source_sha256', {}))
        for relative, expected in hashes.items():
            if sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
                raise RuntimeError('stale report input: ' + relative)
        reports.append({'name': name, 'path': str(path.relative_to(ROOT)), 'passed': passed, 'failed': failed,
                        'sha256': sha256(path.read_bytes()).hexdigest()})
    dependencies = sorted((ROOT / 'content').glob('*bc01.json')) + sorted((ROOT / 'scripts').glob('*bc01*.py'))
    dependencies += [ROOT / 'content' / p for p in (
        'maps.json', 'map_mechanics_v05.json', 'tower_defense_td05.json', 'traps_facilities_td05.json',
        'combat_contracts_td05.json', 'economy_week_td05.json', 'monster_folklore_md01.json',
        'monster_scp_a_md01.json', 'monster_scp_b_md01.json', 'monster_contracts_md01.json',
        'monster_attacks_folklore_ma01.json', 'monster_attacks_scp_ma01.json', 'equipment_eq01.json',
        'equipment_contracts_eq01.json', 'rule_response_contracts_sa02.json')]
    dependencies += [ROOT / 'scripts' / p for p in ('md01_reference.py', 'sa02_response_reference.py', 'td05_reference.py')]
    final = {'version': 'BC01', 'baseline_commit': 'a3d09c3bc8b5e6de83d523daa9d07aa894937f3d',
             'status': 'PASS', 'design_p0_complete': True, 'runtime_integrated': False,
             'existing_behavior_reports_hash_verified': verify_reports_only,
             'passed': sum(r['passed'] for r in reports), 'failed': 0, 'reports': reports,
             'repository_static_validation': {'status': legacy_json['status'], 'checks': legacy_json['checks'],
                                              'scope': legacy_json['scope']},
             'proof_boundary': 'BC01设计/有限参考；真实顾客路线与账本、电源/HP/等级、静态导航、实际本地事务恢复。不是105AI或手机实机胜率。',
             'behavior_commands': scripts + ['check_bc01_p0.py'],
             'this_summary_refresh_commands': [r['script'] for r in results] + ['validate_content.py'],
             'inputs_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in dependencies}}
    (ROOT / 'docs/bc01_validation_report.json').write_text(json.dumps(final, ensure_ascii=False, indent=2) + '\n')
    print(f"BC01 validation PASS: {final['passed']} checks; repository static {legacy_json['checks']}", flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-reports-only', action='store_true',
                        help='After documentation-only repairs, verify every existing report input hash and rerun repository/link checks without repeating unchanged behavioral scenarios.')
    main(parser.parse_args().verify_reports_only)
