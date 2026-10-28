# Type: service

A deployable service: HTTP API, worker, queue consumer, function app, usually with its own infrastructure as code. Blueprint: `python <skill-dir>/scripts/new_doc.py --print service`.

The reader of Part I is product, operations and support; the reader of Part II is the engineer who will change, operate or debug it next.

## Reading plan

| Area | Where to look | What to extract |
| --- | --- | --- |
| Entry points | `Program.cs`/`Startup.cs`, `main.*`, `app.*`, handlers named in IaC (`Handler:`), `Dockerfile` `CMD`/`ENTRYPOINT`, `package.json` `main`/`start` | Every way execution starts: HTTP host, function handlers, consumers, schedulers, CLIs |
| HTTP API | Endpoint/controller/router files, OpenAPI specs, auth attributes/policies, validators | Method + path, request/response shape, validation, auth per route, error codes |
| Domain | Entities, enums (with numeric values), domain services, rules, state transitions | Business rules, statuses and transitions, invariants, limits, time zones |
| Data | ORM models, migrations (in order), repositories, raw SQL, stored procedures, legacy databases | Tables, keys, indexes, who writes/reads what, shared databases |
| Async | IaC queues/topics/streams/schedules, consumers, publishers, message contracts, retry/DLQ, idempotency | Producer → channel → consumer, payloads, failure behaviour |
| Integrations | HTTP/SDK clients, base URLs from config, timeouts, retries, circuit breakers | Each dependency and what happens when it fails |
| Configuration | appsettings/.env/application.yml/config files, binding classes, parameter-store loaders (prefix, reload, precedence), IaC env vars, per-environment overrides (samconfig, tfvars, Helm values, pipeline variables) | Every setting, where it lives per environment, which are secrets, which are fixed by IaC, which must be created by hand |
| Infra | `template.y*ml`, `samconfig*`, `serverless.yml`, `*.tf`, CDK, Helm/K8s, docker-compose | Deployable units, triggers, timeouts/memory, IAM, network, environments, local dependencies |
| Security | Auth setup (JWT issuer/audience, API keys, mTLS), IAM policies, CORS, PII, plaintext credentials from the scan | Who can call what, what is sensitive, what is exposed |
| Observability | Logger setup, log groups, metrics/alarms, tracing, health checks | Where to look when it breaks; ready queries |
| Build, test, run | Solution/project files, test projects and fixtures (Testcontainers, LocalStack), scripts, README | Exact commands, prerequisites with versions, what each suite needs |
| Delivery | Pipelines (stages, environments, approvals, versioning), tags | How code reaches each environment and how to roll back |
| History | Git log, PR titles, ADRs, planning docs | Timeline and the reasons behind decisions |

## Watch for

- **Configuration is the most consulted section.** Build it per environment, with the full parameter path, type, who provides it, and whether it exists or must be created. Never write secret values.
- **Schedules.** Translate AWS `cron()` (UTC) to local time. `rate()` has no wall-clock time.
- **Proxy routes** (`/{proxy+}`) mean routing happens in code. Say so, and list the real routes from the code.
- **Status codes and enums** go in with their numeric values: support teams read them in logs and databases.

## Gate notes

Coverage requires environments, deployment parameters, IaC resources, env vars, config sections, parameter-store references, routes, schedules, pipelines, local containers, test suites and plaintext-credential files. They have home sections:

- environments and deployment parameters → `configuration`;
- routes → `api`, with method and path on the same line;
- schedules → `jobs`;
- queues, topics and streams → `messaging`.
