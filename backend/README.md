# AoE2 Lab — backend

FastAPI service that parses Age of Empires II replays and derives metrics from
them. See the [repository README](../README.md) for setup, what is measured, and
why some metrics are reported as unavailable.

```
app/
  api/          HTTP layer — routers and dependencies, no business logic
  core/         config, logging, errors
  db/           SQLAlchemy models, session management, portable column types
  schemas/      Pydantic request/response models
  services/
    parser/     the ONLY place that imports mgz; the ReplayParser seam
    analysis/   metric derivation, insights, the on-disk store, the DB index
alembic/        migrations
tests/          pytest suite, run against real replay fixtures
```

## The parser seam

Nothing outside `services/parser/` imports `mgz`. Everything else depends on the
`ReplayParser` Protocol and the dataclasses beside it, so swapping the parsing
library means implementing that Protocol and nothing else.

`services/parser/reference.py` resolves object and technology IDs through the
`aocref` dataset rather than hard-coded tables — one logical entity has many IDs,
so grouping by resolved *name* is the only stable way to ask what something is.

## Tests

```bash
pytest              # 46 tests, ~16s, SQLite by default — no containers needed
TEST_DATABASE_URL=postgresql+psycopg://... pytest   # against the real dialect
```

The suite runs against real `.aoe2record` files in `tests/fixtures/`, chosen to
cover distinct parser paths: one where unit-queue commands decode, one where they
do not, and one too old to parse at all.
