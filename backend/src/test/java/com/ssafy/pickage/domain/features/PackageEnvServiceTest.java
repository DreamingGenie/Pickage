package com.ssafy.pickage.domain.features;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.features.PackageEnvRepository.VersionRow;
import com.ssafy.pickage.domain.features.dto.FeatureVersionsResponse;
import com.ssafy.pickage.domain.packages.PackageNames;

/**
 * 기능 비교 버전 목록 — 서비스 규칙 (기능-10-R02).
 *
 * <p>DB 없이 도는 시험이다. SQL(어느 버전을 고르는지 — {@code package_env} 존재 · UNKNOWN ·
 * 사전 배포 제외 · ordinal 정렬)은 여기서 검증할 수 없고 실제 Postgres 가 필요하다. 여기서는
 * <b>행을 응답으로 옮기는 규칙</b>만 본다: 요청 순서, {@code notFound} 와 빈 목록의 구분,
 * 기본값.
 *
 * <p>{@code PackageServiceTest} 와 같이 Mockito 없이 손으로 만든 대역을 쓴다.
 */
class PackageEnvServiceTest {

	/** 받은 행을 그대로 돌려주는 대역. 넘겨받은 limit 도 기록한다. */
	private static final class FakeRepository extends PackageEnvRepository {
		private final List<VersionRow> rows;
		private final List<Integer> limits = new ArrayList<>();

		FakeRepository(List<VersionRow> rows) {
			super(null);
			this.rows = rows;
		}

		@Override
		public List<VersionRow> findRecentVersions(List<String> names, int limit) {
			limits.add(limit);
			return rows;
		}
	}

	private static FeatureVersionsResponse versionsOf(List<VersionRow> rows, String... names) {
		return new PackageEnvService(new FakeRepository(rows)).getVersions(PackageNames.of(List.of(names)));
	}

	@Test
	@DisplayName("최신순 목록의 맨 앞이 기본값이다")
	void latestFirst() {
		FeatureVersionsResponse res = versionsOf(List.of(
			new VersionRow("express", true, "5.2.1"),
			new VersionRow("express", true, "5.2.0"),
			new VersionRow("express", true, "5.1.0")), "express");

		assertThat(res.packages()).hasSize(1);
		FeatureVersionsResponse.Item item = res.packages().get(0);
		assertThat(item.latestStable()).isEqualTo("5.2.1");
		assertThat(item.versions()).containsExactly("5.2.1", "5.2.0", "5.1.0");
		assertThat(res.notFound()).isEmpty();
	}

	@Test
	@DisplayName("드롭다운에 올리는 수는 3 이다")
	void asksForThree() {
		FakeRepository repo = new FakeRepository(List.of());
		new PackageEnvService(repo).getVersions(PackageNames.of(List.of("express")));

		assertThat(repo.limits).containsExactly(3);
	}

	/**
	 * 둘은 사용자가 할 일이 다르다 — 없는 이름은 고치면 되고, 고를 버전이 없는 패키지는
	 * 적재를 기다려야 한다. 합쳐 보내면 화면이 둘을 구분하지 못한다.
	 */
	@Test
	@DisplayName("없는 패키지는 notFound, 고를 버전이 없는 패키지는 빈 목록으로 남긴다")
	void unknownVersusEmpty() {
		FeatureVersionsResponse res = versionsOf(List.of(
			new VersionRow("no-such-pkg", false, null),
			new VersionRow("left-pad", true, null)), "no-such-pkg", "left-pad");

		assertThat(res.notFound()).containsExactly("no-such-pkg");
		assertThat(res.packages()).hasSize(1);
		FeatureVersionsResponse.Item item = res.packages().get(0);
		assertThat(item.packageName()).isEqualTo("left-pad");
		assertThat(item.versions()).isEmpty();
		assertThat(item.latestStable()).isNull();
	}

	@Test
	@DisplayName("요청한 순서대로 돌려준다 — 저장소가 섞어 줘도")
	void keepsRequestOrder() {
		FeatureVersionsResponse res = versionsOf(List.of(
			new VersionRow("restana", true, "6.0.1"),
			new VersionRow("express", true, "5.2.1")), "express", "restana");

		assertThat(res.packages())
			.extracting(FeatureVersionsResponse.Item::packageName)
			.containsExactly("express", "restana");
	}
}
