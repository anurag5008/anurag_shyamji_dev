# Audit manifest

- Audit timestamp: 2026-10-19 UTC (environment date; exact clock timestamp not recorded).
- Bench directory: `/home/hp/frappe-bench-v16` (not a Git repository).
- Application repository: `/home/hp/frappe-bench-v16/apps/ivri_od`.
- Branch: `main`.
- Commit: `eb897fed3db184537945a15524a022dba34698b8`.
- Worktree: clean (`git status --short --branch` showed `## main...origin/main`).
- Scope: checked-in `ivri_od` procurement DocTypes, JSON field metadata, Python/JS controllers, hooks, report definitions/implementations, tests by file inventory and targeted code inspection, CMR code search; bench `sites/apps.txt`.
- Site: `shyamji` named by request but database/runtime was not accessed. No credentials/config content emitted.
- App manifest: bench lists `frappe`, `ivri_od`, `erpnext`, `ivri_app`, `ivri_rice_ag`; not verified per-site.
- Changes: documentation only in this new directory. No app code/config/business documents/database state modified.
- Tests: none executed. Existing tests were inventoried/referenced only; developer instruction prohibits running tests unless requested.
- Exclusions: live site metadata, roles/permissions/workflows, actual data, SQL indexes, report execution, UI/browser behavior, PPAS integration, background execution, and complete audit of other apps.

## Deliverables

1. `00_EXECUTIVE_SUMMARY.md`
2. `01_DOCTYPE_INVENTORY.md`
3. `02_BUSINESS_WORKFLOWS.md`
4. `03_FORMULAS_AND_TOLERANCE.md`
5. `04_RELATIONSHIPS_AND_DATA_LINEAGE.md`
6. `05_DYNAMIC_SCENARIOS_AND_GAPS.md`
7. `06_CMR_READINESS_AND_ROADMAP.md`
8. `07_WORKFLOW_DIAGRAMS.md`
9. `08_EVIDENCE_AND_OPEN_QUESTIONS.md`
10. `09_AUDIT_MANIFEST.md`
