# CMR readiness and roadmap

## Meaning in this repository

The app uses the label `CMR Season` for a season reference copied from `PPAS Transit Pass` into `GRN Note`; `Season Mapping` stores `rice_yield`, collection-point paddy proportions, `rice_due_till_date`, `rice_dispatched`, and `remaining_balance`. Code computes a rice due estimate. No CMR DocType/module, milling batch, rice production, dispatch transaction, acceptance/rejection, return, or reconciliation workflow was found. The expansion/official meaning of CMR and contractual requirements are not established by repository evidence.

| Business capability | Existing implementation | Existing DocTypes/fields | Dependencies | Formula/validation | Tests | Gap / risk | Recommendation / decision |
|---|---|---|---|---|---|---|---|
| Season/CMR period association | Partial | Season Master; PPAS Transit Pass.season; GRN Note.cmr_season | PPAS import and season master | copied season resolution | no CMR tests | semantic distinction of season vs obligation unknown | confirm terminology and source of obligation |
| Paddy eligibility for milling | Partial proxy | TP quantity, GRN net, TP key; Season Mapping target | submitted/received procurement | season mapping includes noncancelled GRNs and entry qty, capped per TP | procurement tests only | not authoritative eligibility/custody record | agree which statuses/receipt quantity qualify |
| Mill allocation / custody | Partial reference | TP.miller, GRN.mill_name, Season Mapping.mill_name | Mill Master/TP | no custody transfer ledger | none | allocation != physical custody | business decision on custody events/owner |
| Milling batches/stages | Missing | none | eligible paddy | none | none | no traceability or WIP | define stages, identities, losses, reversals |
| Rice yield/recovery | Partial estimate | Season Mapping.rice_yield, rice_due_till_date | procured amount | paddy × yield % | season mapping tests not clearly CMR-specific | yield unit/source/version and timing unclear | confirm policy rate, moisture/grade basis, rounding |
| Grades/by-products/deductions | Missing | none | milling output | none | none | output mass balance impossible | define product/by-product categories and measurements |
| CMR obligation/balance | Partial estimate | target quantity, rice yield, due and remaining fields | target allocation, season mapping | rice target minus due | no CMR tests | “remaining_balance” is formula estimate, not accepted balance | define obligation key, amendments, approved obligations |
| Dispatch/delivery | Missing | `rice_dispatched` field only | future obligation/batches | no transaction populates field discovered | none | stale/manual field risk | define dispatch document/status and inventory linkage |
| Acceptance/rejection/shortage/return | Missing | none | dispatch | none | none | no government acknowledgement/audit trail | define acceptance evidence, reject/return handling |
| Reconciliation | Missing | no CMR ledger | paddy receipt, production, delivery | none | none | cannot reconcile paddy to rice delivered | define conservation equation and variance tolerances |
| Government/PPC/agency trace | Partial procurement references | PPC, mill, season, TP, GRN | existing procurement chain | joins via text business keys | procurement/report tests | no explicit agency obligation links in CMR | confirm required dimensions and authoritative keys |
| Audit/status transitions | Missing for CMR | no workflow/documents | future workflow | none | none | no state history | define draft/submitted/cancel/reopen and approvals |

## Safe reuse candidates

Existing Season Master, PPC Master, Mill Master, Target Allocation, PPAS TP key and GRN receipt facts can provide dimensions/source lineage. `Season Mapping` yield/due is an estimate and should not be silently treated as an actual milling or delivery ledger. Mandi Book is procurement reporting, not stock/custody accounting. No proposal here asserts new fields or rules as current behavior.

## Proposed dependency order (requires business decisions)

1. Confirm CMR meaning, governing policy, season/agency/mill/PPC grain, obligation source, eligible receipt statuses, units, quality basis and yield authority.
2. Approve lifecycle/accountability for paddy custody and batch conversion, including losses, by-products and corrections.
3. Specify rice output grade and mass-balance formulas, precision, tolerance, rejection/return and cancellation treatment.
4. Map dispatch quantities to obligation balances and acceptance evidence; agree stock/accounting integration needs.
5. Design audit trail/status transitions, permissions, unique keys and links to TP/GRN/Mill/Season.
6. Only after decisions, implement transaction DocTypes/controllers and validations, then reports and migration-safe backfill strategy, with scenario tests before release.

All proposed capabilities remain PROPOSED / NEEDS BUSINESS CONFIRMATION.
