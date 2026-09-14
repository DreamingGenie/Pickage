"""Read raw and a pinned parent; redirect every Curated write to local files."""
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

from botocore.exceptions import ClientError
from pipeline.curated.build import CURRENT
from pipeline.curated.storage import json_bytes


def error(code):
    return ClientError({"Error": {"Code": code, "Message": "Isolated experiment store"}}, "Object")


class OverlayS3:
    def __init__(self, source, directory, parent):
        self.source, self.root = source, Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.parent = parent
        self.meta = SimpleNamespace(endpoint_url="experiment://" + str(self.root))
        if parent is not None:
            self.put_object(Bucket="pickage-curated", Key=CURRENT, Body=json_bytes(parent))

    def _path(self, bucket, key):
        return self.root / hashlib.sha256((bucket + "\0" + key).encode()).hexdigest()

    def get_object(self, *, Bucket, Key):
        path = self._path(Bucket, Key)
        if path.is_file():
            body = path.read_bytes()
            return {"Body": io.BytesIO(body), "ETag": hashlib.sha256(body).hexdigest(), "ContentLength": len(body)}
        if Bucket == "pickage-raw" or (Bucket == "pickage-curated" and self.parent
                and Key.startswith(self.parent["run_prefix"] + "/")):
            return self.source.get_object(Bucket=Bucket, Key=Key)
        raise error("NoSuchKey")

    def head_object(self, **kwargs):
        result = self.get_object(**kwargs)
        body = result["Body"]
        try:
            if "ContentLength" not in result:
                result["ContentLength"] = len(body.read())
        finally:
            body.close()
        return {k: v for k, v in result.items() if k != "Body"}

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch=None, IfMatch=None, **kwargs):
        if Bucket != "pickage-curated":
            raise ValueError("Experiment cannot write raw or another bucket")
        path = self._path(Bucket, Key)
        exists = path.exists()
        if (IfNoneMatch == "*" and exists) or (IfMatch is not None and
                (not exists or hashlib.sha256(path.read_bytes()).hexdigest() != IfMatch.strip('"'))):
            raise error("PreconditionFailed")
        body = Body.read() if hasattr(Body, "read") else Body
        path.write_bytes(body)
        path.with_suffix(".json").write_bytes(json_bytes({"Bucket": Bucket, "Key": Key}))
        return {"ETag": hashlib.sha256(body).hexdigest()}

    def delete_object(self, *, Bucket, Key, IfMatch=None, **kwargs):
        if Bucket != "pickage-curated":
            raise ValueError("Experiment cannot delete outside its output overlay")
        path = self._path(Bucket, Key)
        if IfMatch is not None and (not path.is_file() or
                hashlib.sha256(path.read_bytes()).hexdigest() != IfMatch.strip('"')):
            raise error("PreconditionFailed")
        path.unlink(missing_ok=True)
        path.with_suffix(".json").unlink(missing_ok=True)
        return {}

    def list_objects_v2(self, *, Bucket, Prefix="", **kwargs):
        contents = []
        for path in self.root.glob("*.json"):
            record = json.loads(path.read_bytes())
            if record["Bucket"] == Bucket and record["Key"].startswith(Prefix):
                contents.append({"Key": record["Key"], "Size": path.with_suffix("").stat().st_size})
        return {"Contents": contents, "IsTruncated": False}
