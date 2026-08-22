from pathlib import Path
import hashlib, sys
ROOT=Path(__file__).resolve().parents[1]
manifest=ROOT/'MANIFEST_SHA256.txt'
if not manifest.exists():
    print('MANIFEST missing'); sys.exit(1)
errors=[]; checked=0
for line in manifest.read_text(encoding='utf-8').splitlines():
    if not line.strip(): continue
    digest,rel=line.split('  ',1)
    p=ROOT/rel
    if not p.exists(): errors.append(f'missing {rel}'); continue
    actual=hashlib.sha256(p.read_bytes()).hexdigest()
    if actual!=digest: errors.append(f'hash mismatch {rel}')
    checked+=1
print(f'Checked: {checked}')
if errors:
    for e in errors: print('ERROR',e)
    sys.exit(1)
print('RESULT: PASS')
