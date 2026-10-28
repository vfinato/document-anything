# Type: product

A product or program as its users and the business see it: who it serves, what it does, how success is measured, where it is going. Blueprint: `python <skill-dir>/scripts/new_doc.py --print product`.

The reader is anyone joining or depending on the product: product managers, designers, sales and support, leadership, and engineers who need the "why" behind the systems.

## Sources and interview

Ask the user for:

- product documents: PRDs, one-pagers, decks, roadmaps, release notes;
- dashboards and metric definitions;
- research and support data;
- the systems or repos that implement the product.

Every source goes in the front matter `sources` with a date and must be cited in `references`.

Interview topics when the sources leave gaps:

- **audiences**: who they are, their need, how many there are;
- **the problem and the value proposition**;
- **features**: for each one, who it serves, its status and how success is measured;
- **the north-star and supporting metrics**, with their exact definitions and current values;
- **roadmap and its confidence**;
- **dependencies**: teams, vendors and contracts;
- **support and operations model**;
- **pricing**, when relevant.

## Writing

- `features` rows are complete: every feature names its audience (an audience listed in `users`, checked by the validator), the problem it solves, its status and the metric that shows it works.
- Metrics have exact definitions (numerator, denominator, period, filters) and a dated current value. "Engagement" without a definition is not a metric.
- Roadmap items carry the dates the sources give. Never invent dates; uncertain items say so.
- When implementing systems are known, link their documents (for example a `service` or `frontend` document) from the feature or from `dependencies`.

## Verification

The Verifier checks every number, date, status and claim against the sources, and flags statements with no source.
