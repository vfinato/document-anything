# Contributing

Thanks for helping. This project is small on purpose. Its value is in the guarantees, so every change has to keep them true.

## Invariants

1. **Zero runtime dependencies.** The Python scripts use only the standard library (3.9+), and the CLI uses only Node built-ins. If a feature needs a dependency, open an issue first.
2. **Deterministic output.** The same Markdown always renders the same HTML: no timestamps, no randomness, no environment-dependent paths.
3. **Single-file HTML.** CSS and JS stay inline. Mermaid, pinned and loaded from a CDN, is the only external asset.
4. **Secrets never leave the process.** The scanner may hold credential values in memory to compare them against the document, but it never prints or serialises them (`scan_repo.public()`).
5. **Blueprints are data.** Section ids, titles, gates, coverage home sections and cross-checks live in `skill/blueprints/`. Scripts read them, and the type guides in `skill/references/types/` explain them. A rule that exists only in code, or only in text, is a bug.
6. **Instructions and scripts agree.** `SKILL.md` and `skill/references/*` describe exactly what the scripts check, because agents follow the text.

## How the pieces fit

| File | Role |
| --- | --- |
| `skill/blueprints/common.json` | Shared section catalog: titles (pt-BR/en), what each section must contain, gates, table columns |
| `skill/blueprints/<type>.json` | A type: its sections per part (`id` required, `id?` optional), extra sections, overrides, view labels, coverage kinds and home sections, cross-checks, whether `sources` are required |
| `skill/scripts/wikilib.py` | Markdown dialect, slugs, blueprint loading, renderer core |
| `skill/scripts/new_doc.py` | Type list, blueprint printout, skeleton generator |
| `skill/scripts/scan_repo.py` | Fact inventory and type/style classification |
| `skill/scripts/validate_wiki.py` | The gate |
| `skill/scripts/render_wiki.py` | Page shell, UI i18n, `--check` |
| `skill/references/` | `classify`, `discovery`, `dialect`, `writing`, `verification`, `update`, and `types/<type>.md` |
| `bin/cli.js` | Installer and script runner |

## Adding a document type

1. Add `skill/blueprints/<type>.json`. Reuse common sections by id, and define new ones in `extra_sections`.
2. Add `skill/references/types/<type>.md` with the sources of truth, reading plan and pitfalls.
3. Add the type to the table in `skill/references/classify.md`. For a code type, also teach `scan_repo.classify()` to suggest it.
4. Add a fixture under `tests/fixtures/` and tests: classification (code types) and a complete passing document (at least for types with cross-checks).
5. Run an end-to-end test: a fresh agent documents the fixture following only the skill. Fix what it finds confusing.

## Adding support for a new stack

Add the extractor to `scan_repo.py`, add a minimal example of that stack to a fixture, and assert the extracted facts in `tests/test_wiki.py`. Keep false positives low: a noisy coverage gate teaches people to add `coverage-ignore` everywhere.

## Checks before a pull request

```bash
python -m unittest discover -s tests
node bin/cli.js doctor
npm pack --dry-run          # only bin/, the skill sources, READMEs and LICENSE are shipped
```

If you change `skill/assets/wiki.css` or `wiki.js`, re-render the sample documents (`node bin/cli.js render <doc.md>`) and refresh the screenshots in `docs/images/` if the look changed.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat(scan): detect Pulumi stacks`, `fix(render): keep pipes inside code spans`, `docs(types): clarify the monorepo workflow`.
