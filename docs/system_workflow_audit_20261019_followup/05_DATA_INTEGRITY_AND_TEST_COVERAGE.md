# 05: Data Integrity Controls and Test Suite Audit

## 1. Executive Summary

This document verifies the operational integrity constraints of the `ivri_od` procurement system against both the codebase implementation and live database evidence on site `shyamji`. Additionally, it documents why test execution was restricted to static auditing to protect live database state.

---

## 2. Integrity Controls Validation (Code vs Live State)

### A. Multiple GRNs Linked to One Transit Pass (TP)
- **Code Capability**: The system is architected to allow multiple vehicles/deliveries against a single Transit Pass. Functions in `grn_tp_fulfillment.py` sort GRNs by receipt datetime/creation and accumulate `net_weight`.
- **Live Database Evidence (`tabGRN Note`)**:
  Confirmed in live database: **4 Transit Passes possess multiple GRN Notes**:
  1. `M051007-BADIMUNDA(S1050812)-K25-TP145`: 2 GRN Notes, total net weight 197.49 QTL.
  2. `M051007-BADIMUNDA(S1050812)-K25-TP146`: 2 GRN Notes, total net weight 286.87 QTL.
  3. `M051007-DHOLMANDAL(S1051411)-K25-TP-200-2P`: 2 GRN Notes, total net weight 144.00 QTL.
  4. `M051007-MALMANDA(S1051105)-K25-TP-300-6P`: **6 GRN Notes**, total net weight 288.00 QTL.
- **Integrity Status**: Fully verified in both code and live operations.

---

### B. One-to-One Weighbridge Measurement (WBM) to GRN Constraint
- **Code Enforcement**: In `GRN Note._validate_duplicate()` (`grn_note.py:130–146`):
  ```python
  if wbm_name:
      filters = {"weigh_bridge_measurement": wbm_name, "docstatus": ["<", 2]}
      if not self.is_new():
          filters["name"] = ["!=", self.name]
      dup = frappe.db.get_value("GRN Note", filters, "name")
      if dup:
          frappe.throw(_("GRN Note {0} already exists for Weigh Bridge Measurement {1}."))
  ```
- **Live Database Evidence**:
  - Query for duplicate `rst_no` in `tabGRN Note`: **0 duplicates found**.
  - All 28 GRN records map strictly 1:1 to unique RST/WBM records.
- **Integrity Status**: Validated and strictly enforced.

---

### C. Duplicate Open Gate Entries Prevention
- **Code Enforcement**: In `GateEntry._validate_gate_in()` (`gate_entry.py:194–206`):
  ```python
  open_visit = get_open_gate_entry_in_for_vehicle(self.vehicle_no, exclude_in=self.name)
  if open_visit:
      frappe.throw(_("Vehicle {0} is already inside the mill (Gate In {1}). Record Gate Out before a new Gate In."))
  ```
- **Live Database Evidence**:
  - Query for open Gate Entries (without an exit) grouped by vehicle: **0 duplicate open entries**.
  - All 14 Gate Entries in `tabGate Entry` have clean visit lifecycles (13 have corresponding Gate Exits, 1 vehicle currently logged inside mill).
- **Integrity Status**: Validated and functioning.

---

### D. Zero Tare Weight / Incomplete Weighment Protection
- **Code Enforcement**: In `WeighBridgeMeasurement.get_grn_creation_block_reasons()` (`weigh_bridge_measurement.py:1165–1166`):
  ```python
  if not flt(wbm.tare_weight):
      reasons.append(_("Enter tare weight on the weigh bridge."))
  ```
  GRN generation buttons and APIs reject any WBM missing tare weight.
- **Live Database Evidence**:
  - Query for WBM records where `IFNULL(tare_weight, 0) <= 0`: **0 records found**.
  - 100% of the 29 WBM records in `tabWeigh Bridge Measurement` have complete gross and tare weights recorded.
- **Integrity Status**: Validated and enforced.

---

### E. Quality Check Rejection Handling
- **Code Enforcement**: In `WeighBridgeMeasurement.effective_quality_test_for_wbm()` (`weigh_bridge_measurement.py:75–76`):
  ```python
  if doc.quality_test == REJECTED_QC:
      doc.net_weight = 0
  ```
  If QC status is "Rejected", WBM forces `net_weight = 0`, preventing paddy intake from recording accepted inventory.
- **Live Database Evidence**:
  - Live QC decisions: 13 `Accepted`, 1 `Partially Accepted`, 0 `Rejected`.
- **Integrity Status**: Confirmed in controller logic.

---

### F. Gate Exit Eligibility
- **Code Enforcement**: In `GateExit.validate()` (`gate_exit.py:20–44`):
  - Requires vehicle to have an active `Gate Entry` where `inside_mill == 1`.
  - Blocks duplicate `Gate Exit` against the same `gate_entry_in`.
  - On submission/update, automatically sets `Gate Entry.inside_mill = 0`.
  - On deletion (`on_trash`), restores `Gate Entry.inside_mill = 1`.
- **Integrity Status**: Confirmed in controller lifecycle.

---

### G. Deletion Hooks and Rollup Recalculations
- **Code Enforcement**: In `GRN Note.on_trash()` (`grn_note.py:181–186`):
  ```python
  def on_trash(self):
      key = (self.pass_unique_key or "").strip()
      if key and not cint(self.is_local_procurement):
          frappe.db.after_commit(lambda k=key: refresh_tp_fulfillment_for_pass(k))
          frappe.db.after_commit(lambda k=key: _sync_procurement_rollups_for_pass(k))
  ```
  If a GRN is deleted, all sibling GRNs and the parent Transit Pass rollups are recalculated post-commit.
- **Integrity Status**: Architectural rollback mechanism confirmed.

---

## 3. Test Suite Audit: Why Live Test Execution Was Prohibited

### A. Analysis of `test_e2e_procurement.py`
Inspection of `apps/ivri_od/ivri_od/procurement/tests/test_e2e_procurement.py` revealed that it is **NOT an isolated unit test**, but rather an un-sandboxed script that mutates live database state:
1. **Explicit Master Data Mutation**:
   Lines 53–107 (`setup_target_allocations()`):
   - Loops over all 48 PPCs and programmatically creates or alters `Target Allocation` and `Chhatni Assign` records in the database.
   - Executes explicit `frappe.db.commit()`.
2. **Hardcoded Record Deletions**:
   Lines 113–135 (`cleanup_tp138_test_data()`):
   - Executes `frappe.delete_doc("Gate Exit", ...)` for vehicle `OD16G4699`.
   - Executes `frappe.delete_doc("GRN Note", ...)` for pass `M051007-DUDUKA(S1050113)-K25-TP138`.
   - Deletes WBM records with prefix `RST-TP138%`.
3. **Absence of Database Rollback**:
   The test does not run in a rollback transaction block or separate mock database. Running it against site `shyamji` would permanently mutate production master data and delete real procurement records.

### B. Analysis of `test_tp_fulfillment.py`
Inspection of `apps/ivri_od/ivri_od/procurement/tests/test_tp_fulfillment.py` revealed:
- Test fixtures bypass normal controller validation and use raw SQL:
  ```python
  frappe.db.set_value("GRN Note", grn_name, "docstatus", 1)
  ```
- Because it artifically forces `docstatus = 1` directly in SQL, it masked the critical bug where normal UI/API operations create GRNs with `docstatus = 0` (non-submittable).

### C. Safety Decision
Under the Strict Safety Rules of this audit, running these tests on site `shyamji` was **strictly disallowed**. Verification was instead achieved through static code audit and non-mutating, read-only Python inspection queries.
