package com.ssafy.pickage.domain.features;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.ssafy.pickage.domain.features.dto.FeatureVersionsResponse;
import com.ssafy.pickage.domain.features.dto.PackageEnvResponse;
import com.ssafy.pickage.domain.packages.PackageNames;

import lombok.RequiredArgsConstructor;

/**
 * 버전별 소비 조건 조회 (기능-11-R01).
 *
 * <p>계산이 없다. {@code package_env} 는 배치가 미리 접어 둔 표이고 여기서는 키 조회만 한다 —
 * 판정({@code module_format} 등)은 적재기가 끝냈다. 요청 경로에 판정을 두면 규칙을 고칠 때마다
 * 과거 응답과 지금 응답이 달라지는데, 그 차이를 표에서 구분할 방법이 없다.
 */
@Service
@RequiredArgsConstructor
public class PackageEnvService {

	/**
	 * 드롭다운에 올리는 버전 수.
	 *
	 * <p>3 인 이유는 화면이다 — 스크롤 없이 한눈에 고를 수 있는 만큼만 둔다(기획 협의). 문헌
	 * 프리로드가 패키지당 최신 정식 2개라, 3번째를 고르면 첫 AI 비교에서 README 를 jsDelivr 로
	 * 받느라 몇 초 더 걸린다. 그 뒤로는 캐시에 남는다.
	 */
	static final int RECENT_VERSIONS = 3;

	private final PackageEnvRepository repository;

	/**
	 * 요청한 순서대로 돌려준다. 없는 것은 {@code notFound} 로 간다.
	 *
	 * <p><b>순서를 다시 맞추는 이유</b> — DB 가 돌려주는 순서는 조인 계획이 정한다. 그대로
	 * 내보내면 프롬프트·화면에서 패키지 순서가 요청과 달라지고, 비교 문장이 엉뚱한 쪽을
	 * 가리킨다.
	 */
	@Transactional(readOnly = true)
	public PackageEnvResponse getEnv(PackageRefs refs) {
		Map<String, PackageEnvRepository.Row> found = new LinkedHashMap<>();
		for (PackageEnvRepository.Row row : repository.findAll(refs.names(), refs.versions())) {
			found.put(row.name() + "@" + row.version(), row);
		}

		List<PackageEnvResponse.Item> items = new ArrayList<>();
		List<String> notFound = new ArrayList<>();
		for (PackageRefs.Ref ref : refs.values()) {
			PackageEnvRepository.Row row = found.get(ref.key());
			if (row == null) {
				notFound.add(ref.key());
				continue;
			}
			items.add(new PackageEnvResponse.Item(
				row.name(), row.version(), row.moduleFormat(), row.typesBundled(),
				row.directDependencies(), row.peerDependencies()));
		}
		return new PackageEnvResponse(items, notFound);
	}

	/**
	 * 패키지마다 고를 수 있는 최근 버전 (기능-10-R02).
	 *
	 * <p>이름이 {@code package} 에 없으면 {@code notFound}, 있는데 고를 버전이 없으면 빈 목록으로
	 * {@code packages} 에 남긴다. 둘을 합치면 화면이 "없는 패키지" 와 "비교할 버전이 아직 없는
	 * 패키지" 를 구분하지 못한다 — 앞은 이름을 고치면 되고 뒤는 기다려야 한다.
	 */
	@Transactional(readOnly = true)
	public FeatureVersionsResponse getVersions(PackageNames names) {
		Map<String, List<String>> versions = new LinkedHashMap<>();
		List<String> notFound = new ArrayList<>();

		for (PackageEnvRepository.VersionRow row
			: repository.findRecentVersions(names.values(), RECENT_VERSIONS)) {
			if (!row.known()) {
				notFound.add(row.name());
				continue;
			}
			List<String> list = versions.computeIfAbsent(row.name(), k -> new ArrayList<>());
			if (row.version() != null) {
				list.add(row.version());
			}
		}

		// 저장소가 요청 순서로 주지만 여기서 다시 맞춘다 — 순서는 이 계층의 약속이다.
		List<FeatureVersionsResponse.Item> packages = new ArrayList<>();
		for (String name : names.values()) {
			List<String> list = versions.get(name);
			if (list == null) {
				continue;
			}
			packages.add(new FeatureVersionsResponse.Item(
				name, list.isEmpty() ? null : list.get(0), List.copyOf(list)));
		}
		return new FeatureVersionsResponse(packages, notFound);
	}
}
