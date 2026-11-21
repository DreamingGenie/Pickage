package com.ssafy.pickage.domain.ops;

import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.pickage.domain.ops.WeeklyIngestServiceTest.FakeStore;

/**
 * 러너와 백엔드가 함께 지키는 규칙표를 백엔드 쪽에서 맞댄다.
 *
 * <p>실행 주 계산·14일 창·수동 요청 대기 판정은 파이썬 러너({@code pipeline/weekly/schedule.py})가
 * 실제로 쓰고, 이 서비스가 화면에 그린다. 전에는 주석("같은 규칙이어야 한다")으로만 묶여 있었다.
 * 표는 {@code pipeline/weekly/contract/weekly_rules.json} 하나이고 러너 쪽은
 * {@code pipeline/weekly/test_contract.py} 가 같은 파일을 읽는다.
 *
 * <p>이 시험이 깨지면: 화면이 보여 주는 회차·수집 구간·"대기 중" 표시가 러너의 실제 거동과
 * 어긋난다. 규칙을 바꾼 것이라면 표를 먼저 고치고 러너 쪽 시험도 같이 본다.
 *
 * <p>표는 backend/ 밖에 있다. Gradle 은 시험을 프로젝트 폴더(backend/)에서 돌리므로 한 단계 위를
 * 본다. 이미지 빌드는 {@code -x test} 라 backend/ 만 복사해도 이 시험에 닿지 않는다.
 */
class WeeklyRulesContractTest {

	static final Path RULES_FILE = Path.of("..", "pipeline", "weekly", "contract", "weekly_rules.json");

	static JsonNode rules;

	@BeforeAll
	static void 표를_읽는다() throws IOException {
		assertTrue(Files.isRegularFile(RULES_FILE),
			"규칙표가 없다: " + RULES_FILE.toAbsolutePath() + " — 저장소 전체를 받은 상태에서 backend/ 에서 실행한다");
		rules = new ObjectMapper().readTree(Files.readString(RULES_FILE));
	}

	static OffsetDateTime moment(JsonNode node) {
		return node == null || node.isNull() ? null : OffsetDateTime.parse(node.asText());
	}

	@Test
	void 실행_주_계산이_러너와_같다() {
		JsonNode cases = rules.get("current_week");
		assertTrue(cases.size() >= 3, "표가 비면 아무것도 보지 않고 통과한다");
		for (JsonNode c : cases) {
			var service = new WeeklyIngestService(new FakeStore(),
				Clock.fixed(Instant.parse(c.get("now_utc").asText()), ZoneOffset.UTC));
			// 목록의 첫 줄이 "이번 주" 다.
			assertEquals(LocalDate.parse(c.get("week_of").asText()), service.recentRuns(1).get(0).weekOf(),
				c.get("why").asText());
		}
	}

	@Test
	void 수집_구간이_러너와_같다() {
		JsonNode cases = rules.get("window");
		assertTrue(cases.size() >= 3, "표가 비면 아무것도 보지 않고 통과한다");
		for (JsonNode c : cases) {
			LocalDate week = LocalDate.parse(c.get("week_of").asText());
			// 지난 주를 묻는 것은 언제나 허용되므로 시계를 그 주 화요일에 둔다.
			var service = new WeeklyIngestService(new FakeStore(),
				Clock.fixed(week.plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC), ZoneOffset.UTC));
			var coverage = service.run(week).coverage();
			assertEquals(LocalDate.parse(c.get("window_start").asText()), coverage.windowStart(), c.get("why").asText());
			assertEquals(LocalDate.parse(c.get("window_end").asText()), coverage.windowEnd(), c.get("why").asText());
		}
	}

	@Test
	void 수동_요청_대기_판정이_러너와_같다() {
		JsonNode cases = rules.get("manual_pending");
		assertTrue(cases.size() >= 3, "표가 비면 아무것도 보지 않고 통과한다");
		LocalDate week = WeeklyIngestServiceTest.THIS_WEEK;
		for (JsonNode c : cases) {
			var store = new FakeStore();
			store.manualRequest = moment(c.get("requested_at"));
			OffsetDateTime claimedAt = moment(c.get("claimed_at"));
			if (claimedAt != null) {
				store.run = WeeklyIngestServiceTest.document(week, "RUNNING", claimedAt);
			}
			assertEquals(c.get("pending").asBoolean(),
				WeeklyIngestServiceTest.service(store).run(week).manualPending(), c.get("why").asText());
		}
	}
}
