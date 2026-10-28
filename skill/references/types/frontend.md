# Type: frontend

A user interface: SPA, SSR/SSG site, micro-frontend, mobile or desktop app. Blueprint: `python <skill-dir>/scripts/new_doc.py --print frontend`.

Part I is the product view (who uses it, journeys, screens in business terms). Part II is for the engineer: routes, state, APIs consumed, design system, configuration, build and hosting.

## Reading plan

| Area | Where to look | What to extract |
| --- | --- | --- |
| Routes and screens | Router config (React Router, Angular routes, Vue Router, TanStack), file-based routing (`app/`, `pages/`, `src/routes/`), guards, layouts | Every route: screen, purpose, access rule, data loaded |
| Journeys | Screens chained by navigation, forms, wizards, e2e tests (best description of real journeys) | Step-by-step journeys per audience |
| State and data | Stores (Redux, Zustand, Pinia, NgRx, signals), query libraries (React Query, SWR, Apollo), caching, SSR/SSG data functions | Where state lives, how data is fetched, cached and revalidated |
| Backend APIs | API clients, generated SDKs, base URLs per environment, interceptors (auth, retry, errors) | Every backend called and how errors reach the user |
| UI system | Component library, theme/tokens, CSS approach, i18n setup, accessibility tooling | How UI is built, which languages, accessibility state |
| Configuration | `.env*` with public prefixes (`VITE_`, `NEXT_PUBLIC_`, `REACT_APP_`), `environment*.ts`, runtime config endpoints, feature flags | Every value per environment and who provides it; what must never be in the bundle |
| Security | Auth flow (OIDC, redirects), token storage, guards, CSP/headers, secrets that leaked into the bundle (scan) | How users authenticate, what is protected |
| Observability | Error tracking (Sentry...), analytics events, performance monitoring | How to find a user's problem |
| Build, test, run | `package.json` scripts, bundler config, unit/component/e2e tests (Vitest, Jest, Testing Library, Playwright, Cypress) | Exact commands, labelled run/copied/derived |
| Delivery | Pipelines, hosting (S3+CloudFront, Vercel, Netlify, App Service, app stores), cache invalidation | How a release reaches users and how to roll back |

## Watch for

- **Public by construction.** Anything in the bundle is public. Values with public prefixes must not be secrets; if the scan found one, it goes to `security` and `risks`.
- **Screens are the vocabulary of support teams.** Name screens the way users see them, with the route next to them.

## Gate notes

Coverage requires:

- screens → `routes-screens`;
- environments and env vars → `configuration`;
- config keys, routes (API routes inside the app), pipelines, local containers, test suites and plaintext-credential files.
