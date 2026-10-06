# ── 1단계: 빌드 ────────────────────────────────────────────────
# JDK 와 Gradle 이 필요하다. 이 이미지는 최종 결과물에 들어가지 않는다.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /app

# 의존성을 먼저 받아 레이어로 굳힌다.
# 소스만 고쳤을 때 이 레이어가 캐시에서 재사용되어 재빌드가 빨라진다.
# (build.gradle 이 바뀌면 그때만 다시 받는다)
COPY gradlew ./
COPY gradle gradle
COPY build.gradle settings.gradle ./
RUN chmod +x gradlew && ./gradlew dependencies --no-daemon

COPY src src
# 테스트는 빌드에서 제외한다 — 테스트는 CI 가 별도로 돌린다.
# 여기서 돌리면 이미지 빌드에 DB 가 필요해진다.
RUN ./gradlew bootJar --no-daemon -x test

# ── 2단계: 실행 ────────────────────────────────────────────────
# JRE 만 있으면 된다. JDK 와 Gradle 을 빼면 이미지가 1GB 넘게 줄어든다.
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/build/libs/*.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
