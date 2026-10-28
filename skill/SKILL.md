---
name: document-anything
description: Documents anything as a pair of files with the same content - a Markdown document for AI agents (source of truth) and a self-contained HTML page for humans that opens in any browser. Detects what is being documented and adapts the process - codebases (service/API, monolith in any style such as MVC, layered/clean, vertical slice or modular; library/SDK; frontend; monorepo; infrastructure as code) and subjects without code (business or operational process; product). Each type has its own blueprint of sections, reading plan and gates. Ships deterministic Python scripts - a repository scanner that suggests the type and inventories the facts to cover (routes, screens, controllers, env vars, SSM/secrets references, queues, schedules including in-process jobs, Web.config/appsettings, pipelines, plaintext credentials), a skeleton generator, a validator (structure, coverage per section, complete tables, RACI cross-checks, sources cited, secret leaks, placeholders, anchors, Mermaid) and an MD-to-HTML renderer. Use when asked to document a repository, service, system, monolith, library, frontend, monorepo, infrastructure, process or product, to write onboarding/handover documentation, or to update existing documentation. Triggers on "document this", "documente isto", "document this service/repo/process/product", "gere a documentação", "documentar o processo", "wiki", "update the documentation", "atualize a documentação". Do NOT use for API reference generation only (OpenAPI), code comments, feature specs, or a single README tweak.
license: MIT
metadata:
  version: 1.0.0
---

# Document Anything

One subject, one document, two files with the same content:

```
docs/<...>/<name>.md     source of truth, written for AI agents (front matter, markers, full detail)
docs/<...>/<name>.html   generated from the .md, written for humans (sidebar, search, overview/detail filter,
                         collapsible blocks, diagrams, dark mode); a single file that opens in any browser
```

The skill first decides **what** it is documenting, then runs the process for that type:

| Family | Types |
| --- | --- |
| Code | `service`, `monolith`, `library`, `frontend`, `monorepo`, `infra` |
| Subject | `process`, `product` |

Every type has the same three parts (overview, detail, appendix) and its own blueprint of sections, so readers find their way in any document.

## Critical rules (read before acting)

**Skill files.** Everything lives relative to the directory that contains this `SKILL.md` (`<skill-dir>`):

- `references/`: common guides, plus one guide per type in `references/types/`;
- `blueprints/`: the section blueprints, as data;
- `scripts/`: the Python scripts;
- `assets/`: the page CSS and JS.

Resolve paths from there, never from the project root. When a step says to read a reference, read it completely (to EOF) before acting.

**Python.** The scripts need Python ≥ 3.9 and nothing else. Use whichever command resolves to it: `python3` on macOS/Linux, `python` or `py -3` on Windows. If none is available, tell the user and perform the same checks by reading (slower and less reliable).

**Non-negotiable:**

1. **Evidence or nothing.** Every statement comes from code, configuration, git history, documents, systems or people the user pointed to, and the source can be named. What cannot be established goes to `open-questions` with who can answer it. Never invent behaviour, names, commands, steps, numbers or dates.
2. **The Markdown is the source; the HTML is generated.** Edit only the `.md`, produce the `.html` with `render_wiki.py`, never hand-edit the HTML, and never deliver a pair out of sync.
3. **No secrets.** Never read secret values (parameter stores, secret managers, `.env`, CI variables, password managers) and never write any credential, not even a local one. Document where each secret lives and who provides it. Keep personal data to the names and roles the sources give.
4. **Read-only on everything but the two document files.** No deploys, applies, migrations, seeds or write calls against any environment. Running local builds and tests is allowed (see verification). Opening systems or listing cloud resources needs the user's explicit authorisation for this task.
5. **Gates decide, not self-assessment.** The document is not done until `validate_wiki.py` passes (exit 0) and the independent fact check has run.
6. **Blast radius.** The request authorises creating or updating the document files only. `git commit`, `git push`, publishing or sharing need an explicit go-ahead.

## Workflow

### 1. Classify

Read [references/classify.md](references/classify.md). For a codebase, run:

```bash
python <skill-dir>/scripts/scan_repo.py <repo> [<other-repo> ...]
```

The output starts with the suggested type, the evidence and the architectural style signals. Decide the type, then **confirm it with the user in one line**, with the evidence: "Vou documentar como **monólito** (MVC + módulos, 46 controllers, Web.config). Ok?". If the user already named the type, use it without asking; just state it in one line ("Documentando como **processo**, como pedido.") unless the evidence clearly contradicts it, in which case ask.

### 2. Load the type

Read `references/types/<type>.md` and print the blueprint:

```bash
python <skill-dir>/scripts/new_doc.py --print <type> --lang <pt-BR|en>
```

Then read [references/discovery.md](references/discovery.md).

### 3. Scope and sources

Ask only what is missing, in one message:

- **What to cover.** Code: the repos (default: the current workspace) and related repos for cross-application flows. Subjects: the documents, links, systems and people that are the sources.
- **Output path.** Code defaults to `docs/wiki/<name>.md` in the repo, where `<name>` is the repo folder name (`--subject` too). Subjects default to `docs/<type>/<name>.md` in the current folder, where `<name>` is a short kebab-case slug of the subject ("reembolso-de-despesas"); the user may choose another place. If a document already exists there, switch to [update mode](references/update.md).
- **Language.** Default to the language the user writes in.

### 4. Discover

Read area by area (code) or source by source (subjects), following the type guide's reading plan, and record findings with evidence. For large subjects, use parallel read-only sub-agents when available (see discovery.md).

Then compile at most ~8 questions only a person can answer, prioritised by impact (what blocks the most sections first), and ask them in one batch. Do not block on the answers: unanswered items go to `open-questions` with the right owner. For processes and products this is the structured interview described in the type guide, and its answers become a source.

### 5. Write

Read [references/dialect.md](references/dialect.md) and [references/writing.md](references/writing.md). Generate the skeleton, then fill it:

```bash
python <skill-dir>/scripts/new_doc.py --type <type> --lang <lang> --title "<Title>" --subject <name> [--repo <repo>] -o <path.md>
```

- Replace every `<!-- guide: -->` comment and every `«…»` placeholder with real content.
- Delete the optional sections that do not apply.
- Mark `na` (with the reason) only on required sections that allow it.
- Write the detail first (that is where the evidence is), then the overview, then the appendix, and the glossary last.

### 6. Gate and render

```bash
python <skill-dir>/scripts/validate_wiki.py <path.md> [--repo <repo> ...] --no-html
python <skill-dir>/scripts/render_wiki.py <path.md>
python <skill-dir>/scripts/validate_wiki.py <path.md> [--repo <repo> ...]
```

- Fix every ERROR. Read every WARN and fix it too; the only acceptable leftovers are a `file-refs` warning for a file that lives in a repo not passed with `--repo`, and a warning the document explains on the same line. Fix in the Markdown and repeat until PASS. After any edit, render again before the final validate.
- **Coverage errors (code)** mean a fact is missing from the document or from its home section. Document it there, or exclude it with `<!-- coverage-ignore: <fact> | <reason> -->` when it is genuinely irrelevant.
- **Crossref and sources errors (subjects)** mean the tables disagree, or a source is not cited.

### 7. Verify

Read [references/verification.md](references/verification.md).

1. For code types, run the safe local commands the document shows and record the results.
2. Run the independent fact check: a fresh Verifier sub-agent when available, otherwise a fresh-eyes pass.
3. Fix, render, re-validate (at most 3 loops).
4. Finish with the report described there.

### 8. Update mode

When the document exists, follow [references/update.md](references/update.md). Never start over. Documents that predate this skill are migrated.

## Scripts

| Script | Purpose | Exit code |
| --- | --- | --- |
| `scripts/scan_repo.py <repo>... [--format json]` | Suggested type and style, plus the fact inventory (never prints secret values) | 0 |
| `scripts/new_doc.py --list` / `--print <type>` / `--type ... -o <md>` | List types, print a blueprint, write a skeleton | 2 on bad input |
| `scripts/validate_wiki.py <md> [--repo <repo>...] [--no-html] [--strict] [--json]` | All gates for the document's type | 1 on any ERROR |
| `scripts/render_wiki.py <md> [-o out.html] [--check]` | Deterministic MD → single-file HTML (CSS/JS inline, Mermaid from CDN) | 1 on `--check` mismatch |

## Output behaviour

Do the work; do not narrate the machinery. Between steps, one short line on what you are doing is enough. Findings go into the document, not into chat. The final message is the report from [references/verification.md](references/verification.md).
