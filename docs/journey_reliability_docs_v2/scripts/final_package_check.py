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

# ---------- required package ----------
required = [
    'README.md', '.env.example',
    'docs/00_governance/00_MASTER_INDEX.md',
    'docs/00_governance/01_DOCUMENT_CONSTITUTION.md',
    'docs/00_governance/02_DECISION_LOG.md',
    'docs/00_governance/03_EVIDENCE_REGISTER.md',
    'docs/00_governance/04_SOURCE_REGISTER.md',
    'docs/00_governance/06_TRACEABILITY_MATRIX.md',
    'docs/00_governance/08_IMPLEMENTATION_STATUS.md',
    'docs/00_governance/09_PHASE1_EVIDENCE_EXECUTION.md',
    'docs/00_governance/10_PHASE2_EVIDENCE_EXECUTION.md',
    'docs/40_data_probability/40_DATA_CONTRACT.md',
    'docs/40_data_probability/41_OBSERVATION_ACTUAL_RESIDUAL.md',
    'docs/40_data_probability/42_PROBABILITY_CONTRACT.md',
    'docs/40_data_probability/43_VALIDATION_PLAN.md',
    'docs/60_delivery/60_WBS_RISK.md',
    'docs/60_delivery/61_QA_ACCEPTANCE.md',
    'docs/60_delivery/62_DEMO_RELEASE.md',
    'baseline/phase0/docs/05_DECISION_LOG.md',
    'baseline/phase0/docs/06_PHASE0_SUMMARY_FOR_PLANNING.md',
    'baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json',
    'evidence/phase1/PHASE1_EVIDENCE_VALIDATION_REPORT.md',
    'evidence/phase1/EVD-CROSS-002/README.md',
    'evidence/phase1/EVD-ACCESS-001/README.md',
    'evidence/phase1/EVD-XFER-B2S-001/README.md',
    'evidence/phase1/EVD-DEST-001/README.md',
    'evidence/phase1/EVD-TRANSFER-001/README.md',
    'evidence/phase1/EVD-SCHED-001/README.md',
    'evidence/phase1/EVD-WAIT-001/README.md',
    'evidence/phase1/SUBWAY_SUSTAINED/README.md',
    'evidence/phase1/BUS_01A_EXTENDED/README.md',
    'evidence/phase1/VOLUME_LATENESS/README.md',
]
missing=[x for x in required if not (ROOT/x).exists()]
ok('required canonical/baseline/phase1 files', not missing, ', '.join(missing))

# ---------- package navigation / execution status ----------
readme=(ROOT/'README.md').read_text(encoding='utf-8')
phase1=(ROOT/'docs/00_governance/09_PHASE1_EVIDENCE_EXECUTION.md').read_text(encoding='utf-8')
phase2=(ROOT/'docs/00_governance/10_PHASE2_EVIDENCE_EXECUTION.md').read_text(encoding='utf-8')
ok('README points to Phase2 current work order', '10_PHASE2_EVIDENCE_EXECUTION.md' in readme)
ok('Phase1 execution contract is SUPERSEDED', re.search(r'(?m)^status:\s*SUPERSEDED\s*$', phase1) is not None)
ok('Phase2 execution contract is LOCKED', re.search(r'(?m)^status:\s*LOCKED\s*$', phase2) is not None)
ok('Phase2 output contract present', 'PHASE2_EVIDENCE_AND_VERTICAL_SLICE_REPORT.md' in phase2)

# ---------- no real secret files/assignments ----------
secret_files=[]
for name in ('.env','.env.local'):
    secret_files += list(ROOT.rglob(name))
ok('no packaged .env/.env.local', not secret_files, ', '.join(str(x.relative_to(ROOT)) for x in secret_files))

secret_vars={'SEOUL_OPEN_API_KEY','SEOUL_SUBWAY_REALTIME_KEY','DATA_GO_BUS_API_KEY','KAKAO_MAP_REST_API_KEY','TMAP_APP_KEY'}
assigned=[]
envex=(ROOT/'.env.example').read_text(encoding='utf-8')
for line in envex.splitlines():
    if '=' not in line or line.lstrip().startswith('#'): continue
    k,v=line.split('=',1)
    if k.strip() in secret_vars and v.strip(): assigned.append(k.strip())
ok('.env.example secret values blank', not assigned, ', '.join(assigned))

# lightweight evidence text secret scan: explicit env assignments / URL query key literals
suspicious=[]
scan_ext={'.md','.json','.log','.txt','.py','.yaml','.yml','.csv'}
for p in ROOT.joinpath('evidence').rglob('*') if (ROOT/'evidence').exists() else []:
    if not p.is_file() or p.suffix.lower() not in scan_ext: continue
    # skip very large official CSVs: they cannot contain our runtime secrets and are provider data files
    if p.stat().st_size > 5_000_000 and p.suffix.lower()=='.csv': continue
    try: txt=p.read_text(encoding='utf-8', errors='ignore')
    except Exception: continue
    for var in secret_vars:
        for m in re.finditer(rf'(?m)^\s*{re.escape(var)}\s*=\s*([^\s#]+)',txt):
            val=m.group(1).strip().strip('"\'')
            if val and not val.startswith(('${','***','<')):
                suspicious.append(f'{p.relative_to(ROOT)}:{var}')
    # query/header literals that look like actual long credentials; code variable names are fine
    for m in re.finditer(r'(?i)(?:ServiceKey|appKey)\s*[=:]\s*["\']?([A-Za-z0-9%_\-]{24,})',txt):
        val=m.group(1)
        if 'REDACT' not in val.upper() and val not in {'DATA_GO_BUS_API_KEY','TMAP_APP_KEY'}:
            suspicious.append(f'{p.relative_to(ROOT)}:literal-key-like')
ok('phase1 evidence secret scan', not suspicious, ', '.join(sorted(set(suspicious))[:10]))

# ---------- Phase0 raw route assertions ----------
rawp=ROOT/'baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json'
try:
    x=json.loads(rawp.read_text(encoding='utf-8'))
    raw=x['raw_payload']
    if isinstance(raw,str): raw=json.loads(raw)
    items=raw['msgBody']['itemList']
    seqs=[[leg.get('routeNm') for leg in (it.get('pathList') or [])] for it in items]
    ok('Phase0 Route A raw assertion', bool(seqs and seqs[0]==['01A','3호선','2호선']), repr(seqs[:3]))
    ok('Phase0 structural Route B assertion', ['01A','3호선','147'] in seqs, repr(seqs[:3]))
except Exception as e:
    ok('Phase0 mixed-route raw parse', False, repr(e))

# ---------- canonical Phase1 reconciliation ----------
evd=(ROOT/'docs/00_governance/03_EVIDENCE_REGISTER.md').read_text(encoding='utf-8')
dec=(ROOT/'docs/00_governance/02_DECISION_LOG.md').read_text(encoding='utf-8')
master=(ROOT/'docs/00_governance/00_MASTER_INDEX.md').read_text(encoding='utf-8')
src=(ROOT/'docs/00_governance/04_SOURCE_REGISTER.md').read_text(encoding='utf-8')
impl=(ROOT/'docs/00_governance/08_IMPLEMENTATION_STATUS.md').read_text(encoding='utf-8')

checks_status = {
    'EVD-CROSS-002 VERIFIED': '| EVD-CROSS-002 | VERIFIED |' in evd,
    'EVD-ACCESS-001 VERIFIED': '| EVD-ACCESS-001 | VERIFIED |' in evd,
    'EVD-XFER-B2S-001 CONDITIONAL': '| EVD-XFER-B2S-001 | CONDITIONAL |' in evd,
    'EVD-DEST-001 VERIFIED': '| EVD-DEST-001 | VERIFIED |' in evd,
    'EVD-TRANSFER-001 VERIFIED': '| EVD-TRANSFER-001 | VERIFIED |' in evd,
    'EVD-SCHED-001 CONDITIONAL': '| EVD-SCHED-001 | CONDITIONAL |' in evd,
    'EVD-WAIT-001 VERIFIED': '| EVD-WAIT-001 | VERIFIED |' in evd,
    'EVD-VOLUME-001 CONDITIONAL': '| EVD-VOLUME-001 | CONDITIONAL |' in evd,
    'EVD-OPS-001 VERIFIED': '| EVD-OPS-001 | VERIFIED |' in evd,
}
for label,cond in checks_status.items(): ok(label,cond)

ok('Route B evidence does not imply Reforecast implementation', 'Reforecast product code가 구현됐다는 뜻이 아님' in evd and 'BUS_SKIPPED Reforecast | NOT_STARTED' in impl)
ok('Bus 54-transition scope caution', '특정 춘추문→안국 leg의 54 residual이라는 뜻이 아님' in evd)
ok('Bus 11 target samples explicitly not residual', 'traverse-time sample이지 Prediction→Actual residual이 아님' in evd and 'PD-036' in dec)
ok('Subway station×line join counts preserved', all(x in evd for x in ['안국3 16/16','교대3 12/12','교대2 12/12','역삼2 11/11']))
ok('Subway actual maturity remains conditional', '안국 53 sightings/11 intervals' in evd and '교대 name-search combined 40/6' in evd and '역삼 0/0' in evd)
ok('Shared subway quota reproduced and policy recorded', 'EVD-OPS-001' in evd and 'PD-033' in dec and 'ERROR-337' in evd)
ok('Wait snapshot iid overcount prohibited', '181 snapshots는 iid headway sample이 아님' in evd and 'PD-034' in dec)
ok('Collector timestamp artifact rejected', 'PD-037' in dec and '0 ms' in master and '실제 latency 증거가 아니다' in master)
ok('OA-22521 144s canonical decision', 'PD-031' in dec and '144 s' in dec and '63 s' in dec)
ok('Final walk station-center provenance preserved', 'PD-035' in dec and 'STATION_CENTER' in evd and '329 m / 300 s' in evd)
ok('Schedule currentness still conditional', 'PD-038' in dec and '2025-09-30' in evd and 'current-validity' in evd)
ok('OA-22521 live URL uses /F/ path', 'OA-22521/F/1/datasetView.do' in src and 'OA-22521/L/1/datasetView.do' not in src)

# ---------- probability / validation gates ----------
prob=(ROOT/'docs/40_data_probability/42_PROBABILITY_CONTRACT.md').read_text(encoding='utf-8')
val=(ROOT/'docs/40_data_probability/43_VALIDATION_PLAN.md').read_text(encoding='utf-8')
data=(ROOT/'docs/40_data_probability/40_DATA_CONTRACT.md').read_text(encoding='utf-8')
obs=(ROOT/'docs/40_data_probability/41_OBSERVATION_ACTUAL_RESIDUAL.md').read_text(encoding='utf-8')

ok('recommended departure re-evaluates service availability', '단순 `d`만큼 shift하지 않는다' in prob and ('재평가' in prob or '다시 구성' in prob))
ok('recommended departure current user-facing availability is HOLD', 'Recommended Departure — **HOLD for user-facing availability**' in master)
ok('probability vertical slice only CONDITIONAL GO', 'Probability Vertical Slice — **CONDITIONAL GO**' in master and 'PD-040' in dec)
ok('walk/transfer unmodeled uncertainty retained', 'UNMODELED' in prob and 'EVD-XFER-B2S-001' in evd)
ok('bus wait dependence limitation in probability contract', 'serial' in prob.lower() or 'dependen' in prob.lower())
ok('validation sample-unit integrity', 'sample-unit' in val.lower() or 'sample unit' in val.lower() or '분석단위' in val)
ok('bus mature claim requires ResidualEvent', 'ResidualEvent' in val and 'EVD-BUS-010' in val)
ok('multi-line subway isolation rule in data contract', 'subwayId' in data and 'statnId' in data and '산술' in data)
ok('timestamp instrumentation invariant', '실제 HTTP request 직전' in data and 'response bytes 수신 직후' in data and 'PD-037' in data)

# ---------- architecture/delivery does not overfreeze ----------
arch=(ROOT/'docs/50_architecture/50_SYSTEM_ARCHITECTURE.md').read_text(encoding='utf-8')
stream=(ROOT/'docs/50_architecture/51_STREAMING_STORAGE_CONTRACT.md').read_text(encoding='utf-8')
risk=(ROOT/'docs/60_delivery/60_WBS_RISK.md').read_text(encoding='utf-8')
qa=(ROOT/'docs/60_delivery/61_QA_ACCEPTANCE.md').read_text(encoding='utf-8')
demo=(ROOT/'docs/60_delivery/62_DEMO_RELEASE.md').read_text(encoding='utf-8')

ok('Phase1 volume is not production load claim', '53 MB/h' in stream and 'production traffic estimate가 아니라' in stream)
ok('partition/watermark/TTL remain profile-gated', all(x in stream for x in ['Partition Count','Watermark','State TTL']) and ('TBD' in stream or '확정하지' in stream))
ok('new Phase1 risks registered', all(x in risk for x in ['RISK-022','RISK-023','RISK-024','RISK-025']))
ok('new data acceptance gates registered', all(x in qa for x in ['AC-DATA-017','AC-DATA-018','AC-DATA-019','AC-DATA-020']))
ok('demo claims preserve Phase1 limitations', 'Route B' in demo and 'Recommended Departure' in demo and ('STATION_CENTER' in demo or 'station-center' in demo.lower()))

# ---------- docs lint ----------
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
