# Classify: decide what is being documented

The type decides the blueprint (sections), the reading plan and the gates. Classify before reading anything in depth. Read this file to EOF.

## Types

| Type | Family | It is... | Typical signals |
| --- | --- | --- | --- |
| `service` | code | A deployable service: API, worker, consumer, function app | IaC with functions/containers, HTTP routes, queues, schedules; one or a few deployables |
| `monolith` | code | One application holding many business areas | MVC folders (Controllers/Views), Web.config/Global.asax, Rails/Django/Laravel structure, many controllers, Razor Pages, large single deployable, layered/vertical-slice/modular structure |
| `library` | code | Code consumed by other code: package, SDK, client, shared kernel | packable project (PackageId), package.json with main/exports and no start script, pyproject package, no deployable, no IaC |
| `frontend` | code | A user interface: SPA, SSR/SSG site, mobile app | React/Vue/Angular/Svelte/Next/Nuxt/React Native, SPA routes or file-based pages, no server routes of its own |
| `monorepo` | code | Several deployables or packages in one repo | workspaces (npm/pnpm/yarn), Nx, Turborepo, Lerna, several solutions, several IaC stacks |
| `infra` | code | Infrastructure as code only | Terraform/CDK/CloudFormation/Helm/K8s with little or no application code |
| `process` | subject | How people and systems get something done | the user describes steps, roles, approvals, deadlines; sources are documents, spreadsheets, interviews |
| `product` | subject | A product or program as users and the business see it | the user talks about audiences, features, metrics, roadmap; sources are product docs, decks, dashboards |

`python <skill-dir>/scripts/new_doc.py --list` prints the types; `--print <type>` prints the full blueprint of one.

## How to decide

1. **The user named it** ("documente este processo", "document this library"): use that type and state it in one line without asking. Ask only if the evidence clearly contradicts it.
2. **The workspace is a codebase**: run `scan_repo.py`. Its output starts with `Suggested type` and the evidence. Check the suggestion against what you see; the scanner is a heuristic.
3. **There is no code, or the request is about people, steps, a business area or a product**: it is a subject type. Decide between `process` (how work flows: steps, roles, deadlines) and `product` (what is offered: audiences, features, metrics).
4. **Mixed requests** pick the reader's need, not the material:
   - "explain how refunds work" in a service repo is usually a `process` that uses the code as one source;
   - "document this repo" is a codebase type.
5. **Still ambiguous**: ask one question with the two most likely options and what each document would contain.

**When you chose the type yourself, confirm before writing**, in one line, with the evidence: "Vou documentar como **monólito** (MVC + módulos em `Modules/`, 46 controllers, Web.config). Ok?" One line is cheap; documenting the wrong thing is not.

## Composite situations

- **Monorepo.** The monorepo document is the map. It lists every part with its own type, and each part gets its own document (pass the part's folder as `--repo`). Ask how many parts to document now; document the map first.
- **Monolith with a strangler in progress.** Type `monolith`, plus the optional `modernization` section. Services already extracted get their own `service` documents, linked from the map.
- **Service plus its product.** Two documents: the `service` (technical source of truth) and, when asked, a `product` that links to it.

## Architectural style (code types)

The scanner reports structure signals (MVC, vertical slice, layered/clean/onion, hexagonal, modular). Treat them as hints, then verify in the code:

- base classes and folder conventions;
- where a typical feature's files live;
- what references what (project references, imports).

Real codebases mix styles by region (old MVC area, new slices). Document each region and the rule for new code; do not force one label.
