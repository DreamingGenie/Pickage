-- 서비스 6개 테이블을 전부 비운다 — 데이터를 넣지 않는다.
--
--   docker compose exec postgres psql -U postgres -d pickage -f seed/seed_reset.sql
--
-- ## 언제 쓰나 — 목업을 실데이터로 교체하기 직전 1회
--
-- 목업 시드로 화면을 굴리다가 Spark 정제 데이터를 적재하는 시점에, 그 **직전에** 한 번
-- 돌린다. 실적재기(`pipeline/postgresql`)는 전량 교체가 아니라 임시 staging + upsert 라
-- 목업 행을 스스로 걷어내지 않는다.
--
-- 안 돌리고 적재하면 어떻게 되나 — **조용히 섞이지 않는다.** 적재기가 게시 직전에
-- 아래 두 가지를 검사하고 예외를 던지며 트랜잭션을 통째로 롤백한다.
--
--   package_id 는 같은데 name 이 다르다   → 'package_id/name collision'
--   name 은 같은데 package_id 가 다르다   → 'package name/id collision'
--
-- 목업은 package_id 를 1 부터 제 순서대로 배정하므로 거의 확실히 걸린다. 즉 이 파일을
-- 잊어도 데이터가 깨지지는 않고 적재가 실패하며 알려 준다. 그 메시지를 보면 여기로 올 것.
--
-- ## 반대 방향은 막혀 있다
--
-- 실적재가 한 번이라도 성공하면 etl_snapshot_reference 에 이력이 남고, 그 뒤로는 목업
-- 시드의 `DELETE FROM snapshot` 이 FK 위반으로 멈춘다. 실데이터를 목업으로 덮을 수 없다.

-- 다섯 표가 FK 로 묶여 있어 하나씩은 비울 수 없다. 한 번에 비운다.
-- CASCADE 를 쓰지 않는 이유: 나중에 추가된 테이블까지 말없이 같이 비워 버린다.
-- 여기 전부 적어 두면 새 테이블이 생겼을 때 이 파일이 에러로 알려 준다.
TRUNCATE similar_package, package_version_snapshot, package_snapshot, version, package;

-- ⚠ snapshot 만 DELETE 다. 이유는 seed_clear_snapshots.sql 의 같은 주석을 볼 것.
DELETE FROM snapshot;
