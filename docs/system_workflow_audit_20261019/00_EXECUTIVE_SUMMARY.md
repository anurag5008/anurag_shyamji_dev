# Executive summary

## Scope and confidence

Read-only repository audit of `/home/hp/frappe-bench-v16/apps/ivri_od`, Frappe v16 bench layout, installed-app manifest, and checked-in app sources. App repository: branch `main`, commit `eb897fed3db184537945a15524a022dba34698b8`; app worktree clean. Bench root has no Git metadata. The site `shyamji` configuration was not opened and no database/runtime calls were made; live installed DocTypes, Custom Fields, roles, permissions, Workflow records, document samples, and runtime behavior are therefore unverified. See manifest for exclusions.

Evidence statuses in this package distinguish source implementation (`VERIFIED IN CODE`) from checked-in definitions (`VERIFIED IN METADATA`), tests reviewed but not run (`NOT RUN`), and unavailable runtime facts (`UNKNOWN`). Code presence is not runtime proof.

## System map

`ivri_od` is a custom Procurement app. It imports PPAS transit-pass information, manages procurement season/target allocation and party/master data, associates transit passes with RST and gate/vehicle movements, performs gate entry/exit, quality checks, weigh bridge measurement and GRN capture, and provides operational reports (including Mandi Book and Abstract Physical). The app is installed alongside `frappe`, `erpnext`, `ivri_app`, and `ivri_rice_ag` per `sites/apps.txt`; whether all are installed on `shyamji` is not live-verified.

There is no dedicated CMR/milling/dispatch/reconciliation DocType, controller, report, or test discovered in `ivri_od`. “CMR Season” on GRN and season-mapping rice-yield/due/dispatched fields expose partial accounting/readiness data only. The rice-yield calculation exists, but dispatch acceptance, recovery, custody, grade/by-product accounting, and reconciliation are absent or unknown.

## Major verified findings

1. TP receipt links by `pass_unique_key`; GRN validation copies TP, RST, QC and weighment information. GRN uniqueness is enforced per non-cancelled WBM, not per TP, so multiple GRNs per TP are structurally supported. However, checked-in metadata does not mark GRN Note (or any Procurement DocType) submittable and defines no workflow states, while canonical TP fulfillment counts only `docstatus=1`; absent live customization/direct status mutation, this helper may never count ordinary GRNs.
2. WBM net weight is `max((load - tare when both are truthy, otherwise load) - gunny - deduction, 0)`, rounded to 3 decimal QTL. Zero/missing tare therefore makes load the gross; strict GRN auto-generation separately requires tare > 0.
3. Canonical TP helper counts `docstatus=1`, but checked-in GRN metadata is not submittable and has no states. Tests manually set docstatus values. Rollup and Mandi Book use `docstatus < 2`, so ordinary draft records count there. This is a code/metadata/test-model mismatch; actual site customization is unverified.
4. Chhatni “assigned rate” is treated as a percentage in the formula/status code; field naming and upstream labels include kg-per-quintal wording. The unit semantics require business confirmation. ±0.30 percentage-point tolerance is hard-coded.
5. `Season Mapping` calculates paddy procurement using a pass-key parsed, non-cancelled GRN aggregation that adds GRN net weight and entry quantity, caps per TP, and deduplicates entry IDs. This differs from receipt-only TP fulfillment and its status filters.
6. Local procurement is actively rejected for new transactions in WBM and GRN validation (while legacy paths/helpers and DocTypes remain). A local purchase order controller exists, but GRN hooks that would update its quantities are empty stubs.
7. CMR “rice due” is calculated as paddy quantity × `rice_yield` / 100. `rice_dispatched` exists as a field but no dispatch workflow was found.

## Readiness and gaps

Procurement path is substantially represented in code and checked-in tests; runtime completeness, user permissions, live metadata sync, and actual operation are unverified. Major audit risks are stale/copied numeric values, draft-vs-submitted divergence, `docstatus < 2` aggregations, manual-vs-table gunny weight precedence, tolerance-unit ambiguity, unverified vehicle/open-gate uniqueness and concurrent submissions, and no CMR execution lifecycle.

## Deliverables

See `01_DOCTYPE_INVENTORY.md` (includes exact checked-in field metadata), `02_BUSINESS_WORKFLOWS.md`, `03_FORMULAS_AND_TOLERANCE.md`, `04_RELATIONSHIPS_AND_DATA_LINEAGE.md`, `05_DYNAMIC_SCENARIOS_AND_GAPS.md`, `06_CMR_READINESS_AND_ROADMAP.md`, `07_WORKFLOW_DIAGRAMS.md`, `08_EVIDENCE_AND_OPEN_QUESTIONS.md`, and `09_AUDIT_MANIFEST.md`.
