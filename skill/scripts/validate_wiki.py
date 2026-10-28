#!/usr/bin/env python3
"""Deterministic gate for a document-anything pair (Markdown + HTML). A non-zero exit means STOP and fix.

The checks follow the blueprint of the document's `type` (front matter):
  front-matter   title, type, subject, lang, as_of; source_commit for code types (must exist in git); sources for subject types
  structure      the three part markers and every required section of the type, in the right part
  content        per-section evidence: cards, diagrams, tables, shell blocks, examples, complete tables; no empty sections
  crossref       values that must match between sections (e.g. every role appears in the RACI matrix)
  sources        every source listed in the front matter is cited in `references` (subject types)
  placeholders   no TODO/TBD/FIXME, «…», {{…}}, template guidance or lorem ipsum left behind
  secrets        no credentials, including values found committed in the repo
  anchors        every internal link (#id) points to an existing heading
  mermaid        diagrams start with a known type; flowchart labels with parentheses are quoted
  tables         rows have the header's column count (warning)
  file-refs      quoted paths exist in the repo (error for a typo inside an existing folder, else warning)
  coverage       every fact the type requires from scan_repo.py is mentioned, in its home section when it has one
  html-sync      the sibling .html was rendered from this exact Markdown

Usage:
    python validate_wiki.py docs/wiki/orders-service.md --repo .
    python validate_wiki.py docs/process/month-end-close.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_wiki  # noqa: E402
import scan_repo  # noqa: E402
import wikilib  # noqa: E402

PART_ORDER = ("overview", "detail", "appendix")
MERMAID_TYPES = re.compile(
    r"^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(-v2)?|erDiagram|journey|gantt|pie|gitGraph|mindmap|timeline"
    r"|quadrantChart|C4Context|C4Container|C4Component|C4Dynamic|C4Deployment|block-beta|sankey-beta|xychart-beta"
    r"|requirementDiagram|architecture-beta|packet-beta|kanban|---|%%)"
)
PLACEHOLDERS = re.compile(
    r"\b(TODO|TBD|FIXME)\b|«[^»\n]*»|(?i:\{\{[^}]*\}\}|<preencher|<fill[ -]in|\[preencher\]|\[fill in\]|lorem ipsum|<!--\s*guide:"
    r"|<(?:papel|nome|data|valor|respons[aá]vel|dono|role|name|date|value|owner)(?:/[a-zà-ú]+)*>)"
)
TEMPLATE_MARK = re.compile(r"«[^»\n]*»")
MIN_SECTION_CHARS = 60
SHELL_LANGS = r"(bash|sh|shell|zsh|console|shell-session|powershell|pwsh|ps1|ps|cmd|bat|batch)"
EMPTY_CELL_OK = {"—", "-", "–", "n/a", "N/A", "na"}
UNKNOWN_CELL = re.compile(r"^(\?+|a definir|a confirmar|tbd|n/?d|desconhecido|unknown|não sei|nao sei|pendente)$", re.I)
OPEN_CELL = re.compile(r"^(em aberto|open)\b", re.I)
RACI_CELL = re.compile(r"^(?:[RACI](?:\s*[/,+]\s*[RACI])*|—|-|–)$")
LABEL_LINE = re.compile(
    r"verificad|executad|copiad|derivad|não executad|nao executad|^do readme|^da esteira|^do pipeline|^de `"
    r"|verified|\bran\b|\brun\b|copied|from the|derived|not run", re.I)
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}(-\d{2})?\b|\b\d{2}/\d{4}\b|\b(19|20)\d{2}\b")
MISSING_FILE_HINT = re.compile(r"ausente|inexistente|não existe|nao existe|não está no reposit|missing|does not exist|not in the repo|not committed|não versionad", re.I)
# node id + shape opener + unquoted label + shape closer; openers/closers longest first so [(db)] and ((x)) stay valid
FLOW_NODE = re.compile(
    r"\b[\w-]+\s*(\[\(|\(\[|\[\[|\(\(\(|\(\(|\{\{|\[/|\[\\|\[|\(|\{|>)"
    r"([^\"\]\)\}\n/\\][^\]\)\}\n\"]*?)"
    r"(\)\]|\]\)|\]\]|\)\)\)|\)\)|\}\}|/\]|\\\]|\]|\)|\})"
)
MESSAGING_TYPES = re.compile(r"SQS::Queue|SNS::Topic|Kinesis|Firehose|Events::EventBus|MSK::|Pipes::|sqs_queue|sns_topic|kinesis")


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def error(self, check, message, line=None):
        self.items.append({"level": "ERROR", "check": check, "message": message, "line": line})

    def warn(self, check, message, line=None):
        self.items.append({"level": "WARN", "check": check, "message": message, "line": line})

    @property
    def errors(self):
        return [i for i in self.items if i["level"] == "ERROR"]


# ---------------------------------------------------------------- parsing helpers

def parse_sections(lines: list[str]) -> tuple[list[dict], list[dict]]:
    """Returns (parts, sections) with 0-based line indexes into the body."""
    parts, sections = [], []
    pending_part = None
    for idx, line, in_code, _ in wikilib.iter_outside_code(lines):
        if in_code:
            continue
        s = line.strip()
        m = wikilib.RE_PART.match(s)
        if m:
            pending_part = {"kind": wikilib.normalize_part(m.group(1)), "marker": idx}
            continue
        if re.match(r"^#\s", line) and pending_part:
            pending_part["heading"] = idx
            parts.append(pending_part)
            pending_part = None
            continue
        m = wikilib.RE_SECTION.match(s)
        if m:
            sections.append({"id": m.group(1).lower(), "na": bool(m.group(2)), "marker": idx,
                             "part": parts[-1]["kind"] if parts else "intro"})
    for sec in sections:
        j = sec["marker"] + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        heading = wikilib.RE_HEADING.match(lines[j]) if j < len(lines) else None
        sec["heading"] = j if heading and len(heading.group(1)) == 2 else None
        start = (sec["heading"] if sec["heading"] is not None else sec["marker"]) + 1
        end = len(lines)
        for idx, line, in_code, _ in wikilib.iter_outside_code(lines):
            if idx >= start and not in_code and (re.match(r"^#{1,2}\s", line) or wikilib.RE_SECTION.match(line.strip())
                                                  or wikilib.RE_PART.match(line.strip())):
                end = idx
                break
        sec["start"], sec["end"] = start, end
    return parts, sections


def tables_in(body: list[str]) -> list[tuple[int, list[str], list[tuple[int, list[str]]]]]:
    """Tables outside code: (header line index, header cells, [(row index, cells)])."""
    outside = {i for i, _, in_code, _ in wikilib.iter_outside_code(body) if not in_code}
    found, k = [], 0
    while k < len(body) - 1:
        if k in outside and "|" in body[k] and "|" in body[k + 1] and wikilib.RE_TABLE_DELIM.match(body[k + 1]):
            header = wikilib.split_row(body[k])
            rows, j = [], k + 2
            while j < len(body) and body[j].strip() and "|" in body[j]:
                rows.append((j, wikilib.split_row(body[j])))
                j += 1
            found.append((k, header, rows))
            k = j
        else:
            k += 1
    return found


def visible_chars(chunk: list[str]) -> int:
    text = "\n".join(chunk)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return len(re.sub(r"\s+", "", text))


def visible_text(lines: list[str]) -> str:
    """Text a reader can see: HTML comments removed (markers and ignores are not mentions)."""
    return re.sub(r"<!--.*?-->", "", "\n".join(lines), flags=re.S)


def strip_code(lines: list[str]) -> list[tuple[int, str]]:
    """Lines outside fenced code, with inline code spans removed."""
    return [(idx, wikilib.RE_CODE.sub("", line)) for idx, line, in_code, _ in wikilib.iter_outside_code(lines) if not in_code]


def cell_text(cell: str) -> str:
    return wikilib.plain_text(cell).strip()


# ---------------------------------------------------------------- checks

def check_front_matter(meta, bp, report):
    required = ["title", "type", "lang", "as_of"]
    if not (meta.get("subject") or meta.get("service")):
        report.error("front-matter", "missing `subject` in the front matter (what is documented: repo, process or product name)")
    if bp and bp["family"] == "code":
        required.append("source_commit")
    for key in required:
        if not str(meta.get(key) or "").strip():
            report.error("front-matter", f"missing `{key}` in the front matter")
    if bp and bp["sources_required"] and not wikilib.as_list(meta.get("sources")):
        report.error("front-matter", "`sources` must list the documents, links, transcripts and people this document was built from")
    if meta.get("as_of") and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(meta["as_of"])):
        report.error("front-matter", "`as_of` must be YYYY-MM-DD")
    if meta.get("source_commit") and not re.match(r"^[0-9a-f]{7,40}$", str(meta["source_commit"])):
        report.error("front-matter", "`source_commit` must be a git commit hash (7-40 hex chars)")


def check_structure(lines, parts, sections, bp, report, offset):
    kinds = [p["kind"] for p in parts]
    for kind in PART_ORDER:
        if kinds.count(kind) != 1:
            report.error("structure", f"expected exactly one `<!-- part: {kind} -->` marker followed by an H1, found {kinds.count(kind)}")
    present = [k for k in kinds if k in PART_ORDER]
    if present != sorted(present, key=PART_ORDER.index):
        report.error("structure", "parts must appear in the order overview, detail, appendix")

    spec_by_id = {s["id"]: s for s in bp["sections"]}
    seen: dict[str, dict] = {}
    for sec in sections:
        line = sec["marker"] + offset
        if sec["id"] in seen:
            report.error("structure", f"section `{sec['id']}` appears twice", line)
            continue
        seen[sec["id"]] = sec
        spec = spec_by_id.get(sec["id"])
        if spec is None:
            report.warn("structure", f"section `{sec['id']}` is not in the `{bp['type']}` blueprint", line)
            continue
        if sec["heading"] is None:
            report.error("structure", f"section marker `{sec['id']}` must be followed by an H2 heading", line)
        if sec["part"] != spec["part"]:
            report.error("structure", f"section `{sec['id']}` belongs to the `{spec['part']}` part, found in `{sec['part']}`", line)
        body = lines[sec["start"]:sec["end"]]
        if sec["na"]:
            if not spec["na"]:
                hint = "it is required and must be written" if spec["required"] else "delete it when it does not apply"
                report.error("content", f"section `{sec['id']}` cannot be marked `na`: {hint}", line)
            elif visible_chars(body) < 20:
                report.error("content", f"section `{sec['id']}` is marked `na` but does not say why", line)
            continue
        if visible_chars(body) < MIN_SECTION_CHARS:
            report.error("content", f"section `{sec['id']}` is empty or too thin", line)
        check_section_content(sec, body, spec["checks"], report, line, offset)
    for spec in bp["sections"]:
        if spec["required"] and spec["id"] not in seen:
            report.error("structure", f"required section `{spec['id']}` is missing (`<!-- section: {spec['id']} -->` + H2)")
    about = seen.get("about")
    first_h1 = next((i for i, ln, in_code, _ in wikilib.iter_outside_code(lines) if not in_code and re.match(r"^#\s", ln)), None)
    if about and first_h1 is not None and not any(lines[k].lstrip().startswith(">") for k in range(first_h1, about["marker"])):
        report.error("content", "the title needs a blockquote (what this document is, who it is for) before `about`", first_h1 + offset)
    return seen


def check_section_content(sec, body, checks, report, line, offset):
    text = "\n".join(body)
    if "cards" in checks:
        cards = re.search(r"<!--\s*cards\s*-->(.*?)<!--\s*/cards\s*-->", text, re.S)
        count = len([ln for ln in (cards.group(1).split("\n") if cards else []) if wikilib.RE_CARD.match(ln.strip())])
        if count < 4:
            report.error("content", f"section `{sec['id']}` needs a `<!-- cards -->` block with at least 4 cards (found {count})", line)
        elif count > 10:
            report.warn("content", f"section `{sec['id']}` has {count} cards; keep the summary to 4-10", line)
    if "mermaid" in checks and not re.search(r"^\s*(```|~~~)\s*mermaid", text, re.M):
        report.error("content", f"section `{sec['id']}` needs a mermaid diagram", line)
    tables = tables_in(body)
    if "table" in checks and not tables:
        report.error("content", f"section `{sec['id']}` needs a table", line)
    if "code" in checks:
        shell_fences = [k for k, ln in enumerate(body) if re.match(r"^\s*(```|~~~)\s*" + SHELL_LANGS + r"\s*$", ln)]
        if not shell_fences:
            report.error("content", f"section `{sec['id']}` needs a fenced shell block (bash, sh, powershell, console...) with the commands", line)
        for k in shell_fences:
            prev = next((body[j].strip() for j in range(k - 1, -1, -1) if body[j].strip()), "")
            if not LABEL_LINE.search(wikilib.plain_text(prev)):
                report.error("content", f"section `{sec['id']}`: the line before each command block must say whether it was run (with date and result), "
                                        "copied (from where) or derived and not run (needs what)", sec["start"] + k + offset)
    if "dated" in checks:
        first = next((ln for ln in body if ln.strip() and not ln.strip().startswith("<!--")), "")
        if not DATE_RE.search(first):
            report.error("content", f"section `{sec['id']}`: the first sentence must carry the date of the status", line)
    if "faq" in checks and len(re.findall(r"<details\b", text)) < 3:
        report.error("content", f"section `{sec['id']}` needs at least 3 questions as collapsible <details> blocks", line)
    if "example" in checks and not re.search(r"^\s*(```|~~~)\s*(?!mermaid\b)(?!" + SHELL_LANGS + r"\s*$)\S+", text, re.M):
        report.error("content", f"section `{sec['id']}` needs a code example in a fenced block with its language", line)
    strict = "table-complete" in checks
    for _, header, rows in tables:
        for row_idx, cells in rows:
            padded = cells + [""] * (len(header) - len(cells))
            empty, unknown = [], []
            for c, cell in enumerate(padded[:len(header)]):
                value = cell_text(cell)
                if not value and cell.strip() not in EMPTY_CELL_OK:
                    empty.append(header[c] or f"#{c + 1}")
                elif UNKNOWN_CELL.match(value):
                    unknown.append(f"{header[c] or '#' + str(c + 1)}: {value}")
            where = sec["start"] + row_idx + offset
            if empty:
                msg = (f"section `{sec['id']}` has empty cells ({', '.join(empty)}); write the value, '—' when the sources say there is none, "
                       "or 'Em aberto (ver Perguntas em aberto)' plus the question")
                (report.error if strict else report.warn)("content", msg, where)
            if unknown:
                report.error("content", f"section `{sec['id']}` uses an unknown marker ({'; '.join(unknown)}); write 'Em aberto (ver Perguntas em aberto)' "
                                        "/ 'Open (see Open questions)' and add the question", where)
    if "raci" in checks:
        check_raci(sec, body, report, offset)


def check_raci(sec, body, report, offset):
    tables = tables_in(body)
    if not tables:
        return
    _, header, rows = tables[0]
    for row_idx, cells in rows:
        where = sec["start"] + row_idx + offset
        values = [cell_text(c) for c in cells[1:len(header)]]
        bad = [v for v in values if v and not RACI_CELL.match(v)]
        if bad:
            report.error("crossref", f"RACI cells must be R, A, C, I (or combinations like R/A) or '—'; found {', '.join(repr(b) for b in bad)}", where)
        accountable = sum(1 for v in values if "A" in re.split(r"\s*[/,+]\s*", v))
        if accountable != 1:
            report.error("crossref", f"RACI row `{cell_text(cells[0])}` must have exactly one A (found {accountable})", where)


def _table_values(lines, sec, column=None, header=False):
    tables = tables_in(lines[sec["start"]:sec["end"]])
    if not tables:
        return None
    _, head, rows = tables[0]
    if header:
        return {cell_text(h).lower() for h in head[1:]}
    return {cell_text(cells[column]).lower() for _, cells in rows if column < len(cells)}


def _matches(value, targets):
    if value.lower() in targets:
        return True
    parts = [p.strip() for p in re.split(r",|;|/|\+|\s+e\s+|\s+and\s+", value) if p.strip()]
    return len(parts) > 1 and all(p.lower() in targets for p in parts)


def check_steps_in_raci(lines, seen, report, offset):
    steps, raci = seen.get("steps"), seen.get("raci")
    if not steps or not raci or steps["na"] or raci["na"]:
        return
    step_tables = tables_in(lines[steps["start"]:steps["end"]])
    raci_rows = _table_values(lines, raci, column=0)
    if not step_tables or raci_rows is None:
        return
    head = [cell_text(h).lower() for h in step_tables[0][1]]
    name_col = 1 if len(head) > 1 and head[0] in ("#", "nº", "n", "no") else 0
    for row_idx, cells in step_tables[0][2]:
        number = cell_text(cells[0]) if name_col == 1 else ""
        name = cell_text(cells[name_col]).lower() if name_col < len(cells) else ""
        if not any(name and name in r or (number and re.match(rf"^{re.escape(number)}\b", r)) for r in raci_rows):
            report.error("crossref", f"step `{name or number}` has no row in the RACI matrix", steps["start"] + row_idx + offset)


def check_crossref(lines, seen, bp, report, offset):
    for rule in bp["crossref"]:
        src, dst = seen.get(rule["from"]), seen.get(rule["to"])
        if not src or not dst or src["na"] or dst["na"]:
            continue
        tables = tables_in(lines[src["start"]:src["end"]])
        if not tables:
            continue
        if rule.get("to_header"):
            targets = _table_values(lines, dst, header=True)
        else:
            targets = _table_values(lines, dst, column=rule.get("to_column", 0))
        if targets is None:
            continue
        for row_idx, cells in tables[0][2]:
            if rule["column"] >= len(cells):
                continue
            value = cell_text(cells[rule["column"]])
            if value and value not in EMPTY_CELL_OK and not OPEN_CELL.match(value) and not _matches(value, targets):
                report.error("crossref", f"`{value}`: {rule['message']}", src["start"] + row_idx + offset)
    check_steps_in_raci(lines, seen, report, offset)


def check_sources(meta, lines, seen, report, offset):
    sources = wikilib.as_list(meta.get("sources"))
    refs = seen.get("references")
    if not sources or not refs:
        return
    text = wikilib.plain_text(visible_text(lines[refs["start"]:refs["end"]])).lower()
    for source in sources:
        if TEMPLATE_MARK.search(source):
            report.error("sources", f"source `{source}` is still a placeholder")
        elif wikilib.plain_text(source).lower() not in text:
            report.error("sources", f"source `{source}` (front matter) is not cited in `references`; copy the exact string there", refs["marker"] + offset)
        if not TEMPLATE_MARK.search(source) and not DATE_RE.search(source):
            report.warn("sources", f"source `{source}` has no date; add when it was written, retrieved or held")


def check_placeholders(lines, meta, report, offset):
    for idx, text in strip_code(lines):
        m = PLACEHOLDERS.search(text)
        if m:
            report.error("placeholders", f"placeholder left in the text: `{m.group(0)}`", idx + offset)
    for idx, line, in_code, _ in wikilib.iter_outside_code(lines):
        if in_code and TEMPLATE_MARK.search(line):
            report.error("placeholders", f"placeholder left in a code block: `{TEMPLATE_MARK.search(line).group(0)}`", idx + offset)
    for key, value in meta.items():
        for item in (value if isinstance(value, list) else [value]):
            if TEMPLATE_MARK.search(str(item)):
                report.error("placeholders", f"front matter `{key}` still has a placeholder: `{item}`")


def check_secrets(lines, report, offset, repo_values):
    for idx, line in enumerate(lines):
        for pattern, label in scan_repo.TOKEN_PATTERNS:
            if pattern.search(line):
                report.error("secrets", f"looks like a {label}; never copy credentials into the document", idx + offset)
        for m in re.finditer(r"""["']?([\w.:-]+)["']?\s*[:=]\s*["']([^"'\n]{3,})["']""", line):
            if scan_repo._secret_key(m.group(1)) and not scan_repo.PLACEHOLDER.match(m.group(2).strip()) and " " not in m.group(2).strip():
                report.error("secrets", f"`{m.group(1)}` has a literal value; write where the value lives and who provides it", idx + offset)
        for m in re.finditer(r"(?i)\b(password|pwd)\s*=\s*([^;\"'\s`|]{3,})", line):
            value = m.group(2)
            if not scan_repo.PLACEHOLDER.match(value) and not value.startswith(("{", "$", "%", "<", "*")):
                report.error("secrets", "connection string with a literal password; replace it with `...`", idx + offset)
    text = "\n".join(lines)
    for source, value in repo_values:
        if len(value) >= 6 and value in text:
            report.error("secrets", f"a credential committed in `{source}` is reproduced in the document; remove the value")


def check_anchors(body, report, offset):
    ids = {h["id"] for h in wikilib.outline(body)}
    ids |= set(re.findall(r"""\bid=["']([^"']+)["']""", body))
    lines = body.split("\n")
    for idx, text in strip_code(lines):
        for m in re.finditer(r"\]\(#([^)\s]+)\)", text):
            target = urllib.parse.unquote(m.group(1))
            if target not in ids:
                report.error("anchors", f"link to `#{target}` has no matching heading", idx + offset)


def check_mermaid(lines, report, offset):
    block, start = None, 0
    for idx, line, in_code, lang in wikilib.iter_outside_code(lines):
        if in_code and lang == "mermaid":
            if block is None:
                block, start = [], idx
            elif not wikilib.RE_FENCE.match(line):
                block.append((idx, line))
            else:
                _validate_diagram(block, start, report, offset)
                block = None
    if block is not None:
        report.error("mermaid", "unterminated mermaid block", start + offset)


def _validate_diagram(block, start, report, offset):
    content = [(i, ln) for i, ln in block if ln.strip()]
    if not content:
        report.error("mermaid", "empty mermaid diagram", start + offset)
        return
    first = content[0][1].strip()
    if not MERMAID_TYPES.match(first):
        report.error("mermaid", f"unknown diagram type `{first.split()[0]}`", content[0][0] + offset)
        return
    if re.match(r"^(flowchart|graph)\b", first):
        for i, ln in content[1:]:
            for m in FLOW_NODE.finditer(ln):
                label = m.group(2)
                if re.search(r"[()\[\]{}]", label):
                    report.error("mermaid", f"quote this node label (it has brackets/parentheses): `{label.strip()}`", i + offset)


def check_tables(lines, report, offset):
    for _, header, rows in tables_in(lines):
        for row_idx, cells in rows:
            if len(cells) != len(header):
                report.warn("tables", f"row has {len(cells)} cells, header has {len(header)} (escape pipes as \\|)", row_idx + offset)


def repo_files(roots):
    files = set()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not scan_repo.skip_dir(Path(dirpath), d, hidden=False)]
            if Path(dirpath) != root:
                files.add(Path(dirpath).relative_to(root).as_posix())
            for name in filenames:
                files.add((Path(dirpath) / name).relative_to(root).as_posix())
    return files


def top_level_dirs(roots):
    return {p.name for r in roots for p in r.iterdir() if p.is_dir() and not scan_repo.skip_dir(r, p.name, hidden=False)}


def check_source_commit(meta, root, report):
    """When the primary repo is a git work tree root, `source_commit` must exist in its history."""
    commit = str(meta.get("source_commit") or "")
    if not re.match(r"^[0-9a-f]{7,40}$", commit) or not shutil.which("git"):
        return
    top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
        return
    found = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True)
    if found.returncode != 0:
        report.error("front-matter", f"`source_commit` {commit} is not a commit of {root.name}; use `git rev-parse --short HEAD`")


def check_file_refs(lines, report, offset, files, top_dirs=frozenset(), roots=()):
    for idx, line, in_code, _ in wikilib.iter_outside_code(lines):
        if in_code or MISSING_FILE_HINT.search(wikilib.RE_CODE.sub("", line)):
            continue
        for m in wikilib.RE_CODE.finditer(line):
            ref = m.group(2).strip().rstrip(":").split(":")[0].split("#")[0]
            if (" " in ref or "://" in ref or "/" not in ref or ref.startswith(("/", "~", "$", "{", "..")) or "*" in ref
                    or "<" in ref or ".." in ref or not re.search(r"\.[A-Za-z0-9]{1,6}$", ref)):
                continue
            ref = ref[2:] if ref.startswith("./") else ref
            if any((root / ref).exists() for root in roots):
                continue
            if ref not in files and not any(f.endswith(ref) and f[-len(ref) - 1] in "/." for f in files if len(f) > len(ref)):
                parent = ref.rsplit("/", 1)[0]
                if ref.split("/")[0] in top_dirs and (parent in files or any(f.endswith("/" + parent) for f in files)):
                    report.error("file-refs", f"`{ref}` does not exist in the repo; fix the path", idx + offset)
                else:
                    report.warn("file-refs", f"`{ref}` not found in the repo (fine only if it lives in a repo not passed with --repo)", idx + offset)


def home_sections(fact, bp) -> tuple[str, list[str]]:
    """("any"|"all", sections) where a fact must be mentioned for this type."""
    home = bp["coverage"].get("home", {})
    spec = home.get("messaging_resource") if fact["kind"] == "iac_resource" and MESSAGING_TYPES.search(fact.get("detail") or "") \
        and "messaging_resource" in home else home.get(fact["kind"], [])
    if isinstance(spec, dict):
        return "all", spec.get("all", [])
    return "any", spec


def check_coverage(lines, sections, facts, bp, report, offset):
    ignores = {}
    for idx, line in enumerate(lines):
        for m in wikilib.RE_COVERAGE_IGNORE_ANY.finditer(line):
            full = wikilib.RE_COVERAGE_IGNORE.match(m.group(0))
            if not full or len(full.group(2).strip()) < 3:
                report.error("coverage", "coverage-ignore needs `<!-- coverage-ignore: <fact> | <reason> -->` on one line", idx + offset)
                continue
            ignores[full.group(1).strip().lower()] = full.group(2).strip()
    required_kinds = set(bp["coverage"].get("kinds", []))
    haystack = visible_text(lines)
    by_section = {s["id"]: s for s in sections}
    used_ignores = set()
    summary: dict[str, list[int]] = {}
    for fact in facts:
        if fact["kind"] not in required_kinds:
            continue
        stats = summary.setdefault(fact["kind"], [0, 0])
        stats[1] += 1
        names = {a.lower() for a in fact["aliases"]}
        hit_ignore = names & set(ignores)
        if hit_ignore:
            used_ignores |= hit_ignore
            stats[0] += 1
            continue
        where = fact["sources"][0] if fact["sources"] else ""
        label = f"{fact['kind']} `{fact['name']}` ({where})"
        if not _mentioned(haystack, fact):
            report.error("coverage", f"{label} is not mentioned; document it or add `<!-- coverage-ignore: {fact['name']} | reason -->`")
            continue
        mode, wanted = home_sections(fact, bp)
        homes = [by_section[h] for h in wanted if h in by_section]
        if homes:
            live = [h for h in homes if not h["na"]]
            if not live:
                report.error("coverage", f"{label} exists, but section `{homes[0]['id']}` is marked na", homes[0]["marker"] + offset)
                continue
            hits = [h for h in live if _mentioned(visible_text(lines[h["start"]:h["end"]]), fact)]
            if mode == "all" and len(hits) < len(live):
                missing = " and ".join(f"`{h['id']}`" for h in live if h not in hits)
                report.error("coverage", f"{label} must also be mentioned in section {missing}", live[0]["marker"] + offset)
                continue
            if not hits:
                names_ = " or ".join(f"`{h['id']}`" for h in live)
                report.error("coverage", f"{label} is mentioned, but not in section {names_}", live[0]["marker"] + offset)
                continue
        stats[0] += 1
    for key in set(ignores) - used_ignores:
        report.warn("coverage", f"coverage-ignore `{key}` does not match any fact")
    return summary


def _mentioned(text, fact) -> bool:
    if fact["kind"] == "route":
        method, _, path = fact["name"].partition(" ")
        return _path_mentioned(text, path, method.upper())
    if fact["kind"] == "screen":
        return _path_mentioned(text, fact["name"], "ANY")
    return any(_mentions(text, alias) for alias in fact["aliases"])


def _path_mentioned(text, path, method) -> bool:
    """Path (with any parameter syntax) and, for routes, the method on the same line."""
    pattern = re.escape(path)
    pattern = re.sub(r"\\\{[^}]*\\\}|:\w+\??|\\<[^>]*\\>|\\\[\\\[?[^\]]*\\\]\\\]?", r"[{:<\\[]?[\\w.+?-]+[}>\\]]?", pattern)
    path_re = re.compile(r"(?<![\w/-])" + pattern + r"(?![\w/-])", re.I)
    method_re = re.compile(r"\b" + re.escape(method) + r"\b", re.I)
    return any(path_re.search(line) and (method == "ANY" or method_re.search(line)) for line in text.split("\n"))


def _mentions(text, alias) -> bool:
    alias = alias.strip()
    if not alias:
        return False
    return re.search(r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])", text, re.I) is not None


def check_html(md_path, md_text, report):
    html_path = md_path.with_suffix(".html")
    if not html_path.is_file():
        report.error("html-sync", f"{html_path.name} is missing; run render_wiki.py {md_path.name}")
    elif render_wiki.html_digest(html_path.read_text(encoding="utf-8")) != wikilib.source_digest(md_text):
        report.error("html-sync", f"{html_path.name} is stale; run render_wiki.py {md_path.name}")


# ---------------------------------------------------------------- driver

def validate(md_path: Path, repos: list[Path], check_html_pair=True) -> tuple[Report, dict]:
    report = Report()
    md_text = md_path.read_text(encoding="utf-8")
    meta, body, first_line = wikilib.split_front_matter(md_text)
    offset = first_line
    lines = body.split("\n")

    bp = None
    doc_type = str(meta.get("type") or "")
    try:
        bp = wikilib.load_blueprint(doc_type) if doc_type else None
    except KeyError as exc:
        report.error("front-matter", exc.args[0])
    check_front_matter(meta, bp, report)
    parts, sections = parse_sections(lines)
    coverage = {}
    if bp:
        seen = check_structure(lines, parts, sections, bp, report, offset)
        check_crossref(lines, seen, bp, report, offset)
        check_sources(meta, lines, seen, report, offset)
    check_placeholders(lines, meta, report, offset)
    check_anchors(body, report, offset)
    check_mermaid(lines, report, offset)
    check_tables(lines, report, offset)

    repo_values = []
    if repos:
        scanned = scan_repo.scan(repos)
        for fact in scanned["facts"]:
            for value in fact.get("_values", []):
                repo_values.append((fact["name"], value))
        if bp:
            coverage = check_coverage(lines, sections, scanned["facts"], bp, report, offset)
        roots = [r.resolve() for r in repos]
        check_file_refs(lines, report, offset, repo_files(roots), top_level_dirs(roots), roots)
        check_source_commit(meta, roots[0], report)
    elif bp and bp["family"] == "code" and bp["coverage"].get("kinds"):
        report.warn("coverage", "coverage, file references and committed-secret checks were skipped: pass --repo <path>")
    check_secrets(lines, report, offset, repo_values)
    if check_html_pair:
        check_html(md_path, md_text, report)
    return report, coverage


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--repo", action="append", type=Path, default=[], help="repository root (repeat for multi-repo documents)")
    parser.add_argument("--no-html", action="store_true", help="skip the HTML sync check (before the first render)")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--json", action="store_true")
    sys.stdout.reconfigure(encoding="utf-8")
    args = parser.parse_args(argv)
    if not args.markdown.is_file():
        print(f"ERROR: {args.markdown} not found", file=sys.stderr)
        return 2
    for repo in args.repo:
        if not repo.is_dir():
            print(f"ERROR: --repo {repo} is not a directory", file=sys.stderr)
            return 2

    report, coverage = validate(args.markdown, args.repo, not args.no_html)
    failed = report.errors or (args.strict and report.items)
    if args.json:
        print(json.dumps({"ok": not failed, "items": report.items, "coverage": coverage}, indent=2, ensure_ascii=False))
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        for item in sorted(report.items, key=lambda i: (i["level"] != "ERROR", i["check"], i["line"] or 0)):
            where = f" (line {item['line']})" if item["line"] else ""
            print(f"{item['level']:5} [{item['check']}] {item['message']}{where}")
        if coverage:
            cov = ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(coverage.items()))
            print(f"coverage: {cov}")
        errors, warns = len(report.errors), len(report.items) - len(report.errors)
        print(f"{'FAIL' if failed else 'PASS'}: {errors} error(s), {warns} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
