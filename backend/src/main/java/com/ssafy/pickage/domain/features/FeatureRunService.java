package com.ssafy.pickage.domain.features;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.pickage.domain.docs.DocsCache;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

import lombok.RequiredArgsConstructor;

/**
 * 기능 비교 run 을 띄우고 상태를 돌려준다 (기능-12·13).
 *
 * <p><b>요청 안에서 RAG 를 기다리지 않는다.</b> LLM 생성이 붙어 있어 분 단위로 갈 수 있는데,
 * nginx 가 60초에 끊는다. 시작만 해 주고 프런트가 상태를 물어보게 한다 — 기능-10-R06 의
 * "부분 완료 시 완료된 항목 먼저 표시" 도 이 모양이라야 가능하다(스펙 표는 별도 엔드포인트라
 * 먼저 뜨고, 이 결과가 나중에 붙는다).
 *
 * <p><b>RAG 를 부르기 전에 문헌을 먼저 확보한다.</b> rag-api 는 문헌 폴더를 읽기 전용으로
 * 마운트해서 없는 파일을 스스로 만들 수 없다 — 그대로 부르면 404 로 끝나고, 사용자에게는
 * "이 버전은 분석이 안 된다" 로만 보인다. 프리로드가 패키지당 최신 2개 안정 버전만 깔았으므로
 * 버전 드롭다운(기능-10-R02)에서 옛 버전을 고르면 대부분 그 경우다.
 *
 * <p>그래서 {@link DocsCache} 로 먼저 채운다. 있으면 파일 하나 여는 것으로 끝나고, 없으면
 * jsDelivr 로 받아 같은 자리에 쓴다 — rag-api 가 곧이어 읽을 그 자리다. 여기서도 못 만든
 * 것만 진짜 "없는 버전" 이다.
 */
@Service
@RequiredArgsConstructor
public class FeatureRunService {

	private static final Logger log = LoggerFactory.getLogger(FeatureRunService.class);

	/** 백엔드가 실제로 지나는 단계. 프런트의 여섯 칸과 대응하지 않는다 — Run 주석 참고. */
	private static final String PHASE_DOCS = "PREPARING_DOCS";
	private static final String PHASE_CALLING = "COMPARING";
	private static final String PHASE_DONE = "DONE";

	/**
	 * 동시에 도는 run 수를 막는다.
	 *
	 * <p>하나가 LLM 을 부르는 동안 메모리와 GMS 호출 한도를 함께 쓴다. api 컨테이너가
	 * 1.6 GB 상한이라 여러 개가 같이 붙으면 다른 요청까지 같이 느려진다. 막히면 429 로
	 * 되돌려 주는 편이 "눌렀는데 아무 일도 안 일어난다" 보다 낫다.
	 */
	private final Semaphore slots = new Semaphore(2);

	private final ExecutorService worker = Executors.newFixedThreadPool(2, runnable -> {
		Thread thread = new Thread(runnable, "feature-run");
		thread.setDaemon(true);
		return thread;
	});

	private final ObjectMapper json = new ObjectMapper();

	private final DocsCache docs;
	private final RagClient rag;
	private final FeatureRunStore store;

	/** run 을 시작하고 식별자를 돌려준다. 이 메서드는 기다리지 않는다. */
	public FeatureRunStore.Run start(PackageRefs refs) {
		if (!slots.tryAcquire()) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED);
		}
		String runId = UUID.randomUUID().toString();
		List<String> keys = refs.values().stream().map(PackageRefs.Ref::key).toList();
		FeatureRunStore.Run queued = new FeatureRunStore.Run(
			runId, FeatureRunStore.Run.RUNNING, PHASE_DOCS, keys,
			Instant.now(), null, null, null, null);
		store.put(queued);

		worker.submit(() -> {
			try {
				execute(queued, refs);
			} finally {
				slots.release();
			}
		});
		return queued;
	}

	/**
	 * 실제 호출. 실패해도 예외를 위로 던지지 않는다 — 부르는 쪽이 이미 응답을 보냈다.
	 *
	 * <p>실패를 run 에 기록해 두어야 프런트가 "왜 안 되는지" 를 볼 수 있다. 로그에만 남기면
	 * 화면에는 영원히 진행 중으로 보인다.
	 */
	private void execute(FeatureRunStore.Run run, PackageRefs refs) {
		try {
			List<String> missing = ensureDocuments(refs);
			if (!missing.isEmpty()) {
				// rag-api 를 부를 것도 없다 — 읽을 파일이 없으니 같은 404 가 돌아온다.
				fail(run, PHASE_DOCS, "DOC_NOT_FOUND", toJson(missing));
				return;
			}
			store.put(new FeatureRunStore.Run(
				run.runId(), FeatureRunStore.Run.RUNNING, PHASE_CALLING, run.refs(),
				run.startedAt(), null, null, null, null));

			String result = rag.compare(refs.values());
			store.put(new FeatureRunStore.Run(
				run.runId(), FeatureRunStore.Run.COMPLETED, PHASE_DONE, run.refs(),
				run.startedAt(), Instant.now(), result, null, null));
		} catch (RagClient.DocumentMissingException e) {
			fail(run, PHASE_CALLING, "DOC_NOT_FOUND", e.detail());
		} catch (RagClient.VerificationFailedException e) {
			fail(run, PHASE_CALLING, "VERIFICATION_FAILED", e.violations());
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			fail(run, PHASE_CALLING, "INTERRUPTED", null);
		} catch (Exception e) {
			log.warn("기능 비교 실패 {} {}", run.refs(), e.toString());
			fail(run, PHASE_CALLING, "RAG_UNAVAILABLE", null);
		}
	}

	/**
	 * 비교 대상의 문헌을 확보하고, 끝내 못 만든 것을 돌려준다.
	 *
	 * <p>한 번에 넘기는 이유는 {@link DocsCache#load(List)} 가 예산을 셋이 나눠 쓰는 것이
	 * 아니라 함께 쓰는 벽시계로 다루기 때문이다 — 하나씩 부르면 앞의 하나가 느릴 때 뒤의
	 * 것들이 각자 예산을 새로 받아 전체가 그 배로 늘어난다.
	 */
	private List<String> ensureDocuments(PackageRefs refs) {
		List<DocsCache.Ref> wanted = refs.values().stream()
			.map(ref -> new DocsCache.Ref(ref.name(), ref.version()))
			.toList();
		var loaded = docs.load(wanted);
		return refs.values().stream()
			.filter(ref -> !loaded.containsKey(new DocsCache.Ref(ref.name(), ref.version())))
			.map(PackageRefs.Ref::key)
			.toList();
	}

	/**
	 * 실패를 기록한다. <b>어느 단계에서 멈췄는지를 인자로 받는다</b> — {@code run} 이 들고 있는
	 * phase 는 시작할 때 값이라, 그걸 그대로 쓰면 RAG 호출에서 죽어도 "문헌 준비 중" 으로 남는다.
	 */
	private void fail(FeatureRunStore.Run run, String phase, String code, String detail) {
		store.put(new FeatureRunStore.Run(
			run.runId(), FeatureRunStore.Run.FAILED, phase, run.refs(),
			run.startedAt(), Instant.now(), null, code, detail));
	}

	/** 실패 사유로 싣는 목록. 응답에 원문 그대로 들어가므로 여기서 JSON 으로 만든다. */
	private String toJson(List<String> values) {
		try {
			return json.writeValueAsString(values);
		} catch (JsonProcessingException e) {
			// 문자열 목록이라 실제로 일어나지 않는다. 일어나도 실패 기록 자체는 남긴다.
			return null;
		}
	}

	/** 없는 runId 는 404 다. 재시작으로 잊었을 수도 있고, 만료됐을 수도 있다. */
	public FeatureRunStore.Run get(String runId) {
		return store.find(runId)
			.orElseThrow(() -> new BusinessException(ExceptionType.RESOURCE_NOT_FOUND));
	}
}
