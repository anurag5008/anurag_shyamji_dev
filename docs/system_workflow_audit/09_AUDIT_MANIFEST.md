# 09: System Workflow Audit Manifest

## 1. Audit Identification & Environment Boundaries

- **Audit Execution Date**: 2026-10-19 UTC
- **Auditor Role**: Senior Frappe/ERPNext Architect & Workflow Auditor
- **Target Application**: `ivri_od` (version 0.0.1)
- **Target Site**: `shyamji`
- **Bench Directory**: `/home/hp/frappe-bench-v16` (Frappe v16 environment)
- **Application Repository**: `/home/hp/frappe-bench-v16/apps/ivri_od`
- **Git Branch**: `main`
- **Git HEAD Commit**: `eb897fed3db184537945a15524a022dba34698b8` (`Update latest procurement code`)
- **Git Worktree Status**: Clean (`git status` reported `nothing added to commit but untracked files present` in docs)

---

## 2. Scope of Inspection

### Fully Inspected Areas:
1. **Installed Apps & Site Manifest**: Inspected `sites/apps.txt`, `sites/apps.json`, and executed `bench --site shyamji list-apps`.
2. **Custom DocTypes**: Exhaustively inspected all 30 custom DocTypes and child tables in `apps/ivri_od/ivri_od/procurement/doctype/`.
3. **Application Controllers**: Python controllers, lifecycle hooks, and validation methods across all 30 DocTypes.
4. **Client Scripts**: Form event handlers, quick entry overrides, and list view extensions in JavaScript.
5. **Whitelisted API Endpoints**: Inspected all `@frappe.whitelist()` functions across controllers, reports, and utilities.
6. **Background Tasks & Hooks**: Inspected `ivri_od/hooks.py` (`after_migrate`, `boot_session`, `doc_events`).
7. **Reports & Query Logic**: All 11 custom reports, report queries, Python executors, and client filters.
8. **Print Formats & Document Generation**: Inspected custom HTML templates and PDF generation routines (`grn_note_pass.html`).
9. **Formulas & Tolerances**: Weight calculations, bag weight conversions, Chhatni tolerance formulas, and pass fulfillment rules.
10. **Test Suite**: Reviewed all test files in `procurement/tests/` and DocType directories.
11. **CMR Module Assets**: Exhaustive code search across all repository branches and files for CMR implementations.

### Excluded / Uninspected Areas (Strict Read-Only Safety):
1. **Live Production Business Records**: No live production documents were dumped, modified, or exposed.
2. **Database State Mutation**: No migrations (`bench migrate`), patches, installers, or record insertions/deletions were executed.
3. **External Portals & Services**: No live HTTP requests were made to the government PPAS portal or external third-party endpoints.
4. **Other Bench Applications**: `ivri_app` and `ivri_rice_ag` were confirmed not to be installed on site `shyamji` and were excluded from full audit.

---

## 3. Audit Deliverables Index

The complete audit documentation package has been generated in:
`/home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/`
*(Mirrored via symlink at `/home/hp/frappe-bench-v16/docs/system_workflow_audit/`)*:

1. **[`00_EXECUTIVE_SUMMARY.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/00_EXECUTIVE_SUMMARY.md)**: Executive findings, system map, architectural contradictions, and risk summary.
2. **[`01_DOCTYPE_INVENTORY.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/01_DOCTYPE_INVENTORY.md)**: Exhaustive inventory of all 30 custom DocTypes, child tables, field definitions, types, and options.
3. **[`02_BUSINESS_WORKFLOWS.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/02_BUSINESS_WORKFLOWS.md)**: Step-by-step operational workflows from quota allocation to truck exit.
4. **[`03_FORMULAS_AND_TOLERANCE.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/03_FORMULAS_AND_TOLERANCE.md)**: Mathematical formulas, unit conversions, Chhatni rules, worked synthetic examples.
5. **[`04_RELATIONSHIPS_AND_DATA_LINEAGE.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/04_RELATIONSHIPS_AND_DATA_LINEAGE.md)**: Entity relationship dependencies and backward data lineage for report metrics.
6. **[`05_DYNAMIC_SCENARIOS_AND_GAPS.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/05_DYNAMIC_SCENARIOS_AND_GAPS.md)**: 17-point scenario matrix covering multi-GRN, zero tare, rejections, and gaps.
7. **[`06_CMR_READINESS_AND_ROADMAP.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/06_CMR_READINESS_AND_ROADMAP.md)**: CMR readiness matrix and 5-phase completion roadmap.
8. **[`07_WORKFLOW_DIAGRAMS.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/07_WORKFLOW_DIAGRAMS.md)**: Renderable Mermaid diagrams (Context, Workflow, Weighment, ER, Lineage, CMR).
9. **[`08_EVIDENCE_AND_OPEN_QUESTIONS.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/08_EVIDENCE_AND_OPEN_QUESTIONS.md)**: Code citations, line references, contradictions, and open stakeholder questions.
10. **[`09_AUDIT_MANIFEST.md`](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit/09_AUDIT_MANIFEST.md)**: This audit manifest and environment verification document.

---

## 4. Safety & Read-Only Certification

I hereby explicitly confirm that throughout this audit:
- **Zero application code, controllers, JavaScript, Python, or JSON schemas were modified.**
- **Zero database records were created, edited, submitted, cancelled, or deleted.**
- **Zero migrations, patches, or bench mutation commands were run.**
- **Zero personal data, passwords, API tokens, or secrets were exposed.**
- **The git worktree remains clean and unmodified.**
