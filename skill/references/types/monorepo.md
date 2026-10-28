# Type: monorepo

A repository holding several deployables or packages. Blueprint: `python <skill-dir>/scripts/new_doc.py --print monorepo`.

The monorepo document is **the map**: what is in the repo, how the parts depend on each other, the shared tooling and conventions. Each part gets **its own document with its own type** (service, frontend, library...). Link those documents from `repo-map`.

## Workflow

1. Scan the whole repo. Then scan each part (pass the part's folder as the repo) to get its suggested type.
2. Show the user the parts with their suggested types and ask which part documents to produce now; the map comes first. Large monorepos are documented in waves.
3. Write the map. For parts without a document yet, write "pendente" in the Document column and add an open question with the owner.
4. Produce each part's document with the normal workflow, rooted at the part's folder (`--repo <part folder>`, output in the part's `docs/` or in a central `docs/<part>/`, as the repo's conventions suggest).

## Reading plan (for the map)

| Area | Where to look | What to extract |
| --- | --- | --- |
| Parts | Workspace config (`workspaces`, `pnpm-workspace.yaml`, `nx.json`, `turbo.json`, solution files, Gradle settings), top-level folders | Every part: name, folder, type, owner (CODEOWNERS), responsibility |
| Dependencies | Package references between parts, imports of internal packages, API calls between apps, shared databases | The dependency graph and the allowed directions |
| Tooling | Task runner config, caching, affected-only builds, shared lint/format/tsconfig/build props | How to build/test/run one part or everything |
| Conventions | CONTRIBUTING, CODEOWNERS, commit and branch rules, release config (changesets, semantic-release, fixed vs independent versions) | How to add a part, how releases work |
| Delivery | CI pipelines and how they select affected parts | What runs on each change and how each part deploys |

## Gate notes

Coverage requires packages and deployables, which have home section `repo-map` (every part appears in the map), plus pipelines, local containers and plaintext-credential files. `repo-map` tables must be complete (no empty cells).
