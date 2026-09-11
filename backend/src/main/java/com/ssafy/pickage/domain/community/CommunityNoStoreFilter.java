package com.ssafy.pickage.domain.community;

import jakarta.servlet.*;
import jakarta.servlet.http.*;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/** 파라미터 바인딩/전역 오류 처리보다 먼저 community 응답의 캐시를 차단한다. */
@Component
public final class CommunityNoStoreFilter extends OncePerRequestFilter {
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String path = request.getRequestURI().substring(request.getContextPath().length());
        if (path.equals("/api/packages/community")
                || path.equals("/api/packages/community/refresh"))
            response.setHeader("Cache-Control", "no-store");
        chain.doFilter(request, response);
    }
}
