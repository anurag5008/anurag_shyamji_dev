# 08: Evidence Citations, Conflicts, and Open Business Questions

## 1. Verified Evidence Index

Every finding in this audit has been assigned a strict confidence classification based on observable proof:

| Area / Discovery | Evidence Status | Primary Source File & Class/Method | Exact Line References | Corroborating Test / Evidence | Notes / Verification Basis |
|---|---|---|---|---|---|
| **Pass Unique Key Format** | `VERIFIED IN CODE` | `ivri_od/procurement/doctype/ppas_transit_pass/pass_unique_key.py:make_pass_unique_key` | Lines 100–111 | `test_ppas_transit_pass.py` | `{miller}-{ppc(code)}-{K/R}{YY}-TP{no}` string format verified. |
| **WBM Gross Weight Formula** | `VERIFIED IN CODE` | `weigh_bridge_measurement.py:WeighBridgeMeasurement._update_weights` | Lines 724–733 | `test_e2e_procurement.py:186` | Net equals load minus tare; gross equals load when tare is 0. |
| **Gunny Weight Deduction Precedence** | `VERIFIED IN CODE` | `weigh_bridge_measurement.py:_resolve_gunny_weight_qt` | Lines 703–721 | `test_weigh_bridge_measurement.py` | Gunny Gross = 0; Manual entry > 0 takes precedence over child table. |
| **Net Weight Formula** | `VERIFIED IN CODE` | `weigh_bridge_measurement.py:WeighBridgeMeasurement._update_weights` | Lines 734–738 | `test_e2e_procurement.py:186, 237` | $\max(\text{gross} - \text{gunny} - \text{deduction}, 0)$ rounded to 3 decimals. |
| **Auto GRN Generation Trigger** | `VERIFIED IN CODE` | `weigh_bridge_measurement.py:_ensure_grn_note_for_weigh_bridge` | Lines 1105–1146 | `test_e2e_procurement.py:241` | Triggers on WBM insert/update when tare > 0 and QC accepted. |
| **GRN Duplicate Validation** | `VERIFIED IN CODE` | `grn_note.py:GRNNote._validate_duplicate_grn` | Lines 125–146 | Tested in unit suite | Disallows second non-cancelled GRN for the same WBM name. |
| **Chhatni Rate Percentage Equality** | `VERIFIED IN CODE` | `chhatni_assign.py:ChhatniAssign.validate` | Lines 10–15 | `test_target_allocation.py` | `chutney_percentage = chutney_quantity_kg_per_quintal` ($1\text{ kg/QTL} = 1\%$). |
| **Chhatni Tolerance Threshold** | `VERIFIED IN CODE` | `grn_tp_fulfillment.py:CHHATNI_TOLERANCE_PCT` | Line 17 | `test_tp_fulfillment.py:181-198` | Hardcoded constant `0.30` percentage points. |
| **TP Multi-Trip Fulfillment Logic** | `VERIFIED BY TEST` | `grn_tp_fulfillment.py:_refresh_tp_fulfillment_for_pass` | Lines 279–353 | `test_e2e_procurement.py:284-360` | Cumulative rollup over multiple trips up to 358.78 QTL verified in test. |
| **Chhatni Contractual Locking** | `VERIFIED BY TEST` | `grn_note.py:GRNNote.validate` | Lines 103–104 | `test_grn_chhatni_lock.py:1-99` | Locked on `self.is_new()`; unaffected by subsequent TA changes. |
| **Gate Entry Inside Mill Enforcement** | `VERIFIED IN CODE` | `gate_entry.py:GateEntry._validate_gate_in` | Lines 194–206 | `test_gate_entry.py` | Blocks new Gate In if previous visit is open without Gate Out. |
| **Full Paddy Rejection QC Rule** | `VERIFIED IN CODE` | `quality_check.py:is_full_paddy_return_from_qc` | Lines 27–42 | `weigh_bridge_measurement.py:54-77` | When returned $\ge$ received, WBM quality becomes Rejected and net=0. |
| **Local Procurement Disabled** | `VERIFIED IN CODE` | `weigh_bridge_measurement.py`, `grn_note.py`, `rst_details.py` | Multiple validation blocks | Code search & controller reviews | Active `frappe.throw` on any attempt to create private purchase. |
| **Non-Submittable DocType Metadata** | `VERIFIED IN METADATA`| Checked-in `.json` schemas in `doctype/` | All 30 files | Schema inspection | No DocType has `"is_submittable": 1`. |
| **CMR Module Implementation State** | `VERIFIED IN CODE` | Search of entire repository for "CMR" / milling | Entire repo | grep search output | No milling batch, dispatch challan, or reconciliation doc exists. |
| **Installed Apps on Site `shyamji`** | `VERIFIED AT RUNTIME` | Bench CLI output (`bench --site shyamji list-apps`) | CLI run output | Verified via bench command | `frappe`, `erpnext`, `ivri_od` installed; other apps not on site. |

---

## 2. Identified Contradictions and Code-Metadata Discrepancies

### Contradiction 1: `docstatus == 1` vs. `docstatus < 2` vs. Non-Submittable Schemas
- **The Evidence**:
  - `grn_note.json` defines `"is_submittable": 0` (non-submittable).
  - Normal Frappe UI / API saves GRNs with `docstatus = 0`.
  - `grn_tp_fulfillment.py:105` in `calculate_tp_status_for_pass()` queries `docstatus: 1`.
  - `grn_tp_fulfillment.py:285` in `_refresh_tp_fulfillment_for_pass()` queries `docstatus: ["<", 2]`.
  - `mandi_book.py:155` and `abstract_physical.py:163` query `docstatus: ["<", 2]`.
- **The Conflict**: `calculate_tp_status_for_pass()` requires `docstatus == 1` (submitted), which normal GRNs will never have. Unit tests for `calculate_tp_status_for_pass` only pass because test fixtures bypass Frappe document controllers and execute direct database writes: `frappe.db.set_value("GRN Note", name, "docstatus", 1)`.
- **Architectural Risk**: Any third-party integration or custom script relying on `calculate_tp_status_for_pass()` will report every transit pass as `"Pending"`, even if 100% of the paddy has been weighed and delivered.

### Contradiction 2: Dead Local Procurement Footprint
- **The Evidence**:
  - `Local Paddy Purchase Order` DocType schema, forms, and client scripts exist.
  - Over 40 fields across `Weigh Bridge Measurement`, `RST Details`, and `GRN Note` reference local procurement (`is_local_procurement`, `party_name`, `purchase_order`, `local_purchase_order`).
  - Python controllers in `weigh_bridge_measurement.py:311`, `grn_note.py:120`, `rst_details.py:32`, and `local_paddy_purchase_order.py:43` actively abort with:
    `"Local Paddy Purchase is disabled. Only Government Paddy Purchase is currently supported."`
  - In `grn_note.py:169, 173`, hooks `_update_linked_purchase_order()` and `_refresh_po_qty()` are empty `pass` statements.
- **The Conflict**: The codebase maintains full schema and form plumbing for a business capability that is hard-blocked in controller code.

### Contradiction 3: Abstract Physical vs. Mandi Book Chhatni Percentage Formula
- **The Evidence**:
  - `grn_tp_fulfillment.py:29-36` (used by Mandi Book) calculates:
    $$\text{pct} = \frac{\text{Received Qty} - \text{TP Qty}}{\text{TP Qty}} \times 100$$
  - `abstract_physical.py:253-257` calculates:
    $$\text{pct} = \frac{\text{Chhatni Qty}}{\text{TP Qty} - \text{Entry Qty}} \times 100$$
- **The Conflict**: The denominator in `Abstract Physical` subtracts direct farmer purchases (`Entry.entry_quantity`) from the Transit Pass quota, whereas the canonical fulfillment engine does not. This results in divergent percentage figures between the two reports for the same PPC.

---

## 3. Open Business & Technical Questions for Stakeholders

1. **Document Submission Lifecycle**:
   - Is `GRN Note` intended to become a submittable document (`is_submittable: 1`) where warehouse managers formally submit records to freeze quantities?
   - If yes, should `calculate_tp_status_for_pass()` continue checking `docstatus == 1` once submission permissions are configured?
   - If no, should `calculate_tp_status_for_pass()` be updated to query `docstatus < 2` to match `_refresh_tp_fulfillment_for_pass()`?

2. **Chhatni Terminology and Statutory Base**:
   - Is Chhatni officially negotiated as a flat deduction percentage (e.g., 4.0%), or is it measured as a physical moisture/refraction cut in kg per quintal on the weighbridge slip?
   - Should the $\pm 0.30$ percentage-point tolerance remain hardcoded in code, or should it be configurable per season / mill in `Season Master` or a new `Procurement Settings` DocType?

3. **Status of Local Paddy Procurement**:
   - Is private farmer paddy purchase permanently discontinued, or is it scheduled for re-introduction in a subsequent release?
   - If discontinued, should the schema fields and dead code paths be cleanly deprecated to reduce technical debt?

4. **CMR Specification Decisions**:
   - What is the statutory rice recovery ratio for site `shyamji`? Is it fixed at $67\%$ (Raw) / $68\%$ (Boiled), or does it vary based on depot contract terms?
   - What by-products (Rice Bran, Broken Rice, Husk) need to be accounted for in the mill ledger?
   - Does OSCSC require delivery challans to be printed directly from the ERP with custom QR codes matching government AC guidelines?
   - What tolerance is allowed for moisture loss during transit between the mill and the FCI/OSCSC godown?

---

## 4. Scope Boundaries & Uninspected Areas

In strict accordance with the read-only audit rules:
- **Database Records**: Live database records containing real production transaction data, mill financials, supplier names, driver personal contact details, or passwords were not dumped or emitted.
- **PPAS Web Scraper at Runtime**: The local scraper `tools/ppas_agent/ppas_agent.py` was inspected statically in source code; no live HTTP connections to the government PPAS portal or local Windows agent service (`http://127.0.0.1:8765`) were opened.
- **Other Bench Apps**: `ivri_app` and `ivri_rice_ag` are sibling directories in the bench root but were confirmed not to be installed on site `shyamji`; their internal code was searched only to verify absence of CMR references.
