# Discovery: understanding the subject before writing

A document is only as good as the reading behind it. Discovery produces **findings with evidence**, not prose. Every claim that will reach the document carries its source: `file:line` for code, a document path or link plus the place inside it, a commit, or "user said on <date>". Read this file to EOF before starting; the type guide (`references/types/<type>.md`) adds the reading plan for the type.

## Knowledge order

For codebases:

1. **Code and IaC.** The truth about what the system does today.
2. **Config files and pipelines.** The truth about how it runs and where.
3. **Git history** (`git log --oneline -50`, `git log --format='%h %ad %s' --date=short`, tags, merged PRs). Why it is the way it is, and the timeline.
4. **Docs in the repo** (README, `docs/`, ADRs, specs, handoffs). Intent, vocabulary, decisions. Docs can be stale: when code and docs disagree, the code wins and the disagreement goes to `risks` or `open-questions`.
5. **The user.** Context the code cannot show: owners, who provides each secret, production status, roadmap.

For subjects without code (process, product):

1. **The sources the user gives**: documents, links, spreadsheets, tickets, transcripts, meeting notes. Each one goes into the front matter `sources` with a date.
2. **Systems and code that implement the subject**, when there are any and the user points to them. They show how things really work, not only how they are described.
3. **The people**, through a structured interview (step 4 of SKILL.md), recorded as a source: "Entrevista com <papel/nome>, <data>".
4. When sources disagree, write what each says and send the decision to `open-questions`.

In both cases, **never invent.** What no source answers goes to `open-questions`, with who can answer it.

## Inventory first

- **Code:** run `scan_repo.py` on every repo the document covers and read the whole output. It is:
  - the checklist of facts the gate will demand for the type;
  - the suggested type and architectural style;
  - the detected stack;
  - the existing docs, which tell you where to look next.
- **Subjects:** list every source before reading any of them, then read each one completely. If a source cannot be read (a private link, a format that cannot be opened), tell the user instead of skipping it silently.

## Parallel reading

When the subject is large (a big repo, several repos, a monolith with many modules, a process with many sources), split the reading into independent groups and, when the harness supports sub-agents, dispatch read-only explorers in parallel, one per group. Give each:

- its rows from the type guide's reading plan;
- the scan output (for code);
- the findings format below.

Each explorer returns findings only. Keep the synthesis yourself.

## Multi-repo and cross-system subjects

When the subject spans applications (a site calls the service, a process runs through three systems), ask whether the document should cover the other repos too and where they are checked out.

- **With the paths:** scan and read them like the primary one, declare one tag per application in the front matter, and mark every cross-application step with its tag.
- **Without them:** document the boundary from the known side (contracts, events, who calls) and list the unknown side in `open-questions`.

## Read-only, always

Discovery never changes anything:

- no write calls, deploys, migrations or seeds;
- no reading of secret values (parameter stores, secret managers, `.env` files, CI variables, password managers).

Listing cloud resource names, or opening systems the user points to, requires the user's explicit authorisation for this task.

## Findings format

Each area or source produces a list like this (sub-agents return exactly this, nothing else):

```markdown
### Area: Async

- [F-ASYNC-01] Every created order is published to SQS queue `OrderCreatedQueue` (`orders-created-{stage}`) by `ApiFunction`; consumers live in other services. Evidence: src/template.yaml:24, src/Orders.Api/Endpoints/OrdersEndpoints.cs:8
- [F-ASYNC-02] The queue has no redrive policy; no DLQ exists. Evidence: src/template.yaml:24
- [GAP-ASYNC-01] Who consumes the queue? Ask: architecture team.
```

```markdown
### Source: Manual de fechamento v3 (PDF, 2025-11)

- [F-STEP-04] Conciliação bancária é feita pelo analista de contas a receber até D+2, no SAP (transação FF67). Evidence: manual p. 7
- [GAP-STEP-01] O manual não diz quem aprova ajustes acima de R$ 10 mil. Ask: controller.
```

Findings carry ids and precise evidence so the Verifier can trace every statement back. The document itself cites paths or sources without line numbers (lines drift); the precise locators stay in the findings. `GAP-*` items become `open-questions` or `risks`.
