#!/usr/bin/env python3
"""Builds a deterministic inventory of a codebase: the facts its documentation must cover, plus a type hint.

It reads the repository the way an on-call engineer would: infrastructure as code, configuration,
environment variables, HTTP routes, screens, controllers, schedules (external and in-process), packages,
pipelines, local dependencies, test suites and credentials committed in plain text. Which kinds are
required depends on the document type (blueprints/<type>.json); validate_wiki.py enforces them.
It also suggests the document type (service, monolith, library, frontend, monorepo, infra) and the
architectural style(s), with the evidence, for the agent to confirm with the user.

Secret values are never printed: plaintext credentials are reported by file, line and key only.

Usage:
    python scan_repo.py <repo> [<repo> ...]            # Markdown inventory for the agent
    python scan_repo.py <repo> --format json           # machine-readable inventory
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "bin", "obj", "dist", "build", "target", "vendor", ".venv", "venv",
    "__pycache__", ".idea", ".vs", ".vscode", "coverage", ".terraform", ".aws-sam", "cdk.out", ".next",
    ".nuxt", ".svelte-kit", ".gradle", ".mvn", "TestResults", ".pytest_cache", ".mypy_cache", ".tox", "out", "bower_components",
}
KEEP_HIDDEN = {".github", ".gitlab", ".circleci", ".azuredevops"}
CODE_EXT = {".cs", ".fs", ".vb", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".java", ".kt", ".go", ".rb", ".php", ".rs", ".scala",
            ".vue", ".svelte", ".cshtml", ".razor"}
CONFIG_EXT = {".json", ".yml", ".yaml", ".xml", ".config", ".properties", ".env", ".ini", ".toml", ".tf", ".tfvars", ".conf"}
MAX_FILE_BYTES = 1_500_000

KIND_INFO = {
    "environment": ("Environments and build configurations", "Deployment environments, plus build configurations such as config transforms (labelled in Detail)"),
    "iac_parameter": ("Deployment parameters", "IaC parameters/variables set per deployment"),
    "iac_resource": ("Infrastructure resources", "Queues, topics, buckets, tables, functions, APIs, schedules, alarms..."),
    "env_var": ("Environment variables", "Defined by IaC/containers or read by the code"),
    "config_key": ("Configuration sections", "Top-level keys of the configuration files"),
    "parameter_ref": ("Parameter store / secret references", "SSM, Secrets Manager and similar references or prefixes"),
    "route": ("HTTP routes", "Endpoints exposed (method + path)"),
    "screen": ("Screens / pages", "UI routes: SPA routes, file-based pages, Razor Pages"),
    "controller": ("Controllers", "MVC controllers (conventional routing)"),
    "schedule": ("Schedules", "Cron/rate triggers, external or in-process"),
    "package": ("Packages / deployables", "Packages and deployable projects declared in the repo"),
    "pipeline": ("CI/CD pipelines", "Build and deploy definitions"),
    "local_dependency": ("Local dependencies", "Containers needed to run the service locally"),
    "test_suite": ("Test suites", "Test projects or folders"),
    "plaintext_secret": ("Plaintext credentials", "Files with credentials committed in plain text (values never shown)"),
    "stack": ("Stack", "Languages, frameworks and notable libraries (informational)"),
    "doc": ("Existing documentation", "Docs already in the repo (informational)"),
}

INTERESTING_CFN = re.compile(
    r"^AWS::(SQS::Queue|SNS::Topic|S3::Bucket|DynamoDB::(Global)?Table|Serverless::(Function|Api|HttpApi|StateMachine|SimpleTable)"
    r"|Lambda::Function|ApiGateway::RestApi|ApiGatewayV2::Api|Events::(Rule|EventBus)|Scheduler::Schedule"
    r"|StepFunctions::StateMachine|RDS::DB(Instance|Cluster)|ElastiCache::\w+|Kinesis::Stream|KinesisFirehose::\w+"
    r"|SecretsManager::Secret|SSM::Parameter|ECS::(Service|TaskDefinition)|CloudWatch::(Alarm|Dashboard)|Cognito::UserPool"
    r"|Pipes::Pipe|MSK::Cluster|OpenSearchService::Domain|EFS::FileSystem|AppSync::GraphQLApi)$"
)
NAME_PROPS = ("QueueName", "TopicName", "FunctionName", "BucketName", "TableName", "Name", "StateMachineName",
              "AlarmName", "RuleName", "DashboardName", "StreamName", "ClusterName", "ServiceName", "DomainName")

SECRET_KEY = re.compile(
    r"(password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|client[_-]?secret|credential)",
    re.I,
)
SECRET_KEY_NOT = re.compile(
    r"(name|url|uri|arn|path|header|prefix|type|enabled|expir|length|ttl|endpoint|policy|rotation|timeout|issuer"
    r"|audience|lifetime|duration|format|mode|provider|field|param|env|file|location|id)$",
    re.I,
)
PLACEHOLDER = re.compile(
    r"^(|''|\"\"|null|none|nil|true|false|\*+|x+|\.\.\.|changeme|change-me|<[^>]*>|\$\{.*\}|\$\(.*\)|\{\{.*\}\}|%.*%|#\{.*\}"
    r"|!(Ref|Sub|GetAtt|ImportValue|FindInMap|Join|Select|If)\b.*|ref\+.*|arn:.*|ssm:.*|resolve:.*|secretsmanager:.*"
    r"|/aws/reference/.*|env\(.*\)|\$[A-Z_][A-Z0-9_]*|[A-Z_][A-Z0-9_]*__[A-Z0-9_]+)$",
    re.I,
)
TOKEN_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\beyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}"), "JWT"),
]


# ---------------------------------------------------------------- helpers

class Inventory:
    def __init__(self) -> None:
        self.facts: dict[tuple[str, str], dict] = {}

    def add(self, kind, name, source, aliases=(), detail="", secret_value=None):
        key = (kind, name.lower())
        fact = self.facts.get(key)
        if fact is None:
            fact = {"kind": kind, "name": name, "aliases": [], "sources": [], "detail": detail}
            self.facts[key] = fact
        for alias in [name, *aliases]:
            alias = str(alias).strip()
            if alias and alias.lower() not in (a.lower() for a in fact["aliases"]):
                fact["aliases"].append(alias)
        if source and source not in fact["sources"] and len(fact["sources"]) < 8:
            fact["sources"].append(source)
        if detail and not fact["detail"]:
            fact["detail"] = detail
        if secret_value:
            fact.setdefault("_values", []).append(secret_value)
        return fact

    def as_list(self):
        return sorted(self.facts.values(), key=lambda f: (list(KIND_INFO).index(f["kind"]), f["name"].lower()))


def skip_dir(parent: Path, name: str, hidden: bool = True) -> bool:
    """Build output, dependencies and caches; `packages` only when it is a NuGet cache (JS workspaces live there)."""
    if name in SKIP_DIRS:
        return True
    if hidden and name.startswith(".") and name not in KEEP_HIDDEN:
        return True
    if name == "packages":
        try:
            return any(child.suffix == ".nupkg" for sub in (parent / name).iterdir() if sub.is_dir() for child in sub.iterdir())
        except OSError:
            return False
    if name == "env":
        return (parent / name / "pyvenv.cfg").is_file()
    return False


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not skip_dir(Path(dirpath), d))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            try:
                if path.stat().st_size <= MAX_FILE_BYTES:
                    yield path
            except OSError:
                continue


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_test_path(relpath: str) -> bool:
    return bool(re.search(r"(^|/)(tests?|specs?|__tests__|e2e|integration[-_]?tests?|testing)(/|$)|\.tests?(\.|/)|[._-](test|spec)s?\.\w+$"
                          r"|Tests?(\.|/)|/test_[^/]+$", relpath, re.I))


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


# ---------------------------------------------------------------- yaml-ish reader (CloudFormation tags safe)

def parse_yamlish(text: str):
    """Indentation-based YAML reader good enough for IaC, compose and pipelines. Returns dict/list/str."""
    root = {"indent": -1, "key": None, "value": None, "children": [], "item": False}
    stack = [root]
    block_indent = None
    for raw in text.split("\n"):
        if block_indent is not None:
            if not raw.strip() or len(raw) - len(raw.lstrip(" ")) > block_indent:
                continue
            block_indent = None
        if not raw.strip() or raw.lstrip().startswith("#") or raw.strip() in ("---", "..."):
            continue
        line = re.sub(r"\s+#(?![^'\"]*['\"]\s*$).*$", "", raw.rstrip())
        indent = len(line) - len(line.lstrip(" "))
        s = line.strip()
        while stack[-1]["indent"] >= indent:
            stack.pop()
        parent = stack[-1]
        if s.startswith("- ") or s == "-":
            node = {"indent": indent, "key": None, "value": None, "children": [], "item": True}
            parent["children"].append(node)
            stack.append(node)
            rest = s[1:].strip()
            if not rest:
                continue
            indent += 2
            s = rest
            parent = node
        m = re.match(r"""^("[^"]*"|'[^']*'|[^\s:'"][^:]*?)\s*:(?:\s+(.*)|$)""", s)
        if m and not s.startswith(("{", "[")):
            key = m.group(1).strip("'\"")
            value = (m.group(2) or "").strip()
            node = {"indent": indent, "key": key, "value": value or None, "children": [], "item": False}
            parent["children"].append(node)
            stack.append(node)
            if value in ("|", ">", "|-", ">-", "|+", ">+"):
                node["value"] = ""
                block_indent = indent
        else:
            if parent["item"] and parent["value"] is None and not parent["children"]:
                parent["value"] = s
            else:
                parent["children"].append({"indent": indent, "key": None, "value": s, "children": [], "item": True})
    return _to_py(root)


def _to_py(node):
    if not node["children"]:
        value = node["value"]
        if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        return value
    if all(c["item"] for c in node["children"]):
        return [_to_py(c) for c in node["children"]]
    result = {}
    for child in node["children"]:
        if child["key"] is not None:
            result[child["key"]] = _to_py(child)
    return result


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def literal_name(value) -> str | None:
    """A resource name usable as alias: plain strings only, or !Sub strings without variables."""
    if not isinstance(value, str):
        return None
    v = re.sub(r"^!Sub\s+", "", value.strip()).strip("'\"")
    if not v or v.startswith("!") or "${" in v or "{{" in v:
        return None
    return v


# ---------------------------------------------------------------- extractors

def scan_cloudformation(doc: dict, src: str, inv: Inventory) -> None:
    resources = as_dict(doc.get("Resources"))
    globals_env = as_dict(as_dict(as_dict(as_dict(doc.get("Globals")).get("Function")).get("Environment")).get("Variables"))
    for name in globals_env:
        inv.add("env_var", name, src, aliases=_env_aliases(name), detail="Globals.Function (all functions)")
    for pname, pdef in as_dict(doc.get("Parameters")).items():
        pdef = as_dict(pdef)
        ptype, default = str(pdef.get("Type") or ""), pdef.get("Default")
        inv.add("iac_parameter", pname, src, detail=f"{ptype}" + (f", default {default}" if isinstance(default, str) and default else ", no default"))
        if ptype.startswith("AWS::SSM::Parameter::Value") and isinstance(default, str):
            inv.add("parameter_ref", default, src, aliases=[pname], detail=f"CloudFormation parameter {pname}")
        elif re.search(r"ssm|parameter", pname + " " + str(pdef.get("Description") or ""), re.I) and isinstance(default, str) and default.startswith("/"):
            inv.add("parameter_ref", default, src, aliases=[pname], detail=f"prefix parameter {pname}")
    for lid, res in resources.items():
        res = as_dict(res)
        rtype = str(res.get("Type") or "")
        props = as_dict(res.get("Properties"))
        if INTERESTING_CFN.match(rtype):
            names = [n for n in (literal_name(props.get(p)) for p in NAME_PROPS) if n]
            inv.add("iac_resource", lid, src, aliases=names, detail=rtype)
        for var in as_dict(as_dict(props.get("Environment")).get("Variables")):
            inv.add("env_var", var, src, aliases=_env_aliases(var), detail=f"function {lid}")
        for ev_name, event in as_dict(props.get("Events")).items():
            event = as_dict(event)
            etype = str(event.get("Type") or "")
            eprops = as_dict(event.get("Properties"))
            if etype in ("Schedule", "ScheduleV2"):
                expr = str(eprops.get("Schedule") or eprops.get("ScheduleExpression") or "")
                inv.add("schedule", ev_name, src, aliases=[expr] if expr else [], detail=f"{expr} -> {lid}")
            elif etype in ("Api", "HttpApi"):
                path, method = str(eprops.get("Path") or ""), str(eprops.get("Method") or "ANY").upper()
                if path and path != "/" and method != "OPTIONS":
                    inv.add("route", f"{method} {path}", src, aliases=[path], detail=f"API event on {lid}")
        if rtype in ("AWS::Events::Rule", "AWS::Scheduler::Schedule") and props.get("ScheduleExpression"):
            inv.add("schedule", lid, src, aliases=[str(props["ScheduleExpression"])], detail=str(props["ScheduleExpression"]))
    _find_dynamic_refs(json.dumps(doc), src, inv)


def _find_dynamic_refs(text: str, src: str, inv: Inventory) -> None:
    for m in re.finditer(r"\{\{resolve:(ssm|ssm-secure|secretsmanager):([^}:\"]+)", text):
        inv.add("parameter_ref", m.group(2), src, detail=f"dynamic reference ({m.group(1)})")
    for m in re.finditer(r"\$\{ssm:([^}\"]+)\}", text):
        inv.add("parameter_ref", m.group(1).split("~")[0], src, detail="serverless ssm reference")
    for m in re.finditer(r"/aws/reference/secretsmanager/([\w/+=.@-]+)", text):
        inv.add("parameter_ref", m.group(1), src, detail="Secrets Manager via SSM reference")


def _env_aliases(name: str) -> list[str]:
    return [name.replace("__", ":"), name.replace("__", ".")] if "__" in name else []


def scan_samconfig(text: str, path: Path, src: str, inv: Inventory) -> None:
    doc = parse_yamlish(text) if path.suffix in (".yml", ".yaml") else {}
    if isinstance(doc, dict):
        for env in doc:
            if env not in ("version", "default"):
                inv.add("environment", env, src, detail="samconfig environment")
    for m in re.finditer(r"^\[([\w-]+)[.\]]", text, re.M):
        if m.group(1) != "default":
            inv.add("environment", m.group(1), src, detail="samconfig environment")
    for m in re.finditer(r"([\w]*(?:SSM|Ssm|Prefix|Parameter)[\w]*)=\"?(/[^\s\"']+)", text):
        inv.add("parameter_ref", m.group(2), src, aliases=[m.group(1)], detail=f"parameter override {m.group(1)}")


def scan_serverless(doc: dict, text: str, src: str, inv: Inventory) -> None:
    provider = as_dict(doc.get("provider"))
    for var in as_dict(provider.get("environment")):
        inv.add("env_var", var, src, detail="provider.environment")
    for fname, fdef in as_dict(doc.get("functions")).items():
        fdef = as_dict(fdef)
        for var in as_dict(fdef.get("environment")):
            inv.add("env_var", var, src, detail=f"function {fname}")
        for event in fdef.get("events") or []:
            event = as_dict(event)
            for etype in ("http", "httpApi"):
                e = event.get(etype)
                if isinstance(e, dict) and e.get("path"):
                    path = "/" + str(e["path"]).lstrip("/")
                    inv.add("route", f'{str(e.get("method") or "ANY").upper()} {path}', src, aliases=[path], detail=f"function {fname}")
            if event.get("schedule"):
                sched = event["schedule"]
                expr = sched.get("rate") if isinstance(sched, dict) else sched
                inv.add("schedule", f"{fname} schedule", src, aliases=[str(expr), fname], detail=str(expr))
    for stage in re.findall(r"^\s*stage:\s*['\"]?([\w-]+)", text, re.M):
        if not stage.startswith("$"):
            inv.add("environment", stage, src, detail="serverless stage")
    _find_dynamic_refs(text, src, inv)


def scan_compose(doc: dict, src: str, inv: Inventory) -> None:
    for service, sdef in as_dict(doc.get("services")).items():
        sdef = as_dict(sdef)
        image = str(sdef.get("image") or "")
        inv.add("local_dependency", service, src, aliases=[image.split(":")[0]] if image else [], detail=image or "build")


def scan_kubernetes(doc, src: str, inv: Inventory) -> None:
    def visit(node):
        if isinstance(node, dict):
            env = node.get("env")
            if isinstance(env, list):
                for item in env:
                    if isinstance(item, dict) and isinstance(item.get("name"), str):
                        inv.add("env_var", item["name"], src, detail="container env")
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(doc)


def scan_terraform(text: str, src: str, inv: Inventory) -> None:
    for m in re.finditer(r'resource\s+"(aws_(?:sqs_queue|sns_topic|s3_bucket|dynamodb_table|lambda_function|apigatewayv2_api|api_gateway_rest_api'
                         r'|cloudwatch_event_rule|scheduler_schedule|sfn_state_machine|db_instance|rds_cluster|elasticache_\w+|kinesis_stream'
                         r'|secretsmanager_secret|ssm_parameter|ecs_service|cloudwatch_metric_alarm|cognito_user_pool)|google_\w+|azurerm_\w+)"\s+"([\w-]+)"\s*\{',
                         text):
        block = text[m.end(): m.end() + 2000]
        name = re.search(r'^\s*name\s*=\s*"([^"$]+)"', block, re.M)
        inv.add("iac_resource", m.group(2), src, aliases=[name.group(1)] if name else [], detail=m.group(1))
        sched = re.search(r'schedule_expression\s*=\s*"([^"]+)"', block)
        if sched:
            inv.add("schedule", m.group(2), src, aliases=[sched.group(1)], detail=sched.group(1))
    for m in re.finditer(r'^variable\s+"([\w-]+)"', text, re.M):
        inv.add("iac_parameter", m.group(1), src, detail="terraform variable")
    for m in re.finditer(r"variables\s*=\s*\{([^}]*)\}", text, re.S):
        for var in re.findall(r"^\s*\"?([A-Za-z_][\w]*)\"?\s*=", m.group(1), re.M):
            inv.add("env_var", var, src, detail="terraform environment")
    for m in re.finditer(r'data\s+"aws_ssm_parameter"\s+"[\w-]+"\s*\{[^}]*name\s*=\s*"([^"]+)"', text, re.S):
        inv.add("parameter_ref", m.group(1), src, detail="terraform data source")


def scan_appsettings(text: str, path: Path, src: str, inv: Inventory) -> None:
    try:
        data = json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    m = re.match(r"appsettings\.(\w+)\.json$", path.name, re.I)
    if m and m.group(1).lower() not in ("json",):
        inv.add("environment", m.group(1), src, detail="appsettings environment file")
    for key, value in data.items():
        if key in ("Logging", "AllowedHosts", "$schema", "Kestrel"):
            continue
        leaves = sorted(_flatten(value, key))
        inv.add("config_key", key, src, detail=", ".join(k for k, _ in leaves[:12]) + (" ..." if len(leaves) > 12 else ""))


def _flatten(value, prefix):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _flatten(v, f"{prefix}:{k}")
    else:
        yield prefix, value


def scan_dotenv(text: str, src: str, inv: Inventory, example: bool) -> None:
    for m in re.finditer(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", text, re.M):
        inv.add("env_var", m.group(1), src, detail="dotenv example" if example else "dotenv")


def scan_spring(text: str, path: Path, src: str, inv: Inventory) -> None:
    m = re.match(r"application-(\w+)\.(ya?ml|properties)$", path.name)
    if m:
        inv.add("environment", m.group(1), src, detail="spring profile")
    if path.suffix == ".properties":
        keys = {line.split("=")[0].split(".")[0].strip() for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#")}
    else:
        doc = parse_yamlish(text)
        keys = set(doc) if isinstance(doc, dict) else set()
    for key in sorted(keys - {"logging", "spring", "server", "management", ""}):
        inv.add("config_key", key, src, detail="spring configuration")


ROUTE_PATTERNS = [
    (re.compile(r"\[(Http(Get|Post|Put|Delete|Patch))\(\s*\"([^\"]*)\""), lambda m: (m.group(2), m.group(3))),
    (re.compile(r"\bMap(Get|Post|Put|Delete|Patch)\(\s*\"([^\"]+)\""), lambda m: (m.group(1), m.group(2))),
    (re.compile(r"^\s*(Get|Post|Put|Delete|Patch)\(\s*\"(/[^\"]*)\"", re.M), lambda m: (m.group(1), m.group(2))),
    (re.compile(r"\b(?:app|router|server|fastify|api|route|r|routes)\.(get|post|put|delete|patch)\(\s*['\"`](/[^'\"`]*)"), lambda m: (m.group(1), m.group(2))),
    (re.compile(r"@(Get|Post|Put|Delete|Patch)\(\s*['\"]([^'\"]*)['\"]"), lambda m: (m.group(1), "/" + m.group(2).lstrip("/"))),
    (re.compile(r"@\w+\.(get|post|put|delete|patch)\(\s*['\"](/[^'\"]*)"), lambda m: (m.group(1), m.group(2))),
    (re.compile(r"@\w+\.route\(\s*['\"](/[^'\"]*)['\"](?:[^)]*methods\s*=\s*\[\s*['\"](\w+))?"), lambda m: (m.group(2) or "GET", m.group(1))),
    (re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\""), lambda m: (m.group(1), m.group(2))),
    (re.compile(r"\.(GET|POST|PUT|DELETE|PATCH)\(\s*\"(/[^\"]*)\""), lambda m: (m.group(1), m.group(2))),
    (re.compile(r"\bHandleFunc\(\s*\"((?:GET|POST|PUT|DELETE|PATCH) )?(/[^\"]*)\""), lambda m: ((m.group(1) or "ANY").strip(), m.group(2))),
    (re.compile(r"\bRoute::(get|post|put|delete|patch|any)\(\s*['\"]([^'\"]*)['\"]"), lambda m: (m.group(1), "/" + m.group(2).lstrip("/"))),
    (re.compile(r"\bMapControllerRoute\([^)]*?pattern:\s*\"([^\"]+)\"", re.S), lambda m: ("ANY", "/" + m.group(1).lstrip("/"))),
    (re.compile(r"\bMapRoute\(\s*(?:name:\s*)?\"[^\"]*\",\s*(?:url:\s*)?\"([^\"]*)\"", re.S), lambda m: ("ANY", "/" + m.group(1).lstrip("/"))),
]
ENV_READ_PATTERNS = [
    re.compile(r"GetEnvironmentVariable\(\s*\"([A-Za-z_][\w:.]*)\""),
    re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\[\s*['\"]([^'\"]+)['\"]\s*\]"),
    re.compile(r"import\.meta\.env\.([A-Z_][A-Z0-9_]*)"),
    re.compile(r"os\.environ(?:\.get)?[\[(]\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"os\.getenv\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"System\.getenv\(\s*\"([^\"]+)\""),
    re.compile(r"os\.(?:Getenv|LookupEnv)\(\s*\"([^\"]+)\""),
    re.compile(r"env::var\(\s*\"([^\"]+)\""),
    re.compile(r"ENV\[\s*['\"]([^'\"]+)['\"]\s*\]"),
]
ENV_BUILTINS = {"NODE_ENV", "MODE", "DEV", "PROD", "SSR", "BASE_URL"}
CONTROLLER_PATTERNS = [
    (re.compile(r"(?<!abstract )class\s+(\w+Controller)\s*:\s*(?:[\w.]+\.)?(\w*Controller(?:Base)?|ApiController|AsyncController)\b"), "ASP.NET"),
    (re.compile(r"class\s+(\w+Controller)\s*<\s*(?:ApplicationController|ActionController::Base|\w+Controller)"), "Rails"),
    (re.compile(r"(?<!abstract )class\s+(\w+Controller)\s+extends\s+\w*Controller\b"), "Laravel/Symfony"),
    (re.compile(r"@Controller\s+(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+)?class\s+(\w+)"), "Spring MVC"),
]
SCHEDULE_PATTERNS = [
    (re.compile(r"RecurringJob\.AddOrUpdate(?:<[^>]+>)?\(\s*(?:recurringJobId:\s*)?\"([^\"]+)\""), "Hangfire recurring job"),
    (re.compile(r"WithCronSchedule\(\s*\"([^\"]+)\""), "Quartz cron trigger"),
    (re.compile(r"@Scheduled\(\s*(?:cron\s*=\s*\"([^\"]+)\"|fixed(?:Rate|Delay)(?:String)?\s*=\s*\"?([\w${}.]+))"), "Spring @Scheduled"),
    (re.compile(r"\bcron\.schedule\(\s*['\"]([^'\"]+)['\"]"), "node-cron"),
    (re.compile(r"new\s+CronJob\(\s*['\"]([^'\"]+)['\"]"), "cron (node)"),
    (re.compile(r"['\"]([\w.:-]+)['\"]\s*:\s*\{[^{}]*?['\"]schedule['\"]\s*:\s*(?:crontab|timedelta|schedule)\(", re.S), "Celery beat entry"),
    (re.compile(r"class\s+(\w+)\s*:\s*(?:[\w.]+\.)?BackgroundService\b"), ".NET hosted background service"),
    (re.compile(r"\[TimerTrigger\(\s*\"([^\"]+)\""), "Azure Functions timer"),
]


def scan_code(text: str, src: str, inv: Inventory, test: bool) -> None:
    if test:
        return
    for pattern, extract in ROUTE_PATTERNS:
        for m in pattern.finditer(text):
            method, path = extract(m)
            if path is None or (not path.startswith("/") and path != ""):
                continue
            path = path or "/"
            inv.add("route", f"{method.upper()} {path}", f"{src}:{line_of(text, m.start())}", aliases=[path] if path != "/" else [])
    for pattern in ENV_READ_PATTERNS:
        for m in pattern.finditer(text):
            name = m.group(1)
            if name in ENV_BUILTINS or len(name) < 3:
                continue
            inv.add("env_var", name, f"{src}:{line_of(text, m.start())}", aliases=_env_aliases(name), detail="read by the code")
    for pattern, framework in CONTROLLER_PATTERNS:
        for m in pattern.finditer(text):
            name = m.group(1)
            if name.lower() in ("controller", "basecontroller", "applicationcontroller"):
                continue
            short = name[: -len("Controller")] if name.endswith("Controller") and len(name) > len("Controller") else name
            inv.add("controller", name, f"{src}:{line_of(text, m.start())}", detail=f"{framework}; route prefix /{short}")
    for pattern, label in SCHEDULE_PATTERNS:
        for m in pattern.finditer(text):
            value = next((g for g in m.groups() if g), "")
            window = text[m.end(): m.end() + 400]
            expr = re.search(r"Cron\.\w+\([^)]*\)|\"(?:[\d*/?,LW#-]+\s+){4,6}[\d*/?,LW#-]+\"", window) if "Hangfire" in label else None
            aliases = [expr.group(0).strip('"')] if expr else []
            inv.add("schedule", value, f"{src}:{line_of(text, m.start())}", aliases=aliases, detail=label + (f" ({aliases[0]})" if aliases else ""))


SCREEN_PATTERNS = [
    re.compile(r"<Route\b[^>]*?\bpath=\{?\s*[\"'`]([^\"'`]+)[\"'`]"),
    re.compile(r"\bpath:\s*[\"'`]([^\"'`]*)[\"'`]"),
]


def scan_screens(text: str, path: Path, relpath: str, src: str, inv: Inventory, test: bool) -> None:
    """SPA routes (React Router, Angular, Vue), Razor Pages and Blazor `@page`."""
    if test:
        return
    suffix = path.suffix.lower()
    parts = Path(relpath).parts
    if suffix in (".cshtml", ".vbhtml") and "Views" in parts and not path.name.startswith("_"):
        rest = parts[parts.index("Views") + 1:]
        if len(rest) == 2 and rest[0] not in ("Shared", "Layouts") and not re.search(r"^@page", text, re.M):
            controller, action = rest[0], Path(rest[1]).stem
            route = f"/{controller}" if action == "Index" else f"/{controller}/{action}"
            inv.add("screen", route, src, aliases=[f"Views/{controller}/{rest[1]}"], detail=f"MVC view ({controller}Controller.{action})")
            return
    if suffix in (".cshtml", ".razor"):
        page = re.search(r"^@page(?:\s+\"([^\"]*)\")?", text, re.M)
        if page:
            route = page.group(1)
            if not route:
                parts = Path(relpath).with_suffix("").parts
                tail = parts[parts.index("Pages") + 1:] if "Pages" in parts else parts[-1:]
                tail = [p for p in tail if p != "Index"]
                route = "/" + "/".join(tail)
            inv.add("screen", "/" + route.lstrip("/"), src, detail="Razor Page" if suffix == ".cshtml" else "Blazor page")
        return
    if suffix not in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue"):
        return
    if not re.search(r"react-router|createBrowserRouter|RouterModule|Routes\b|createRouter|VueRouter|vue-router|@tanstack/react-router", text):
        return
    for pattern in SCREEN_PATTERNS:
        for m in pattern.finditer(text):
            route = m.group(1).strip()
            if route in ("**", "*") or route.startswith(("http", "./", "../")) or ("/" in route and "." in route.rsplit("/", 1)[-1]):
                continue
            inv.add("screen", "/" + route.lstrip("/"), f"{src}:{line_of(text, m.start())}", detail="SPA route")


def file_route(relpath: str):
    """File-system routing: Next.js (app/ and pages/), Nuxt pages/, SvelteKit src/routes/. Returns (kind, path) or None."""
    parts = Path(relpath).parts
    name = parts[-1]
    if "routes" in parts and name in ("+page.svelte", "+server.ts", "+server.js"):
        segs = parts[parts.index("routes") + 1:-1]
        return ("route" if name.startswith("+server") else "screen", "/" + "/".join(s for s in segs if not s.startswith("(")))
    if "app" in parts and re.match(r"(page|route)\.(tsx|ts|jsx|js|mdx)$", name):
        segs = parts[len(parts) - parts[::-1].index("app"):-1]
        return ("route" if name.startswith("route") else "screen", "/" + "/".join(s for s in segs if not s.startswith(("(", "@"))))
    if "pages" in parts and re.search(r"\.(tsx|jsx|ts|js|vue)$", name) and not name.startswith("_"):
        segs = list(parts[len(parts) - parts[::-1].index("pages"):])
        segs[-1] = re.sub(r"\.(tsx|jsx|ts|js|vue)$", "", segs[-1])
        if segs[-1] == "index":
            segs = segs[:-1]
        kind = "route" if segs[:1] == ["api"] else "screen"
        return kind, "/" + "/".join(segs)
    return None


def scan_web_config(text: str, path: Path, src: str, inv: Inventory) -> None:
    m = re.match(r"(?:web|app)\.(\w+)\.config$", path.name, re.I)
    if m:
        inv.add("environment", m.group(1), src, detail="build configuration (config transform), not necessarily a deployment environment")
        return
    for m in re.finditer(r"<add\s+key=\"([^\"]+)\"\s+value=\"([^\"]*)\"", text):
        inv.add("config_key", m.group(1), f"{src}:{line_of(text, m.start())}", detail="appSettings")
    for m in re.finditer(r"<add\s+name=\"([^\"]+)\"[^>]*\bconnectionString=", text):
        inv.add("config_key", m.group(1), f"{src}:{line_of(text, m.start())}", detail="connectionStrings")


def scan_secrets(text: str, path: Path, src: str, inv: Inventory) -> None:
    if path.name.lower().endswith((".lock", "lock.json", ".sum")) or path.name.lower() in ("package-lock.json", "yarn.lock"):
        return
    hits = []
    for m in re.finditer(r"""["']?([\w.:-]+)["']?\s*[:=]\s*["']([^"'\n]{3,})["']""", text):
        key, value = m.group(1), m.group(2).strip()
        if _secret_key(key) and not PLACEHOLDER.match(value) and " " not in value:
            hits.append((line_of(text, m.start()), key, value))
    for m in re.finditer(r"<add\s+key=\"([^\"]+)\"\s+value=\"([^\"]{3,})\"", text):
        if _secret_key(m.group(1)) and not PLACEHOLDER.match(m.group(2)):
            hits.append((line_of(text, m.start()), m.group(1), m.group(2)))
    if path.suffix.lower() not in (".json", ".xml", ".config"):
        for m in re.finditer(r"(?m)^\s*(?:-\s*)?(?:export\s+)?([\w.-]+)\s*[:=]\s*([^\s\"'#,{}\[\]]{3,})\s*(?:#.*)?$", text):
            key, value = m.group(1), m.group(2)
            if _secret_key(key) and not PLACEHOLDER.match(value):
                hits.append((line_of(text, m.start()), key, value))
    for m in re.finditer(r"(?i)\b(password|pwd)\s*=\s*([^;\"'\s]{3,})", text):
        value = m.group(2)
        if not PLACEHOLDER.match(value) and not value.startswith(("{", "$", "%")):
            hits.append((line_of(text, m.start()), m.group(1) + " (connection string)", value))
    for pattern, label in TOKEN_PATTERNS:
        for m in pattern.finditer(text):
            hits.append((line_of(text, m.start()), label, m.group(0)))
    if hits:
        seen = sorted({(ln, key) for ln, key, _ in hits})
        detail = "; ".join(f"line {ln}: {key}" for ln, key in seen[:6]) + (" ..." if len(seen) > 6 else "")
        short = "/".join(Path(src).parts[-2:])
        fact = inv.add("plaintext_secret", src, src, aliases=[short] if short != src else [], detail=detail)
        fact.setdefault("_values", []).extend(v for _, _, v in hits)


def _secret_key(key: str) -> bool:
    last = re.split(r"[.:_-]{1,2}", key)[-1] if re.search(r"[.:]", key) else key
    return bool(SECRET_KEY.search(last)) and not SECRET_KEY_NOT.search(last)


def scan_csproj(text: str, path: Path, src: str, inv: Inventory, stack: set) -> None:
    packages = re.findall(r'<PackageReference\s+Include="([^"]+)"', text)
    framework = re.search(r"<TargetFrameworks?>([^<]+)<", text) or re.search(r"<TargetFrameworkVersion>([^<]+)<", text)
    if framework:
        stack.add(f".NET ({framework.group(1)})")
    notable = [p for p in packages if re.match(r"(FastEndpoints|MediatR|Microsoft\.EntityFrameworkCore|Npgsql|Dapper|Amazon\.Lambda|AWSSDK|MassTransit"
                                               r"|Hangfire|Serilog|Polly|Refit|FluentValidation|Swashbuckle|NSwag|xunit|NUnit|MSTest|Moq|NSubstitute"
                                               r"|FluentAssertions|Testcontainers|WireMock|Quartz|StackExchange\.Redis|Confluent\.Kafka|SSH\.NET|Grpc"
                                               r"|Microsoft\.AspNet\.Mvc|EntityFramework|Autofac|AutoMapper|Microsoft\.AspNetCore\.Components)", p)]
    notable = sorted(set(notable))
    for p in notable:
        if p.startswith("AWSSDK"):
            stack.add("AWSSDK")
        elif not any(p != q and p.startswith(q + ".") for q in notable):
            stack.add(p)
    if re.search(r"test", path.stem, re.I) or re.search(r"(xunit|nunit|mstest|Microsoft\.NET\.Test\.Sdk)", text, re.I):
        inv.add("test_suite", path.stem, src, detail="test project")
        return
    package_id = re.search(r"<PackageId>([^<]+)<", text)
    packable = package_id or re.search(r"<(IsPackable|GeneratePackageOnBuild)>\s*true", text, re.I)
    web = (re.search(r'Sdk="Microsoft\.NET\.Sdk\.(Web|BlazorWebAssembly|Razor|Worker)"', text) or re.search(r"<OutputType>\s*(Exe|WinExe)", text)
           or re.search(r"\{349c5851-65df-11da-9384-00065b846f21\}", text, re.I))
    if packable:
        inv.add("package", package_id.group(1) if package_id else path.stem, src, aliases=[path.stem], detail=".NET package (NuGet)")
    elif web:
        inv.add("package", path.stem, src, detail=".NET deployable (web/worker/exe)")


def scan_package_json(text: str, path: Path, relpath: str, src: str, inv: Inventory, stack: set) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    deps = {**as_dict(data.get("dependencies")), **as_dict(data.get("devDependencies")), **as_dict(data.get("peerDependencies"))}
    stack.add("Node.js")
    for dep in sorted(deps):
        if re.match(r"^(express|fastify|koa|hono|@nestjs/core|next|nuxt|react|react-dom|vue|@angular/core|svelte|@sveltejs/kit|vite|react-router(-dom)?"
                    r"|typeorm|prisma|@prisma/client|sequelize|mongoose|pg|mysql2|knex|jest|vitest|mocha|cypress|playwright|@playwright/test"
                    r"|aws-cdk-lib|@aws-sdk/[\w-]+|kafkajs|bullmq|ioredis|turbo|nx|lerna|react-native|expo|electron)$", dep):
            stack.add(dep)
    scripts = as_dict(data.get("scripts"))
    name = str(data.get("name") or path.parent.name)
    runnable = any(k in scripts for k in ("start", "dev", "serve"))
    lib = any(k in data for k in ("main", "module", "exports", "types"))
    if any(k.startswith("test") for k in scripts) or any(d in deps for d in ("jest", "vitest", "mocha")):
        inv.add("test_suite", f"{name} (npm test)", src, aliases=["npm test", "npm run test"], detail="npm scripts")
    root_of_workspace = bool(data.get("workspaces")) and "/" not in relpath
    if data.get("name") and not root_of_workspace:
        kind = "app" if runnable else ("library" if lib else "package")
        inv.add("package", name, src, detail=f"npm {kind}" + (", private" if data.get("private") else ""))
    return {"workspaces": bool(data.get("workspaces")), "runnable": runnable, "lib": lib and not data.get("private")}


def detect_stack_file(path: Path, text: str, src: str, inv: Inventory, stack: set) -> None:
    name = path.name.lower()
    if name in ("pyproject.toml", "requirements.txt", "setup.py", "pipfile"):
        stack.add("Python")
        for dep in ("fastapi", "flask", "django", "sqlalchemy", "celery", "pytest", "boto3", "pydantic", "alembic"):
            if re.search(rf"(?im)^\s*['\"]?{dep}\b", text) or re.search(rf"['\"]{dep}[><=~\['\"]", text):
                stack.add(dep)
        m = re.search(r"(?ms)^\[(?:project|tool\.poetry)\][^\[]*?^name\s*=\s*['\"]([^'\"]+)['\"]", text) if name == "pyproject.toml" else None
        if m:
            inv.add("package", m.group(1), src, detail="Python package")
    elif name in ("pom.xml", "build.gradle", "build.gradle.kts"):
        stack.add("JVM (Java/Kotlin)")
        for dep in ("spring-boot", "quarkus", "micronaut", "junit", "flyway", "liquibase"):
            if dep in text:
                stack.add(dep)
    elif name == "go.mod":
        stack.add("Go")
        m = re.search(r"(?m)^module\s+(\S+)", text)
        if m:
            inv.add("package", m.group(1), src, detail="Go module")
    elif name == "cargo.toml":
        stack.add("Rust")
    elif name == "gemfile":
        stack.add("Ruby")
        if "rails" in text:
            stack.add("rails")
    elif name == "composer.json":
        stack.add("PHP")
        if "laravel/framework" in text:
            stack.add("laravel")


# ---------------------------------------------------------------- classification

def _children(dirs: set, parent_name: str) -> int:
    """How many distinct sub-folders sit directly under folders named `parent_name`."""
    return len({d for d in dirs if "/" in d and d.rsplit("/", 2)[-2].lower() == parent_name}) if dirs else 0


STYLE_RULES = [
    ("MVC", lambda n, d: {"controllers", "views"} <= n),
    ("vertical slice", lambda n, d: _children(d, "features") >= 2 or _children(d, "slices") >= 2),
    ("layered / clean / onion", lambda n, d: len({"domain", "application", "infrastructure"} & n) >= 2),
    ("hexagonal (ports and adapters)", lambda n, d: {"ports", "adapters"} <= n),
    ("modular monolith", lambda n, d: _children(d, "modules") >= 2),
]


def classify(dirs: set, files: set, facts: list, stack: set, signals: dict) -> dict:
    """Suggests the document type and architectural styles from structure and facts (the agent confirms)."""
    names = {d.rsplit("/", 1)[-1].lower() for d in dirs}
    names |= {d.rsplit("/", 1)[-1].split(".")[-1].lower() for d in dirs}

    def count(kind):
        return sum(1 for f in facts if f["kind"] == kind)

    deployables = [f for f in facts if f["kind"] == "package" and re.search(r"deployable|npm app", f["detail"])]
    lower_stack = {s.lower() for s in stack}
    frontend_libs = lower_stack & {"react", "vue", "@angular/core", "svelte", "@sveltejs/kit", "next", "nuxt", "react-native", "expo"}
    mvc_markers = [m for m in ("web.config", "global.asax", "manage.py", "artisan", "config/routes.rb") if any(f.lower().endswith(m) for f in files)]
    styles = [label for label, rule in STYLE_RULES if rule(names, dirs)]
    code_files = signals.get("code_files", 0)
    iac = count("iac_resource") > 0 or signals.get("iac_files", 0) > 0
    evidence, suggested = [], "unknown"
    npm_apps = sum(1 for f in deployables if "npm app" in f["detail"])
    if (signals.get("workspace_tool") or signals.get("solutions", 0) >= 2 or npm_apps >= 3
            or (signals.get("iac_stacks", 0) >= 3 and len(deployables) >= 3)):
        suggested = "monorepo"
        evidence.append(f"workspace tooling: {signals.get('workspace_tool') or 'none'}; solutions: {signals.get('solutions', 0)}; "
                        f"npm apps: {npm_apps}; IaC stacks: {signals.get('iac_stacks', 0)}; deployable parts: {len(deployables)}")
    elif iac and code_files <= 5 and count("route") == 0 and count("screen") == 0:
        suggested = "infra"
        evidence.append(f"{signals.get('iac_files', 0)} IaC file(s) and almost no application code")
    elif frontend_libs and count("route") == 0 and not mvc_markers and count("controller") == 0:
        suggested = "frontend"
        evidence.append(f"frontend stack ({', '.join(sorted(frontend_libs))}); {count('screen')} screen route(s)")
    elif signals.get("library") and not deployables and not iac:
        suggested = "library"
        evidence.append("packable/exported package with no runnable entry point or infrastructure")
    elif mvc_markers or count("controller") >= 5 or "MVC" in styles or "modular monolith" in styles or (code_files > 400 and not iac):
        suggested = "monolith"
        evidence.append(f"{count('controller')} controller(s); markers: {', '.join(mvc_markers) or 'none'}; {code_files} source files")
    elif iac or count("route") or count("schedule"):
        suggested = "service"
        evidence.append(f"{count('iac_resource')} IaC resource(s), {count('route')} route(s), {count('schedule')} schedule(s)")
    if styles:
        evidence.append("structure suggests: " + ", ".join(styles))
    return {"suggested": suggested, "styles": styles, "evidence": evidence,
            "stats": {"source_files": code_files, "routes": count("route"), "screens": count("screen"), "controllers": count("controller"),
                      "packages": count("package"), "iac_resources": count("iac_resource")}}


# ---------------------------------------------------------------- driver

PIPELINE_NAMES = re.compile(r"^(azure-pipelines.*\.ya?ml|\.gitlab-ci\.ya?ml|jenkinsfile|bitbucket-pipelines\.ya?ml|buildspec.*\.ya?ml|cloudbuild\.ya?ml"
                            r"|appveyor\.ya?ml|\.travis\.ya?ml|codemagic\.ya?ml)$", re.I)
WORKSPACE_FILES = {"pnpm-workspace.yaml": "pnpm workspaces", "nx.json": "Nx", "turbo.json": "Turborepo", "lerna.json": "Lerna", "rush.json": "Rush"}


def scan(roots: list) -> dict:
    inv = Inventory()
    stack: set = set()
    dirs: set = set()
    files: set = set()
    signals = {"code_files": 0, "iac_files": 0, "iac_stacks": 0, "solutions": 0, "workspace_tool": None, "library": False}
    multi = len(roots) > 1
    for root in roots:
        root = root.resolve()
        prefix = f"{root.name}/" if multi else ""
        for path in walk(root):
            relpath = rel(path, root)
            src = prefix + relpath
            files.add(relpath)
            parent = relpath.rsplit("/", 1)[0] if "/" in relpath else ""
            while parent:
                dirs.add(parent)
                parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
            name = path.name.lower()
            suffix = path.suffix.lower()
            if name in WORKSPACE_FILES and "/" not in relpath:
                signals["workspace_tool"] = WORKSPACE_FILES[name]
            if suffix == ".sln":
                signals["solutions"] += 1
            is_config = suffix in CONFIG_EXT or name.startswith(".env") or name in ("dockerfile", "jenkinsfile")
            is_code = suffix in CODE_EXT
            test = is_test_path(relpath)
            if is_code and not test:
                signals["code_files"] += 1
                route = file_route(relpath)
                if route:
                    kind, rpath = route
                    if kind == "route":
                        inv.add("route", f"ANY {rpath}", src, aliases=[rpath], detail="file-based API route")
                    else:
                        inv.add("screen", rpath, src, detail="file-based page")
            if not (is_config or is_code or name in ("go.mod", "pipfile", "gemfile") or suffix == ".csproj" or suffix in (".md", ".adoc")):
                continue
            text = read(path)

            if PIPELINE_NAMES.match(path.name) or ("/.github/workflows/" in "/" + relpath and suffix in (".yml", ".yaml")) or relpath.endswith(".circleci/config.yml"):
                inv.add("pipeline", relpath, src, aliases=[path.name], detail="CI/CD definition")
                for env in re.findall(r"(?im)^\s*-?\s*(?:environment|deployment|stage):\s*['\"]?([A-Za-z][\w-]{1,15})['\"]?\s*$", text):
                    if env.lower() in ("dev", "development", "qa", "test", "uat", "hml", "homolog", "staging", "stg", "rc", "preprod", "prod", "production", "sandbox"):
                        inv.add("environment", env.lower(), src, detail="pipeline stage/environment")
            if suffix in (".yml", ".yaml", ".json") and not test:
                if name.startswith("samconfig"):
                    scan_samconfig(text, path, src, inv)
                elif re.search(r"(?m)^Resources\s*:|\"Resources\"\s*:", text) and re.search(r"AWS::|Transform", text):
                    signals["iac_files"] += 1
                    signals["iac_stacks"] += 1
                    doc = json.loads(text) if suffix == ".json" and text.lstrip().startswith("{") else parse_yamlish(text)
                    if isinstance(doc, dict):
                        scan_cloudformation(doc, src, inv)
                elif re.match(r"serverless\.ya?ml$", name):
                    signals["iac_files"] += 1
                    signals["iac_stacks"] += 1
                    doc = parse_yamlish(text)
                    if isinstance(doc, dict):
                        scan_serverless(doc, text, src, inv)
                elif re.match(r"(docker-)?compose[\w.-]*\.ya?ml$", name):
                    doc = parse_yamlish(text)
                    if isinstance(doc, dict):
                        scan_compose(doc, src, inv)
                elif suffix in (".yml", ".yaml") and re.search(r"(?m)^kind:\s*(Deployment|StatefulSet|CronJob|Job|DaemonSet)", text):
                    signals["iac_files"] += 1
                    for part in re.split(r"(?m)^---\s*$", text):
                        scan_kubernetes(parse_yamlish(part), src, inv)
                        for sched in re.findall(r"(?m)^\s*schedule:\s*['\"]?([^'\"\n]+)", part):
                            inv.add("schedule", f"{path.stem} cronjob", src, aliases=[sched.strip()], detail=sched.strip())
                elif name == "cdk.json":
                    signals["iac_files"] += 1
                if re.match(r"appsettings(\.\w+)?\.json$", path.name, re.I):
                    scan_appsettings(text, path, src, inv)
                elif re.match(r"application(-\w+)?\.ya?ml$", path.name):
                    scan_spring(text, path, src, inv)
                elif suffix == ".json" and path.parent.name == "config" and re.match(r"(default|production|development|staging|test|custom-environment-variables)\.json$", name):
                    try:
                        for key in as_dict(json.loads(text)):
                            inv.add("config_key", key, src, detail="node-config")
                    except ValueError:
                        pass
            if re.match(r"application(-\w+)?\.properties$", path.name) and not test:
                scan_spring(text, path, src, inv)
            if re.match(r"(web|app)(\.\w+)?\.config$", name) and not test:
                scan_web_config(text, path, src, inv)
            env_ts = re.match(r"environment\.(\w+)\.ts$", name)
            if env_ts and "environments" in relpath:
                inv.add("environment", env_ts.group(1), src, detail="Angular environment file")
            if suffix in (".tf", ".tfvars"):
                signals["iac_files"] += 1
                scan_terraform(text, src, inv)
                if suffix == ".tfvars":
                    inv.add("environment", path.stem, src, detail="terraform var file")
            if name.startswith(".env"):
                scan_dotenv(text, src, inv, example=bool(re.search(r"example|sample|template|dist", name)))
            if name == "dockerfile" or name.startswith("dockerfile."):
                for m in re.finditer(r"(?m)^ENV\s+([A-Za-z_][\w]*)", text):
                    inv.add("env_var", m.group(1), src, detail="Dockerfile ENV")
            if suffix == ".csproj":
                scan_csproj(text, path, src, inv, stack)
                if re.search(r"<(PackageId|IsPackable)>", text) and not re.search(r'Sdk="Microsoft\.NET\.Sdk\.(Web|Worker)"', text):
                    signals["library"] = True
            if name == "package.json":
                info = scan_package_json(text, path, relpath, src, inv, stack)
                if info.get("workspaces") and "/" not in relpath:
                    signals["workspace_tool"] = signals["workspace_tool"] or "npm/yarn workspaces"
                if info.get("lib") and not info.get("runnable"):
                    signals["library"] = True
            detect_stack_file(path, text, src, inv, stack)
            if is_code:
                scan_code(text, src, inv, test)
                scan_screens(text, path, relpath, src, inv, test)
                if relpath.endswith("config/routes.rb"):
                    for m in re.finditer(r"(?m)^\s*(get|post|put|patch|delete)\s+['\"]([^'\"]+)['\"]", text):
                        inv.add("route", f"{m.group(1).upper()} /{m.group(2).lstrip('/')}", src, aliases=["/" + m.group(2).lstrip("/")], detail="Rails route")
                    for m in re.finditer(r"(?m)^\s*resources?\s+:(\w+)", text):
                        inv.add("route", f"ANY /{m.group(1)}", src, aliases=[f"/{m.group(1)}"], detail="Rails resources")
                if name == "urls.py":
                    for m in re.finditer(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]", text):
                        inv.add("route", f"ANY /{m.group(1).lstrip('^').lstrip('/')}", src, detail="Django URL")
            if is_config and not name.endswith((".md",)):
                scan_secrets(text, path, src, inv)
            if suffix in (".md", ".adoc") and not test and (relpath.lower().startswith("docs/") or "/" not in relpath):
                inv.add("doc", relpath, src, detail="")
            if test and re.search(r"(?i)(^|/)(tests?|__tests__|spec)/?$", str(Path(relpath).parent.as_posix())) and is_code:
                folder = Path(relpath).parent.as_posix()
                if not any(f["kind"] == "test_suite" for f in inv.facts.values()):
                    inv.add("test_suite", folder, src, detail="test folder")
    facts = inv.as_list()
    return {
        "generator": "document-anything scan_repo",
        "repos": [str(r) for r in roots],
        "stack": sorted(stack, key=str.lower),
        "profile": classify(dirs, files, facts, stack, signals),
        "facts": facts,
    }


def public(report: dict) -> dict:
    """The report without private fields (secret values never leave the process)."""
    clean = dict(report)
    clean["facts"] = [{k: v for k, v in f.items() if not k.startswith("_")} for f in report["facts"]]
    return clean


def to_markdown(report: dict) -> str:
    profile = report["profile"]
    lines = ["# Repository inventory (scan_repo.py)", ""]
    lines.append("Repos: " + ", ".join(f"`{r}`" for r in report["repos"]))
    lines.append("")
    lines.append(f"**Suggested type: `{profile['suggested']}`** (confirm with the user). Evidence: " + ("; ".join(profile["evidence"]) or "none") + ".")
    if profile["styles"]:
        lines.append("")
        lines.append("Architectural style signals: " + ", ".join(profile["styles"]) + " (verify in the code; a codebase can mix styles by region).")
    lines.append("")
    lines.append("Stats: " + ", ".join(f"{k} {v}" for k, v in profile["stats"].items()) + ".")
    lines.append("")
    lines.append("Stack: " + (", ".join(report["stack"]) or "not detected"))
    lines.append("")
    lines.append("Which kinds are required depends on the document type (`new_doc.py --print <type>`); validate_wiki.py enforces them. "
                 "Exclude a fact on purpose with `<!-- coverage-ignore: <fact> | <reason> -->`.")
    for kind, (title, desc) in KIND_INFO.items():
        facts = [f for f in report["facts"] if f["kind"] == kind]
        if not facts or kind == "stack":
            continue
        lines += ["", f"## {title} ({len(facts)})", "", desc, "", "| Fact | Also matches | Detail | Source |", "| --- | --- | --- | --- |"]
        for f in facts:
            aliases = ", ".join(f"`{a}`" for a in f["aliases"][1:4])
            detail = f["detail"].replace("|", "\\|")
            sources = ", ".join(f"`{s}`" for s in f["sources"][:3])
            lines.append(f"| `{f['name']}` | {aliases} | {detail} | {sources} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repos", nargs="+", type=Path)
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("-o", "--output", type=Path)
    sys.stdout.reconfigure(encoding="utf-8")
    args = parser.parse_args(argv)
    for repo in args.repos:
        if not repo.is_dir():
            print(f"ERROR: {repo} is not a directory", file=sys.stderr)
            return 2
    report = public(scan(args.repos))
    text = json.dumps(report, indent=2, ensure_ascii=False) if args.format == "json" else to_markdown(report)
    if args.output:
        args.output.write_text(text, encoding="utf-8", newline="\n")
        print(f"OK: wrote {args.output} ({len(report['facts'])} facts)")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
