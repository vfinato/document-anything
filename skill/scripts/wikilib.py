"""Shared core of the document-anything scripts: the Markdown dialect, slugs, markers and the HTML renderer.

Standard library only (Python 3.9+), so the skill runs wherever the agent can run Python.
The dialect is GitHub-flavoured Markdown plus a few conventions that an AI can write and a
human never has to see:

    ---                         front matter (flat YAML subset)
    <!-- part: overview -->     the next H1 opens a part: overview | detail | appendix (business/technical accepted)
    <!-- section: api -->       the next H2 is the blueprint section "api" (add " na" when not applicable)
    <!-- cards --> ... <!-- /cards -->   "- **Title** — Value | Description" items become a card grid
    <details markdown="1">      collapsible block whose body is Markdown
    ```mermaid                  diagram rendered in the browser
    > [!NOTE] / [!TIP] / [!IMPORTANT] / [!WARNING] / [!CAUTION]   callouts
    (Label)                     a tag declared in the front matter becomes a coloured pill
    <!-- coverage-ignore: fact | reason -->   accepted gap for validate_wiki.py
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

VERSION = "1.0.0"

PART_KINDS = ("intro", "overview", "detail", "appendix", "other")
PART_ALIASES = {"business": "overview", "technical": "detail"}
BLUEPRINT_DIR = Path(__file__).resolve().parent.parent / "blueprints"


def normalize_part(kind: str) -> str:
    kind = (kind or "").lower()
    return PART_ALIASES.get(kind, kind)


def available_types() -> list[str]:
    return sorted(p.stem for p in BLUEPRINT_DIR.glob("*.json") if p.stem != "common")


def load_blueprint(type_name: str) -> dict:
    """Merges blueprints/common.json with blueprints/<type>.json into one ready-to-use description.

    sections: list of {id, part, required, na, checks, title{lang}, must, columns{lang}?}, in document order.
    """
    path = BLUEPRINT_DIR / f"{type_name}.json"
    if not path.is_file():
        raise KeyError(f"unknown type `{type_name}`; available: {', '.join(available_types())}")
    common = json.loads((BLUEPRINT_DIR / "common.json").read_text(encoding="utf-8"))
    spec = json.loads(path.read_text(encoding="utf-8"))
    catalog = {k: dict(v) for k, v in common["sections"].items()}
    catalog.update({k: dict(v) for k, v in spec.get("extra_sections", {}).items()})
    for sid, override in spec.get("overrides", {}).items():
        catalog[sid] = {**catalog[sid], **override}
    sections = []
    for part, entries in spec["sections"].items():
        for entry in entries:
            optional = entry.endswith("?")
            sid = entry.rstrip("?")
            item = catalog[sid]
            sections.append({
                "id": sid, "part": part, "required": not optional, "na": bool(item.get("na")) and not optional,
                "checks": tuple(item.get("checks", ())), "title": item["title"], "must": item["must"],
                "columns": item.get("columns"), "skeleton": item.get("skeleton"), "skeleton_diagram": item.get("skeleton_diagram"),
            })
    return {
        "type": spec["type"], "family": spec["family"], "label": spec["label"], "summary": spec.get("summary", ""),
        "view_labels": spec.get("view_labels", {"pt-BR": ["Tudo", "Visão geral", "Detalhe"], "en": ["All", "Overview", "Detail"]}),
        "parts": {**common["parts"], **spec.get("parts", {})},
        "sections": sections,
        "coverage": spec.get("coverage", {"kinds": [], "home": {}}),
        "crossref": spec.get("crossref", []),
        "sources_required": bool(spec.get("sources_required")),
    }


def lang_key(lang: str) -> str:
    return "pt-BR" if str(lang or "").lower().startswith("pt") else "en"


RE_FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
RE_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
RE_HR = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
RE_LIST = re.compile(r"^( *)([-*+]|\d{1,9}[.)])( +|$)(.*)$")
RE_TABLE_DELIM = re.compile(r"^ *\|? *:?-+:? *(\| *:?-+:? *)*\|? *$")
RE_HTML_BLOCK = re.compile(
    r"^ {0,3}</?(details|summary|div|section|figure|figcaption|table|thead|tbody|tfoot|tr|td|th|p|br|hr|img"
    r"|ul|ol|li|dl|dt|dd|pre|blockquote|aside|nav|center|h[1-6])\b",
    re.I,
)
RE_PART = re.compile(r"^<!--\s*part:\s*([\w-]+)\s*-->$", re.I)
RE_SECTION = re.compile(r"^<!--\s*section:\s*([\w-]+)(?:\s+(na))?\s*-->$", re.I)
RE_CARDS_OPEN = re.compile(r"^\s*<!--\s*cards\s*-->\s*$", re.I)
RE_CARDS_CLOSE = re.compile(r"^\s*<!--\s*/cards\s*-->\s*$", re.I)
RE_CARD = re.compile(r"^[-*+]\s+\*\*(.+?)\*\*\s*(?:—|–|-|:)\s*(.*?)\s*(?:\|\s*(.*))?$")
RE_COVERAGE_IGNORE = re.compile(r"<!--\s*coverage-ignore:\s*([^|\n]+?)\s*\|\s*([^\n]*?)\s*-->")
RE_COVERAGE_IGNORE_ANY = re.compile(r"<!--\s*coverage-ignore:([^\n]*?)-->")

RE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
RE_RAW_INLINE = re.compile(
    r"</?(?:code|kbd|br|sub|sup|b|i|em|strong|span|a|mark|small|s|del|ins|abbr|u|wbr)\b[^<>]*>", re.I
)
RE_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"([^\"]*)\")?\s*\)")
RE_LINK = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])+)\]\(\s*<?([^)\s>]+)>?(?:\s+\"([^\"]*)\")?\s*\)")
RE_BARE_URL = re.compile(r"(?<![\"'=/\w])(https?://[^\s<>\"'\x00]+)")

CALLOUT_LABELS = {
    "pt-BR": {"note": "Nota", "tip": "Dica", "important": "Importante", "warning": "Atenção", "caution": "Cuidado"},
    "en": {"note": "Note", "tip": "Tip", "important": "Important", "warning": "Warning", "caution": "Caution"},
}


# ---------------------------------------------------------------- text helpers

def normalize(text: str) -> str:
    """Normalises newlines, drops a BOM and expands leading tabs so indentation rules hold."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    return "\n".join(_expand_leading_tabs(line) for line in text.split("\n"))


def _expand_leading_tabs(line: str) -> str:
    stripped = line.lstrip(" \t")
    return line[: len(line) - len(stripped)].expandtabs(4) + stripped


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def esc_attr(text: str) -> str:
    return html.escape(text, quote=True)


def source_digest(md_text: str) -> str:
    """Hash of the Markdown source; the HTML carries it so validators can prove the pair is in sync."""
    return hashlib.sha256(normalize(md_text).encode("utf-8")).hexdigest()


def plain_text(md_inline: str) -> str:
    """Inline Markdown reduced to the visible text (used for slugs, TOC and checks)."""
    t = RE_CODE.sub(lambda m: m.group(2).strip(), md_inline)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\*+|~~", "", t)
    return html.unescape(t).strip()


def slugify(text: str) -> str:
    t = plain_text(text).lower()
    t = re.sub(r"[^\w\s-]", "", t)
    return re.sub(r"[-\s]+", "-", t).strip("-") or "section"


class SlugRegistry:
    """Unique heading ids in document order; the renderer and the validator must share it."""

    def __init__(self) -> None:
        self.seen: dict[str, int] = {}

    def make(self, text: str, explicit: str | None = None) -> str:
        base = explicit or slugify(text)
        count = self.seen.get(base, 0)
        self.seen[base] = count + 1
        return base if count == 0 else f"{base}-{count}"


def split_heading_id(text: str) -> tuple[str, str | None]:
    m = re.search(r"\s*\{#([\w-]+)\}\s*$", text)
    return (text[: m.start()], m.group(1)) if m else (text, None)


# ---------------------------------------------------------------- front matter

def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_simple_yaml(raw: str) -> dict:
    """Flat YAML subset: `key: value`, `key: [a, b]` and `key:` followed by `  - item` lines."""
    meta: dict = {}
    current = None
    for line in raw.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s*(.*)$", line)
        if item and current is not None:
            if not isinstance(meta.get(current), list):
                meta[current] = []
            meta[current].append(_unquote(item.group(1)))
            continue
        pair = re.match(r"^([\w.-]+)\s*:\s*(.*)$", line)
        if pair:
            current, value = pair.group(1), pair.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                meta[current] = [_unquote(v) for v in value[1:-1].split(",") if v.strip()]
            else:
                meta[current] = _unquote(value) if value else []
    return meta


def split_front_matter(text: str) -> tuple[dict, str, int]:
    """Returns (meta, body, first_body_line) where first_body_line is 1-based."""
    text = normalize(text)
    if not text.startswith("---\n"):
        return {}, text, 1
    lines = text.split("\n")
    for idx in range(1, len(lines)):
        if lines[idx].strip() in ("---", "..."):
            return parse_simple_yaml("\n".join(lines[1:idx])), "\n".join(lines[idx + 1:]), idx + 2
    return {}, text, 1


def as_list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


# ---------------------------------------------------------------- outline (shared with the validator)

def iter_outside_code(lines: list[str]):
    """Yields (index, line, in_code, fence_lang); fence delimiter lines report in_code=True."""
    fence = None
    lang = ""
    for idx, line in enumerate(lines):
        m = RE_FENCE.match(line)
        if fence is None and m and "`" not in m.group(3):
            fence, lang = m.group(2), (m.group(3).strip().split() or [""])[0].lower()
            yield idx, line, True, lang
            continue
        if fence is not None:
            if re.match(r"^\s*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", line):
                fence = None
            yield idx, line, True, lang
            continue
        yield idx, line, False, ""


def outline(body: str) -> list[dict]:
    """Headings with the same ids the renderer assigns (front matter must already be stripped)."""
    registry = SlugRegistry()
    result = []
    for idx, line, in_code, _ in iter_outside_code(body.split("\n")):
        if in_code:
            continue
        m = RE_HEADING.match(line)
        if m:
            text, explicit = split_heading_id(m.group(2))
            result.append({"level": len(m.group(1)), "text": plain_text(text), "raw": text,
                           "id": registry.make(text, explicit), "index": idx})
    return result


def guess_part(text: str, index: int) -> str:
    t = text.lower()
    if re.search(r"neg[oó]cio|business|macro|vis[aã]o geral|overview|produto|product|para quem usa|for users", t):
        return "overview"
    if re.search(r"detalh|t[eé]cnic|technical|develop|desenvolv|engenharia|engineering|passo a passo|step by step|mant[eé]m|maintain", t):
        return "detail"
    if re.search(r"apoio|ap[eê]ndice|appendix|anexo|support|refer[eê]ncia|reference", t):
        return "appendix"
    return "intro" if index == 0 else "other"


# ---------------------------------------------------------------- renderer

def split_row(line: str) -> list[str]:
    """Splits a table row on pipes that are neither escaped nor inside code spans."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]

    def split(respect_code: bool) -> tuple[list[str], bool]:
        cells, buf, code, k = [], [], 0, 0
        while k < len(s):
            c = s[k]
            if c == "\\" and k + 1 < len(s) and s[k + 1] == "|":
                buf.append("|")
                k += 2
                continue
            if c == "`" and respect_code:
                run = len(s[k:]) - len(s[k:].lstrip("`"))
                code = run if code == 0 else (0 if code == run else code)
                buf.append("`" * run)
                k += run
                continue
            if c == "|" and code == 0:
                cells.append("".join(buf).strip())
                buf = []
            else:
                buf.append(c)
            k += 1
        cells.append("".join(buf).strip())
        return cells, code == 0

    cells, balanced = split(True)
    return cells if balanced else split(False)[0]


def _align(cell: str) -> str:
    c = cell.strip()
    if c.startswith(":") and c.endswith(":"):
        return "center"
    if c.endswith(":"):
        return "right"
    return "left" if c.startswith(":") else ""


class Renderer:
    def __init__(self, tags=(), lang: str = "pt-BR") -> None:
        self.tags = [t for t in tags if t]
        self.lang = lang if lang in CALLOUT_LABELS else ("pt-BR" if lang.lower().startswith("pt") else "en")
        self.slugs = SlugRegistry()
        self.mermaid = 0

    # ---------- block level

    def blocks(self, lines: list[str], top: bool = False) -> list:
        out: list = []
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            s = line.strip()
            if not s:
                i += 1
                continue
            m = RE_FENCE.match(line)
            if m and ("`" not in m.group(3) or m.group(2)[0] == "~"):
                i = self._fence(lines, i, m, out)
            elif s.startswith("<!--"):
                i = self._comment(lines, i, out, top)
            elif RE_HEADING.match(line):
                self._heading(RE_HEADING.match(line), out, top)
                i += 1
            elif RE_HR.match(line):
                out.append("<hr>")
                i += 1
            elif s.startswith(">"):
                i = self._blockquote(lines, i, out)
            elif self._is_table(lines, i):
                i = self._table(lines, i, out)
            elif RE_LIST.match(line):
                i = self._list(lines, i, out)
            elif RE_HTML_BLOCK.match(line):
                i = self._html(lines, i, out)
            else:
                i = self._paragraph(lines, i, out)
        return out

    def _starts_block(self, line: str) -> bool:
        s = line.strip()
        return bool(
            RE_FENCE.match(line) or RE_HEADING.match(line) or RE_HR.match(line) or s.startswith(">")
            or RE_LIST.match(line) or RE_HTML_BLOCK.match(line) or s.startswith("<!--")
        )

    def _fence(self, lines, i, m, out) -> int:
        indent, fence, info = len(m.group(1)), m.group(2), m.group(3).strip()
        lang = info.split()[0].lower() if info else ""
        close = re.compile(r"^\s*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
        body, j = [], i + 1
        while j < len(lines) and not close.match(lines[j]):
            raw = lines[j]
            body.append(raw[indent:] if raw[:indent].strip() == "" else raw.lstrip())
            j += 1
        code = "\n".join(body)
        if lang == "mermaid":
            self.mermaid += 1
            out.append(f'<div class="diagram"><pre class="mermaid">{esc(code)}</pre></div>')
        else:
            cls = f' class="language-{esc_attr(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{esc(code)}</code></pre>")
        return j + 1

    def _comment(self, lines, i, out, top) -> int:
        if RE_CARDS_OPEN.match(lines[i]):
            return self._cards(lines, i + 1, out)
        buf, j = [], i
        while j < len(lines):
            buf.append(lines[j])
            if "-->" in lines[j]:
                break
            j += 1
        text = "\n".join(buf).strip()
        if top:
            part = RE_PART.match(text)
            section = RE_SECTION.match(text)
            if part:
                out.append(("part", part.group(1).lower()))
            elif section:
                out.append(("section", section.group(1).lower()))
        trailing = text.split("-->", 1)[1].strip() if "-->" in text else ""
        if trailing:
            out.extend(self.blocks([trailing]))
        return j + 1

    def _cards(self, lines, i, out) -> int:
        cards, j = [], i
        while j < len(lines) and not RE_CARDS_CLOSE.match(lines[j]):
            s = lines[j].strip()
            m = RE_CARD.match(s) if s else None
            if m:
                cards.append([m.group(1), m.group(2) or "", m.group(3) or ""])
            elif s and cards:
                cards[-1][2] = (cards[-1][2] + " " + s).strip()
            j += 1
        items = "".join(
            f'<div class="card"><div class="card-title">{self.inline(t)}</div>'
            f'<div class="card-value">{self.inline(v)}</div><div class="card-desc">{self.inline(d)}</div></div>'
            for t, v, d in cards
        )
        out.append(f'<div class="cards">{items}</div>')
        return j + 1

    def _heading(self, m, out, top) -> None:
        level = len(m.group(1))
        text, explicit = split_heading_id(m.group(2))
        hid = self.slugs.make(text, explicit)
        rendered = f'<h{level} id="{esc_attr(hid)}">{self.inline(text)}</h{level}>'
        if top and level <= 2:
            out.append(("h", level, hid, plain_text(text), rendered))
        else:
            out.append(rendered)

    def _blockquote(self, lines, i, out) -> int:
        buf, j = [], i
        while j < len(lines):
            raw = lines[j]
            if raw.strip().startswith(">"):
                buf.append(re.sub(r"^\s*> ?", "", raw, count=1))
            elif raw.strip() and buf and buf[-1].strip() and not self._starts_block(raw):
                buf.append(raw)
            else:
                break
            j += 1
        kind = None
        if buf:
            m = re.match(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$", buf[0].strip(), re.I)
            if m:
                kind = m.group(1).lower()
                buf = ([m.group(2)] if m.group(2) else []) + buf[1:]
        inner = "\n".join(self.blocks(buf))
        if kind:
            label = CALLOUT_LABELS[self.lang][kind]
            out.append(f'<blockquote class="callout {kind}"><p class="callout-title">{label}</p>\n{inner}\n</blockquote>')
        else:
            out.append(f"<blockquote>\n{inner}\n</blockquote>")
        return j

    def _is_table(self, lines, i) -> bool:
        return (
            "|" in lines[i] and i + 1 < len(lines) and "|" in lines[i + 1] and "-" in lines[i + 1]
            and RE_TABLE_DELIM.match(lines[i + 1]) is not None
        )

    def _table(self, lines, i, out) -> int:
        header = split_row(lines[i])
        aligns = [_align(c) for c in split_row(lines[i + 1])]
        rows, j = [], i + 2
        while j < len(lines) and lines[j].strip() and "|" in lines[j] and not lines[j].strip().startswith("<!--"):
            rows.append(split_row(lines[j]))
            j += 1
        ncol = len(header)

        def cell(tag, text, col):
            a = aligns[col] if col < len(aligns) else ""
            style = f' style="text-align:{a}"' if a else ""
            return f"<{tag}{style}>{self.inline(text)}</{tag}>"

        head = "".join(cell("th", h, c) for c, h in enumerate(header))
        body = "\n".join(
            "<tr>" + "".join(cell("td", (row + [""] * ncol)[c], c) for c in range(ncol)) + "</tr>" for row in rows
        )
        out.append(f'<div class="table-wrap"><table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n{body}\n</tbody>\n</table></div>')
        return j

    def _list(self, lines, i, out) -> int:
        first = RE_LIST.match(lines[i])
        base = len(first.group(1))
        ordered = first.group(2)[0].isdigit()
        start = int(first.group(2)[:-1]) if ordered else 1
        items, loose, j = [], False, i
        while j < len(lines):
            m = RE_LIST.match(lines[j])
            if not m or RE_HR.match(lines[j]) or abs(len(m.group(1)) - base) > 1 or m.group(2)[0].isdigit() != ordered:
                break
            spaces = len(m.group(3)) if m.group(4) else 1
            width = len(m.group(1)) + len(m.group(2)) + (spaces if spaces <= 4 else 1)
            content, j, blank = [m.group(4)], j + 1, False
            while j < len(lines):
                raw = lines[j]
                if not raw.strip():
                    content.append("")
                    blank = True
                    j += 1
                    continue
                indent = len(raw) - len(raw.lstrip(" "))
                if indent >= width:
                    content.append(raw[width:])
                    blank = False
                    j += 1
                    continue
                if blank or RE_LIST.match(raw) or self._starts_block(raw):
                    break
                content.append(raw.strip())
                j += 1
            trailing_blank = bool(content) and not content[-1].strip()
            while content and not content[-1].strip():
                content.pop()
            if "" in content:
                loose = True
            nxt = RE_LIST.match(lines[j]) if j < len(lines) else None
            if trailing_blank and nxt and abs(len(nxt.group(1)) - base) <= 1:
                loose = True
            items.append(content)
        rendered = []
        for content in items:
            task = None
            if content:
                mt = re.match(r"^\[([ xX])\]\s+", content[0])
                if mt:
                    task = mt.group(1).lower() == "x"
                    content = [content[0][mt.end():]] + content[1:]
            parts = self.blocks(content)
            if not loose:
                parts = [p[3:-4] if isinstance(p, str) and p.startswith("<p>") and p.endswith("</p>") else p for p in parts]
            body = "\n".join(p for p in parts if isinstance(p, str))
            if task is None:
                rendered.append(f"<li>{body}</li>")
            else:
                box = '<input type="checkbox" disabled' + (" checked" if task else "") + ">"
                rendered.append(f'<li class="task">{box} {body}</li>')
        tag = "ol" if ordered else "ul"
        attr = f' start="{start}"' if ordered and start != 1 else ""
        out.append(f"<{tag}{attr}>\n" + "\n".join(rendered) + f"\n</{tag}>")
        return j

    def _html(self, lines, i, out) -> int:
        line = re.sub(r"\s+markdown=(\"1\"|'1'|1)", "", lines[i].strip())
        m = re.match(r"^<summary>(.*)</summary>$", line, re.S)
        out.append(f"<summary>{self.inline(m.group(1))}</summary>" if m else line)
        return i + 1

    def _paragraph(self, lines, i, out) -> int:
        buf, j = [lines[i]], i + 1
        while j < len(lines) and lines[j].strip() and not self._starts_block(lines[j]) and not self._is_table(lines, j):
            buf.append(lines[j])
            j += 1
        joined = []
        for k, raw in enumerate(buf):
            text = raw.strip()
            if k < len(buf) - 1 and (raw.endswith("  ") or text.endswith("\\")):
                text = text.rstrip("\\").rstrip() + "\x02"
            joined.append(text)
        out.append("<p>" + self.inline("\n".join(joined)).replace("\x02", "<br>") + "</p>")
        return j

    # ---------- inline level

    def inline(self, text: str) -> str:
        holder: list[str] = []

        def keep(fragment: str) -> str:
            holder.append(fragment)
            return f"\x00{len(holder) - 1}\x00"

        s = self._inline(text, keep)
        while "\x00" in s:
            s = re.sub(r"\x00(\d+)\x00", lambda m: holder[int(m.group(1))], s)
        return s

    def _inline(self, s: str, keep) -> str:
        s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
        s = RE_CODE.sub(lambda m: keep("<code>" + esc(_code_strip(m.group(2))) + "</code>"), s)
        s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|<>~])", lambda m: keep(esc(m.group(1))), s)
        s = re.sub(r"<(https?://[^\s<>]+)>", lambda m: keep(f'<a href="{esc_attr(m.group(1))}">{esc(m.group(1))}</a>'), s)
        s = RE_RAW_INLINE.sub(lambda m: keep(m.group(0)), s)
        s = RE_IMAGE.sub(lambda m: keep(f'<img src="{esc_attr(m.group(2))}" alt="{esc_attr(m.group(1))}">'), s)
        s = RE_LINK.sub(
            lambda m: keep(f'<a href="{esc_attr(m.group(2))}"'
                           + (f' title="{esc_attr(m.group(3))}"' if m.group(3) else "")
                           + ">" + self._inline(m.group(1), keep) + "</a>"),
            s,
        )
        s = esc(s)
        s = RE_BARE_URL.sub(lambda m: _bare_url(m.group(1), keep), s)
        s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", s, flags=re.S)
        s = re.sub(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", r"<strong>\1</strong>", s, flags=re.S)
        s = re.sub(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])", r"<em>\1</em>", s, flags=re.S)
        s = re.sub(r"(?<!\w)_(?=[^\s_])(.+?)(?<=[^\s_])_(?!\w)", r"<em>\1</em>", s, flags=re.S)
        s = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<del>\1</del>", s, flags=re.S)
        for idx, label in enumerate(self.tags):
            s = s.replace(f"({esc(label)})", keep(f'<span class="tag t{idx % 8}">{esc(label)}</span>'))
        return s


def _code_strip(code: str) -> str:
    code = code.replace("\n", " ")
    if len(code) > 2 and code[0] == " " and code[-1] == " " and code.strip():
        return code[1:-1]
    return code


def _bare_url(url: str, keep) -> str:
    trail = ""
    while url and url[-1] in ".,;:!?)":
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        trail = url[-1] + trail
        url = url[:-1]
    return keep(f'<a href="{url}">{url}</a>') + trail


# ---------------------------------------------------------------- document

class Document:
    def __init__(self, meta, body_html, toc, mermaid, title):
        self.meta, self.body_html, self.toc, self.mermaid, self.title = meta, body_html, toc, mermaid, title


def render_document(md_text: str, tags=None, lang: str | None = None) -> Document:
    """Renders the Markdown body and wraps H1 in parts and H2 in searchable sections."""
    meta, body, _ = split_front_matter(md_text)
    tags = as_list(meta.get("tags")) if tags is None else tags
    lang = lang or str(meta.get("lang") or "pt-BR")
    renderer = Renderer(tags, lang)
    tokens = renderer.blocks(body.split("\n"), top=True)

    out: list[str] = []
    toc: list[dict] = []
    state = {"part": False, "sec": False}
    pending_part = pending_section = None
    depth = h1_count = 0
    title = str(meta.get("title") or "")

    def close_section():
        if state["sec"]:
            out.append("</section>")
            state["sec"] = False

    def open_part(kind):
        close_section()
        if state["part"]:
            out.append("</div>")
        out.append(f'<div class="part" data-part="{kind}">')
        state["part"] = True

    for token in tokens:
        if isinstance(token, tuple) and token[0] == "part":
            pending_part = normalize_part(token[1])
            continue
        if isinstance(token, tuple) and token[0] == "section":
            pending_section = token[1]
            continue
        if isinstance(token, tuple):
            _, level, hid, text, rendered = token
            if depth == 0 and level == 1:
                kind = pending_part if pending_part in PART_KINDS else guess_part(text, h1_count)
                open_part(kind)
                out.append(rendered)
                toc.append({"id": hid, "text": text, "children": []})
                title = title or text
                h1_count += 1
                pending_part = None
                continue
            if depth == 0 and level == 2:
                if not state["part"]:
                    open_part("intro")
                close_section()
                data = f' data-section="{esc_attr(pending_section)}"' if pending_section else ""
                out.append(f'<section class="sec"{data}>{rendered}')
                state["sec"] = True
                pending_section = None
                if not toc:
                    toc.append({"id": None, "text": "", "children": []})
                toc[-1]["children"].append({"id": hid, "text": text})
                continue
            token = rendered
        if not state["part"]:
            open_part("intro")
        out.append(token)
        depth = max(0, depth + len(re.findall(r"<details\b", token)) - token.count("</details>"))

    close_section()
    if state["part"]:
        out.append("</div>")
    return Document(meta, "\n".join(out), toc, renderer.mermaid, title)
