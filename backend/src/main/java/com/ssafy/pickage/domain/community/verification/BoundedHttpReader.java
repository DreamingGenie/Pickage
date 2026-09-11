package com.ssafy.pickage.domain.community.verification;

import java.io.*;
import java.net.URI;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.Flow;

import javax.net.ssl.SSLSession;

/** 전송부터 body 완료까지 한 번의 deadline과 byte 상한을 적용한다. */
public final class BoundedHttpReader {
    private BoundedHttpReader() {}

    public static HttpResponse<InputStream> send(
            HttpClient client, HttpRequest request, long maxBytes)
            throws IOException, InterruptedException {
        var future = client.sendAsync(request, info -> new LimitedSubscriber(maxBytes));
        try {
            var response =
                    future.get(
                            request.timeout().orElse(Duration.ofSeconds(10)).toNanos(),
                            TimeUnit.NANOSECONDS);
            byte[] bytes = response.body();
            String encoding = response.headers().firstValue("Content-Encoding").orElse("identity");
            if ("gzip".equalsIgnoreCase(encoding)) {
                try (var gzip =
                        new java.util.zip.GZIPInputStream(new ByteArrayInputStream(bytes))) {
                    bytes = readBytes(gzip, maxBytes);
                }
            } else if (!"identity".equalsIgnoreCase(encoding))
                throw new IOException("Unsupported content encoding");
            return new BufferedResponse(response, new ByteArrayInputStream(bytes));
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new HttpTimeoutException("Community response deadline exceeded");
        } catch (ExecutionException e) {
            future.cancel(true);
            if (e.getCause() != null
                    && "Community response size limit".equals(e.getCause().getMessage()))
                throw new IOException("Community response size limit");
            throw new IOException("Community response failed");
        } catch (InterruptedException e) {
            future.cancel(true);
            throw e;
        }
    }

    private static final class LimitedSubscriber implements HttpResponse.BodySubscriber<byte[]> {
        private final HttpResponse.BodySubscriber<byte[]> delegate =
                HttpResponse.BodySubscribers.ofByteArray();
        private final long max;
        private long count;
        private Flow.Subscription subscription;

        LimitedSubscriber(long max) {
            this.max = max;
        }

        public CompletionStage<byte[]> getBody() {
            return delegate.getBody();
        }

        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            delegate.onSubscribe(s);
        }

        public void onNext(List<ByteBuffer> buffers) {
            for (var b : buffers) {
                count += b.remaining();
                if (count > max) {
                    subscription.cancel();
                    delegate.onError(new IOException("Community response size limit"));
                    return;
                }
            }
            delegate.onNext(buffers);
        }

        public void onError(Throwable error) {
            delegate.onError(new IOException("Community response failed"));
        }

        public void onComplete() {
            delegate.onComplete();
        }
    }

    private record BufferedResponse(HttpResponse<byte[]> response, InputStream body)
            implements HttpResponse<InputStream> {
        public int statusCode() {
            return response.statusCode();
        }

        public HttpRequest request() {
            return response.request();
        }

        public Optional<HttpResponse<InputStream>> previousResponse() {
            return Optional.empty();
        }

        public HttpHeaders headers() {
            return response.headers();
        }

        public Optional<SSLSession> sslSession() {
            return response.sslSession();
        }

        public URI uri() {
            return response.uri();
        }

        public HttpClient.Version version() {
            return response.version();
        }
    }

    private static byte[] readBytes(InputStream body, long maxBytes) throws IOException {
        var buffer = new ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        long count = 0;
        int n;
        while ((n = body.read(chunk)) != -1) {
            count += n;
            if (count > maxBytes) throw new IOException("Community response size limit");
            buffer.write(chunk, 0, n);
        }
        return buffer.toByteArray();
    }

    /** send() 이후에는 메모리에 제한된 body만 전달된다. */
    public static String readBounded(InputStream body, long maxBytes, String source) {
        try (body) {
            return new String(readBytes(body, maxBytes), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UpstreamFetchException("Community response read failed");
        }
    }
}
