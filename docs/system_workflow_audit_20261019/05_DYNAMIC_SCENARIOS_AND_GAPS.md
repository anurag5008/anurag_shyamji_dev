# Dynamic scenarios and gaps

| Scenario | Code-supported observed behavior | Status / test evidence | Risk |
|---|---|---|---|
| TP with zero GRNs | No grouped Mandi Book row; helper returns Pending | Code; runtime unknown | no report row can hide unreceived TP |
| TP with one/multiple GRNs | Aggregates by exact pass key; multiple allowed | Code; tests in `test_tp_fulfillment.py` not run | mismatched key splits totals |
| Partial / exact / excess | In Progress / Completed / Completed; pending/excess floor at 0 | Code; tests present not run | over-receipt is reported, not rejected |
| Draft vs submitted/status lifecycle | canonical helper requires `docstatus=1`; rollup/report/season map use `<2` | Verified in code + metadata: checked-in GRN not submittable, tests set docstatus directly | ordinary GRNs may never be “submitted” through standard lifecycle; counts diverge; runtime customization unknown |
| Cancelled GRN | `docstatus <2` excludes cancellation; duplicate check excludes cancelled, so replacement can be created | Code | cancellation refresh paths are not explicit everywhere; stale totals possible |
| Duplicate WBM/GRN | GRN validate rejects same WBM for any noncancelled GRN | Code | concurrency race/DB unique constraint not established |
| Duplicate TP GRNs | not prohibited when distinct WBM/RST | Code | duplicates are intended aggregation or accidental? business confirmation |
| Missing RST/WBM | GRN validation requires RST and resolvable WBM | Code | recovery is manual link correction |
| Incorrect pass key | WBM validates existence; GRN checks WBM key equals GRN key | Code | non-FK text field integrity still vulnerable to edits |
| Missing/zero tare | WBM can compute gross=load; strict auto GRN requires tare >0 | Code | manually created/different GRN path strictness requires runtime verification |
| Negative weight/quantity | net floors at zero; input rejection depends on metadata `non_negative` and validation | Metadata/code partial | negative gross if tare>load not explicitly rejected in inspected formula |
| Zero load | gross=0; net=0 | Code | no explicit load requirement shown in formula snippet |
| QC rejected/full returned | WBM net set 0; accepted/partially accepted required for strict GRN | Code | `Partially Accepted` treatment does not prorate net in shown logic |
| Repeated QC/Gate Entry links | vehicle resolver prefers open visit; duplicate/cross-link protections are partial | Code search; runtime unknown | multiple open visits/concurrent save ambiguous |
| Vehicle already inside | open Gate Entry/visit lookup used; Gate Exit selects inside vehicle | Code | uniqueness/locking not confirmed |
| Gate Entry without TP | RST awaiting TP and WBM early state are represented; standard gov WBM ultimately requires pass key unless RST permits temporary omission | Code | operational exception handling unclear |
| Empty/duplicate bag rows | QC controller rejects multiple filled rows in certain child tables; WBM weight validates details | Code | all permutations of empty/incomplete rows not tested here |
| Manual vs table gunny | positive manual weight takes precedence over computed bag-table QTL | Code | stale/manual override can disagree with child rows |
| Tolerance boundary | status compares rounded two-decimal actual to assigned ±0.30 with epsilon | Code | synthetic unit boundary needs domain signoff |
| Concurrent edits | after-commit recomputation reads a pass then writes each GRN; no lock/atomic aggregate observed | Code inspection | totals can race under simultaneous submissions |
| Delete/upstream edits | WBM/GRN trash callbacks exist; GRN refresh after update; full cascade from TP/QC/Gate/RST edits not established | Code partial | stale snapshots possible |
| Local procurement | new WBM/GRN local path rejected; legacy PO/RST support remains | Code | UI/config may expose nonfunctional path |
| CMR partial/rejected/return | no CMR transaction model found | Unknown/not implemented in app | no operational audit trail |

The fulfillment test `test_tp_fulfillment.py` labels cases “Submitted” but assigns `docstatus=1` with `frappe.db.set_value`; it does not exercise a submit transition, and checked-in GRN metadata has no submittable lifecycle.

Expected business result is taken only from explicit code comments/formulas. Government policy expectation beyond hard-coded behavior is UNKNOWN. Tests discovered: individual DocType tests, `test_e2e_procurement.py`, fulfillment and report tests; none run. See open questions.
