"""Wait once on the verifier process, then write a human-readable result without an agent monitor."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path


def render(folder):
    record_path = folder / "recovery_record.json"
    failure_path = folder / "failure.json"
    if failure_path.exists():
        failure = json.loads(failure_path.read_bytes())
        return ("# 07 검증 중 문제 발생\n\n"
                f"단계: `{failure['phase']}`. 오류 종류: `{failure['type']}`.\n\n"
                f"상세 오류와 재개 판단은 [실패 기록]({failure_path.as_posix()})을 확인한다. "
                "전체 검증 완료로 간주하지 않는다. 원본 계산 결과는 보존했다.\n")
    if not record_path.exists():
        return ("# 07 검증 미완료\n\n검증 프로세스가 종료됐으나 최종 검증 기록이 없다. "
                "완료로 간주하지 않으며 실행 로그 확인이 필요하다.\n")
    record = json.loads(record_path.read_bytes())
    report_path = Path(record["data_verification"]["path"])
    report = json.loads(report_path.read_bytes())
    if record["status"] != "RECOVERED_VERIFIED_WITH_PROVENANCE_GAP" or not report["data_checks_passed"]:
        raise ValueError("Unexpected verification result")
    metrics = report["metrics"]
    return ("# 07 재부팅 후 최종 검증 결과\n\n"
            f"완료 시각(UTC): {record['completed_utc']}. **데이터 검사 통과, 초기 실행 증거 누락 유지.**\n\n"
            f"- 승인 입력 {report['input_counts']}의 로컬 내용 SHA와 원격 승인 manifest를 재검증했다.\n"
            f"- 결과 Parquet {report['output_files']:,}개, {report['output_bytes']:,}bytes의 내용 SHA와 파일 목록·행 수를 확인했다.\n"
            f"- 데이터 검사 {len(report['checks'])}개를 통과했다. source/target 적격 모집단, 선언/관계 중복, "
            "해석 선언과 edge의 정확한 관계·건수 일치, 상태 집계, lineage를 확인했다.\n"
            f"- source {metrics['source_versions']:,}개, 선언 {metrics['selected_declarations']:,}건, "
            f"해석 {metrics['resolved_declarations']:,}건, 미해석 {metrics['unresolved_declarations']:,}건이다.\n"
            f"- NULL 배포일 제외 {metrics['excluded_null_publication_versions']:,}개, "
            f"미래 배포 제외 {metrics['excluded_future_publication_versions']:,}개다.\n"
            "- 결과는 **PARTIAL**, `ready_for_dependents=false`다. 계산 재실행, MinIO 게시, 08 집계, DB 적재는 하지 않았다.\n\n"
            "초기 코드 hash·런타임 identity와 당시 host 후속 검사가 저장되지 않아, 표준 `run_manifest.json` 및 "
            "`_SUCCESS`는 만들지 않았다. 기존 integration과 현재 코드/runtime 일치는 보강 자료이며 초기 실행 증명을 대신하지 않는다. "
            "이번 별도 기록은 현재 데이터 검증 결과다.\n\n"
            f"[복구 검증 기록]({record_path.as_posix()}) · [상세 검사·사례]({report_path.as_posix()})\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, args.pid)
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) != 0:
                raise OSError("Failed waiting for verifier")
        finally:
            kernel.CloseHandle(handle)
    elif ctypes.get_last_error() != 87:
        raise ctypes.WinError(ctypes.get_last_error())
    content = render(args.folder.resolve())
    temporary = args.output.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(content)
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
