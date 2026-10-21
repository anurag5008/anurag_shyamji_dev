# Formulas, tolerances, and worked examples

All examples are synthetic. QTL means quintal in app labels; code does not consistently encode units in numeric types. WBM/GRN metadata uses 3 decimal places for operational weights.

## Weigh bridge

**Gross commodity weight** (`Weigh Bridge Measurement._update_weights`, `weigh_bridge_measurement.py:722-737`):

- if load and tare are truthy: `gross = load_weight - tare_weight`
- else if load is truthy: `gross = load_weight`
- else: `gross = 0`

**Net weight:** `max(gross - gunny_weight - deduction, 0)`, `flt(..., 3)`.

Gunny: for `Gunny Cut`, a positive manually entered `gunny_weight` wins; otherwise child bag table sum. For non-Gunny Cut, zero (except RST-linked legacy branch can take RST gunny QTL). QC bag line QTL = bag count × kg/bag ÷ 100; total is sum jute/plastic. Example: load 280 QTL, tare 80 QTL => gross 200; gunny 1.25 QTL and deduction 0.50 QTL => net `198.250 QTL`. With tare missing, gross becomes 280, not “unknown”; this is a material edge behavior. Negative result floors at zero. Negative input validation is not uniformly established.

## TP quantity/status

Cumulative receipt for rollup is the sum of GRN `net_weight` by identical `pass_unique_key`, government flag, and `docstatus < 2`. `calculate_tp_status_for_pass` separately uses only `docstatus=1` and QTL precision 3 (`grn_tp_fulfillment.py:67-111`). Checked-in GRN metadata does not enable submission; tests manually assign docstatus. Unless live customization changes that, the helper will not count ordinary GRNs. Status: cumulative <= 0 => Pending; positive but below positive TP quantity => In Progress; >= TP quantity => TP Completed. For nonpositive TP quantity with positive receipt, current function returns In Progress (because completion requires `tp_qty > 0`). Remaining = `max(TP-cumulative,0)`, excess=`max(cumulative-TP,0)`, each 3 decimals. Example TP 100 QTL; submitted GRNs 42 + 61 = 103 QTL: status Completed, pending 0, excess 3 QTL. There is no hard over-receipt block in the discovered validation.

## Chhatni

`required = TP QTL × assigned rate / 100`, rounded 3. Actual percentage=`max((cumulative received - TP)/TP × 100, 0)`, rounded 2; TP <=0 => 0. Assigned value is rounded 2 and treated as a percentage, though source field terminology is inconsistent. Tolerance constant is ±0.30 percentage points (`grn_tp_fulfillment.py:16-17, 24-47, 140-210`). Actual above assigned+0.30 => Extra Chhatni Received; within inclusive lower/upper boundaries => Chhatni Received; below => Chhatni Not Received. A rate <=0 yields Chhatni Pending. Example TP=100 QTL, assigned=2.00%, receipt=102.20 QTL: actual 2.20%, required 2.000 QTL, deviation +0.20 percentage points => received. At 102.31 QTL actual=2.31%, classified extra; at 101.69 QTL actual=1.69%, not received. Since actual is rounded to two decimals before compare, boundary outcomes are quantized; epsilon 1e-6 is applied.

The cumulative deduction is recorded in `tp_chhatni_balance = max(received - TP - cumulative deductions,0)` but does not enter `received_chhatni_pct` or chhatni status thresholds. In other words, deductions are shown in balance but are not subtracted to determine the percentage. Example TP 100, received 102, deduction 1 => displayed balance 1 QTL and actual percentage 2%, not 1%.

## Season mapping / rice due (CMR-adjacent only)

Controller: `season_mapping.py:67-79`. Collection point paddy procured = season/mill/PPC procurement × `paddy_proportion / 100`, rounded 3; rice due = paddy procured × `rice_yield / 100`; remaining = season target × yield /100 × proportion /100 − rice due. Example paddy procured 500 QTL, proportion 20%, yield 67% => allocated paddy 100 QTL; rice due 67 QTL. Target 800 QTL yields allocated rice target 107.2 QTL; remaining 40.2 QTL. No rounding is specified on rice due/remaining beyond Frappe float/database precision. Whether `rice_yield` is percent, recovery ratio, or policy-defined CMR rate requires confirmation.

Procurement source used by `get_grn_paddy_procured` (`season_mapping.py:149-207`): noncancelled GRN rows, pass key parsed for mill/season/PPC matching, `max(net_weight,0)` summed by pass plus distinct GRN entry quantity (`max(entry_quantity,0)`, dedup key `(pass, entry ID)`), then `min(net+entry_qty, max tp_quantity)` per pass and sum, final 3 decimals. Drafts included; cancelled excluded. This differs from receipt-only fulfillment; synthetic: net=95, unique entry quantities=7, TP=100 => contributes 100 QTL.

## Entry and other discovered arithmetic

`Entry.total_amount = entry_quantity × entry_price_per_quintal` (entry controller; report fallback rounds amount to 2 decimals). `Daily Planning` truck estimates and other report formulas are described in source lineage; not all could be reconciled to one canonical implementation. No CMR milling recovery/dispatch reconciliation formula exists beyond season mapping rice-yield due.

## Formula discrepancies and coverage

- Report/cumulative Mandi Book includes drafts (`docstatus < 2`); submitted-only status helper excludes drafts.
- Season Mapping sourcing includes entry quantity and caps per pass; TP fulfillment is net weight only.
- Chhatni balance subtracts deductions, while actual chhatni percentage/status does not.
- WBM net excludes gross? `load - tare` is gross commodity, then subtracts bag tare (gunny) and deduction. UI labels are reviewed through metadata but expected unit conventions are not universally documented.
- Tests exist in `test_tp_fulfillment.py`, `test_grn_chhatni_lock.py`, `test_weigh_bridge_measurement.py`, and report-specific files. They were not executed during this read-only audit, by instruction not to add/run tests absent a verification request; exact test outcomes: NOT RUN.
