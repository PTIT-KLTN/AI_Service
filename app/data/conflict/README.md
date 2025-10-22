This folder stores the crawled raw evidence and the aggregated dataset that powers the
conflict guardrail.  Raw CSV snapshots are taken from food safety advisories and
traditional medicine bulletins published by Vietnamese governmental and professional
organisations.  Each row in the raw dataset retains the original source attribution so we
can regenerate the guardrail data whenever new advisories are added.

Run the helper script below whenever you refresh the snapshots:

```bash
python scripts/build_conflict_dataset.py
```

The script aggregates conflicts by dish, merges duplicated entries across sources, and
produces `ingredient_conflicts.json`, which is read by `ConflictDetectionService`.