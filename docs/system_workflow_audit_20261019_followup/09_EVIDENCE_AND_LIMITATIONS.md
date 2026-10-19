# 09: Evidence Log, Reproduction Scripts, and Safety Limitations

## 1. Certification of Read-Only Audit Integrity

This document certifies that the investigation conducted on 2026-10-19 adhered strictly to the **Read-Only Safety Rules**:
- **Application Code & Schemas**: Zero files modified. Git worktree for `ivri_od` remains clean on branch `main` at commit `eb897fe`.
- **Database Operations**: Zero write transactions executed. No records were created, updated, submitted, cancelled, or deleted.
- **System Configurations**: No migrations, patches, cache clears, or site setting changes were triggered.
- **Sensitive Credentials**: Zero passwords, private tokens, or sensitive farmer personal identifiers are exposed in documentation.

---

## 2. Reproduction Scripts & Verification Queries

All validation findings can be independently reproduced using the following read-only scripts executed from `/home/hp/frappe-bench-v16/sites`:

### A. Reproduction Script 1: GRN Status & Defect Reproduction
```python
# Command: /home/hp/frappe-bench-v16/env/bin/python
import frappe
from ivri_od.procurement.grn_tp_fulfillment import calculate_tp_status_for_pass

frappe.init(site="shyamji")
frappe.connect()

# 1. Inspect DocType submittability in live metadata
is_submittable = frappe.db.get_value("DocType", "GRN Note", "is_submittable")
print("GRN Note is_submittable:", is_submittable)  # Outputs: 0

# 2. Inspect live docstatus distribution
dist = frappe.db.sql("SELECT docstatus, COUNT(*) FROM `tabGRN Note` GROUP BY docstatus")
print("GRN docstatus distribution:", dist)  # Outputs: [(0, 28)]

# 3. Test transit pass with 6 completed GRNs totaling 288 QTL
pass_key = "M051007-MALMANDA(S1051105)-K25-TP-300-6P"
res = calculate_tp_status_for_pass(pass_key)
print("calculate_tp_status_for_pass output:", res)  # Outputs: 'Pending' (Defect confirmed)

# 4. Compare with stored status and report query
stored = frappe.db.get_values("GRN Note", {"pass_unique_key": pass_key}, ["name", "tp_fulfillment_status"])
print("Stored tp_fulfillment_status:", stored)  # Outputs: 'TP Completed'

frappe.destroy()
```

---

### B. Reproduction Script 2: Operational Data Integrity Checks
```python
import frappe
frappe.init(site="shyamji")
frappe.connect()

# Check 1: 1-to-1 WBM to GRN constraint
dup_rst = frappe.db.sql("""
    SELECT rst_no, COUNT(*) as cnt 
    FROM `tabGRN Note` 
    WHERE IFNULL(rst_no, '') != '' 
    GROUP BY rst_no HAVING cnt > 1
""")
print("Duplicate RST in GRN:", dup_rst)  # Outputs: []

# Check 2: WBM Tare Weight completeness
zero_tare = frappe.db.sql("""
    SELECT count(*) FROM `tabWeigh Bridge Measurement` 
    WHERE IFNULL(tare_weight, 0) <= 0
""")
print("WBM with zero tare weight:", zero_tare[0][0])  # Outputs: 0

# Check 3: Duplicate open Gate Entries
dup_gate = frappe.db.sql("""
    SELECT vehicle_no, COUNT(*) as cnt 
    FROM `tabGate Entry` ge 
    WHERE NOT EXISTS (
        SELECT 1 FROM `tabGate Exit` gx WHERE gx.gate_entry_in = ge.name
    )
    GROUP BY vehicle_no HAVING cnt > 1
""")
print("Vehicles with multiple open Gate Entries:", dup_gate)  # Outputs: []

frappe.destroy()
```

---

### C. Reproduction Script 3: CMR Live State & Inactive Schema Verification
```python
import frappe
frappe.init(site="shyamji")
frappe.connect()

# Check 1: rice_yield in Season Mapping
yields = frappe.db.sql("SELECT DISTINCT rice_yield FROM `tabSeason Mapping`")
print("Distinct rice_yield in Season Mapping:", yields)  # Outputs: [(0.0,)]

# Check 2: Season Mapping Collection Point child table count
child_count = frappe.db.sql("SELECT COUNT(*) FROM `tabSeason Mapping Collection Point`")
print("Season Mapping Collection Point count:", child_count[0][0])  # Outputs: 0

# Check 3: Verify parent table column absence
cols = frappe.db.get_table_columns("Season Mapping")
print("Is 'rice_dispatched' in parent Season Mapping?:", "rice_dispatched" in cols)  # Outputs: False

frappe.destroy()
```

---

## 3. Evidence Index & Key Source Citations

| Topic / Finding | Source File | Line Numbers | Table / Object |
| :--- | :--- | :--- | :--- |
| **GRN Status Defect** | `grn_tp_fulfillment.py` | 80–111 | `tabGRN Note` |
| **Chhatni Tolerance $\pm 0.30$** | `grn_tp_fulfillment.py` | 16–17, 179–198 | `tabGRN Note` |
| **Double Deduction Flaw** | `grn_tp_fulfillment.py` | 38–47, 343 | `tabGRN Note.tp_chhatni_balance` |
| **Chhatni Rate = Percentage** | `chhatni_assign.py` | 10–14 | `tabChhatni Assign` |
| **Historical Rate Locking** | `grn_note.py` | 103–104 | `tabGRN Note.chhatni` |
| **Abstract Denominator Discrepancy** | `abstract_physical.py` | 253–257 | Report Output |
| **1:1 WBM-GRN Constraint** | `grn_note.py` | 130–146 | `tabGRN Note` |
| **Open Gate In Block** | `gate_entry.py` | 194–206 | `tabGate Entry` |
| **Zero Tare Block** | `weigh_bridge_measurement.py` | 1165–1166 | `tabWeigh Bridge Measurement` |
| **Inactive CMR Yield** | `tabSeason Mapping` | Live DB Query | `tabSeason Mapping.rice_yield` |

---

## 4. Uninspected Areas & Operational Limitations

Due to safety guidelines and production environment constraints, the following items were intentionally not executed:
1. **Live Test Execution of `test_e2e_procurement.py`**:
   - As proven in [05_DATA_INTEGRITY_AND_TEST_COVERAGE.md](file:///home/hp/frappe-bench-v16/apps/ivri_od/docs/system_workflow_audit_20261019_followup/05_DATA_INTEGRITY_AND_TEST_COVERAGE.md), running this script executes raw database deletions and master data mutation commits. It was audited statically.
2. **External OSCSC / PPAS Online Government Portal Integration**:
   - Network calls to live Odisha state procurement servers were not attempted. The system currently imports data via offline/transit files or manual pass creation.
3. **Hardware Weighbridge Scale Drivers**:
   - Serial port / COM port integrations with physical Toledo/weighbridge indicators could not be tested without live physical hardware connected.
