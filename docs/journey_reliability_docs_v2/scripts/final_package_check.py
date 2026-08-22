from pathlib import Path
import json, re, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
errors=[]
checks=[]

def ok(label, cond, detail=''):
    if cond:
        checks.append((label,'PASS',detail))
    else:
        checks.append((label,'FAIL',detail))
        errors.append(label + (f': {detail}' if detail else ''))

# Required package files
required = [
    'README.md', '.env.example',
    'docs/00_governance/00_MASTER_INDEX.md',
    'docs/00_governance/02_DECISION_LOG.md',
    'docs/00_governance/03_EVIDENCE_REGISTER.md',
    'docs/00_governance/08_IMPLEMENTATION_STATUS.md',
    'docs/00_governance/09_PHASE1_EVIDENCE_EXECUTION.md',
    'docs/40_data_probability/42_PROBABILITY_CONTRACT.md',
    'docs/40_data_probability/43_VALIDATION_PLAN.md',
    'baseline/phase0/docs/05_DECISION_LOG.md',
    'baseline/phase0/docs/06_PHASE0_SUMMARY_FOR_PLANNING.md',
    'baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json',
]
missing=[x for x in required if not (ROOT/x).exists()]
ok('required files', not missing, ', '.join(missing))

# README must point to current canonical execution doc
readme=(ROOT/'README.md').read_text(encoding='utf-8')
ok('README canonical phase1 path', 'docs/00_governance/09_PHASE1_EVIDENCE_EXECUTION.md' in readme and '10_PHASE1_EVIDENCE_EXECUTION.md' not in readme)

# env example must contain no assigned secret values
secret_vars={'SEOUL_OPEN_API_KEY','SEOUL_SUBWAY_REALTIME_KEY','DATA_GO_BUS_API_KEY','KAKAO_MAP_REST_API_KEY','TMAP_APP_KEY'}
assigned=[]
for line in (ROOT/'.env.example').read_text(encoding='utf-8').splitlines():
    if '=' not in line or line.lstrip().startswith('#'): continue
    k,v=line.split('=',1)
    if k.strip() in secret_vars and v.strip(): assigned.append(k.strip())
ok('.env.example secret values blank', not assigned, ', '.join(assigned))

# Cross-mode raw: same OD must have primary A and structural B
rawp=ROOT/'baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json'
try:
    x=json.loads(rawp.read_text(encoding='utf-8'))
    raw=x['raw_payload']
    if isinstance(raw,str): raw=json.loads(raw)
    items=raw['msgBody']['itemList']
    seqs=[[leg.get('routeNm') for leg in (it.get('pathList') or [])] for it in items]
    primary = bool(seqs and seqs[0]==['01A','3호선','2호선'])
    cross = ['01A','3호선','147'] in seqs
    ok('Phase0 Route A raw assertion', primary, repr(seqs[:3]))
    ok('Phase0 Route B SUBWAY_TO_BUS structural assertion', cross, repr(seqs[:3]))
except Exception as e:
    ok('Phase0 mixed-route raw parse', False, repr(e))

# Evidence caution: 54 transitions must not be claimed as target-leg 54 residuals
evd=(ROOT/'docs/00_governance/03_EVIDENCE_REGISTER.md').read_text(encoding='utf-8')
ok('54-transition scope caution', '특정 춘추문→안국 leg의 54 residual이라는 뜻이 아님' in evd)

# Structural vs realtime E2E separation
ok('cross-mode structural/E2E evidence split', 'EVD-CROSS-001 | VERIFIED' in evd and 'EVD-CROSS-002 | TO_VERIFY' in evd)

# Demo walk/transfer blockers exist
for evid in ['EVD-ACCESS-001','EVD-XFER-B2S-001','EVD-DEST-001','EVD-TRANSFER-001','EVD-SCHED-001','EVD-WAIT-001']:
    ok(f'{evid} explicit blocker', f'| {evid} | TO_VERIFY |' in evd)

# Probability semantics checks
prob=(ROOT/'docs/40_data_probability/42_PROBABILITY_CONTRACT.md').read_text(encoding='utf-8')
ok('recommended departure re-evaluates time-conditioned service availability', '단순 `d`만큼 shift하지 않는다' in prob and 'service availability/WAIT model 재평가' in prob)
ok('future bus exact vehicle not required', 'exact future bus vehicle ID는 correctness 전제가 아니다' in prob)
ok('Wilson CI limitation explicit', 'Wilson' in prob and ('model uncertainty' in prob or '모델' in prob) and ('calibration' in prob or 'Calibration' in prob))
ok('whole-leg correlation tier', 'whole-leg' in prob.lower() or 'whole leg' in prob.lower())

# Validation scope ladder
val=(ROOT/'docs/40_data_probability/43_VALIDATION_PLAN.md').read_text(encoding='utf-8')
data=(ROOT/'docs/40_data_probability/40_DATA_CONTRACT.md').read_text(encoding='utf-8')
ok('validation scope ladder', all(x in data for x in ['UNVALIDATED','COMPONENT_ONLY','CORRIDOR_REPLAY','END_TO_END']) and all(x in val for x in ['V0 Engine Logic','V1 Component Hold-out','V2 Corridor Replay','V3 End-to-End Journey']))

# Architecture must preserve Bronze independent of Kafka
arch=(ROOT/'docs/50_architecture/50_SYSTEM_ARCHITECTURE.md').read_text(encoding='utf-8')
ok('collector to immutable Bronze path', 'C --> BZ[Bronze Raw Store]' in arch and 'C --> K[Kafka]' in arch and 'raw immutable write' in arch)

# No stale package defects
joined='\n'.join(p.read_text(encoding='utf-8',errors='ignore') for p in list((ROOT/'docs').rglob('*.md'))+[ROOT/'README.md'])
for phrase in ['10_PHASE1_EVIDENCE_EXECUTION.md','Spreadsheet runtime warmup failed','Markdown files: 27']:
    ok(f'no stale phrase: {phrase}', phrase not in joined)

# docs lint subprocess
proc=subprocess.run([sys.executable, str(ROOT/'scripts/docs_lint.py')],capture_output=True,text=True)
ok('docs_lint.py', proc.returncode==0, (proc.stdout+proc.stderr).strip())

for label,status,detail in checks:
    print(f'{status}: {label}' + (f' — {detail}' if detail and status=='FAIL' else ''))
if errors:
    print('\nRESULT: FAIL')
    for e in errors: print('ERROR:',e)
    sys.exit(1)
print(f'\nChecks: {len(checks)}')
print('RESULT: PASS')
