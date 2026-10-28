# Type: process

How people and systems get something done: an operational, business or engineering process (month-end close, customer onboarding, incident response, release, refund approval...). Blueprint: `python <skill-dir>/scripts/new_doc.py --print process`.

The reader is someone who has to **perform, approve, audit or improve** the process, often on their first time. A good process document lets them do the job without asking anyone.

## Sources and interview

There is no code to prove the truth, so the sources are everything. Ask the user for:

- documents: manuals, policies, procedures, spreadsheets, forms, tickets, chat exports;
- the systems involved (and whether you may look at them);
- the people who perform each role.

Every source goes in the front matter `sources` with a date and must be cited in `references`. The validator checks both.

When the sources leave gaps, run one structured interview (a batch of questions, step 4 of SKILL.md). The answers become a source: "Entrevista com <papel/nome>, <data>". Ask about:

- **trigger and outcome**: what starts the process, what "done" looks like, how often it runs and how long it takes;
- **steps**: in order, and for each one who does it, what they receive, what they produce, in which system, and by when;
- **decisions and approvals**: who decides and by which criteria (values, limits);
- **exceptions**: what goes wrong most often, what happens then, who to escalate to;
- **controls**: what evidence is kept, where and for how long, and which audits apply;
- **metrics**: SLAs and KPIs, and where the data comes from;
- **pain points and planned changes**.

## Interview priorities

SKILL.md caps the batch at about 8 questions, while the topics above produce many more. Ask first what blocks the most cells: owners of steps, approval limits, deadlines and the accountable role per step. Everything else goes to `open-questions` with who can answer. If no interview happens, note it in `references` (not in `sources`).

## Writing

- `steps` is the heart of the document: one row per step, with every column filled. Use "—" only when a source says there is none; when no one knows, the unknown goes to `open-questions` instead of a blank cell (the validator rejects empty cells).
- `roles` and `raci` must agree, by exact name (checked by the validator):
  - every role in Roles is a column header of the RACI matrix;
  - every step owner is a role from Roles;
  - every step has a RACI row (by name or number);
  - cells are R, A, C, I or combinations (`R/A`), or "—" for "no participation stated by the sources";
  - exactly one A per step. When the sources name only who performs a step, mark the performer `R/A` and add an open question about accountability.
- **Conditional paths** (approval tiers by value, exceptions by type) are one row per branch with the condition in the step name ("5a. Aprovação até R$ 500,00"), or a decision step followed by its branches. Say when the sources do not tell whether approvals run in sequence or in parallel.
- **Sources in the passive voice** ("os pedidos são devolvidos") have no actor. Attribute the step to the role or area that owns the source document, say so, and add an open question to confirm.
- Name roles, not only people. People change; write the role in the tables and who holds it today in `roles`.
- Use a flowchart or a sequence diagram with roles as participants for `flow`. Show decision points as diamonds with the criteria on the edges.
- **Personal data:** names and roles of people given by the sources are fine. No personal documents, contact details or salaries unless the user explicitly asks and the document's audience is allowed to see them.

## Verification

The Verifier checks every step, owner, deadline, value limit and rule against the sources, citing the source and location, and flags statements with no source.
