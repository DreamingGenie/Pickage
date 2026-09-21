package com.ssafy.pickage.domain.docs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 문헌 파일 쓰기 규칙.
 *
 * <p>권한 시험은 <b>POSIX 파일시스템에서만</b> 돈다(CI·운영과 같은 리눅스). 윈도우 로컬에서는
 * 건너뛴다 — 거기서는 이 문제가 생기지 않는다.
 */
class DocStoreTest {

	@TempDir
	Path root;

	/**
	 * rag-api 가 다른 사용자(uid 1000)로 같은 폴더를 읽는다. {@code Files.createTempFile} 기본값
	 * {@code 600} 으로 남으면 캐시 미스로 받은 버전만 못 열어, 재분석이 매번
	 * "분석 서버에 연결하지 못했습니다" 로 끝났다.
	 */
	@Test
	@DisplayName("새로 쓴 문헌은 다른 사용자도 읽을 수 있다")
	void writtenDocIsWorldReadable() throws Exception {
		assumeTrue(root.getFileSystem().supportedFileAttributeViews().contains("posix"));
		DocStore store = new DocStore(root.toString());

		store.write("@babel/core", "7.28.4", "# README\n");

		Path file = root.resolve("b").resolve("@babel__core@7.28.4.md");
		assertThat(PosixFilePermissions.toString(Files.getPosixFilePermissions(file)))
			.isEqualTo("rw-r--r--");
	}

	@Test
	@DisplayName("쓴 내용을 그대로 읽는다")
	void roundTrip() throws Exception {
		DocStore store = new DocStore(root.toString());

		store.write("express", "5.1.0", "# express\n");

		assertThat(store.read("express", "5.1.0")).contains("# express\n");
		// 임시 파일이 남지 않는다
		try (var files = Files.list(root.resolve("e"))) {
			assertThat(files.map(p -> p.getFileName().toString())).containsExactly("express@5.1.0.md");
		}
	}
}
