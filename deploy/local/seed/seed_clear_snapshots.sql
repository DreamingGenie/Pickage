-- 스냅샷만 비운다 — "자료 축적 중" 상태를 만든다.
--
--   docker compose exec postgres psql -U postgres -d pickage -f seed/seed_clear_snapshots.sql
--
-- 경로 앞에 `/` 를 붙이지 않는다. Git Bash 가 `/seed/...` 를 윈도우 경로로 바꿔 버려서
-- "No such file or directory" 가 난다.
--
-- ## 다른 세 시드와 성격이 다르다
--
-- `seed_sample` · `seed_mock_parity` · `seed_service_full` 은 서로 배타적이다(셋 다 전량
-- TRUNCATE 로 시작한다). 이 파일은 그 셋 중 하나를 적용한 **뒤에** 얹어 쓴다. 데이터를 넣지
-- 않고 스냅샷 계열만 걷어내므로, 어느 시드 위에서든 같은 상태가 된다.
--
--   package · version                       남는다  ← 이름은 존재한다
--   snapshot · package_snapshot ·
--   package_version_snapshot                비운다  ← 관측값이 아직 없다
--
-- ## 무엇을 보려고 만들었나 (S15P21A506-298)
--
-- 적재 전이거나 첫 스냅샷을 기다리는 동안의 **정상 상태**다. 장애가 아니다.
-- 이 상태에서 조회 엔드포인트 5개가 전부 200 이어야 하고, 추이는 빈 시리즈,
-- `snapshot_at` 은 null 로 나가야 한다. 예전에는 여기서 500(S001) 이 났다.
--
-- `seed_sample.sql` 이 만드는 "자료가 모자란 상태"(스냅샷 2개)와도 다르다.
-- 저쪽은 값이 적은 것이고 이쪽은 값이 아예 없는 것이라, 화면 분기가 갈린다.

-- 두 표가 snapshot 을 FK 로 참조하므로 먼저 비운다.
TRUNCATE package_version_snapshot, package_snapshot;

-- ⚠ snapshot 은 TRUNCATE 가 아니라 DELETE 다 (다른 시드와 같은 이유).
--
-- V3 가 etl_snapshot_reference.snapshot_at → snapshot 의 FK 를 만들었다. PostgreSQL 의
-- TRUNCATE 는 참조하는 테이블이 비어 있어도 같이 지정하지 않으면 거절한다. 목록에
-- etl_snapshot_reference 를 넣으면 파이프라인의 적재 이력을 지우게 되므로 넣지 않는다.
--
-- DELETE 는 참조가 실제로 있을 때만 FK 위반으로 실패한다. 즉 **실적재가 한 번이라도 성공한
-- DB 에서는 이 파일이 조용히 덮어쓰지 않고 에러로 멈춘다.** 그게 의도다.
DELETE FROM snapshot;
