# Type: monolith

One application holding many business areas. It can be MVC, layered/clean/onion, vertical slice, hexagonal, modular monolith, or (most often) a mix by region. Blueprint: `python <skill-dir>/scripts/new_doc.py --print monolith`.

A service document answers "what does it do and who talks to it". A monolith document must also answer **"how is it organised inside, and where do I change things without breaking them"**. The sections `architecture-style`, `module-map` and `adding-a-feature` carry that.

## Reading plan

Monoliths are large: split by **module or business area**, not only by technical area. Get the module list first (top-level folders, areas, projects, namespaces, menu entries), then give each parallel explorer a set of modules plus the cross-cutting rows below.

| Area | Where to look | What to extract |
| --- | --- | --- |
| Style and layering | Solution/project references, folder conventions (`Controllers/Models/Views`, `Features/<X>/`, `Domain/Application/Infrastructure`, `Modules/<X>/`, `ports/adapters`), base classes, DI registrations, MediatR/handlers | Which style(s) and where, the dependency rule, where it is broken (cite the files) |
| Modules | Areas, module folders, namespaces, menus, route prefixes, DbContexts or schemas per module | Responsibility of each module, its code, its tables, which modules it calls or shares tables with |
| UI | Controllers + Views, Razor Pages, Blazor pages, server templates (ERB, Blade, Django templates), menus, layout/partials, client-side scripts bundled with the views | Every screen: route, purpose, controller/page, permission, menu entry |
| Routing | `RouteConfig`/`MapControllerRoute`, attribute routes, Rails `routes.rb`, Django `urls.py`, Laravel `routes/*.php` | Conventional and explicit routes, areas, API vs pages |
| Data | ORM (EF6/EF Core/NHibernate/ActiveRecord/Django ORM/Eloquent), migrations or SQL scripts, stored procedures, views, triggers | Tables per module, shared tables (coupling), procedures the code depends on |
| Background work | Hangfire/Quartz/Sidekiq/Celery/hosted services/Windows services/scheduled tasks/cron | Every job: trigger with time zone, what it does, failure handling, how to run by hand |
| Configuration | `Web.config` + transforms (`Web.Release.config`...), `appsettings*.json`, `.env`, `config/*.yml`, settings tables in the database, feature flags | Every setting per environment, where it lives, who provides secrets |
| Integrations | Service references (WCF/SOAP), HTTP clients, SDKs, file drops (FTP/SFTP/shared folders), e-mail | Each dependency and what happens when it fails |
| Security | Authentication (Forms, Identity, OIDC, Windows), authorisation attributes/filters, roles and permissions tables, anti-forgery, plaintext credentials | Who can see and do what, per screen and route |
| Build, run, test | Solution, build scripts, IIS Express/Kestrel/rails server, seed data, test projects | Exact commands (labelled run/copied/derived), what each suite covers |
| Delivery | Pipelines, publish profiles, web deploy, IIS/VM/container, migration steps, maintenance windows | How a release reaches each environment, how to roll back |
| History | Git log, ADRs, migration plans | Timeline, decisions, modernization direction |

## Watch for

- **Coupling hot spots.** Shared tables, cross-module calls and god classes. Name them in `module-map` and `risks`; they are what makes changes dangerous.
- **`adding-a-feature` is the most valuable section for a new engineer.** Write it as a recipe with real files to copy from, all registration points (DI, routes, menus, permissions, resources) and the tests expected.
- **Legacy configuration.** `Web.config` transforms differ per build configuration (Debug/Release/custom). Document what each sets, without secret values.
- **Screens.** The scanner lists MVC views (`Views/<Controller>/<Action>.cshtml`), Razor Pages and Blazor pages as screens; each must appear in `ui`.
- **Config transforms are build configurations** (`Web.Release.config`), not necessarily deployment environments. Map which build configuration goes to which environment, or ask.
- **Many controllers.** Coverage requires every controller to be mentioned in `ui`, `api`, `module-map` or `code-walkthrough`. A table per module is the readable way to do it.

## Gate notes

Coverage requires everything a service requires, plus controllers and screens:

- routes → `api` or `ui`;
- screens → `ui`;
- controllers → `ui`, `api`, `module-map` or `code-walkthrough`;
- schedules (including in-process jobs) → `jobs`;
- environments and deployment parameters → `configuration`.
