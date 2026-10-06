package com.ssafy.pickage.domain.docs;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/*
* 패키지 문헌 한 장을 만든다. 네트워크도 파일시스템도 모른다.
*
* 같은 문헌을 파이썬 프리로드(RAG_docs/preload_docs.py)가 19만 건 만들어 두었고,
* 여기서 만든 것과 글자 하나까지 같아야 한다. 서식이 갈리면 LLM 이 보는 입력이
* 패키지마다 달라져 비교 결과가 흔들린다.
*
* 그래서 파이썬을 그대로 옮겼다. 더 자바다운 방식이 있어도 쓰지 않는다. 아래 넷은
* 언어 차이가 에러 없이 값만 바꾸는 자리라 일부러 어색하게 적혀 있다.
*
*   1. \s        파이썬은 유니코드 공백(NBSP 등)을 잡고 자바 기본은 ASCII 만 잡는다
*   2. 글자수     파이썬 len() 은 코드포인트, 자바 length() 는 UTF-16 코드 유닛이다
*   3. strip()   자바 trim() 은 U+0020 이하만 없앤다
*   4. lstrip    파이썬 인자는 접두사가 아니라 문자 집합이다
*
* 실측으로 1 을 틀리면 eslint-plugin-import@2.32.0 이 92자 어긋나고, 2 를 틀리면
* 이모지 든 README 가 어긋난다.
*/
public final class DocAssembler {

	// README·.d.ts 본문 상한. 글자가 아니라 바이트다.
	public static final int MAX_README_BYTES = 32 * 1024;

	// 이만큼 넘는 산문이 있으면 문헌이 쓸 만하다고 본다.
	public static final int STUB_PROSE = 1000;

	// 문서에 적는 진입점 개수 상한. 넘으면 "외 N개" 로 줄인다.
	public static final int MAX_SUBPATHS = 30;

	// 소비 형태를 사람이 읽는 말로 바꾼다. 화면과 프롬프트가 같은 표현을 쓰게 하려는 것이다.
	private static final String KIND_CSS = "스타일시트로 소비 (CSS import)";
	private static final String KIND_CLI = "명령줄 도구";
	private static final String KIND_LIB = "라이브러리 (진입점 다수)";
	private static final String KIND_TYPES = "라이브러리 (타입 선언 제공)";
	private static final String KIND_BARE = "라이브러리";

	/*
	 * 파이썬 prose() 의 정규식 일곱을 순서 그대로 옮긴 것. 순서를 바꾸면 글자수가 달라지고,
	 * 그 값이 STUB_PROSE 경계를 넘나든다 — 실측으로 1,004자(OK)와 998자(LIMITED) 사이다.
	 *
	 * UNICODE_CHARACTER_CLASS 가 위 1 이다. 빼면 \s 가 NBSP 를 안 잡는다.
	 */
	private static final int U = Pattern.UNICODE_CHARACTER_CLASS;
	private static final Pattern FENCE = Pattern.compile("```.*?```", Pattern.DOTALL);
	private static final Pattern TAG = Pattern.compile("<[^>]+>");
	private static final Pattern IMAGE = Pattern.compile("!\\[[^\\]]*\\]\\([^)]*\\)");
	private static final Pattern LINK = Pattern.compile("\\[([^\\]]*)\\]\\([^)]*\\)");
	private static final Pattern RULE = Pattern.compile("^\\s*[-=*_]{3,}\\s*$", Pattern.MULTILINE | U);
	private static final Pattern HEADING = Pattern.compile("^#+\\s*", Pattern.MULTILINE | U);
	private static final Pattern SPACES = Pattern.compile("\\s+", U);

	// 파이썬 lstrip("./")·lstrip("/")·lstrip("@") 용.
	private static final Pattern LEAD_DOT_SLASH = Pattern.compile("^[./]+");

	private DocAssembler() {}

	/*
	 * jsDelivr 파일 목록에서 뽑은 것. count·unpackedBytes 는 목록의 합이다.
	 * readmePath 는 루트에 있는 README, 없으면 null. dts 는 정렬해 최대 20개다.
	 */
	public record Tree(int count, long unpackedBytes, String readmePath, List<String> dts) {}

	/*
	 * package.json 에서 뽑아 정규화한 것. 원문은 형식이 제각각이라 여기서 편다 — bin 이
	 * 문자열일 때가 있고, keywords 가 쉼표 문자열일 때가 있고(lodash), license 가
	 * {"type":"MIT"} 옛 형식일 때가 있다. 읽는 쪽이 매번 그 분기를 하지 않게 하려는 것이다.
	 *
	 * type 이 null 이면 문서에 "commonjs (기본값)" 으로 적는다. main 은 존재 여부만 쓴다.
	 * subpathCount 는 줄이기 전의 실제 개수고 subpaths 는 최대 30개다.
	 */
	public record Manifest(
			String description,
			List<String> keywords,
			String license,
			String type,
			boolean main,
			String style,
			List<String> bin,
			int subpathCount,
			List<String> subpaths,
			int dependencies) {}

	/*
	 * 어느 근거를 주근거로 쓸지 정한다. 판정 순서가 곧 프롬프트의 해석 규칙이다.
	 *
	 *   1. CSS    스타일시트로 소비되는 패키지
	 *   2. CLI    bin 이 있는 명령줄 도구
	 *   3. LIB    subpath 가 셋 이상이라 이름 자체가 기능 영역인 것
	 *   4. TYPES  .d.ts 가 실제 API 표면인 것
	 *   5. BARE   아무것도 없어 description 한 줄뿐인 것
	 *
	 * CSS 를 맨 앞에 두는 것이 이 순서의 핵심이다. .d.ts 부터 보면 tailwindcss 를
	 * 라이브러리로 잘못 읽는다 — 그 .d.ts 는 compile()·compileAst() 뿐인데 실제 사용은
	 * CSS 다. 표본의 12.5% 가 이 함정에 걸렸다.
	 *
	 * filesField 와 hasStyleInExports 는 CSS 판정에만 쓴다.
	 */
	public static String entryKind(Manifest manifest, Tree tree, List<String> filesField,
			boolean hasStyleInExports) {
		boolean css = manifest.style() != null || hasStyleInExports;
		if (!css && filesField != null) {
			for (String f : filesField) {
				if (f != null && (f.endsWith(".css") || f.endsWith(".scss"))) {
					css = true;
					break;
				}
			}
		}
		if (css) return "CSS";
		if (!manifest.bin().isEmpty()) return "CLI";
		if (manifest.subpathCount() >= 3) return "LIB";
		if (!tree.dts().isEmpty()) return "TYPES";
		return "BARE";
	}

	// 문헌이 서술에 쓸 만한지 표시한다. 화면의 dataStatus 가 이 값을 그대로 쓴다.
	public static String docStatus(int proseChars, Manifest manifest, Tree tree) {
		if (proseChars >= STUB_PROSE) return "OK";
		if (manifest.subpathCount() >= 3 || !manifest.bin().isEmpty() || !tree.dts().isEmpty()) {
			return "LIMITED";
		}
		if (!manifest.description().isEmpty()) return "LIMITED";
		return "NONE";
	}

	/*
	 * 산문만 남긴다. 글자수를 세려고만 돌리고 결과는 문서에 들어가지 않는다.
	 * 배지와 코드블록만 가득한 README 가 OK 로 올라가는 것을 막는다.
	 */
	public static String prose(String markdown) {
		String t = FENCE.matcher(markdown).replaceAll("");
		t = TAG.matcher(t).replaceAll("");
		t = IMAGE.matcher(t).replaceAll("");
		t = LINK.matcher(t).replaceAll("$1");
		t = RULE.matcher(t).replaceAll("");
		t = HEADING.matcher(t).replaceAll("");
		return SPACES.matcher(t).replaceAll(" ").strip();
	}

	// 파이썬 len() 과 같게 센다. 코드포인트라 이모지가 1자다.
	public static int charCount(String s) {
		return s.codePointCount(0, s.length());
	}

	/*
	 * 본문을 바이트로 자른다. 글자로 자르면 파이썬과 결과가 달라진다 — 저쪽은
	 * raw[:32768] 로 바이트를 자른 뒤 디코딩한다. 잘린 자리에 깨진 UTF-8 이 남으면
	 * 양쪽 다 U+FFFD 가 된다.
	 */
	public static String clip(byte[] raw) {
		int n = Math.min(raw.length, MAX_README_BYTES);
		return new String(raw, 0, n, StandardCharsets.UTF_8);
	}

	// 파이썬 lstrip("./") 과 같다. 접두사가 아니라 문자 집합이라 "..//x" 가 "x" 가 된다.
	public static String lstripDotSlash(String s) {
		return LEAD_DOT_SLASH.matcher(s).replaceFirst("");
	}

	/*
	 * 참조 문헌 한 장. README 원문 위에 소비 형태와 설치 조건을 붙인 고정 서식이다.
	 *
	 * 항목은 값이 없어도 "없음" 으로 항상 적는다. 두 패키지를 나란히 놓았을 때 줄이
	 * 어긋나 비교가 안 되는 것을 막는다.
	 *
	 * 본문은 자르지 않는다. 길이 조절은 프롬프트를 조립하는 쪽의 일이고, 문헌은 원문을
	 * 온전히 들고 있어야 나중에 자르는 기준이 바뀌어도 다시 받을 필요가 없다.
	 */
	public static String assemble(String name, String version, Manifest manifest, Tree tree,
			String body, String entryKind, String docStatus, int readmeBytes, int proseChars) {
		StringBuilder b = new StringBuilder(body.length() + 1024);

		line(b, "# " + name + "@" + version);
		line(b, "");
		line(b, manifest.description().isEmpty() ? "(설명 없음)" : manifest.description());
		line(b, "");
		line(b, "## 소비 형태 · 진입점");
		line(b, "");
		line(b, "- 형태: " + kindLabel(entryKind));
		line(b, "- 명령: " + (manifest.bin().isEmpty() ? "없음" : String.join(", ", manifest.bin())));
		line(b, "- 스타일 진입점: " + (manifest.style() == null ? "없음" : manifest.style()));

		if (!manifest.subpaths().isEmpty()) {
			int shown = manifest.subpaths().size();
			String extra = manifest.subpathCount() <= shown
					? ""
					: " 외 " + (manifest.subpathCount() - shown) + "개";
			line(b, "- 진입점 " + manifest.subpathCount() + "개: "
					+ String.join(", ", manifest.subpaths()) + extra);
		} else {
			line(b, "- 진입점: exports 선언 없음 (단일 진입점)");
		}

		line(b, "- 모듈 형식: type=" + (manifest.type() == null ? "commonjs (기본값)" : manifest.type())
				+ ", main " + (manifest.main() ? "있음" : "없음"));
		line(b, "- 타입 선언: " + (tree.dts().isEmpty()
				? "없음 (@types 별도 필요)"
				: "포함 — " + String.join(", ", tree.dts().subList(0, Math.min(5, tree.dts().size())))));
		line(b, "- 키워드: " + (manifest.keywords().isEmpty() ? "없음" : String.join(", ", manifest.keywords())));

		line(b, "");
		line(b, "## 설치 조건");
		line(b, "");
		line(b, "- 설치 크기: " + comma(tree.unpackedBytes()) + " B");
		line(b, "- 파일 수: " + tree.count());
		line(b, "- 직접 의존성: " + manifest.dependencies() + "개");
		line(b, "- 라이선스: " + (manifest.license() == null ? "미표기" : manifest.license()));
		line(b, "");
		line(b, "## README 전문");
		line(b, "");
		line(b, body.strip().isEmpty() ? "(README 없음)" : body.strip());
		line(b, "");
		line(b, "---");
		b.append("근거: S1 README ").append(comma(readmeBytes)).append(" B / 산문 ")
				.append(comma(proseChars)).append("자 · S2 manifest · S3 spec · 상태 ").append(docStatus);
		return b.toString();
	}

	private static void line(StringBuilder b, String s) {
		b.append(s).append('\n');
	}

	// 천 단위 쉼표. 로캘을 고정해 컨테이너 로캘이 바뀌어도 구분자가 안 달라지게 한다.
	private static String comma(long n) {
		return String.format(Locale.ROOT, "%,d", n);
	}

	private static String kindLabel(String kind) {
		return switch (kind) {
			case "CSS" -> KIND_CSS;
			case "CLI" -> KIND_CLI;
			case "LIB" -> KIND_LIB;
			case "TYPES" -> KIND_TYPES;
			case "BARE" -> KIND_BARE;
			default -> kind;
		};
	}
}
