import js from '@eslint/js'
import betterTailwind from 'eslint-plugin-better-tailwindcss'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import prettier from 'eslint-config-prettier/flat'

/**
 * ESLint 는 "틀린 것"만 잡는다. 줄바꿈·따옴표 같은 모양은 Prettier 몫이고,
 * 맨 끝 `prettier` 설정이 겹치는 규칙을 전부 꺼서 둘이 싸우지 않게 한다.
 */
export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'docs'] },

  js.configs.recommended,
  tseslint.configs.recommended,
  // eslint-plugin-react-hooks v7 은 flat 전용 프리셋을 `configs.flat` 아래에 둔다.
  reactHooks.configs.flat['recommended-latest'],

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
    },
    plugins: { 'react-refresh': reactRefresh },
    rules: {
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // 쓰지 않는 값은 지운다. 다만 `_` 로 시작하면 의도한 것으로 본다.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' },
      ],

      // 타입은 `import type` 으로 분리한다. 번들에 런타임 import 가 남지 않는다.
      '@typescript-eslint/consistent-type-imports': [
        'warn',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],

      /*
       * 타이머로 상태를 되감는 자리(분석 진행, 인트로 카드 순환, 로딩 오버레이)에서 걸린다.
       * 파생시킬 수 있는 것은 이미 걷어냈고 남은 건 외부 시계와 맞추는 동기화라
       * 막지 않고 눈에만 띄게 둔다. 새로 걸리면 파생으로 풀 수 있는지 먼저 본다.
       */
      'react-hooks/set-state-in-effect': 'warn',
    },
  },

  /*
   * Tailwind 클래스 검사.
   *
   * 이 프로젝트는 공통 컴포넌트가 기본 클래스를 들고 있고 호출부가 `className` 으로
   * 덮어쓰는 구조라, 조합이 조용히 깨지는 자리가 세 군데 생긴다.
   *
   *   no-conflicting-classes   같은 속성을 두 번 지정해 CSS 순서에 운을 맡기는 것
   *   no-concatenated-classes  문자열을 이어 붙여 tailwind-merge 를 건너뛰는 것
   *   no-unknown-classes       오타·삭제된 유틸리티가 조용히 무시되는 것
   *
   * 덮어쓰기 자체는 막지 않는다. `cn()` 을 거치면 tailwind-merge 가 뒤엣것을 남기므로
   * 의도한 덮어쓰기는 정상이다. 문제는 `cn()` 을 건너뛴 조합이라 그쪽을 잡는다.
   *
   * 정렬·줄바꿈은 prettier-plugin-tailwindcss 가 하므로 여기서는 끈다.
   */
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { 'better-tailwindcss': betterTailwind },
    settings: {
      'better-tailwindcss': {
        entryPoint: 'src/index.css',
      },
    },
    rules: {
      ...betterTailwind.configs['correctness-error'].rules,
      'better-tailwindcss/no-duplicate-classes': 'error',
      'better-tailwindcss/enforce-consistent-class-order': 'off',
      'better-tailwindcss/enforce-consistent-line-wrapping': 'off',
    },
  },

  {
    // shadcn 원본은 손대지 않는다(CLAUDE.md). 규칙으로도 건드리지 않게 둔다.
    files: ['src/components/ui/**'],
    rules: {
      'react-refresh/only-export-components': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      'better-tailwindcss/no-conflicting-classes': 'off',
    },
  },

  prettier,
)
