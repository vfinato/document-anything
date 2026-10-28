# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-23

### Added

- **`document-anything` skill.** Classifies what is being documented, then runs the process for that type:
  - code types: `service`, `monolith`, `library`, `frontend`, `monorepo`, `infra`;
  - subject types: `process`, `product`.
- **Blueprints as data** (`skill/blueprints/*.json`): a shared section catalog plus one blueprint per type, in pt-BR and en, with per-section gates, home sections for coverage and cross-checks.
- **Type guides** (`skill/references/types/*.md`): sources of truth, reading plan and pitfalls per type. Common guides for classification, discovery, dialect, writing, verification and updates.
- **`scan_repo.py`**: suggests the type and the architectural style (MVC, vertical slice, layered/clean, hexagonal, modular) with evidence, and inventories the facts to cover:
  - infrastructure: IaC resources and parameters;
  - configuration: environments, env vars, config keys including `Web.config` appSettings and connection strings, SSM/Secrets Manager references;
  - code: HTTP routes (incl. conventional MVC, Rails, Django, Laravel, file-based API routes), screens (SPA routes, Next/Nuxt/SvelteKit pages, Razor Pages, Blazor), controllers;
  - schedules: external and in-process (Hangfire, Quartz, Spring, node-cron, Celery beat, hosted services, timer triggers);
  - packages and deployables, pipelines, local containers, test suites, plaintext credentials (values never printed).
- **`new_doc.py`**: lists types, prints blueprints and writes document skeletons with `«…»` placeholders.
- **`validate_wiki.py`**: front matter, structure, content, complete tables, cross-checks (e.g. roles × RACI), sources cited, placeholders (also inside code blocks), secrets, anchors, Mermaid, tables, file references, coverage by home section and HTML sync.
- **`render_wiki.py`**: deterministic single-file HTML with sidebar, search, overview/detail filter labelled per type, collapsible blocks, cards, tags, callouts, Mermaid, dark mode, copy buttons and print styles.
- **`document-anything` CLI**: `install`, `uninstall`, `where`, `doctor`, `types`, `blueprint`, `new`, `scan`, `validate`, `render`.
- **Fixtures and tests** for every code type and for processes, including a complete service document and a complete process document.
