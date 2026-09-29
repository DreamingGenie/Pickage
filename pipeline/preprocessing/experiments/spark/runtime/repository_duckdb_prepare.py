"""Build an immutable code bundle locally; does not connect to any server."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from pipeline.preprocessing.common.paths import REPO_ROOT

def prepare(output):
    root = REPO_ROOT
    files = sorted(p for p in (root / 'pipeline').rglob('*')
                   if p.is_file() and p.suffix in ('.py', '.cjs') and 'node_modules' not in p.parts)
    bodies = {p.relative_to(root).as_posix(): p.read_bytes() for p in files}
    prepared = {'status': 'PREPARED_LOCAL_ONLY',
                'code_files_sha256': {name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()},
                'scope': 'repository local Spark vs DuckDB; server not started'}
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, body in bodies.items():
            archive.writestr('code/' + name, body)
        archive.writestr('prepared.json', json.dumps(prepared, indent=2))
    return {'file_count': len(bodies), 'zip_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'output': str(output.resolve()), 'server_started': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))


if __name__ == '__main__':
    main()
