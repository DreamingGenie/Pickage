package com.ssafy.pickage.domain.report;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * PDF 에 더할 수 있는 구역.
 *
 * <h2>생태계는 여기 없다</h2>
 *
 * 생태계 결과는 <b>끌 수 없다</b> — 그게 없으면 보고서가 아니다(구상안 §13.4 필수 구성).
 * 목록에 넣어 두면 화면이 체크를 풀 수 있게 되고, 서버는 "생태계 빼고 만들기" 라는 있지도
 * 않은 상태를 다뤄야 한다. <b>고를 수 있는 것만 목록에 있다.</b>
 *
 * <h2>아직 만들 수 없는 구역도 목록에 있다</h2>
 *
 * 커뮤니티·기능 비교는 기능 자체가 아직 없다. 그래도 값을 받는 이유는, 화면이 세 갈래
 * 선택을 지금 붙여 두고 기능이 붙는 대로 문서만 채우면 되게 하기 위해서다.
 * 요청은 받되 <b>문서에 "아직 제공되지 않습니다" 를 적고 응답으로도 알린다</b> —
 * 조용히 빼면 사용자는 체크한 것이 사라진 이유를 알 수 없다.
 */
public enum ReportSection {

	/** 확장-03 GitHub 커뮤니티 현황. 기준 패키지 하나만 대상이다(`DEC-COMMUNITY-20260909-01`). */
	COMMUNITY("커뮤니티 분석"),

	/** 기능-10~13 기능 비교와 근거 요약. */
	FEATURES("기능 심화 분석");

	private final String label;

	ReportSection(String label) {
		this.label = label;
	}

	public String label() {
		return label;
	}

	/**
	 * 요청 값을 그대로 받지 않는다.
	 *
	 * <p>모르는 값을 무시하면 오타({@code COMUNITY})가 "안 넣었네" 로만 보인다. 형식 오류로
	 * 돌려보내야 화면이 무엇을 잘못 보냈는지 안다.
	 *
	 * <p>순서와 중복은 서버가 정한다 — 같은 구역을 두 번 보내도 문서에 두 번 나오지 않고,
	 * 보내는 순서와 무관하게 문서 구성이 같다.
	 */
	public static Set<ReportSection> parse(List<String> raw) {
		Set<ReportSection> found = new LinkedHashSet<>();
		if (raw == null) return found;

		for (String value : raw) {
			if (value == null || value.isBlank()) continue;
			try {
				found.add(ReportSection.valueOf(value.trim().toUpperCase()));
			} catch (IllegalArgumentException e) {
				throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT,
					"알 수 없는 보고서 구역입니다: " + value);
			}
		}
		return found;
	}
}
