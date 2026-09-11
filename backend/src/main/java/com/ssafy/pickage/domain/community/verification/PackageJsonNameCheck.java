package com.ssafy.pickage.domain.community.verification;

/** 특정 경로(루트 또는 npm이 지정한 directory)의 {@code package.json} {@code name} 필드 대조 결과. */
enum PackageJsonNameCheck {
	MATCH,
	MISMATCH,
	NOT_FOUND
}
