# develop 병합 충돌 해결

## 범위와 처리
- 현재 기능 브랜치의 a7f9d6e와 사용자가 병합한 develop 2c9c791 사이의 진행 중 병합을 완료한다.
- 충돌은 deploy/ci/README.md의 미구현 CI/배포 항목 표 한 곳이다.
- develop의 data 상주 서비스/로더/배치 실행 관련 설명을 보존하고, Python 테스트 명령은 pipeline.preprocessing 경로를 사용한다.
- 자동 병합된 develop 코드 변경은 그대로 보존한다. 서버 배포나 추가 fetch는 수행하지 않는다.

## 검증
- 미해결 index 항목·충돌 마커 없음, staged diff --check 통과.
- 로컬 DuckDB 변환/게시·전처리 경로 회귀 테스트17개 통과. develop 전체 백엔드/프런트 테스트는 재실행하지 않았다.
