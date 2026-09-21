package com.ssafy.pickage.domain.features;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.ssafy.pickage.domain.features.dto.PackageEnvResponse;

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
}
