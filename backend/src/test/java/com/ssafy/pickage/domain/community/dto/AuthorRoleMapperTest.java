package com.ssafy.pickage.domain.community.dto;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class AuthorRoleMapperTest {

	@Test
	void 이슈_작성자면_association과_무관하게_ISSUE_AUTHOR다() {
		assertThat(AuthorRoleMapper.toWireRole("CONTRIBUTOR", true)).isEqualTo("ISSUE_AUTHOR");
		assertThat(AuthorRoleMapper.toWireRole(null, true)).isEqualTo("ISSUE_AUTHOR");
	}

	@Test
	void OWNER는_REPOSITORY_OWNER로_옮긴다() {
		assertThat(AuthorRoleMapper.toWireRole("OWNER", false)).isEqualTo("REPOSITORY_OWNER");
	}

	@Test
	void MEMBER는_ORGANIZATION_MEMBER로_옮긴다() {
		assertThat(AuthorRoleMapper.toWireRole("MEMBER", false)).isEqualTo("ORGANIZATION_MEMBER");
	}

	@Test
	void COLLABORATOR와_CONTRIBUTOR는_그대로_옮긴다() {
		assertThat(AuthorRoleMapper.toWireRole("COLLABORATOR", false)).isEqualTo("COLLABORATOR");
		assertThat(AuthorRoleMapper.toWireRole("CONTRIBUTOR", false)).isEqualTo("CONTRIBUTOR");
	}

	@Test
	void 확인되지_않는_값은_추측하지_않고_null이다() {
		assertThat(AuthorRoleMapper.toWireRole("FIRST_TIME_CONTRIBUTOR", false)).isNull();
		assertThat(AuthorRoleMapper.toWireRole("NONE", false)).isNull();
		assertThat(AuthorRoleMapper.toWireRole(null, false)).isNull();
	}
}
