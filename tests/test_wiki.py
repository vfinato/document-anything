"""Tests for the document-anything scripts. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill"
SCRIPTS = SKILL / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "orders-service"
WIKI = FIXTURE / "docs" / "wiki" / "orders-service.md"
FIXTURES = ROOT / "tests" / "fixtures"
PROCESS_DOC = FIXTURES / "month-end-close" / "docs" / "process" / "fechamento-mensal.md"
sys.path.insert(0, str(SCRIPTS))

import new_doc  # noqa: E402
import render_wiki  # noqa: E402
import scan_repo  # noqa: E402
import validate_wiki  # noqa: E402
import wikilib  # noqa: E402


def render(md: str, tags=()) -> str:
    return wikilib.render_document(md, tags=list(tags)).body_html


class InlineTests(unittest.TestCase):
    def setUp(self):
        self.r = wikilib.Renderer(["Service"])

    def test_code_spans_are_escaped_and_protected(self):
        self.assertEqual(self.r.inline("`a <b> **c**`"), "<code>a &lt;b&gt; **c**</code>")

    def test_emphasis_and_links(self):
        out = self.r.inline("**bold** *it* [x](#y) ~~no~~")
        self.assertEqual(out, '<strong>bold</strong> <em>it</em> <a href="#y">x</a> <del>no</del>')

    def test_snake_case_is_not_italic(self):
        self.assertEqual(self.r.inline("use snake_case_name here"), "use snake_case_name here")

    def test_tags_become_pills_outside_code(self):
        out = self.r.inline("runs in (Service) not `(Service)`")
        self.assertIn('<span class="tag t0">Service</span>', out)
        self.assertIn("<code>(Service)</code>", out)

    def test_html_is_escaped_except_whitelist(self):
        self.assertEqual(self.r.inline("List<string> a<br>b"), "List&lt;string&gt; a<br>b")

    def test_bare_url_keeps_trailing_punctuation_out(self):
        self.assertEqual(self.r.inline("see https://x.io/a."), 'see <a href="https://x.io/a">https://x.io/a</a>.')

    def test_comments_are_dropped(self):
        self.assertEqual(self.r.inline("a <!-- hidden --> b"), "a  b")


class BlockTests(unittest.TestCase):
    def test_list_without_blank_line_after_paragraph(self):
        html = render("Intro:\n- one\n- two\n")
        self.assertIn("<p>Intro:</p>", html)
        self.assertIn("<ul>\n<li>one</li>\n<li>two</li>\n</ul>", html)

    def test_nested_and_ordered_lists(self):
        html = render("1. a\n   - b\n2. c\n")
        self.assertRegex(html, r"<ol>\n<li>a\n<ul>\n<li>b</li>\n</ul></li>\n<li>c</li>\n</ol>")

    def test_table_with_escaped_pipe_and_code_pipe(self):
        html = render("| A | B |\n| --- | :-: |\n| x \\| y | `a|b` |\n")
        self.assertIn("<td>x | y</td>", html)
        self.assertIn('<td style="text-align:center"><code>a|b</code></td>', html)

    def test_cards(self):
        html = render("<!-- cards -->\n- **Goal** — Value | Desc\n<!-- /cards -->\n")
        self.assertIn('<div class="card-title">Goal</div><div class="card-value">Value</div><div class="card-desc">Desc</div>', html)

    def test_details_with_markdown_body(self):
        html = render('<details markdown="1" open>\n<summary>Title `x`</summary>\n\n**b**\n\n</details>\n')
        self.assertIn("<details open>", html)
        self.assertIn("<summary>Title <code>x</code></summary>", html)
        self.assertIn("<p><strong>b</strong></p>", html)

    def test_mermaid_is_escaped_text(self):
        html = render('```mermaid\nflowchart TD\n  A["x<br/>y"] --> B\n```\n')
        self.assertIn('<pre class="mermaid">flowchart TD\n  A["x&lt;br/&gt;y"] --&gt; B</pre>', html)

    def test_callout(self):
        html = render("> [!WARNING]\n> careful\n")
        self.assertIn('<blockquote class="callout warning"><p class="callout-title">Atenção</p>', html)

    def test_parts_and_sections(self):
        md = "# Title\n\nintro\n\n<!-- part: business -->\n# Part I\n\n<!-- section: summary -->\n## Summary\n\ntext\n"
        doc = wikilib.render_document(md)
        self.assertIn('<div class="part" data-part="intro"><h1 id="title">', doc.body_html.replace("\n", ""))
        self.assertIn('<div class="part" data-part="overview">', doc.body_html)
        self.assertIn('<section class="sec" data-section="summary"><h2 id="summary">Summary</h2>', doc.body_html)
        self.assertEqual([t["text"] for t in doc.toc], ["Title", "Part I"])

    def test_heading_slugs_match_outline(self):
        md = "# Parte I — Visão (negócio)\n## Onde estamos (30/09/2026)\n## Onde estamos (30/09/2026)\n"
        ids = [h["id"] for h in wikilib.outline(md)]
        self.assertEqual(ids, ["parte-i-visão-negócio", "onde-estamos-30092026", "onde-estamos-30092026-1"])
        html = render(md)
        for hid in ids:
            self.assertIn(f'id="{hid}"', html)


class RenderPageTests(unittest.TestCase):
    def test_page_is_deterministic_and_self_contained(self):
        md = WIKI.read_text(encoding="utf-8")
        a = render_wiki.build_page(md, "orders-service.md")
        b = render_wiki.build_page(md, "orders-service.md")
        self.assertEqual(a, b)
        self.assertNotRegex(a, r'<link[^>]+stylesheet')
        scripts = re.findall(r'<script src="([^"]+)"', a)
        self.assertEqual(scripts, [render_wiki.MERMAID_CDN])
        self.assertIn(wikilib.source_digest(md), a)

    def test_committed_fixture_html_is_in_sync(self):
        self.assertEqual(render_wiki.main([str(WIKI), "--check"]), 0)


class ScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = scan_repo.scan([FIXTURE])
        cls.by_kind = {}
        for f in cls.report["facts"]:
            cls.by_kind.setdefault(f["kind"], set()).add(f["name"])

    def test_finds_every_kind_of_fact(self):
        k = self.by_kind
        self.assertEqual(k["environment"], {"dev", "prod"})
        self.assertEqual(k["iac_resource"], {"ApiFunction", "ExpireOrdersFunction", "OrderCreatedQueue"})
        self.assertTrue({"Database__Server", "Expiration__Hours", "SSM__Prefix", "ORDERS_DEBUG"} <= k["env_var"])
        self.assertEqual(k["config_key"], {"Database", "Payments", "SSM"})
        self.assertIn("/orders-service/prod", k["parameter_ref"])
        self.assertEqual(k["route"], {"ANY /{proxy+}", "GET /health", "GET /orders/{id}", "POST /orders"})
        self.assertEqual(k["iac_parameter"], {"Stage", "SSMPrefix"})
        self.assertEqual(k["schedule"], {"ExpireOrdersSchedule"})
        self.assertEqual(k["pipeline"], {"azure-pipelines.yml"})
        self.assertEqual(k["local_dependency"], {"postgres"})
        self.assertEqual(k["test_suite"], {"Orders.Tests"})
        self.assertEqual(k["plaintext_secret"], {"src/Orders.Api/appsettings.json", "src/docker-compose.yml"})

    def test_public_output_never_contains_secret_values(self):
        text = json.dumps(scan_repo.public(self.report)) + scan_repo.to_markdown(scan_repo.public(self.report))
        self.assertNotIn("local-orders-pass", text)

    def test_yamlish_handles_cloudformation_tags(self):
        doc = scan_repo.parse_yamlish("A:\n  B: !Sub x-${Y}\n  C:\n    - !Ref Z\n    - k: v\n")
        self.assertEqual(doc, {"A": {"B": "!Sub x-${Y}", "C": ["!Ref Z", {"k": "v"}]}})


class ValidateTests(unittest.TestCase):
    def run_validate(self, md_text: str, html=True):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wiki.md"
            path.write_text(md_text, encoding="utf-8")
            if html:
                path.with_suffix(".html").write_text(render_wiki.build_page(md_text, "wiki.md"), encoding="utf-8")
            report, coverage = validate_wiki.validate(path, [FIXTURE], check_html_pair=True)
            return report, coverage

    def checks(self, report):
        return {i["check"] for i in report.errors}

    def setUp(self):
        self.md = WIKI.read_text(encoding="utf-8")

    def test_fixture_passes(self):
        report, coverage = self.run_validate(self.md)
        self.assertEqual(report.errors, [])
        self.assertTrue(all(v[0] == v[1] for v in coverage.values()))

    def test_missing_required_section(self):
        md = self.md.replace("<!-- section: observability -->", "")
        report, _ = self.run_validate(md)
        self.assertIn("required section `observability` is missing", " ".join(i["message"] for i in report.errors))

    def test_placeholder(self):
        report, _ = self.run_validate(self.md.replace("48 horas a partir", "TODO 48 horas a partir"))
        self.assertIn("placeholders", self.checks(report))

    def test_portuguese_todo_is_not_a_placeholder(self):
        report, _ = self.run_validate(self.md.replace("48 horas a partir", "todo pedido tem 48 horas a partir"))
        self.assertNotIn("placeholders", self.checks(report))

    def test_secret_value_from_repo_is_blocked(self):
        report, _ = self.run_validate(self.md.replace("*secreto* | SecureString | DBA", "local-orders-pass | SecureString | DBA"))
        self.assertIn("secrets", self.checks(report))

    def test_broken_anchor(self):
        report, _ = self.run_validate(self.md.replace("(#glossário)", "(#glossary-missing)"))
        self.assertIn("anchors", self.checks(report))

    def test_unquoted_mermaid_label(self):
        report, _ = self.run_validate(self.md.replace('S["ExpireOrdersSchedule"]', "S[ExpireOrdersSchedule (rate)]"))
        self.assertIn("mermaid", self.checks(report))

    def test_cylinder_shape_is_valid(self):
        report, _ = self.run_validate(self.md.replace('DB[("PostgreSQL")]', "DB[(PostgreSQL)]"))
        self.assertNotIn("mermaid", self.checks(report))

    def test_coverage_gap_and_ignore(self):
        md = self.md.replace("`ORDERS_DEBUG`", "a variável de depuração")
        report, _ = self.run_validate(md)
        self.assertIn("coverage", self.checks(report))
        md += "\n<!-- coverage-ignore: ORDERS_DEBUG | only read in local debugging -->\n"
        report, _ = self.run_validate(md)
        self.assertNotIn("coverage", self.checks(report))

    def test_route_needs_method_and_path_in_api(self):
        report, _ = self.run_validate(self.md.replace("| `POST` | `/orders` |", "| `PUT` | `/orders` |"))
        self.assertIn("route `POST /orders`", " ".join(i["message"] for i in report.errors))

    def test_mention_inside_comment_does_not_count(self):
        md = self.md.replace("`ORDERS_DEBUG`", "a variável de depuração") + "\n<!-- ORDERS_DEBUG -->\n"
        report, _ = self.run_validate(md)
        self.assertIn("ORDERS_DEBUG", " ".join(i["message"] for i in report.errors))

    def test_fact_must_be_in_its_home_section(self):
        md = self.md.replace("| `ExpireOrdersSchedule` → `ExpireOrdersFunction` | `rate(1 hour)` |", "| `ExpireOrdersFunction` | a cada hora |")
        report, _ = self.run_validate(md)
        self.assertIn("not in section `jobs`", " ".join(i["message"] for i in report.errors))

    def test_coverage_ignore_without_reason(self):
        report, _ = self.run_validate(self.md + "\n<!-- coverage-ignore: ORDERS_DEBUG -->\n")
        self.assertIn("coverage-ignore needs", " ".join(i["message"] for i in report.errors))

    def test_optional_section_cannot_be_na(self):
        md = self.md.replace("<!-- section: business-rules -->",
                             "<!-- section: journeys na -->\n## Jornadas\n\nNão se aplica: só existe um público.\n\n<!-- section: business-rules -->")
        report, _ = self.run_validate(md)
        self.assertIn("delete it when it does not apply", " ".join(i["message"] for i in report.errors))

    def test_title_blockquote_is_required(self):
        head, tail = self.md.split("<!-- section: about -->", 1)
        head = "\n".join(ln for ln in head.split("\n") if not ln.startswith(">"))
        report, _ = self.run_validate(head + "<!-- section: about -->" + tail)
        self.assertIn("blockquote", " ".join(i["message"] for i in report.errors))

    def test_wrong_path_inside_repo_is_an_error(self):
        report, _ = self.run_validate(self.md.replace("`src/template.yaml`, com deploy", "`src/template-x.yaml`, com deploy"))
        self.assertIn("file-refs", self.checks(report))

    def test_commands_need_a_shell_fence(self):
        report, _ = self.run_validate(self.md.replace("```bash\ndocker compose", "```text\ndocker compose"))
        self.assertIn("fenced shell block", " ".join(i["message"] for i in report.errors))

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_source_commit_must_exist_in_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "orders-service"
            shutil.copytree(FIXTURE, repo)
            git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "-c", "core.autocrlf=false"]
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(git + ["add", "-A"], check=True)
            subprocess.run(git + ["commit", "-qm", "init"], check=True)
            head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
            wiki = repo / "docs" / "wiki" / "orders-service.md"
            report, _ = validate_wiki.validate(wiki, [repo], check_html_pair=False)
            self.assertIn("is not a commit", " ".join(i["message"] for i in report.errors))
            wiki.write_text(self.md.replace("source_commit: 0a1b2c3", f"source_commit: {head}"), encoding="utf-8")
            report, _ = validate_wiki.validate(wiki, [repo], check_html_pair=False)
            self.assertEqual(report.errors, [])

    def test_stale_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wiki.md"
            path.write_text(self.md, encoding="utf-8")
            path.with_suffix(".html").write_text(render_wiki.build_page(self.md + "\nchanged\n", "wiki.md"), encoding="utf-8")
            report, _ = validate_wiki.validate(path, [], check_html_pair=True)
            self.assertIn("html-sync", self.checks(report))

    def test_cli_exit_codes(self):
        cmd = [sys.executable, str(SCRIPTS / "validate_wiki.py"), str(WIKI), "--repo", str(FIXTURE)]
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.md"
            bad.write_text("# nothing\n", encoding="utf-8")
            cmd = [sys.executable, str(SCRIPTS / "validate_wiki.py"), str(bad), "--no-html"]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)


class BlueprintTests(unittest.TestCase):
    def test_every_type_loads_with_titles_in_both_languages(self):
        types = wikilib.available_types()
        self.assertEqual(set(types), {"service", "monolith", "library", "frontend", "monorepo", "infra", "process", "product"})
        for name in types:
            bp = wikilib.load_blueprint(name)
            ids = [s["id"] for s in bp["sections"]]
            self.assertEqual(len(ids), len(set(ids)), f"duplicate section in {name}")
            self.assertEqual(ids[0], "about", name)
            for required in ("risks", "open-questions", "glossary", "references"):
                self.assertIn(required, ids, f"{name} lacks {required}")
            for sec in bp["sections"]:
                self.assertTrue(sec["title"].get("pt-BR") and sec["title"].get("en"), f"{name}.{sec['id']} title")
                self.assertTrue(sec["must"], f"{name}.{sec['id']} must")
                if sec["columns"]:
                    self.assertEqual(len(sec["columns"]["pt-BR"]), len(sec["columns"]["en"]), f"{name}.{sec['id']} columns")
            for rule in bp["crossref"]:
                self.assertIn(rule["from"], ids)
                self.assertIn(rule["to"], ids)
            for kind, homes in bp["coverage"]["home"].items():
                for home in (homes["all"] if isinstance(homes, dict) else homes):
                    self.assertIn(home, ids, f"{name}: home {home} of {kind}")
            self.assertTrue((SKILL / "references" / "types" / f"{name}.md").is_file(), f"type guide for {name}")

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(KeyError):
            wikilib.load_blueprint("spaceship")

    def test_skeletons_are_structurally_valid_and_fail_only_on_placeholders(self):
        for name in wikilib.available_types():
            for lang in ("pt-BR", "en"):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "doc.md"
                    self.assertEqual(new_doc.main(["--type", name, "--lang", lang, "--title", "T", "--subject", "s", "-o", str(path)]), 0)
                    report, _ = validate_wiki.validate(path, [], check_html_pair=False)
                    checks = {i["check"] for i in report.errors}
                    self.assertNotIn("structure", checks, f"{name}/{lang}: {[i for i in report.errors if i['check'] == 'structure']}")
                    self.assertIn("placeholders", checks, f"{name}/{lang}")
                    self.assertNotIn("anchors", checks, f"{name}/{lang}")
                    self.assertNotIn("mermaid", checks, f"{name}/{lang}")


class ClassifyTests(unittest.TestCase):
    EXPECTED = {
        "orders-service": "service",
        "legacy-mvc": "monolith",
        "web-store": "frontend",
        "shared-lib": "library",
        "platform-monorepo": "monorepo",
        "infra-only": "infra",
    }

    def test_each_fixture_gets_its_type(self):
        for folder, expected in self.EXPECTED.items():
            report = scan_repo.scan([FIXTURES / folder])
            self.assertEqual(report["profile"]["suggested"], expected, f"{folder}: {report['profile']}")

    def facts(self, folder):
        kinds = {}
        for f in scan_repo.scan([FIXTURES / folder])["facts"]:
            kinds.setdefault(f["kind"], set()).add(f["name"])
        return kinds

    def test_monolith_facts_and_style(self):
        k = self.facts("legacy-mvc")
        self.assertEqual(k["controller"], {"HomeController", "OrdersController", "InvoicesController"})
        self.assertEqual(k["schedule"], {"expire-carts"})
        self.assertEqual(k["screen"], {"/Orders"})
        self.assertEqual(k["environment"], {"Release"})
        self.assertTrue({"StoreDb", "Smtp.Host", "Payments.ApiKey", "Feature.NewCheckout"} <= k["config_key"])
        self.assertIn("ANY /{controller}/{action}/{id}", k["route"])
        self.assertEqual(k["plaintext_secret"], {"Store.Web/Web.config"})
        self.assertIn("MVC", scan_repo.scan([FIXTURES / "legacy-mvc"])["profile"]["styles"])

    def test_nuget_packages_folder_is_skipped_but_js_packages_are_read(self):
        self.assertTrue(scan_repo.skip_dir(FIXTURES / "legacy-mvc", "packages"))
        self.assertFalse(scan_repo.skip_dir(FIXTURES / "platform-monorepo", "packages"))
        self.assertIn("@platform/ui", self.facts("platform-monorepo")["package"])

    def test_frontend_screens_and_public_env(self):
        k = self.facts("web-store")
        self.assertEqual(k["screen"], {"/", "/products/:id", "/checkout"})
        self.assertEqual(k["env_var"], {"VITE_API_URL"})

    def test_library_package_and_infra_resources(self):
        self.assertEqual(self.facts("shared-lib")["package"], {"@acme/money"})
        infra = self.facts("infra-only")
        self.assertEqual(infra["iac_resource"], {"orders", "assets"})
        self.assertEqual(infra["environment"], {"dev", "prod"})
        self.assertEqual(infra["iac_parameter"], {"environment", "vpc_cidr"})

    def test_file_routes(self):
        self.assertEqual(scan_repo.file_route("app/(shop)/products/[id]/page.tsx"), ("screen", "/products/[id]"))
        self.assertEqual(scan_repo.file_route("src/pages/api/orders.ts"), ("route", "/api/orders"))
        self.assertEqual(scan_repo.file_route("src/routes/cart/+page.svelte"), ("screen", "/cart"))
        self.assertIsNone(scan_repo.file_route("src/components/Button.tsx"))


class SubjectTypeTests(unittest.TestCase):
    def setUp(self):
        self.md = PROCESS_DOC.read_text(encoding="utf-8")

    def run_validate(self, md_text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            path.write_text(md_text, encoding="utf-8")
            path.with_suffix(".html").write_text(render_wiki.build_page(md_text, "doc.md"), encoding="utf-8")
            report, _ = validate_wiki.validate(path, [], check_html_pair=True)
            return report

    def messages(self, report):
        return " ".join(i["message"] for i in report.errors)

    def test_process_fixture_passes_and_html_is_in_sync(self):
        self.assertEqual(self.run_validate(self.md).errors, [])
        self.assertEqual(render_wiki.main([str(PROCESS_DOC), "--check"]), 0)

    def test_step_owner_must_be_a_role(self):
        md = self.md.replace("| 4 | Provisões e ajustes | Analista contábil |", "| 4 | Provisões e ajustes | Gerente de custos |")
        self.assertIn("`Gerente de custos`: every step owner must be a role listed in Roles", self.messages(self.run_validate(md)))

    def test_role_must_be_in_raci(self):
        md = self.md.replace("| Controller | Aprova ajustes", "| Controller | Aprova ajustes").replace(
            "| Analista de tesouraria | Envia extratos", "| Auditor interno | Revisa o fechamento | Auditoria |\n| Analista de tesouraria | Envia extratos")
        self.assertIn("`Auditor interno`: every role in Roles must be a column of the RACI matrix", self.messages(self.run_validate(md)))

    def test_empty_cell_in_complete_table(self):
        md = self.md.replace("| Extratos bancários do mês |", "|  |")
        self.assertIn("has empty cells (Entrada)", self.messages(self.run_validate(md)))

    def test_sources_required_and_cited(self):
        md = self.md.replace("| Política de Alçadas Financeiras v2 (02/2025) | Alçada de ajustes |\n", "")
        self.assertIn("is not cited in `references`", self.messages(self.run_validate(md)))
        md = re.sub(r"sources:\n(  - .*\n)+", "", self.md)
        self.assertIn("`sources` must list", self.messages(self.run_validate(md)))

    def test_view_labels_follow_the_type(self):
        page = render_wiki.build_page(self.md, "doc.md")
        self.assertIn('data-view="detail" aria-pressed="false">Passo a passo</button>', page)
        page = render_wiki.build_page(WIKI.read_text(encoding="utf-8"), "doc.md")
        self.assertIn('data-view="detail" aria-pressed="false">Técnico</button>', page)

    def test_template_placeholder_inside_code_is_rejected(self):
        md = self.md.replace("<!-- section: glossary -->", "```bash\n«comando»\n```\n\n<!-- section: glossary -->")
        self.assertIn("placeholder left in a code block", self.messages(self.run_validate(md)))

    def test_legacy_part_names_are_aliases(self):
        md = self.md.replace("<!-- part: overview -->", "<!-- part: business -->").replace("<!-- part: detail -->", "<!-- part: technical -->")
        self.assertEqual(self.run_validate(md).errors, [])

    def test_unknown_type(self):
        self.assertIn("unknown type `spaceship`", self.messages(self.run_validate(self.md.replace("type: process", "type: spaceship"))))


class RegressionTests(unittest.TestCase):
    """One test per false negative/positive found by the end-to-end agent runs."""

    def setUp(self):
        self.process = PROCESS_DOC.read_text(encoding="utf-8")
        self.service = WIKI.read_text(encoding="utf-8")

    def errors(self, md_text, repos=()):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            path.write_text(md_text, encoding="utf-8")
            path.with_suffix(".html").write_text(render_wiki.build_page(md_text, "doc.md"), encoding="utf-8")
            report, _ = validate_wiki.validate(path, list(repos), check_html_pair=True)
            return report

    def msg(self, report):
        return " ".join(i["message"] for i in report.errors)

    def test_raci_needs_exactly_one_a(self):
        md = self.process.replace("| 5. Aprovação de ajustes | R | — | A |", "| 5. Aprovação de ajustes | A | — | A |")
        self.assertIn("must have exactly one A (found 2)", self.msg(self.errors(md)))
        md = self.process.replace("| 3. Conciliação bancária | R/A | C | I |", "| 3. Conciliação bancária | R | C | I |")
        self.assertIn("must have exactly one A (found 0)", self.msg(self.errors(md)))

    def test_raci_cell_values(self):
        md = self.process.replace("| 1. Corte de lançamentos | R/A | I | I |", "| 1. Corte de lançamentos | R/A | sim | X |")
        self.assertIn("RACI cells must be R, A, C, I", self.msg(self.errors(md)))

    def test_every_step_has_a_raci_row(self):
        md = self.process.replace("| 4. Provisões e ajustes | R/A | — | C |\n", "")
        self.assertIn("step `provisões e ajustes` has no row in the RACI matrix", self.msg(self.errors(md)))

    def test_roles_match_whole_names(self):
        md = self.process.replace("| 4 | Provisões e ajustes | Analista contábil |", "| 4 | Provisões e ajustes | Analista |")
        self.assertIn("`Analista`: every step owner must be a role listed in Roles", self.msg(self.errors(md)))
        md = self.process.replace("| Etapa | Analista contábil | Analista de tesouraria | Controller |", "| Etapa | Analista contábil | Analista de tesouraria | Diretor |")
        self.assertIn("`Controller`: every role in Roles must be a column", self.msg(self.errors(md)))

    def test_open_marker_is_accepted_and_unknown_markers_are_not(self):
        ok = self.process.replace("| Calendário de fechamento |", "| Em aberto (ver Perguntas em aberto) |")
        self.assertEqual(self.errors(ok).errors, [])
        bad = self.process.replace("| Calendário de fechamento |", "| A definir |")
        self.assertIn("uses an unknown marker (Entrada: A definir)", self.msg(self.errors(bad)))

    def test_angle_bracket_placeholder(self):
        md = self.process.replace("Entrevista com Marina Souza (controller), 20/10/2026 | Papéis", "Entrevista com <papel/nome>, <data> | Papéis")
        self.assertIn("placeholder left in the text", self.msg(self.errors(md)))

    def test_status_needs_a_date(self):
        md = self.process.replace("Em 23/10/2026: o processo é documentado e medido.", "O processo é documentado e medido.")
        self.assertIn("the first sentence must carry the date", self.msg(self.errors(md)))

    def test_command_block_needs_its_label(self):
        md = self.service.replace("Derivado de `tests/Orders.Tests/Orders.Tests.csproj`; não executado (exige .NET 8).\n\n", "")
        self.assertIn("the line before each command block must say", self.msg(self.errors(md, [FIXTURE])))

    def test_plaintext_secret_must_be_in_security_and_risks(self):
        md = self.service.replace("Os arquivos `src/Orders.Api/appsettings.json` e `src/docker-compose.yml` têm", "O arquivo `src/Orders.Api/appsettings.json` tem")
        self.assertIn("must also be mentioned in section `security`", self.msg(self.errors(md, [FIXTURE])))

    def test_faq_needs_three_questions(self):
        start = self.process.index("<details markdown=\"1\">\n<summary>Posso lançar")
        end = self.process.index("</details>", start) + len("</details>")
        self.assertIn("needs at least 3 questions", self.msg(self.errors(self.process[:start] + self.process[end:])))

    def test_file_refs_under_skipped_folders_and_declared_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "packages" / "Lib.1.0").mkdir(parents=True)
            (repo / "packages" / "Lib.1.0" / "Lib.1.0.nupkg").write_text("x", encoding="utf-8")
            (repo / "src").mkdir()
            (repo / "src" / "App.cs").write_text("class App {}", encoding="utf-8")
            report = validate_wiki.Report()
            files = validate_wiki.repo_files([repo])
            lines = ["Pacote em `packages/Lib.1.0/Lib.1.0.nupkg`.", "O arquivo `src/Global.asax.cs` está ausente do repositório.",
                     "Veja `src/Missing.cs`."]
            validate_wiki.check_file_refs(lines, report, 1, files, validate_wiki.top_level_dirs([repo]), [repo])
            self.assertEqual([i["message"] for i in report.items], ["`src/Missing.cs` does not exist in the repo; fix the path"])

    def test_mvc_views_become_screens_and_single_module_is_not_modular(self):
        report = scan_repo.scan([FIXTURES / "legacy-mvc"])
        screens = {f["name"] for f in report["facts"] if f["kind"] == "screen"}
        self.assertEqual(screens, {"/Orders"})
        self.assertNotIn("modular monolith", report["profile"]["styles"])
        release = next(f for f in report["facts"] if f["kind"] == "environment" and f["name"] == "Release")
        self.assertIn("build configuration", release["detail"])

    def test_source_without_date_warns(self):
        md = self.process.replace("  - Política de Alçadas Financeiras v2 (02/2025)\n", "  - Política de Alçadas Financeiras\n").replace(
            "| Política de Alçadas Financeiras v2 (02/2025) | Alçada de ajustes |", "| Política de Alçadas Financeiras | Alçada de ajustes |")
        report = self.errors(md)
        self.assertIn("has no date", " ".join(i["message"] for i in report.items if i["level"] == "WARN"))

    def test_skeleton_has_family_specific_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.md"
            new_doc.main(["--type", "process", "--lang", "pt-BR", "--title", "T", "--subject", "s", "-o", str(path)])
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("tags:", text)
            self.assertIn("valores em reais", text)
            self.assertIn("| Etapa | «Papel 1» | «Papel 2» |", text)
            path2 = Path(tmp) / "s.md"
            new_doc.main(["--type", "service", "--lang", "pt-BR", "--title", "T", "--subject", "s", "--repo", str(FIXTURE), "-o", str(path2)])
            text2 = path2.read_text(encoding="utf-8")
            self.assertIn("  - orders-service", text2)
            self.assertIn("stateDiagram-v2", text2)
            self.assertIn("**Em uma frase:**", text2)
            self.assertIn("### Parâmetros e segredos por ambiente", text2)


if __name__ == "__main__":
    unittest.main()
