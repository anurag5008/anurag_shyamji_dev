# 08: Business Decisions & Stakeholder Approvals Required

## 1. Executive Summary

Before implementing code modifications or proceeding with the CMR module development, specific architectural, operational, and policy decisions must be formally approved by system stakeholders and domain owners.

This document compiles the complete decision checklist, outlining the technical reality, business dilemma, options available, and architectural recommendation for each.

---

## 2. Decision Matrix & Action Items

### Decision 1: GRN Note Submittability Architecture
- **Context**: In `tabDocType`, `GRN Note.is_submittable = 0`. All 28 live records have `docstatus = 0`. However, `calculate_tp_status_for_pass()` checks `docstatus == 1`, returning `"Pending"` for all passes.
- **Options**:
  - **Option A (Fix Query Filter)**: Keep `GRN Note` as a standard document (`is_submittable = 0`) and change `calculate_tp_status_for_pass()` to filter `docstatus < 2`. This aligns with `_refresh_tp_fulfillment_for_pass()`, `mandi_book.py`, and requires **zero database data migrations**.
  - **Option B (Convert to Submittable DocType)**: Set `GRN Note.is_submittable = 1`. Write a migration patch to submit all 28 existing production GRNs (`docstatus = 1`). Enforce strict submit/cancel permissions.
- **Architectural Recommendation**: **Option B** is recommended for long-term audit compliance and statutory accounting in government procurement; **Option A** can be deployed as an immediate hotfix if schema migrations are deferred.

---

### Decision 2: Double-Deduction in Chhatni Balance Formula
- **Context**: In `grn_tp_fulfillment.py:38–47`, `tp_chhatni_balance_qt` calculates:
  $$\text{Balance} = \text{cumulative\_received} - \text{tp\_qty} - \text{total\_deduction}$$
  Because `cumulative_received` is the sum of `net_weight` (which already had `deduction` subtracted), `total_deduction` is subtracted twice.
- **Options**:
  - **Option A (Correct Math)**: Modify formula to `max(cumulative_received - tp_qty, 0)`.
  - **Option B (Business Intent Clarification)**: If business intends the formula to start from gross delivered paddy: `max(cumulative_gross - tp_qty - total_deduction, 0)`.
- **Architectural Recommendation**: **Option A**. In Odisha mandi operations, Chhatni balance is the excess physical paddy delivered over the transit pass after accounting for quality refractions.

---

### Decision 3: Abstract Physical Denominator Discrepancy
- **Context**: `grn_tp_fulfillment.py` calculates Chhatni % with denominator = `tp_qty`. `abstract_physical.py` calculates Chhatni % with denominator = `(tp_qty - entry_qty)`.
- **Options**:
  - **Option A**: Standardize on `tp_qty` across all reports.
  - **Option B**: Maintain `(tp_qty - entry_qty)` only if direct local Entry records are intended to reduce the effective government TP allocation.
- **Architectural Recommendation**: **Option A**. The official Transit Pass allocated quota is the standard base denominator recognized by OSCSC.

---

### Decision 4: Parameterization of Chhatni Tolerance Limit
- **Context**: The tolerance is currently hard-coded as `CHHATNI_TOLERANCE_PCT = 0.30` in Python code.
- **Options**:
  - **Option A**: Leave hard-coded in Python.
  - **Option B**: Add `chhatni_tolerance_pct` (default 0.30) to `Season Master` or a new `Procurement Settings` Single DocType, allowing authorized admins to adjust tolerances per season or district.
- **Architectural Recommendation**: **Option B**. Government procurement orders frequently revise allowable moisture and milling loss tolerances across crop seasons.

---

### Decision 5: CMR Statutory Out-Turn Ratios (OTR) and Deviation Handling
- **Context**: Odisha Food Supplies norms dictate 67% yield for Parboiled rice and 68% for Raw rice.
- **Options**:
  - **Option A (Hard Stop)**: Block submission of `CMR Milling Batch` if calculated yield deviates from 67%/68%.
  - **Option B (Configurable Soft Warning with Audit Log)**: Allow submission but log yield deviation and require supervisor justification remark if yield falls outside an acceptable band (e.g. $66.5\% - 68.5\%$).
- **Architectural Recommendation**: **Option B**. Physical milling yields vary based on paddy moisture and grain quality; hard stops disrupt operational data entry during peak season.

---

### Decision 6: Gunny Bag Reconciliation Policy
- **Context**: Paddy arrives in used 50kg bags; CMR rice must be dispatched in new, specified HDPE/Jute bags with mandatory stenciling.
- **Questions for Stakeholders**:
  1. Does the miller retain the empty paddy gunny bags against a fixed government credit, or are bags returned to PACS/PPC?
  2. Are new CMR gunny bags supplied directly by OSCSC, or purchased by the miller and billed to the corporation?
- **Action Required**: Stakeholder sign-off on gunny accounting ledger schema.

---

### Decision 7: Permanent Deprecation of Local Paddy Procurement
- **Context**: Code in `GRN Note`, `Weigh Bridge Measurement`, `RST Details`, and `Purchase Order` has hard validation blocks preventing any local procurement transactions.
- **Options**:
  - **Option A**: Formally remove local procurement fields and code clutter from DocTypes and controllers.
  - **Option B**: Retain disabled code hooks in case private commercial procurement is reactivated in subsequent fiscal years.
- **Architectural Recommendation**: Retain fields in schema but hide in UI via Property Setters until a future phase.

---

### Decision 8: Frappe Stock Ledger Integration vs Custom Ledger
- **Context**: Currently, paddy intake and stock quantities are tracked through custom rollups and database queries without generating standard ERPNext `Stock Ledger Entry` (SLE) or `Bin` records.
- **Options**:
  - **Option A (Custom Lightweight Architecture)**: Continue tracking CMR paddy, rice, and by-products through dedicated custom DocTypes and database rollups.
  - **Option B (Full ERPNext Stock Integration)**: Hook GRN and CMR batches into ERPNext `Purchase Receipt`, `Stock Entry` (Manufacture), and `Delivery Note` to drive core ERPNext Stock Ledgers and Valuation.
- **Architectural Recommendation**: **Option A**. The Odisha CMR lifecycle has highly specialized statutory compliance, deduction cuts, and government billing rules that conflict with standard ERPNext weighted-average FIFO stock valuation.
