# Verification

A document that is wrong is worse than no document: people trust it. Verification has three layers and none is optional. Read this file to EOF before verifying.

## 1. Deterministic gates (scripts)

```bash
python <skill-dir>/scripts/validate_wiki.py <doc.md> [--repo <repo> ...] --no-html   # before the first render
python <skill-dir>/scripts/render_wiki.py <doc.md>
python <skill-dir>/scripts/validate_wiki.py <doc.md> [--repo <repo> ...]             # final gate, includes html-sync
```

`--repo` is mandatory for code types: coverage, file references and committed-secret checks need it. Subject types pass `--repo` only when the document also covers code.

**Exit code 1 means STOP:** fix the Markdown (never the HTML) and run again.

- **Always render before the final validate.** Any edit to the `.md` makes the HTML stale until `render_wiki.py` runs again.
- **Warnings must be read and fixed too.** The only acceptable leftovers are a `file-refs` warning for a file that lives in a repo not passed with `--repo`, and a warning the document explains on the same line.
- **A quoted path whose folder exists but whose file does not** (a typo or a rename) is an ERROR. When the document deliberately cites a file that is missing from the repo (legacy references, untracked files), say so on the same line ("ausente do repositório", "missing from the repo"); the check then skips that line.

## 2. Executable claims (code types)

Commands in `run-local`, `development`, `quick-start` and `tests` are claims too.

- **Run what is safe.** When the toolchain is available locally and the command is safe (build, unit tests, lint, format check, starting local containers), run it and record the outcome in the document: date, command, result ("312 testes, 0 falhas").
- **Never run** anything that deploys, applies infrastructure, migrates or seeds a shared environment, calls a production API, or needs secret values.
- **Label what was not run** as derived, and say what it needs ("Derivado de `src/docker-compose.yml`; não executado (exige Docker).") instead of claiming it works.

## 3. Independent fact check (author ≠ verifier)

After the gates pass, a fresh reviewer checks the content against the sources. With sub-agents available, dispatch one read-only Verifier with the payload below. Without them, do the same pass yourself after clearing your working assumptions: re-read the sources, and do not trust your earlier notes.

Verifier payload:

```text
You are verifying a document produced by the document-anything skill. You did not write it. Be adversarial: evidence or zero.
Document: <path to .md> (type: <type>). Sources: <repo paths and/or the `sources` list>. Blueprint: run
`python <skill-dir>/scripts/new_doc.py --print <type>`.
Check every number, name, status code, route, setting, schedule, permission, step, owner, deadline, value limit,
metric and command in the document against the sources (file:line for code; document + page/section for others).
Classify each checked claim:
  CONFIRMED (evidence matches), WRONG (evidence contradicts; give the correct fact and evidence),
  UNSUPPORTED (no evidence found), STALE (true in an older source, false in the current one).
Also report MISSING: important behaviour, steps or rules present in the sources but absent from the document,
and any secret value or personal data present.
Do not edit files. Return: verdict PASS/FAIL, counts per class, and the WRONG/STALE/MISSING/UNSUPPORTED items
ranked by impact, each with section, claim, evidence.
```

Fix every WRONG, STALE and MISSING item. Move UNSUPPORTED items that no source backs to `open-questions`. Re-run the gates. Loop at most 3 times; if items remain, report them to the user instead of hiding them.

When you do the pass yourself, keep the same bookkeeping as the Verifier: count the claims checked and list each correction (section, before, after, evidence). The final report quotes those numbers.

## Final report to the user

Short, decided, in the user's language:

- the type documented and the two file paths (MD and HTML), and how to open the HTML (any browser, double-click);
- the gate result (PASS, plus coverage numbers for code types) and the Verifier result (claims checked, corrections made);
- for code types, the commands verified by running them and those that could not be run (subject types skip this item);
- the open questions that need a person, with who should answer them;
- confirmation that nothing was committed or pushed (unless the user asked for it).
