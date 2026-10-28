# Writing the document

Two readers share one Markdown file: an AI agent that will load it as context, and a human who reads the HTML. Both need the same thing: correct, complete, unambiguous, findable. Read this file to EOF before writing.

## Voice

- **Lead with the answer.** The first sentence of every section says what the reader most needs ("O serviço não tem tela: é chamado pelo site e pelo backoffice." / "O fechamento começa no 1º dia útil e termina no 5º."). Context comes after.
- **Decided, plain, concrete.** Write "A busca roda às 5h de Brasília (08:00 UTC)", not "a busca deve rodar aproximadamente de manhã". Use numbers, names, units and time zones.
- **Overview without jargon.** Part I must make sense to someone outside the team. Every technical term that survives goes to the glossary. Explain acronyms on first use.
- **Detail precise.**
  - Code types: exact names (`Payments:BaseUrl`, `OrderCreatedQueue`), file paths in `code`, commands that work when pasted.
  - Subject types: exact roles, systems, deadlines and values ("aprovação do controller acima de R$ 10.000,00").
- **No hedging filler.** Remove "basicamente", "de forma geral", "it is worth noting", "robust", "seamless". If something is uncertain, say exactly what is uncertain and put it in `open-questions`.
- **Tenses and dates.** Present tense for how things are, past tense for history. Dates in the document's locale (pt-BR: dd/mm/aaaa), always absolute, never "ontem" or "last week".
- **Language.** Write in the document's language (`lang` in the front matter; default: the language the user writes in). Identifiers stay exactly as they are in the code or the source systems.

## Shape

- Prefer tables for anything with 3 or more items sharing attributes (routes, settings, steps, roles, features, risks, glossary).
- Use collapsible blocks for detail that only some readers need (per route, per environment, per step, FAQ answers). Keep the summary line informative: `<summary>UAT — prefixo <code>/svc/uat</code> (12 parâmetros)</summary>`.
- One diagram per idea. Every diagram is followed by prose that walks through it, because the Markdown reader (an AI) gets more from the text than from the diagram source.
- When the subject crosses applications, say where each step happens, using tags such as `(Service)` and `(Site)`.
- Cite sources where a reader may want to check:
  - **code types:** a short "Fontes:" line at the end of detailed sections listing the key files (paths, not line numbers; the validator checks the paths exist);
  - **subject types:** the source name next to the claim ("conforme a Política de Reembolso v4").

## Secrets and sensitive data

- Never write a secret value, even an obviously local one. Write `*secreto*` / `*secret*` in the value column, plus where it lives (parameter path, secret name, vault) and who provides it.
- Connection strings show their shape, with `...` in place of the credentials: `Server=db-dev;Database=orders;User Id=...;Password=...;`.
- Files with plaintext credentials (from the scan) go to `security` and `risks` by **file path**, with the action (rotate, move to a parameter store, ignore in git).
- No personal data (CPF, e-mail, phone, salary) of real people. Names and roles given by the sources are fine in process documents. Examples use clearly fake values.

## Completeness rules

- Every fact the type requires from `scan_repo.py` is mentioned in its home section. The validator fails otherwise.
- Every persisted status or enum value appears with its numeric code.
- Every table row is complete. When the sources say there is nothing, write "—". When nobody knows, write **"Em aberto (ver Perguntas em aberto)"** / **"Open (see Open questions)"** and add the question; never leave the cell empty or write "?", "A definir" or "TBD" (the validator rejects them).
- Every command block is one of three things, and the line before it says which:
  - **run by the agent**: "Verificado em 23/10/2026: 42 testes, 0 falhas.";
  - **copied** from a source in the repo: "Do README." / "Da esteira `azure-pipelines.yml`.";
  - **derived** from a file that implies it (compose file → `docker compose up`, test project → `dotnet test`, samconfig → `sam deploy --config-env`) and not run: "Derivado de `src/docker-compose.yml`; não executado (exige Docker)."

  Anything else is an invented command: do not write it.
- Use a shell language on command fences (` ```bash `, ` ```powershell `, ` ```console `). The gate only accepts those where it asks for commands.

## What counts as evidence

Besides the subject's own code and sources, **documented defaults of the libraries and frameworks it uses** are evidence, cited as such: "padrão do Hangfire (UTC, 10 novas tentativas automáticas)", "comportamento padrão do ASP.NET MVC". Your own judgment is allowed only where the blueprint asks for it (risk severity) and is labelled as judgment.

## Thin sources

Small or incomplete subjects have required sections with nothing behind them (no observability in a tiny repo, no decisions recorded). Do not pad. Write the section in two or three sentences: what was looked at, what was not found, and the pointer to the open question ("O código não configura logs além do padrão do IIS; ver [Perguntas em aberto](#perguntas-em-aberto)."). That is a complete section.

## Length

As long as the subject needs and **never padded**. Length follows the volume of the sources: a tiny repo or three short source documents give a few hundred lines; a large monolith or a service with many flows can reach ~2500. Cut repetition: say a thing once in the right section and link to it (`[Configuração por ambiente](#configuração-por-ambiente)`).
