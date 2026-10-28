# Type: library

Code consumed by other code: package, SDK, generated client, shared kernel, framework extension, CLI library. Blueprint: `python <skill-dir>/scripts/new_doc.py --print library`.

Part I is for **users of the library** (other developers): what it is for, how to start, the public API, options and compatibility. Part II is for **maintainers**: internals, development, tests, publishing.

## Reading plan

| Area | Where to look | What to extract |
| --- | --- | --- |
| Public surface | Exported modules/namespaces, `index.*`, `__init__.py`, public classes/interfaces, `PublicAPI.Shipped.txt`, type declarations, generated clients | Every public entry point grouped by area; what is internal or unstable |
| Usage | README, samples, tests (best real usage examples), docs folder | Install command and the smallest working example (copied from samples/tests) |
| Options | Options/settings classes, DI extension methods (`AddX(options => ...)`), env vars read, config keys | Every option with default and effect |
| Compatibility | Target frameworks, `engines`, `python_requires`, peer dependencies, CI matrix | Supported runtimes and dependency versions |
| Internals | Main components, extension points, I/O, threading/async, caching | How it works inside, what it does to the host application |
| Consumers | Other repos the user points to, dependency manifests, package feed stats if provided | Who uses which version for what |
| Build, test | Project files, scripts, test projects, linters | Exact commands, labelled run/copied/derived |
| Publishing | Pipelines, `PackageId`/`name`/version source (tags, GitVersion, changesets), changelog, feed configuration | How a version is cut and published, who can publish |
| History | Git tags, changelog, breaking changes | Versions and migrations between majors |

## Watch for

- **Examples must compile.** Copy them from tests or samples, or derive them from signatures and label them as derived. An invented example is worse than none.
- **Breaking-change policy.** Say what counts as breaking and how deprecations are announced; consumers depend on it.
- **Side effects on the host.** Global state, background threads, network calls at import time and logging configuration belong in `architecture` and `risks`.

## Gate notes

Coverage requires:

- packages → `publishing` or `quick-start`;
- env vars the library reads → `configuration-options`;
- pipelines, test suites and plaintext-credential files.
