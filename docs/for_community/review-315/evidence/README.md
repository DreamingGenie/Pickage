# 검수 증거와 재현 방법

수정 전 증거를 보존한 문서다. 현재 시험은 정규 sourceSets로 이관했다. 아래 init script는 **d9193a3 체크아웃에서만** 사용한다. 수정 후 결과는 [수정 대장](../remediation.md) 및 최종 검수 기록을 따른다.

2026-09-11, Windows/Java21/PostgreSQL, 코드 `d9193a3`. 제품 소스 수정 전 결과다.

| 검증 | 결과 | 제한 |
|---|---|---|
| 기준선 backend test/build | compileTestJava 실패 | 기존 PdfStoreTest 2곳 save 인자 누락 |
| 해당 한 파일만 제외한 기존 단위 시험 | 197 통과 | 제외 없는 전체 build 통과 아님 |
| 기존 community DB 시험 | 15 통과 | migration 6, repository 4, controller 5 |
| 새 단위 계약 반례 | 27 실패 | 원문 기대값과 현재 구현의 차이 |
| 새 실제 앱+DB 반례 | 11 중 8 실패·3 통과 | real Spring context, real PostgreSQL, 실제 외부 API 미호출 |
| develop+317 통합 backend test/build | 통과 | 동일 PdfStoreTest 제외 |
| develop+317 통합 frontend typecheck/build | 통과 | 브라우저 E2E·PDF 시각 검수 아님 |

[probe-results.json](probe-results.json)은 38개 새 시험의 메서드·결과·첫 실패 메시지다. [community-file-inventory.json](community-file-inventory.json)은 community main/test/integrationTest 101개 파일의 경로·hash·라인 및 시험 파일 내 메서드 후보 목록이다. 파일 목록이 101개의 독립 기능 시험을 뜻하지 않는다.

검수 코드는 `probes/`에 있고 기본 Gradle sourceSets에는 등록하지 않았다. 아래 init script를 명시한 실행에만 포함된다. 현재 계약을 고쳐 PASS로 바꾸기 위한 **의도적으로 실패하는 회귀 반례**다.

저장소 루트에서 Java21의 JAVA_HOME을 설정한 뒤 backend에서 각각 실행한다. `test`가 실패해도 DB 반례를 수행하도록 명령을 분리한다.

```powershell
cd backend
.\gradlew.bat -I ..\docs\for_community\review-315\probes\review.init.gradle test --tests '*ContractReviewTest' --console=plain
.\gradlew.bat -I ..\docs\for_community\review-315\probes\review.init.gradle integrationTest --tests '*ApplicationContractReviewTest' --console=plain
cd ..
python -X utf8 docs/for_community/review-315/probes/capture_evidence.py
```

실제 통합 실행은 `DisposableTestDatabase.createFor("315")`가 별도 random DB를 생성하고 종료 시 drop한다. application datasource URL/user/password를 해당 DB로 명시한다. 기존 개발 DB의 package나 seed를 삭제하지 않는다. PostgreSQL 컨테이너가 실행되어 있고 기존 지원 클래스의 접속 환경이 필요하다.

body stall 시험은 127.0.0.1의 임시 HTTP 서버만 사용한다. private metadata·오류 payload도 synthetic fixture다. 실제 GitHub private 저장소나 rate 제한을 유발하지 않는다. 새 단위 전체 27개를 기존 197개와 함께 실행한 마지막 로그는 `.git/community-315-all-probes.log`(224 중 27 실패); 위 필터 명령은 새 27개만 실행한다.

기존 DB 시험 재현:

```powershell
cd backend
.\gradlew.bat integrationTest --tests '*CommunitySnapshotMigrationIntegrationTest' --tests '*CommunitySnapshotRepositoryIntegrationTest' --tests '*CommunityControllerIntegrationTest' --console=plain
```

통합 기준은 `8372b17b90c91bc80a1b6ebbdf90e0eb2ff69af4`에 `d9193a3744c904963ad13c8c710f0548a9ab8437`를 no-commit merge한 tree다. 원래 317 브랜치를 병합하거나 수정하지 않았다. frontend package.json/lock 차이는 없음을 확인하고 설치된 node_modules를 junction으로 재사용했다. `npm.cmd run typecheck`, `npm.cmd run build` 통과. PowerShell npm.ps1 실행 정책 오류는 npm.cmd로 해소했으며 제품 실패로 세지 않았다.

로컬 원본 로그는 `.git/community-315-*.log`, Gradle XML은 `backend/build/test-results/`에 있다. 후속 시험은 XML을 덮어쓰므로 증거 JSON을 먼저 저장했다. 원본 로그는 커밋 산출물이 아니며 raw stack trace 전체를 문서에 복사하지 않았다. build plugin timing 경고는 exit 0인 번들 생성 결과와 구분했다.

아직 실행하지 않은 gate는 [검수 결과](../findings.md)의 마지막 절에 명시했다. 실외부·FE 화면·운영 자원 사용량 증거는 여기 없다.

## 수정 후 재현

코드 `ce4dd91` 및 그 이후 문서 커밋에서 다음 정규 시험을 실행한다. Python/Playwright 브라우저 시험은 `probes/browser_regression.py`에 있다. 로컬 Chrome, Node 의존성, Java21, `pickage-local-postgres-1`이 필요하며 시험용 임의 DB만 생성·삭제한다. Python Playwright는 저장소 의존성이 아니며 별도 환경 또는 `.git/phase5-pylibs`에 설치할 수 있다.

```powershell
cd backend
.\gradlew.bat test build integrationTest --console=plain
cd ../frontend
npm.cmd run typecheck
npm.cmd run build
cd ..
python -X utf8 docs/for_community/review-315/probes/browser_regression.py
python -X utf8 docs/for_community/review-315/probes/capture_post_fix.py
```

전체 integrationTest의 기존 PickageApplicationTests는 Spring datasource를 쓰므로 `SPRING_DATASOURCE_URL`을 별도 시험 DB로 지정한다. 새 CommunityAcceptanceIntegrationTest는 자체 disposable DB를 사용한다. 실 GitHub 호출 3개는 opt-in이고 자동 실행에서는 skipped다.

브라우저 최초 스크립트의 `/report`(실제 `/report/:id`)와 textbox/combobox selector, seed의 유사후보 미적재 가정 오류는 시험 harness를 고쳐 해결했다. 제품 변경으로 세지 않는다. 결과 JSON은 최종 성공 실행만 가리킨다. 기능 비교는 기존 sample 화면이고 새 커뮤니티 탭은 포함하지 않는다.
