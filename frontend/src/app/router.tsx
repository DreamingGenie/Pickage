import { Navigate, createBrowserRouter } from 'react-router'

import { AppLayout } from '@/app/app-layout'
import { paths } from '@/app/routes'
import { ServiceIntroPage } from '@/routes/intro/service-intro-page'

/**
 * intro 만 eager. 랜딩에서 청크를 한 번 더 왕복하면 첫 페인트가 늦는다.
 * 나머지는 라우트 단위 `lazy` — React.lazy 와 달리 라우터가 전환을 붙잡아 주므로
 * Suspense 폴백이 깜빡이지 않는다. 대기 표시는 AppLayout 의 useNavigation 이 담당.
 */
export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <ServiceIntroPage /> },
      {
        path: 'analyze',
        lazy: async () => {
          const { AnalyzePage } = await import('@/routes/analyze/analyze-page')
          return { Component: AnalyzePage }
        },
      },
      // 01·02 를 한 화면으로 합쳤다. 예전 경로로 들어오면 되돌려 보낸다.
      { path: 'analyze/candidates', element: <Navigate to={paths.analyze()} replace /> },
      {
        path: 'report/:reportId',
        lazy: async () => {
          const { ReportPage } = await import('@/routes/report/report-page')
          return { Component: ReportPage }
        },
      },
      { path: '*', element: <ServiceIntroPage /> },
    ],
  },
])
