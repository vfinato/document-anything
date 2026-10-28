# Markdown dialect

The Markdown file is the source of truth and is written for AI agents: complete, explicit, greppable. The HTML is generated from it by `render_wiki.py` and is written for humans: navigable, searchable, collapsible. Never edit the HTML by hand. Start every document from the skeleton (`new_doc.py`), which already has every marker in place.

Plain GitHub-flavoured Markdown plus these conventions (all invisible or harmless when the MD is read raw):

## Structure markers

```markdown
<!-- part: overview -->
# Parte I — Visão geral

<!-- section: summary -->
## Resumo em uma página
```

- `<!-- part: X -->` immediately before an H1. X is `overview`, `detail` or `appendix` (`business` and `technical` are accepted as aliases). The intro (title H1, blockquote, `about`) has no marker. The HTML view filter uses the parts; its labels come from the type (e.g. Negócio/Técnico for a service, Visão geral/Passo a passo for a process).
- `<!-- section: id -->` immediately before an H2. Ids come from the type's blueprint (`new_doc.py --print <type>`). Add ` na` (`<!-- section: messaging na -->`) only on sections the blueprint allows, and write one sentence saying why. Optional sections that do not apply are deleted.
- Only H1 opens a part and only H2 opens a section. Use H3/H4 inside sections.

## Cards

```markdown
<!-- cards -->
- **Objetivo** — Pedido com prazo de pagamento | Todo pedido expira se não for pago em 48 horas.
- **Volume** — ~20 mil pedidos/dia | Picos de 3x na Black Friday.
<!-- /cards -->
```

`**Title** — Value | Description`. Value short (≤ 5 words), description one sentence.

## Collapsible blocks

```markdown
<details markdown="1">
<summary>POST /orders — cria um pedido</summary>

Markdown body here (blank line after the summary line is required).

</details>
```

Use `<details markdown="1" open>` for blocks that should start open. Use them for per-route, per-environment, per-flow and FAQ detail so the page stays scannable. Never put an H1/H2 inside a details block.

## Diagrams

Fenced ` ```mermaid ` blocks, rendered in the browser (Mermaid 10 from CDN; without network the source stays visible).

- Quote every label that has punctuation: `A["Valida o pedido (Loja)"]`, never `A[Valida o pedido (Loja)]`; the validator rejects unquoted brackets/parentheses.
- Line breaks inside labels: `<br/>`.
- Prefer `flowchart LR/TD`, `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`. Keep each diagram under ~25 nodes; split instead.

## Tags

Declare them in the front matter (`tags:` list). Writing `(Service)` anywhere in the text (outside code) renders a coloured pill, so steps that cross repositories say where they happen: "a loja (Loja) chama o serviço (Service)". Use tags only for multi-application wikis.

## Callouts

```markdown
> [!WARNING]
> A pilha não define `Database__Server` em PROD; sem o parâmetro SSM o serviço usa o servidor de DEV do `appsettings.json`.
```

`NOTE`, `TIP`, `IMPORTANT`, `WARNING`, `CAUTION`. Use them sparingly, for what a reader must not miss.

## Tables

GitHub tables. Escape pipes inside cells as `\|`. `<br>` is allowed inside cells for line breaks. Keep identifiers in `code`.

## Anchors

Heading ids are the lowercase text with punctuation removed and spaces collapsed to `-`, accents kept: `## Configuração por ambiente` → `#configuração-por-ambiente`. Link with `[Glossário](#glossário)`. A custom id is possible with `## Título {#custom-id}`. The validator checks every internal link.

## Front matter sources (subject types)

Each item of `sources` is one source with its date: `Política de Reembolso v4 (vigente desde 01/03/2026)`, `Entrevista com a controller, 20/10/2026`. Copy each string **exactly** into the `references` section (a table row is the usual place); the validator matches the exact text and warns about sources without a date. An interview that was planned but did not happen is not a source: say so in `references` and in `open-questions`.

## Unknown values

In tables, an unknown value is written `Em aberto (ver Perguntas em aberto)` / `Open (see Open questions)`, with the question added to `open-questions`. `—` means the sources say there is none.

## Coverage exclusions

`<!-- coverage-ignore: SampleQueue | leftover from the service template, not used by any code path -->`. One per fact, on one line, always with a reason (the validator rejects an ignore without one). Comments are invisible to readers, so a fact mentioned only inside a comment does not count as covered.

## Things that are not allowed

- Secret values of any kind (passwords, keys, tokens, connection strings with credentials). Write where the value lives and who provides it.
- Placeholders (`«…»` from the skeleton, `TODO`, `TBD`, `{{...}}`, `<!-- guide: -->` comments). Unknowns go to `open-questions`. `«…»` is rejected even inside code blocks.
- Raw HTML beyond `details`/`summary` and inline tags (`code`, `br`, `kbd`, `sub`, `sup`, `mark`).
- Images that are not embedded or public URLs: the HTML must open alone in any browser.
