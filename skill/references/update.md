# Update mode: the document already exists

Never start over when a document exists: update it. Read this file to EOF.

## Code types

1. Read the front matter: `type`, `source_commit`, `as_of`, `repos`.
2. On each repo, run `git log --oneline <source_commit>..HEAD` and `git diff --stat <source_commit>..HEAD`, and map the changed files to sections. The scan's facts and the reading plan of the type guide tell you which section owns which file.
3. Re-run `scan_repo.py` and `validate_wiki.py --repo ...`:
   - coverage errors show new facts;
   - anchor and file-ref errors show renamed or moved things.
4. Re-read the code behind every affected section and update it; leave unaffected sections alone. Update `status`, `history`, `dev-decisions`, `risks` and `open-questions` as needed.
5. Set `as_of` to today and `source_commit` to the new `git rev-parse --short HEAD`. Then render, validate, verify the changed sections and report what changed.

## Subject types

1. Ask what changed, or which new sources exist (a new policy version, a meeting, a new feature).
2. Add new sources to `sources` (keep the old ones while still cited), then read them.
3. Update the affected sections, `status` and `open-questions` (close the questions that were answered, citing the answer's source).
4. Set `as_of` to today. Then render, validate, verify and report.

## Documents that predate this skill

A document without the skill's front matter or markers (for example an older wiki) is **migrated**, not rewritten:

1. Classify it.
2. Add the front matter and the part and section markers.
3. Map its existing sections onto the blueprint, keeping its content and its anchors where possible.
4. Run the gates. The structure, coverage and file-ref errors become the to-do list.
