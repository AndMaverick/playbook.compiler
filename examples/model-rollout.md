---
owner: Platform AI
version: 1.2.0
reviewed: 2026-09-01
---
# Model rollout

Moving a new model version into production. Every step has a named owner, and the risky ones are gated.

## Step 1: Evaluate {risk=1}
Run the offline suite first. See step 2 for what happens if it fails.
- [x] Baseline recorded @ana due:2026-10-01
- [ ] Regression gate green @ana due:2026-10-05 blocked-by:1.1
  - [ ] Cost per task within 10 percent of baseline @ana
- [ ] Red-team results reviewed @priya

## Step 2: Approve {risk=2}
- [ ] Risk owner signs off !approval @dmitri
- [ ] Rollback plan reviewed @dmitri

## Step 3: Ship {risk=4}
Rollback: revert the routing table to the previous model id and flush the cache.
```
## Step 9: this is an example command, not a step
kubectl rollout restart deploy/router
```
- [ ] Canary at 5 percent for 24 hours @sam blocked-by:2.1
- [ ] Ship approval !approval @dmitri
- [ ] Rollback: previous model id pinned @sam
