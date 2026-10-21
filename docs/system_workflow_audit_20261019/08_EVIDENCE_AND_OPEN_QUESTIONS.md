# Evidence and open questions

## Evidence map

| Area | Source | Evidence status |
|---|---|---|
| App repository state | `apps/ivri_od` Git metadata, branch `main`, clean; commit recorded in manifest | VERIFIED IN CODE / repository |
| Installed app manifest | `sites/apps.txt` | VERIFIED IN METADATA (bench-level manifest; not site-specific) |
| Custom DocTypes and fields | `ivri_od/procurement/doctype/*/*.json` | VERIFIED IN METADATA (checked-in only) |
| Controllers/lifecycle | procurement `*.py` controllers | VERIFIED IN CODE |
| TP/chhatni arithmetic | `procurement/grn_tp_fulfillment.py` | VERIFIED IN CODE |
| Weight arithmetic | WBM controller | VERIFIED IN CODE |
| Reports | report Python/JSON/JS/HTML files | VERIFIED IN CODE/METADATA |
| Tests | tests under procurement and DocType folders | VERIFIED IN CODE as test assets; NOT RUN |
| Site-specific installed apps, metadata, roles, customizations, workflows, indexes, live records | database not queried | UNKNOWN |
| Actual gate/PPAS integrations and job execution | not exercised | UNKNOWN |

## Material contradictions / risks

1. `GRN Note` checked-in metadata has no `is_submittable` or states, yet `calculate_tp_status_for_pass` requires `docstatus=1`; the fulfillment tests set `docstatus` directly. Report/rollup/season mapping use `<2`. Runtime customization is unknown.
2. Receipt quantity differs by subsystem: TP status uses net only; Season Mapping adds entry quantities and caps at TP; report totals vary by report.
3. Deductions reduce TP chhatni balance but not actual chhatni percentage/status.
4. Chhatni field naming/unit has kg/QTL and percentage conventions; code treats numeric rate as percentage.
5. CMR `rice_dispatched` has no discovered application writer; manual/current DB value cannot be verified.
6. GRN linked purchase-order update and refresh methods are `pass` stubs (`grn_note.py:168-173`), while local purchase order support structures remain.
7. Code contains legacy/local purchase paths but rejects new local purchase WBM and GRN; exposed UI/live permission state unknown.
8. Target allocations and season mappings synchronize copied values; concurrent or stale master changes can leave divergent derived fields.

## Business questions

- What is CMR’s formal meaning and governing agency requirement in this deployment?
- Is CMR yield `rice_yield` a percent of accepted paddy, and what is its unit/precision/version source?
- Which GRN states count as received for target, physical, and rice obligation: draft, submitted, or both? Should canceled/amended revisions affect totals?
- Is GRN entry quantity an amount to add to paddy receipt, and should every pass be capped at TP quantity?
- Does deduction represent QTL paddy deduction, or a separate quality/weight figure? Should it reduce chhatni status percentage?
- Is chhatni rate kg per QTL or percent? Which exact tolerance boundary is policy-approved?
- Are over-receipts allowed operationally? Who approves, and does TP completion mean net receipt only?
- Can two open Gate Entry visits share a normalized vehicle? What is the expected recovery for wrong vehicle/pass links?
- Who owns role assignment, QC acceptance, weighment approvals and GRN submission permissions?
- What constitutes rice dispatch acceptance evidence, shortage/rejection/return, and reconciliation closure?

## Not investigated / limitations

No site config values, secrets, business records, database schema/custom fields, Workflow/Role records, live permissions, installed app state for `shyamji`, query logs, patch history, or actual runtime behavior were inspected. Confirm live GRN `is_submittable`, custom workflow and whether any trusted process sets docstatus before relying on TP fulfillment. The other installed app source trees were searched only for CMR/related procurement terms, not fully audited. Standard ERPNext DocTypes are dependencies only if controllers/metadata refer to them; no full ERPNext module audit was in scope. Patches were inventoried but not executed/read exhaustively because they are historical mutators and must not be run.
