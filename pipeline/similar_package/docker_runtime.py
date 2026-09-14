"""Spark 변환을 고정 이미지·자원 제한 컨테이너에서 실행한다."""
import json
from pathlib import Path
import subprocess
import uuid

# TODO(확인): EC2 #1 에 이 이미지가 받아져 있는지. 없으면 docker pull 선행
IMAGE = "apache/spark@sha256:936ff39fd63e2bb5ed064f0fbe1518198473f1cdbfa2f863d087a9a8e58116ba"
ROOT = Path(__file__).resolve().parents[2]


# 입력 경로를 컨테이너 마운트 경로로 바꿔 invocation.json 을 쓰고, Spark 컨테이너를 돌린 뒤 결과를 돌려준다.
def transform_docker(inputs, output, *, threads=2, driver_memory="4g",
                     container_memory="6g", shuffle_partitions=32):
    output = Path(output).resolve()
    attempt = output.parent
    mappings = [(Path(value).resolve(), "/input/" + key) for key, value in inputs["sources"].items()]
    for path, _ in mappings:
        if output.is_relative_to(path) or path.is_relative_to(output):
            raise ValueError("산출 경로가 입력 경로와 겹친다")

    adapted = dict(inputs)
    for field in ("raw_paths", "curated_package_paths", "curated_version_paths"):
        adapted[field] = []
        for value in inputs.get(field) or []:
            path = Path(value).resolve()
            matches = [(root, target) for root, target in mappings if path.is_relative_to(root)]
            if len(matches) != 1:
                raise ValueError(f"입력 파일에 읽기 전용 마운트가 하나로 정해지지 않는다: {path}")
            root, target = matches[0]
            adapted[field].append(target + "/" + path.relative_to(root).as_posix())
    adapted.update(threads=threads, driver_memory=driver_memory,
                   shuffle_partitions=shuffle_partitions)
    adapted.pop("sources", None)

    with (attempt / "spark-invocation.json").open("x", encoding="utf-8") as stream:
        json.dump(adapted, stream, ensure_ascii=False, sort_keys=True)

    # --memory 와 --memory-swap 은 짝으로 준다. 한쪽만 주면 상한이 두 배가 된다.
    command = ["docker", "run", "--rm", "--name", "pickage-package-text-" + uuid.uuid4().hex[:12],
               "--cpus", str(threads), "--memory", container_memory, "--memory-swap", container_memory,
               "--network", "none",
               "-e", "PYTHONPATH=/workspace", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "SPARK_LOCAL_IP=127.0.0.1", "-e", "SPARK_LOCAL_HOSTNAME=localhost",
               "--mount", f"type=bind,source={ROOT},target=/workspace,readonly",
               "--mount", f"type=bind,source={attempt},target=/run", "--workdir", "/workspace"]
    for source, target in mappings:
        command += ["--mount", f"type=bind,source={source},target={target},readonly"]
    command += [IMAGE, "/opt/spark/bin/spark-submit", "--master", f"local[{threads}]",
                "--driver-memory", driver_memory,
                "/workspace/pipeline/similar_package/spark_job.py",
                "--input", "/run/spark-invocation.json",
                "--output", "/run/outputs",
                "--result", "/run/spark-result.json"]

    log_path = attempt / "spark-driver.log"
    print(f"Spark 컨테이너 실행; 로그: {log_path}", flush=True)
    with log_path.open("xb") as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Spark 컨테이너 실패 (exit {completed.returncode}); {log_path}")
    result = json.loads((attempt / "spark-result.json").read_bytes())
    result["runtime"].update(engine="docker", image=IMAGE, cpus=threads,
                             memory_limit=container_memory, shuffle_partitions=shuffle_partitions)
    return result
