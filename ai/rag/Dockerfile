# rag-api — app 노드, 130(백엔드)이 호출하는 상시 HTTP 서버 (S15P21A506-178).
# ai/similarity(일회성 배치)와 달리 이 컨테이너는 계속 떠 있는다 (2026-09-18 결정).
FROM python:3.11-slim-bookworm

# 파이썬 stdout 버퍼링 방지 — ai/similarity/Dockerfile과 같은 이유(docker logs 의존).
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성을 코드보다 먼저 복사해 레이어 캐시를 활용.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ai/rag/* 파일들은 서로 `from ai.rag.X import ...` 절대 import로 참조한다(테스트도
# `python -m unittest ai.rag.test_generation`처럼 이 경로로 돈다). 빌드 컨텍스트가
# ai/rag/ 라 평평하게 COPY하면 ai 네임스페이스가 안 생겨서 import가 깨진다 — 그래서
# /app/ai/rag/ 아래에 패키지 구조를 그대로 살려서 복사한다. test_*.py는 이미지에
# 안 싣는다(ai/similarity의 "pytest는 CI에서만 설치" 관례와 같은 이유).
COPY generation.py main.py pipeline.py readme_chunker.py retrieval.py types.py verification.py ai/rag/

# non-root 사용자로 실행 (ai/similarity/Dockerfile과 같은 관례)
RUN useradd --create-home --uid 1000 appuser
USER appuser

# GMS_API_KEY 등은 여기서 하드코딩하지 않는다 — deploy/prod/app/.env를 통해
# compose environment로 주입한다(app/compose.yaml의 api 서비스와 같은 GMS_* 값 재사용).

EXPOSE 8000

CMD ["uvicorn", "ai.rag.main:app", "--host", "0.0.0.0", "--port", "8000"]
