"""Select history only through a verified, completed preprocessing bundle."""
import json

from pipeline.curated.storage import json_bytes, read_optional
from .contracts import STAGES
from .storage import BUCKET, PREFIX, required, sha, verify_descriptor

CURRENT = PREFIX + "/_current.json"


def read_bundle(s3, pointer):
    prefix = pointer["run_prefix"]
    body = required(s3, BUCKET, prefix + "/run_manifest.json")
    marker = json.loads(required(s3, BUCKET, prefix + "/_SUCCESS"))
    if sha(body) != pointer["manifest_sha256"] or marker != {"manifest_sha256": sha(body)}:
        raise ValueError("Parent bundle manifest or completion marker differs")
    bundle = json.loads(body)
    request = bundle.get("request", {})
    expected = f"{PREFIX}/snapshot={request.get('snapshot')}/run_id={request.get('run_id')}"
    if (bundle.get("status") != "COMPLETE" or prefix != expected
            or request.get("snapshot") != pointer["snapshot"]
            or set(bundle.get("stages", {})) != set(STAGES)):
        raise ValueError("Parent bundle is not a complete matching snapshot")
    return bundle


def validate_parent(s3, request):
    parent = request["parent_bundle"]
    current = read_optional(s3, BUCKET, CURRENT)
    if current is None or json.loads(current[0]) != parent:
        raise ValueError("Current completed bundle does not match pinned parent")
    bundle = read_bundle(s3, parent)
    population = bundle["stages"]["package_version"]
    expected = {"run_prefix": population["prefix"],
                "manifest_sha256": population["manifest_sha256"], "snapshot": parent["snapshot"]}
    if request["parent"] != expected:
        raise ValueError("Package/version parent is outside completed parent bundle")
    # Calendar extension cannot silently drop or rewrite previous snapshots.
    prior = bundle["request"]["calendar_refs"]
    if request["calendar_refs"][:len(prior)] != prior:
        raise ValueError("Weekly calendar changed completed parent history")
    verify_descriptor(s3, population, workers=request.get("options", {}).get("workers", 2))
    return bundle


def publish_current(s3, request, body, *, replay=False):
    """CAS after _SUCCESS; replay repairs a crash without rewinding history."""
    pointer = {"run_prefix": f"{PREFIX}/snapshot={request['snapshot']}/run_id={request['run_id']}",
               "manifest_sha256": sha(body), "snapshot": request["snapshot"]}
    found = read_optional(s3, BUCKET, CURRENT)
    current = json.loads(found[0]) if found else None
    if current == pointer:
        return
    if request["format_version"] == 2 and current != request["parent_bundle"]:
        if replay and current and current["snapshot"] >= request["snapshot"]:
            read_bundle(s3, current)
            return
        raise ValueError("Completed bundle parent advanced before publication")
    if current and current["snapshot"] > request["snapshot"]:
        if replay:
            return
        raise ValueError("Cannot publish a bundle older than current history")
    if replay and current and current["snapshot"] == request["snapshot"]:
        return
    condition = {"IfMatch": found[1]} if found else {"IfNoneMatch": "*"}
    s3.put_object(Bucket=BUCKET, Key=CURRENT, Body=json_bytes(pointer), **condition)
