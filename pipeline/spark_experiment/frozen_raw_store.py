"""Read-only S3-shaped access to a verified raw freeze; no live-store fallback."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from pipeline.curated.storage import json_bytes
from .freeze_raw import safe_key, sha
from .overlay import error


class VerifiedBody:
    def __init__(self, path, record):
        self.stream, self.record = path.open('rb'), record
        self.digest, self.size = hashlib.sha256(), 0

    def read(self, size=-1):
        data = self.stream.read(size)
        self.digest.update(data); self.size += len(data)
        if size < 0 or not data or self.size >= self.record['bytes']:
            if self.size != self.record['bytes'] or self.digest.hexdigest() != self.record['sha256']:
                raise ValueError('Frozen raw bytes changed')
        return data

    def close(self):
        self.stream.close()


class FrozenRawS3:
    def __init__(self, manifest_path):
        path = Path(manifest_path).resolve()
        self.root = path.parent
        self.manifest = json.loads(path.read_bytes())
        m = self.manifest
        if m.get('status') != 'VERIFIED' or m.get('scope') != 'RAW_ONLY_NO_PREPROCESSING':
            raise ValueError('Raw freeze is not verified')
        if sha(json_bytes({'request': m['source_request'], 'objects': m['objects']})) != m['input_identity']:
            raise ValueError('Frozen input identity differs')
        expected = {(r['bucket'], r['key']): r for r in m['objects']}
        self.files = {}
        for r in m['input_files']:
            identity = (r['bucket'], safe_key(r['key']))
            if identity in self.files or {k: r[k] for k in ('bucket', 'key', 'bytes', 'sha256')} != expected.get(identity):
                raise ValueError('Frozen inventory differs')
            relative = 'objects/' + r['bucket'] + '/' + r['key']
            if r['relative_path'] != relative:
                raise ValueError('Frozen path differs')
            local = (self.root / relative).resolve()
            local.relative_to(self.root)
            self.files[identity] = (local, r)
        if self.files.keys() != expected.keys():
            raise ValueError('Frozen inventory is incomplete')
        self.meta = SimpleNamespace(endpoint_url='frozen-raw://' + str(self.root))

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.files:
            raise error('NoSuchKey')
        path, r = self.files[(Bucket, Key)]
        if path.stat().st_size != r['bytes']:
            raise ValueError('Frozen raw size changed')
        return {'ContentLength': r['bytes'], 'ETag': r['sha256']}

    def get_object(self, *, Bucket, Key):
        metadata = self.head_object(Bucket=Bucket, Key=Key)
        path, record = self.files[(Bucket, Key)]
        return {**metadata, 'Body': VerifiedBody(path, record)}

    def list_objects_v2(self, *, Bucket, Prefix='', **kwargs):
        return {'IsTruncated': False, 'Contents': [
            {'Key': key, 'Size': record['bytes']} for (bucket, key), (_, record) in sorted(self.files.items())
            if bucket == Bucket and key.startswith(Prefix)]}
