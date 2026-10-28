#!/usr/bin/env python3
"""Lists the document types, prints a type's blueprint, or writes a document skeleton from it.

Usage:
    python new_doc.py --list
    python new_doc.py --print monolith [--lang pt-BR]
    python new_doc.py --type service --lang pt-BR --title "Serviço de Pedidos" --subject orders-service \
                      [--repo .] -o docs/wiki/orders-service.md

The skeleton has every marker, heading and table header in place; `<!-- guide: -->` comments and «…»
placeholders mark what must be written. validate_wiki.py fails while any of them remains.
"""
from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wikilib  # noqa: E402

TEXT = {
    "pt-BR": {
        "what_code": "**O que é este documento.** A fonte de verdade sobre «assunto»: o que é, por que existe e como funciona, conforme o código de «dd/mm/aaaa» (commit em `source_commit`).",
        "what_subject": "**O que é este documento.** A fonte de verdade sobre «assunto»: o que é, por que existe e como funciona, conforme as fontes listadas em [Referências](#referências) (a mais recente de «dd/mm/aaaa»).",
        "who": "**Para quem é.** Qualquer pessoa que precise entender, operar ou evoluir «assunto» sem depender de quem o conhece hoje.",
        "parts": "- **{p1}.** {d1}\n- **{p2}.** {d2}\n- **{p3}.** Riscos, perguntas em aberto, glossário e referências.",
        "d1": "O essencial, sem exigir conhecimento técnico.",
        "d2": "O detalhe para quem vai operar, manter ou evoluir.",
        "conventions_code": "**Convenções.**\n\n- Datas no formato dia/mês/ano; horários em Brasília, salvo quando indicado \"UTC\".\n- Termos e siglas estão no [Glossário](#glossário).\n- Nenhum segredo é reproduzido aqui: o documento diz **onde** cada valor está e **quem** o fornece.\n- O Markdown é a fonte; a página HTML é gerada a partir dele.",
        "conventions_subject": "**Convenções.**\n\n- Datas no formato dia/mês/ano; valores em reais (R$); prazos em dias corridos ou úteis, como nas fontes.\n- \"Em aberto\" numa tabela significa que nenhuma fonte responde; a pergunta está em [Perguntas em aberto](#perguntas-em-aberto).\n- Termos e siglas estão no [Glossário](#glossário).\n- O Markdown é a fonte; a página HTML é gerada a partir dele.",
        "tags_guide": "Se o documento cobre mais de uma aplicação, inclua a tabela de etiquetas (Etiqueta | Aplicação | Repositório) e declare as etiquetas no front matter; senão, remova a lista `tags`.",
        "maintenance_code": "**Como este documento é mantido.** O `.md` é a fonte de verdade e o `.html` é gerado a partir dele pela skill `document-anything`. Para atualizar, peça \"atualize a documentação\": o agente relê o código alterado desde o `source_commit`, ajusta as seções afetadas e valida o par novamente.",
        "maintenance_subject": "**Como este documento é mantido.** O `.md` é a fonte de verdade e o `.html` é gerado a partir dele pela skill `document-anything`. Para atualizar, peça \"atualize a documentação\" e entregue as fontes novas (nova versão de política, ata, entrevista): elas entram em `sources`, as seções afetadas são revistas e o par é validado novamente.",
        "one_sentence": "**Em uma frase:** «…»",
        "req": "obrigatória", "opt": "opcional: apague a seção se não se aplicar", "na": "pode ser marcada `na` com o motivo",
        "card": "- **«Título»** — «valor curto» | «uma frase»",
        "glossary_anchor": "glossário",
    },
    "en": {
        "what_code": "**What this document is.** The source of truth about «subject»: what it is, why it exists and how it works, as of the code on «YYYY-MM-DD» (commit in `source_commit`).",
        "what_subject": "**What this document is.** The source of truth about «subject»: what it is, why it exists and how it works, according to the sources listed in [References](#references) (the most recent from «YYYY-MM-DD»).",
        "who": "**Who it is for.** Anyone who needs to understand, operate or evolve «subject» without depending on the people who know it today.",
        "parts": "- **{p1}.** {d1}\n- **{p2}.** {d2}\n- **{p3}.** Risks, open questions, glossary and references.",
        "d1": "The essentials, no technical knowledge needed.",
        "d2": "The detail for whoever operates, maintains or evolves it.",
        "conventions_code": "**Conventions.**\n\n- Dates in ISO format (YYYY-MM-DD); times in UTC unless stated otherwise.\n- Terms and acronyms are in the [Glossary](#glossary).\n- No secret is reproduced here: the document says **where** each value lives and **who** provides it.\n- The Markdown is the source; the HTML page is generated from it.",
        "conventions_subject": "**Conventions.**\n\n- Dates in ISO format (YYYY-MM-DD); amounts and deadlines (calendar or business days) as in the sources.\n- \"Open\" in a table means no source answers it; the question is in [Open questions](#open-questions).\n- Terms and acronyms are in the [Glossary](#glossary).\n- The Markdown is the source; the HTML page is generated from it.",
        "tags_guide": "If the document covers more than one application, add the tag table (Tag | Application | Repository) and declare the tags in the front matter; otherwise remove the `tags` list.",
        "maintenance_code": "**How this document is maintained.** The `.md` is the source of truth and the `.html` is generated from it by the `document-anything` skill. To update it, ask to \"update the documentation\": the agent re-reads the code changed since `source_commit`, updates the affected sections and validates the pair again.",
        "maintenance_subject": "**How this document is maintained.** The `.md` is the source of truth and the `.html` is generated from it by the `document-anything` skill. To update it, ask to \"update the documentation\" and hand over the new sources (a new policy version, minutes, an interview): they go into `sources`, the affected sections are revised and the pair is validated again.",
        "one_sentence": "**In one sentence:** «…»",
        "req": "required", "opt": "optional: delete the section if it does not apply", "na": "may be marked `na` with the reason",
        "card": "- **«Title»** — «short value» | «one sentence»",
        "glossary_anchor": "glossary",
    },
}


def git_head(repo: Path | None) -> str:
    if not repo:
        return "«git rev-parse --short HEAD»"
    res = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else "«git rev-parse --short HEAD»"


def scaffold(section: dict, lang: str) -> list[str]:  # noqa: C901
    t = TEXT[lang]
    lines = []
    status = [t["req"] if section["required"] else t["opt"]]
    if section["na"]:
        status.append(t["na"])
    lines.append(f"<!-- guide: ({'; '.join(status)}) {section['must']} -->")
    lines.append("")
    checks = section["checks"]
    if (section.get("skeleton") or {}).get(lang):
        return lines + section["skeleton"][lang].rstrip("\n").split("\n") + [""]
    if "cards" in checks:
        lines += ["<!-- cards -->"] + [t["card"]] * 4 + ["<!-- /cards -->", "", t["one_sentence"], ""]
    if "mermaid" in checks:
        diagram = section.get("skeleton_diagram") or 'flowchart TD\n    A["«…»"] --> B["«…»"]'
        lines += ["```mermaid"] + diagram.split("\n") + ["```", ""]
    if "faq" in checks:
        q = ("<details markdown=\"1\">", "<summary>«Pergunta»</summary>" if lang == "pt-BR" else "<summary>«Question»</summary>", "", "«…»", "", "</details>", "")
        lines += list(q) * 3
    if "table" in checks:
        cols = (section.get("columns") or {}).get(lang) or ["«…»", "«…»"]
        lines += ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |",
                  "| " + " | ".join("«…»" for _ in cols) + " |", ""]
    if "code" in checks:
        lines += ["«Executado / copiado de … / derivado de …; não executado (exige …).»" if lang == "pt-BR"
                  else "«Run / copied from … / derived from …; not run (needs …).»", "", "```bash", "«…»", "```", ""]
    if "example" in checks:
        lines += ["```«language»", "«…»", "```", ""]
    if not checks or set(checks) <= {"dated"}:
        lines += [("Em «dd/mm/aaaa»: «…»" if lang == "pt-BR" else "As of «YYYY-MM-DD»: «…»") if "dated" in checks else "«…»", ""]
    return lines


def skeleton(bp: dict, lang: str, title: str, subject: str, repo: Path | None) -> str:
    t = TEXT[lang]
    code = bp["family"] == "code"
    today = datetime.date.today().isoformat()
    fm = ["---", f"title: {title}", "subtitle: «uma linha: o que é e para quem»" if lang == "pt-BR" else "subtitle: «one line: what it is and for whom»",
          f"type: {bp['type']}", f"subject: {subject}", f"lang: {lang}", f"as_of: {today}"]
    if code:
        repo_name = repo.resolve().name if repo else "«pasta do repositório»"
        fm += [f"source_commit: {git_head(repo)}", "repos:", f"  - {repo_name}", "tags:", "  - «Etiqueta»" if lang == "pt-BR" else "  - «Tag»"]
    else:
        fm += ["sources:", "  - «documento, link, transcrição ou pessoa entrevistada (com data)»" if lang == "pt-BR"
               else "  - «document, link, transcript or person interviewed (with date)»"]
    fm += [f"generator: document-anything {wikilib.VERSION}", "---", ""]
    family = "code" if code else "subject"
    out = fm + [f"# {title}", "", "> " + t["what_" + family], ">", "> " + t["who"], ""]
    titles = {p: bp["parts"][p][lang] for p in ("overview", "detail", "appendix")}
    for part in ("intro", "overview", "detail", "appendix"):
        if part != "intro":
            out += [f"<!-- part: {part} -->", f"# {titles[part]}", ""]
        for section in (s for s in bp["sections"] if s["part"] == part):
            out += [f"<!-- section: {section['id']} -->", f"## {section['title'][lang]}", ""]
            if section["id"] == "about":
                out += [t["parts"].format(p1=titles["overview"], d1=t["d1"], p2=titles["detail"], d2=t["d2"], p3=titles["appendix"]), ""]
                if code:
                    out += [f"<!-- guide: {t['tags_guide']} -->", ""]
                out += [t["conventions_" + family], ""]
            elif section["id"] == "references":
                out += scaffold(section, lang) + [t["maintenance_" + family], ""]
            else:
                out += scaffold(section, lang)
    return "\n".join(out).rstrip() + "\n"


def print_blueprint(bp: dict, lang: str) -> str:
    rows = [f"# Blueprint: {bp['type']} ({bp['label'][lang]})", "", bp["summary"], "",
            f"Family: {bp['family']}. " + ("Front matter needs `source_commit` and the coverage gate needs `--repo`." if bp["family"] == "code"
                                            else "Front matter needs `sources`; each source must be cited in `references`."), ""]
    if bp["coverage"]["kinds"]:
        homes = ", ".join(f"{k} → {'/'.join(v)}" for k, v in bp["coverage"]["home"].items())
        rows += [f"Coverage kinds required: {', '.join(bp['coverage']['kinds'])}.", f"Home sections: {homes or 'none'}.", ""]
    for x in bp["crossref"]:
        rows.append(f"Cross-check: {x['message']}.")
    rows += ["", "| Part | id | Heading | Status | Gate | Must contain |", "| --- | --- | --- | --- | --- | --- |"]
    for s in bp["sections"]:
        status = ("required" if s["required"] else "optional") + (", na allowed" if s["na"] else "")
        rows.append(f"| {s['part']} | `{s['id']}` | {s['title'][lang]} | {status} | {', '.join(s['checks']) or '—'} | {s['must'].replace('|', '/')} |")
    return "\n".join(rows) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list the document types")
    parser.add_argument("--print", metavar="TYPE", help="print the blueprint of a type")
    parser.add_argument("--type")
    parser.add_argument("--lang", default="pt-BR")
    parser.add_argument("--title")
    parser.add_argument("--subject")
    parser.add_argument("--repo", type=Path, help="primary repo (fills source_commit and repos; code types)")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--force", action="store_true", help="overwrite an existing file")
    sys.stdout.reconfigure(encoding="utf-8")
    args = parser.parse_args(argv)
    lang = wikilib.lang_key(args.lang)

    if args.list:
        for name in wikilib.available_types():
            bp = wikilib.load_blueprint(name)
            print(f"{name:10} {bp['family']:8} {bp['summary']}")
        return 0
    if args.print:
        try:
            print(print_blueprint(wikilib.load_blueprint(args.print), lang))
        except KeyError as exc:
            print(f"ERROR: {exc.args[0]}", file=sys.stderr)
            return 2
        return 0
    if not (args.type and args.title and args.subject and args.output):
        parser.error("--type, --title, --subject and -o are required to write a skeleton")
    try:
        bp = wikilib.load_blueprint(args.type)
    except KeyError as exc:
        print(f"ERROR: {exc.args[0]}", file=sys.stderr)
        return 2
    if args.output.exists() and not args.force:
        print(f"ERROR: {args.output} exists; update it instead of starting over (or pass --force)", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write(skeleton(bp, lang, args.title, args.subject, args.repo))
    print(f"OK: wrote {args.output} ({args.type}, {lang}, {len(bp['sections'])} sections)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
