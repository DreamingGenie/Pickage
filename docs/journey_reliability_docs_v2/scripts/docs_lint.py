from pathlib import Path
import re, sys, collections, datetime

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
files = sorted(DOCS.rglob('*.md'))
texts = {p: p.read_text(encoding='utf-8') for p in files}
errors, warnings = [], []

REQUIRED_FM = [
    'doc_id','title','version','status','owner','last_updated',
    'depends_on','source_of_truth_for','supersedes'
]
ALLOWED_DOC_STATUS = {'DRAFT','REVIEW','LOCKED','SUPERSEDED'}

# ----- frontmatter -----
doc_ids = {}
frontmatters = {}
for p,t in texts.items():
    rel=p.relative_to(ROOT)
    if not t.startswith('---\n') or t.count('---') < 2:
        errors.append(f'missing/invalid frontmatter: {rel}')
        continue
    try:
        fm=t.split('---',2)[1]
    except Exception:
        errors.append(f'invalid frontmatter split: {rel}')
        continue
    frontmatters[p]=fm
    for k in REQUIRED_FM:
        if not re.search(rf'(?m)^{re.escape(k)}:',fm):
            errors.append(f'missing frontmatter key {k}: {rel}')
    m=re.search(r'(?m)^doc_id:\s*(JR-DOC-\d+)\s*$',fm)
    if not m:
        errors.append(f'missing/invalid doc_id: {rel}')
    else:
        did=m.group(1)
        if did in doc_ids: errors.append(f'duplicate doc_id {did}: {doc_ids[did]} and {rel}')
        doc_ids[did]=rel
    sm=re.search(r'(?m)^status:\s*([^\n#]+)',fm)
    if sm and sm.group(1).strip() not in ALLOWED_DOC_STATUS:
        errors.append(f'invalid doc status {sm.group(1).strip()}: {rel}')
    dm=re.search(r'(?m)^last_updated:\s*(\d{4}-\d{2}-\d{2})\s*$',fm)
    if not dm:
        errors.append(f'invalid last_updated: {rel}')
    else:
        try: datetime.date.fromisoformat(dm.group(1))
        except ValueError: errors.append(f'invalid date value: {rel}')

# depends_on references
for p,fm in frontmatters.items():
    refs=re.findall(r'JR-DOC-\d+',fm)
    for r in refs:
        if r not in doc_ids:
            errors.append(f'unknown JR dependency/ref {r}: {p.relative_to(ROOT)}')

# ----- ID definitions -----
defs=collections.defaultdict(set)

def add(kind,val,where):
    if val in defs[kind]: errors.append(f'duplicate definition {val}: {where}')
    defs[kind].add(val)

patterns = {
    'PD': r'(?m)^\|\s*(PD-\d+)\s*\|',
    'EVD': r'(?m)^\|\s*(EVD-[A-Z0-9]+-\d+)\s*\|',
    'SRC': r'(?m)^\|\s*(SRC-[A-Z0-9]+-\d+)\s*\|',
    'REQ': r'(?m)^###\s+(REQ-\d+)\b',
    'BR': r'(?m)^\*\*(BR-\d+)\*\*',
    'NFR': r'(?m)^###\s+(NFR-\d+)\b',
    'SCR': r'(?m)^#\s+(SCR-\d+)\b',
    'API': r'(?m)^#\s+(API-\d+)\b',
    'ENT': r'(?m)^###\s+(ENT-\d+)\b',
    'DQ': r'(?m)^\|\s*(DQ-\d+)\s*\|',
    'ADR': r'(?m)^\|\s*(ADR-\d+)\s*\|',
    'RISK': r'(?m)^\|\s*(RISK-\d+)\s*\|',
    'AC': r'(?m)^###\s+(AC-[A-Z]+-\d+)\b',
    'TST': r'(?m)^##\s+(TST-[A-Z]+-\d+)\b',
    'F': r'(?m)^\|\s*(F-\d+)\s*\|',
}
for kind,pat in patterns.items():
    for p,t in texts.items():
        for m in re.finditer(pat,t): add(kind,m.group(1),p.relative_to(ROOT))

# all references must resolve
ref_patterns = {
    'PD': r'\bPD-\d+\b',
    'EVD': r'\bEVD-[A-Z0-9]+-\d+\b',
    'SRC': r'\bSRC-[A-Z0-9]+-\d+\b',
    'REQ': r'\bREQ-\d+\b',
    'BR': r'\bBR-\d+\b',
    'NFR': r'\bNFR-\d+\b',
    'SCR': r'\bSCR-\d+\b',
    'API': r'\bAPI-\d+\b',
    'ENT': r'\bENT-\d+\b',
    'DQ': r'\bDQ-\d+\b',
    'ADR': r'\bADR-\d+\b',
    'RISK': r'\bRISK-\d+\b',
    'AC': r'\bAC-[A-Z]+-\d+\b',
    'TST': r'\bTST-[A-Z]+-\d+\b',
    'F': r'\bF-\d+\b',
}
for kind,pat in ref_patterns.items():
    refs=set()
    for t in texts.values(): refs.update(re.findall(pat,t))
    for x in sorted(refs-defs[kind]): errors.append(f'unknown {kind} reference: {x}')

# ----- markdown relative links -----
for p,t in texts.items():
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',t):
        if '://' in target or target.startswith('#') or target.startswith('mailto:'): continue
        target=target.split('#')[0]
        if not target: continue
        q=(p.parent/target).resolve()
        if not q.exists(): errors.append(f'broken relative link {p.relative_to(ROOT)} -> {target}')

# ----- evidence artifact paths -----
evfile=DOCS/'00_governance'/'03_EVIDENCE_REGISTER.md'
if evfile.exists():
    for line in evfile.read_text(encoding='utf-8').splitlines():
        if not line.startswith('| EVD-'): continue
        cells=[c.strip() for c in line.strip('|').split('|')]
        if len(cells)<6: continue
        evid,status,claim,scope,artifact,lim=cells[:6]
        # explicit package-root paths in backticks must resolve; URLs/external refs/summary refs can be prose
        for path in re.findall(r'`([^`]+)`',artifact):
            if path.startswith(('baseline/','docs/','scripts/')):
                if not (ROOT/path).exists(): errors.append(f'{evid} artifact path missing: {path}')
        if status in {'VERIFIED','CONDITIONAL'} and artifact in {'','—','-'}:
            errors.append(f'{evid} {status} has no artifact/reference')

# ----- traceability orphan checks -----
trace=DOCS/'00_governance'/'06_TRACEABILITY_MATRIX.md'
if trace.exists():
    tt=trace.read_text(encoding='utf-8')
    traced_req=set(re.findall(r'\bREQ-\d+\b',tt))
    # all MUST/CLAIM_GATE requirements should appear in traceability
    reqfile=DOCS/'20_requirements'/'20_REQUIREMENTS.md'
    if reqfile.exists():
        rt=reqfile.read_text(encoding='utf-8')
        chunks=re.split(r'(?m)^###\s+(REQ-\d+)\b',rt)
        for i in range(1,len(chunks),2):
            rid,body=chunks[i],chunks[i+1]
            pm=re.search(r'\*\*Priority:\*\*\s*([^\n]+)',body)
            if pm and pm.group(1).strip() in {'MUST','CLAIM_GATE'} and rid not in traced_req:
                errors.append(f'orphan required requirement not in traceability: {rid}')

# ----- dangerous stale phrases -----
joined='\n'.join(texts.values())
for phrase in [
    'EVD-CROSS-001 TO_VERIFY',
    'placeholder variance',
    'Corridor B reverse direction',
]:
    if phrase in joined: warnings.append(f'stale/risky phrase present: {phrase}')

print(f'Markdown files: {len(files)}')
print(f'doc_ids: {len(doc_ids)}')
for k in ['PD','EVD','SRC','REQ','BR','NFR','SCR','API','ENT','DQ','ADR','RISK','AC','TST','F']:
    print(f'{k}: {len(defs[k])}')
if warnings:
    print('\nWARNINGS')
    for x in warnings: print('-',x)
if errors:
    print('\nERRORS')
    for x in errors: print('-',x)
    sys.exit(1)
print('\nRESULT: PASS')
