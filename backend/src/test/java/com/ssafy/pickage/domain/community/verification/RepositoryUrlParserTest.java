package com.ssafy.pickage.domain.community.verification;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class RepositoryUrlParserTest {

	@Test
	void https_URL을_owner_repo로_분리한다() {
		CandidateSource result = RepositoryUrlParser.parse("https://github.com/pinojs/pino", null);
		assertThat(result).isInstanceOf(CandidateSource.GitHubUrl.class);
		CandidateSource.GitHubUrl url = (CandidateSource.GitHubUrl) result;
		assertThat(url.owner()).isEqualTo("pinojs");
		assertThat(url.repo()).isEqualTo("pino");
		assertThat(url.directory()).isNull();
	}

	@Test
	void 끝의_dot_git을_제거한다() {
		CandidateSource result = RepositoryUrlParser.parse("https://github.com/pinojs/pino.git", null);
		assertThat(((CandidateSource.GitHubUrl) result).repo()).isEqualTo("pino");
	}

	@Test
	void git_plus_https_접두사를_처리한다() {
		CandidateSource result = RepositoryUrlParser.parse("git+https://github.com/pinojs/pino.git", null);
		assertThat(result).isInstanceOf(CandidateSource.GitHubUrl.class);
	}

	@Test
	void scp_스타일_SSH_주소를_처리한다() {
		CandidateSource result = RepositoryUrlParser.parse("git@github.com:pinojs/pino.git", null);
		assertThat(result).isInstanceOf(CandidateSource.GitHubUrl.class);
		CandidateSource.GitHubUrl url = (CandidateSource.GitHubUrl) result;
		assertThat(url.owner()).isEqualTo("pinojs");
		assertThat(url.repo()).isEqualTo("pino");
	}

	@Test
	void directory를_그대로_전달한다() {
		CandidateSource result = RepositoryUrlParser.parse("https://github.com/facebook/react", "packages/react");
		assertThat(((CandidateSource.GitHubUrl) result).directory()).isEqualTo("packages/react");
	}

	@Test
	void null_이나_공백은_Absent다() {
		assertThat(RepositoryUrlParser.parse(null, null)).isInstanceOf(CandidateSource.Absent.class);
		assertThat(RepositoryUrlParser.parse("  ", null)).isInstanceOf(CandidateSource.Absent.class);
	}

	@Test
	void GitHub가_아닌_host는_NonGitHubHost다() {
		CandidateSource result = RepositoryUrlParser.parse("https://gitlab.com/foo/bar", null);
		assertThat(result).isInstanceOf(CandidateSource.NonGitHubHost.class);
	}

	@Test
	void 서브도메인은_거부한다() {
		// github.com 서브도메인(예: raw.githubusercontent.com 흉내)도 정확히 일치해야 한다.
		CandidateSource result = RepositoryUrlParser.parse("https://evil.github.com/foo/bar", null);
		assertThat(result).isInstanceOf(CandidateSource.NonGitHubHost.class);
	}

	@Test
	void IP_리터럴_host는_거부한다() {
		CandidateSource result = RepositoryUrlParser.parse("http://169.254.169.254/foo/bar", null);
		assertThat(result).isInstanceOf(CandidateSource.NonGitHubHost.class);
	}

	@Test
	void 명시적_포트는_거부한다() {
		CandidateSource result = RepositoryUrlParser.parse("https://github.com:8443/foo/bar", null);
		assertThat(result).isInstanceOf(CandidateSource.NonGitHubHost.class);
	}

	@Test
	void 경로_탈출_세그먼트는_Absent다() {
		CandidateSource result = RepositoryUrlParser.parse("https://github.com/../etc", null);
		assertThat(result).isInstanceOf(CandidateSource.Absent.class);
	}

	@Test
	void 세그먼트가_하나뿐이면_Absent다() {
		CandidateSource result = RepositoryUrlParser.parse("https://github.com/onlyowner", null);
		assertThat(result).isInstanceOf(CandidateSource.Absent.class);
	}

	@Test
	void 대소문자만_다른_host는_허용한다() {
		CandidateSource result = RepositoryUrlParser.parse("https://GitHub.com/pinojs/pino", null);
		assertThat(result).isInstanceOf(CandidateSource.GitHubUrl.class);
	}
}
