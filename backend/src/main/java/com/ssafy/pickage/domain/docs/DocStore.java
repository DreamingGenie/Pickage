package com.ssafy.pickage.domain.docs;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Optional;
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/*
* 문헌 파일을 읽고 쓴다. 판정도 조립도 하지 않는다.
*
* 읽는 경로가 서비스의 정상 경로다 — 19만 건이 미리 깔려 있어 대부분의 요청이 파일 하나
* 여는 것으로 끝난다.
*/
@Component
public class DocStore {

	private static final Logger log = LoggerFactory.getLogger(DocStore.class);

	/**
	 * 새로 쓴 문헌의 권한. 주인은 읽고 쓰고, 나머지는 읽기만 한다.
	 *
	 * <p>{@code rag-api} 가 <b>다른 사용자(uid 1000)</b>로 같은 폴더를 읽는다. 이 컨테이너는
	 * root 로 돌고, {@code Files.createTempFile} 은 POSIX 에서 {@code 600}(주인만 읽기)으로
	 * 만든다 — 그대로 두면 캐시 미스로 받아 쓴 버전만 rag-api 가 못 열어 {@code PermissionError}
	 * 가 나고, 사용자에게는 "분석 서버에 연결하지 못했습니다" 로만 보였다. 문헌은 공개 README 라
	 * 읽기를 열어도 된다.
	 */
	private static final Set<PosixFilePermission> READABLE = PosixFilePermissions.fromString("rw-r--r--");

	private final Path root;

	public DocStore(@Value("${pickage.docs.path:/var/lib/pickage/docs}") String root) {
		this.root = Path.of(root);
	}

	public Path root() {
		return root;
	}

	/*
	 * 문헌을 읽는다. 없으면 빈 값이다.
	 *
	 * 파일이 없는 것과 읽다가 실패한 것을 구분하지 않는다 — 둘 다 "지금 문헌이 없다" 이고,
	 * 부르는 쪽은 그때 jsDelivr 로 받아 만든다. 읽기 실패를 예외로 올리면 문헌 하나 때문에
	 * 분석 전체가 멈춘다.
	 */
	public Optional<String> read(String name, String version) {
		if (!DocsPath.valid(name, version)) {
			return Optional.empty();
		}
		Path file = DocsPath.resolve(root, name, version);
		try {
			return Optional.of(Files.readString(file, StandardCharsets.UTF_8));
		} catch (IOException e) {
			return Optional.empty();
		}
	}

	/*
	 * 문헌을 쓴다. 쓴 파일이 차지하는 디스크 크기를 돌려준다.
	 *
	 * 같은 폴더에 임시 이름으로 쓴 뒤 이름만 바꾼다. 곧바로 최종 이름에 쓰면 아직 덜 쓰인
	 * 파일을 다른 요청이 읽어 잘린 문헌이 프롬프트로 들어간다. 이름 바꾸기는 같은
	 * 파일시스템 안에서 원자적이라, 읽는 쪽에는 파일이 없거나 온전하거나 둘 중 하나다.
	 *
	 * 줄 끝은 LF 로 고정한다. 프리로드가 만든 19만 건과 같아야 한다.
	 */
	public long write(String name, String version, String document) throws IOException {
		Path file = DocsPath.resolve(root, name, version);
		Files.createDirectories(file.getParent());

		Path temp = Files.createTempFile(file.getParent(), ".tmp-", ".md");
		try {
			Files.writeString(temp, document, StandardCharsets.UTF_8);
			makeReadable(temp);
			Files.move(temp, file, StandardCopyOption.REPLACE_EXISTING,
				StandardCopyOption.ATOMIC_MOVE);
		} catch (IOException e) {
			Files.deleteIfExists(temp);
			throw e;
		}
		return allocated(document.getBytes(StandardCharsets.UTF_8).length);
	}

	/*
	 * 다른 사용자도 읽게 한다. 이름을 바꾸기 전에 해야 한다 — 바꾼 뒤에 하면 그 사이에 읽는
	 * 쪽이 권한 없는 파일을 만난다.
	 *
	 * POSIX 권한이 없는 파일시스템(윈도우 로컬 개발)에서는 건너뛴다. 거기서는 권한 문제가
	 * 생기지 않고, 호출하면 예외가 난다.
	 */
	private static void makeReadable(Path file) throws IOException {
		if (file.getFileSystem().supportedFileAttributeViews().contains("posix")) {
			Files.setPosixFilePermissions(file, READABLE);
		}
	}

	/*
	 * 겉보기 크기를 블록 단위로 올린다.
	 *
	 * 자바가 st_blocks 를 안 내주어 실제 할당량을 못 읽는다. 문서 평균이 5,081 B 라 대부분
	 * 4 KiB 블록 두 개를 차지하고, 이 계산이 지금 코퍼스에서 du 와 맞는다. 겉보기 크기로
	 * 세면 실제 디스크 사용을 40% 과소평가한다.
	 */
	public static long allocated(long size) {
		long block = DocsProperties.BLOCK_SIZE;
		return (size + block - 1) / block * block;
	}

	/*
	 * 문헌 하나를 지운다. 지운 만큼의 디스크 크기를 돌려주고, 없던 파일이면 0 이다.
	 *
	 * 지우기 전에 크기를 먼저 읽는다. 지운 뒤에는 읽을 수 없어 누적에서 뺄 값을 모른다.
	 */
	public long delete(Path file) {
		try {
			long size = Files.size(file);
			if (Files.deleteIfExists(file)) {
				return allocated(size);
			}
		} catch (IOException e) {
			log.debug("문헌을 지우지 못했다: {}", file, e);
		}
		return 0L;
	}
}
