package com.ssafy.pickage.domain.docs;

import java.nio.file.Path;
import java.util.regex.Pattern;

/*
* (패키지 이름, 버전) 을 문헌 파일 경로로 바꾼다.
*
* 프리로드가 19만 개를 이 규칙으로 깔아 두었다. 한 글자라도 다르게 계산하면 있는 파일을
* 못 찾아 전부 미스가 나고, 그때마다 jsDelivr 로 다시 받는다.
*
*   <루트>/{shard}/{key}.md
*   key   = 이름의 / 를 __ 로 바꾸고 끝에 @ + 버전
*   shard = 이름에서 맨 앞 @ 를 뗀 첫 글자를 소문자로. 비면 _
*
*   express@4.21.2        e/express@4.21.2.md
*   @babel/core@7.28.4    b/@babel__core@7.28.4.md
*   lodash.get@4.4.2      l/lodash.get@4.4.2.md
*
* 이름은 소문자로 내리지 않는다. 대문자가 든 패키지가 71건 있고 리눅스는 대소문자를
* 가려서, 내리면 그 71건을 영영 못 찾는다. 소문자로 바꾸는 것은 샤드 글자 하나뿐이다.
*
* 스코프 패키지가 전체의 54% 다. / 치환을 빠뜨리면 절반이 안 열린다.
*/
public final class DocsPath {

	/*
	 * 경로에 넣어도 되는 이름·버전인지 본다.
	 *
	 * npm 이 허용하는 것보다 좁게 잡는다. 여기서 막지 않으면 이름에 .. 이나 / 가 섞였을 때
	 * 문헌 폴더 밖의 파일을 읽거나 덮어쓴다. 값은 DB 에서 오지만 그걸 믿고 통과시키지 않는다.
	 */
	private static final Pattern SAFE_NAME =
		Pattern.compile("^(?:@[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*$");
	private static final Pattern SAFE_VERSION = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9.+_-]*$");

	private DocsPath() {}

	// 이름·버전이 경로로 쓸 수 있는 모양인가.
	public static boolean valid(String name, String version) {
		return name != null && version != null
			&& SAFE_NAME.matcher(name).matches()
			&& SAFE_VERSION.matcher(version).matches();
	}

	// 파일 이름에서 확장자를 뺀 부분.
	public static String key(String name, String version) {
		return name.replace("/", "__") + "@" + version;
	}

	/*
	 * 샤드 폴더 이름.
	 *
	 * 한 글자로 나눠 34개 폴더가 된다. t/ 에 19,708개가 들어가는데, 정확한 경로로 여는
	 * 한 파일 수는 문제가 안 된다(ext4 해시 인덱스). 폴더를 훑는 쪽만 그 비용을 진다.
	 */
	public static String shard(String name) {
		String bare = name.startsWith("@") ? name.substring(1) : name;
		if (bare.isEmpty()) {
			return "_";
		}
		return bare.substring(0, 1).toLowerCase(java.util.Locale.ROOT);
	}

	// 문헌 파일의 전체 경로. 이름·버전이 형식에 안 맞으면 막는다.
	public static Path resolve(Path root, String name, String version) {
		if (!valid(name, version)) {
			throw new IllegalArgumentException("문헌 경로로 쓸 수 없는 이름·버전: " + name + "@" + version);
		}
		return root.resolve(shard(name)).resolve(key(name, version) + ".md");
	}
}
