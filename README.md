# Public legal metrology test selection

This is a bounded public selection of Python source and complete test modules.
It is not the full application. Features with excluded modules or private data
are outside this selection. The retained candidate control modes are unchanged.

Python 3.14 is preferred. CI tries 3.13 only if setup-python cannot obtain 3.14.
Install `pytest>=8,<10`, then run a shard in an empty temporary directory:

```sh
python -B .ci/run.py --shard 0 --work /tmp/public-test-shard-0
```

The runner verifies all SHA-256 chunks, reconstructs the public SQLite snapshot,
checks its integrity, relationships and table counts, and executes the shard in
an isolated application directory. It rejects skipped tests and blocked access.
The exact selection and order are in `.ci/shards.json`. CI runs at most 20 jobs;
each job has a 14-minute time limit. This is a limit, not a cloud timing result.

The database contains only selected BOE and Official Journal/EUR-Lex material.
Original paid standards, restricted publishers, certificates, customer datasets
and database history are excluded. Database provenance is in
`base_publica/sources.json`; reconstruction hashes are in its `manifest.json`.
The source selection is tested with synthetic fixtures and does not exercise
the full database-backed application. CI reconstructs and checks the snapshot.

BOE source attribution: https://www.boe.es/
EUR-Lex source attribution: https://eur-lex.europa.eu/
The local provenance identifies the source and version of each retained work.
No official endorsement or independent legal verification is implied.
