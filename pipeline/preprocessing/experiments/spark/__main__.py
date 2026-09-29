"""Separate experiment commands; the normal orchestrator remains unchanged."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Read pinned MinIO inputs; freeze reference inputs locally")
    prepare.add_argument("--request", type=Path, required=True)
    prepare.add_argument("--work-dir", type=Path, required=True)
    frozen = commands.add_parser("prepare-frozen", help="Compute baseline reference inputs from verified frozen raw; no live MinIO access")
    frozen.add_argument("--manifest", type=Path, required=True)
    frozen.add_argument("--work-dir", type=Path, required=True)
    fixture = commands.add_parser("fixture", help="Create a small synthetic experiment without MinIO credentials")
    fixture.add_argument("--work-dir", type=Path, required=True)
    bench = commands.add_parser("benchmark", help="Run both engines sequentially and compare every output row")
    bench.add_argument("--manifest", type=Path, required=True)
    bench.add_argument("--image", default="pickage-spark-experiment:local")
    bench.add_argument("--repetitions", type=int, default=3)
    bench.add_argument("--threads", type=int, default=2)
    bench.add_argument("--memory", default="2GB")
    bench.add_argument("--container-memory", default="6g")
    cluster = commands.add_parser("cluster-bundle", help="Prepare an offline bundle; does not upload or submit jobs")
    cluster.add_argument("--manifest", type=Path, required=True)
    cluster.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare-frozen':
        import copy
        from pipeline.preprocessing.experiments.spark.frozen_raw_store import FrozenRawS3
        from pipeline.preprocessing.experiments.spark.prepare import prepare
        source = FrozenRawS3(args.manifest)
        request = copy.deepcopy(source.manifest['source_request'])
        request['options']['repository_engine'] = 'native'
        result = prepare(source, request, args.work_dir)
    elif args.command in ("prepare", "fixture"):
        from pipeline.preprocessing.experiments.spark.prepare import prepare
        if args.command == "fixture":
            from pipeline.preprocessing.tests.fixtures.orchestration_fixture import make_fixture
            args.work_dir.mkdir(parents=True, exist_ok=False)
            data = make_fixture(args.work_dir / "f")
            data.bootstrap_parent()
            result = prepare(data.s3, data.request, args.work_dir / "i")
        else:
            from pipeline.minio.ingest_raw import client
            request = json.loads(args.request.read_text(encoding="utf-8-sig"))
            result = prepare(client(), request, args.work_dir)
    elif args.command == "cluster-bundle":
        from pipeline.preprocessing.experiments.spark.cluster import build_cluster_bundle
        result = build_cluster_bundle(args.manifest, args.output_dir)
    else:
        from pipeline.preprocessing.experiments.spark.benchmark import benchmark
        result = benchmark(args.manifest, image=args.image, repetitions=args.repetitions,
                           threads=args.threads, memory=args.memory, container_memory=args.container_memory)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
