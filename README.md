# Public candidate test battery

66 complete test modules from candidate 4c280f5, split into 20 independent jobs.

The corpus and PDF library contain only the BOE and EUR-Lex/Official Journal sources identified by SHA-256 in their manifests. Technical-standard identifiers and titles are bibliographic metadata. Restricted corpus, customer cases, credentials and private repository history are excluded.

Run a shard with Python 3.14 on Windows, pytest and PyMuPDF from `.ci/requirements.txt`, and Git's Xpdf:

```powershell
python -m pip install -r .ci/requirements.txt
python -X utf8 -B .ci/run.py --shard 0 --work ../public-test-work-0
```

Use a new work directory outside this tree. Each module gets a separate writable source copy, a verified public database, isolated user/cache/temp directories, and a read-only public library. Test execution blocks network access and unapproved processes. Prerequisite installation in Actions uses the network.

The common query fixture uses the verified public snapshot. Explicit reconstruction fixtures rebuild from the public library. The independent-model reviewer is the original test double; no model is called and model judgment is not evaluated. Application control modes are preserved.

This is a selected test distribution. Passing it does not certify the complete candidate, a production deployment or excluded documents. The workflow targets Windows, matching local validation; Linux coverage of the expanded selection is not claimed.

Source attribution: https://www.boe.es/ and https://eur-lex.europa.eu/ . Reuse basis is the one authorized for this delivery: BOE public-information reuse and Commission Decision 2011/833/EU. No additional online legal verification was performed.
