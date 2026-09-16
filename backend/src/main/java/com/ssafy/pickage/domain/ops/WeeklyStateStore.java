package com.ssafy.pickage.domain.ops;

import java.io.IOException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Response;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * 주간 수집 회차의 상태를 MinIO 에서 읽는다.
 *
 * <pre>
 * pickage-raw/_ops/weekly/&lt;week_of&gt;/run.json             수집 러너가 쓴다. 여기서는 읽기만
 * pickage-raw/_ops/weekly/&lt;week_of&gt;/manual-request.json  여기서 쓴다 (우편함)
 * </pre>
 *
 * <p><b>{@code run.json} 을 쓰지 않는 것이 중요하다.</b> 그 객체의 필자는 러너 하나뿐이고,
 * 그래서 러너가 잠금 없이 읽고-고쳐-쓰기를 할 수 있다. 여기서 같이 쓰기 시작하면 그 전제가
 * 무너진다. 수동 실행 요청도 회차 객체를 만들지 않고 우편함만 남긴다 — 러너는 우편함만
 * 있어도 회차로 친다({@code pipeline/weekly/state.py} 의 {@code load}).
 *
 * <h2>왜 MinIO 인가</h2>
 *
 * 수집은 {@code data} 노드에서 돌고 이 서비스는 {@code app} 노드에 있다. 그쪽에서 이쪽
 * PostgreSQL 에 닿을 수 없다 — 운영 compose 의 postgres 에는 {@code ports:} 가 없고 api 는
 * 루프백에만 묶여 있으며 둘 다 의도된 결정이다. MinIO 는 양쪽에서 이미 닿는다.
 *
 * <h2>자격증명이 없어도 애플리케이션은 뜬다</h2>
 *
 * 클라이언트를 <b>첫 호출 때</b> 만든다. 시작할 때 만들면 MinIO 설정이 없는 로컬 개발
 * 환경에서 애플리케이션이 아예 뜨지 않는데, 백엔드만 띄우는 팀원에게 MinIO 를 요구할
 * 이유가 없다. 설정이 비어 있으면 그 시점에 무엇이 없는지 말해 준다.
 */
@Slf4j
@Component
public class WeeklyStateStore {

	static final String PREFIX = "_ops/weekly";

	/**
	 * 상태 객체 전용 매퍼.
	 *
	 * <p><b>주입받지 않는다.</b> 이 저장소가 읽는 것은 수집기가 쓴 파일이라 표기 규약이
	 * 이 서비스의 응답 규약과 무관하다(응답은 {@code application.yaml} 의 전역 snake_case 가
	 * 맡는다 — 그쪽은 Jackson 3 이다). 그리고 주입하면 하나뿐인 Jackson 2 {@code ObjectMapper}
	 * 빈인 {@code communityObjectMapper} 가 들어오는데, 그건 community 도메인이 자기 필요에
	 * 맞춰 만든 것이라 그쪽 설정이 바뀌면 여기 파싱이 같이 바뀐다.
	 *
	 * <p>같은 이유로 {@code GitHubIssueCommentsClient} 도 자기 매퍼를 들고 있다.
	 */
	private static final ObjectMapper JSON = new ObjectMapper()
		.findAndRegisterModules()
		.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
		.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
		// 수집기가 상태 객체에 필드를 더해도 이쪽이 깨지지 않게 한다. 인계 채널이 아니라
		// 사람이 보는 창이므로, 모르는 필드는 무시하는 쪽이 맞다.
		.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

	private final String bucket;
	private final String endpoint;
	private final String accessKey;
	private final String secretKey;

	/** 첫 호출 때 만들어 들고 있는다. {@code volatile} 은 double-checked locking 때문이다. */
	private volatile S3Client client;

	public WeeklyStateStore(
		@Value("${pickage.ops.s3.bucket:pickage-raw}") String bucket,
		@Value("${pickage.ops.s3.endpoint:}") String endpoint,
		@Value("${pickage.ops.s3.access-key:}") String accessKey,
		@Value("${pickage.ops.s3.secret-key:}") String secretKey
	) {
		this.bucket = bucket;
		this.endpoint = endpoint;
		this.accessKey = accessKey;
		this.secretKey = secretKey;
	}

	static String runKey(LocalDate weekOf) {
		return PREFIX + "/" + weekOf + "/run.json";
	}

	static String manualKey(LocalDate weekOf) {
		return PREFIX + "/" + weekOf + "/manual-request.json";
	}

	/** 저장된 회차. 없으면 비어 있다 — 아직 한 번도 돌지 않은 주다. */
	public Optional<WeeklyRunDocument> readRun(LocalDate weekOf) {
		return readJson(runKey(weekOf), WeeklyRunDocument.class);
	}

	/** 대기 중인 수동 실행 요청 시각. 우편함은 회차 객체와 별개다. */
	public Optional<OffsetDateTime> readManualRequest(LocalDate weekOf) {
		return readJson(manualKey(weekOf), ManualRequest.class)
			.map(ManualRequest::requestedAt);
	}

	/**
	 * 우편함에 요청을 남긴다. <b>멱등이다</b> — 같은 내용을 덮어써도 결과가 같다.
	 *
	 * <p>이미 대기 중인 요청이 있어도 덮어쓴다. 시각이 뒤로 가지 않으므로 러너의 판정
	 * ({@code manual_claimed_at < manual_request_at} 이면 대기 중)이 그대로 성립한다.
	 */
	public void writeManualRequest(LocalDate weekOf, OffsetDateTime requestedAt) {
		byte[] body = write(new ManualRequest(requestedAt));
		// ⚠ client() 를 try 밖에서 부른다. 설정이 비었을 때 build() 가 던지는
		//    "무엇이 없는지" 예외를 아래 catch (RuntimeException) 이 삼켜서
		//    "저장소에 접근할 수 없습니다" 로 바꿔 버리면 운영자가 원인을 못 찾는다.
		S3Client s3 = client();
		try {
			s3.putObject(
				PutObjectRequest.builder()
					.bucket(bucket)
					.key(manualKey(weekOf))
					.contentType("application/json; charset=utf-8")
					.build(),
				RequestBody.fromBytes(body));
		} catch (RuntimeException error) {
			throw storageFailure(error);
		}
	}

	/** 저장된 회차 날짜. 최신순. */
	public List<LocalDate> weeks() {
		List<LocalDate> found = new ArrayList<>();
		String token = null;
		S3Client s3 = client();   // try 밖에서 — 위 writeManualRequest 의 주석 참고
		try {
			do {
				ListObjectsV2Response page = s3.listObjectsV2(
					ListObjectsV2Request.builder()
						.bucket(bucket)
						.prefix(PREFIX + "/")
						.delimiter("/")
						.continuationToken(token)
						.build());
				for (var item : page.commonPrefixes()) {
					parseWeek(item.prefix()).ifPresent(found::add);
				}
				token = Boolean.TRUE.equals(page.isTruncated()) ? page.nextContinuationToken() : null;
			} while (token != null);
		} catch (RuntimeException error) {
			throw storageFailure(error);
		}
		found.sort(Comparator.reverseOrder());
		return found;
	}

	private static Optional<LocalDate> parseWeek(String prefix) {
		String[] parts = prefix.split("/");
		try {
			// 회차 날짜가 아닌 이름이 섞여 있어도 목록 전체를 버리지 않는다.
			return Optional.of(LocalDate.parse(parts[parts.length - 1]));
		} catch (RuntimeException ignored) {
			return Optional.empty();
		}
	}

	private <T> Optional<T> readJson(String key, Class<T> type) {
		S3Client s3 = client();   // try 밖에서 — 위 writeManualRequest 의 주석 참고
		ResponseBytes<?> bytes;
		try {
			bytes = s3.getObjectAsBytes(
				GetObjectRequest.builder().bucket(bucket).key(key).build());
		} catch (NoSuchKeyException absent) {
			return Optional.empty();
		} catch (RuntimeException error) {
			throw storageFailure(error);
		}
		try {
			return Optional.of(JSON.readValue(bytes.asByteArray(), type));
		} catch (IOException malformed) {
			// 사람이 손으로 고칠 수 있는 파일이다. 어느 객체가 깨졌는지 로그에 남긴다.
			log.warn("상태 객체를 읽을 수 없다: {}", key, malformed);
			throw new BusinessException(ExceptionType.INTERNAL_ERROR,
				"상태 객체를 읽을 수 없습니다: " + key);
		}
	}

	private byte[] write(Object value) {
		try {
			return JSON.writeValueAsBytes(value);
		} catch (IOException impossible) {
			log.warn("우편함 객체를 만들 수 없다", impossible);
			throw new BusinessException(ExceptionType.INTERNAL_ERROR);
		}
	}

	/**
	 * 저장소 접근 실패.
	 *
	 * <p><b>원인을 여기서 로그에 남긴다.</b> {@code GlobalExceptionHandler} 는 예외를
	 * 응답으로만 바꾸고 로깅하지 않으므로, 넘겨 봐야 어디에도 남지 않는다. 그리고 원인에는
	 * 엔드포인트·키 같은 내부 정보가 들어 있어 응답에 실을 것도 아니다.
	 */
	private BusinessException storageFailure(RuntimeException cause) {
		log.warn("수집 상태 저장소 접근 실패: endpoint={} bucket={}", endpoint, bucket, cause);
		return new BusinessException(ExceptionType.INTERNAL_ERROR,
			"수집 상태 저장소에 접근할 수 없습니다.");
	}

	private S3Client client() {
		S3Client local = client;
		if (local == null) {
			synchronized (this) {
				local = client;
				if (local == null) {
					client = local = build();
				}
			}
		}
		return local;
	}

	private S3Client build() {
		// ⚠ 빈 문자열도 "설정 없음" 이다. 위 @Value 의 기본값이 빈 문자열이고, compose 도
		//   ${VAR:-} 로 넘겨서 **값을 안 채우면 빈 문자열이 온다** — 둘 다 "값이 없어도
		//   애플리케이션은 떠야 한다" 는 같은 결정에서 나왔다. 여기서 null 검사만 하면
		//   URI.create("") 로 넘어가 엉뚱한 곳에서 터진다.
		List<String> missing = new ArrayList<>();
		if (endpoint.isBlank()) {
			missing.add("endpoint");
		}
		if (accessKey.isBlank()) {
			missing.add("access-key");
		}
		if (secretKey.isBlank()) {
			missing.add("secret-key");
		}
		if (!missing.isEmpty()) {
			throw new BusinessException(ExceptionType.INTERNAL_ERROR,
				"수집 상태 저장소 설정이 없습니다: " + String.join(", ", missing)
					+ " (pickage.ops.s3.*)");
		}
		return S3Client.builder()
			.endpointOverride(java.net.URI.create(endpoint))
			// MinIO 는 리전을 쓰지 않지만 SDK 가 하나를 요구한다.
			.region(Region.US_EAST_1)
			.credentialsProvider(StaticCredentialsProvider.create(
				AwsBasicCredentials.create(accessKey, secretKey)))
			// path-style 이 아니면 버킷을 호스트 이름 앞에 붙여 pickage-raw.minio 로 간다.
			// MinIO 에는 그런 이름이 없다.
			.serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
			.build();
	}

	/** 우편함 객체. 수집기의 {@code state.py} 가 {@code requested_at} 하나만 읽는다. */
	record ManualRequest(OffsetDateTime requestedAt) {
	}

	/**
	 * 컨테이너가 내려갈 때 연결 풀을 닫는다.
	 *
	 * <p>프로세스가 끝나면 어차피 사라지지만, 시험이나 컨텍스트 재시작처럼 같은 JVM 안에서
	 * 빈이 여러 번 만들어지는 경우에는 닫지 않으면 풀과 스레드가 쌓인다.
	 */
	@PreDestroy
	void close() {
		S3Client local = client;
		if (local != null) {
			local.close();
		}
	}

	/** 시험이 가짜 클라이언트를 밀어 넣는 자리. 운영 경로에서는 쓰지 않는다. */
	void useClient(S3Client injected) {
		this.client = injected;
	}
}
