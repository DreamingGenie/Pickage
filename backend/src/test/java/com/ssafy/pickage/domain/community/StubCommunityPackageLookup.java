package com.ssafy.pickage.domain.community;

import java.util.Map;
import java.util.Optional;

/** {@link StubRepositoryVerificationService}와 같은 기법 — 실제 DB 없이 이름→식별자 조회를 고정한다. */
class StubCommunityPackageLookup extends CommunityPackageLookup {

	private final Map<String, PackageIdentity> byName;

	StubCommunityPackageLookup(Map<String, PackageIdentity> byName) {
		super(null);
		this.byName = byName;
	}

	@Override
	public Optional<PackageIdentity> findByName(String name) {
		return Optional.ofNullable(byName.get(name));
	}
}
