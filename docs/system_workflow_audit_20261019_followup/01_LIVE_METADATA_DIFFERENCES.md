# 01: Live Metadata, Database Schema, and Configuration Discrepancies

## 1. Installed Applications Baseline

Verification of installed apps via Frappe CLI (`bench --site shyamji list-apps`) and `sites/apps.txt`:

| App Name | App Version | Git Branch / Ref | Installation Status on `shyamji` | Notes |
|---|---|---|---|---|
| **`frappe`** | 16.30.0 | `version-16` | **Installed & Active** | Core framework |
| **`erpnext`** | 16.31.1 | `version-16` | **Installed & Active** | Upstream ERP suite |
| **`ivri_od`** | 0.0.1 | `main` (commit `eb897fe`) | **Installed & Active** | Target procurement application |
| **`ivri_app`** | — | — | **Not Installed on Site** | Present in `apps/` directory only |
| **`ivri_rice_ag`** | — | — | **Not Installed on Site** | Present in `apps/` directory only |

---

## 2. DocType Submittability (`is_submittable`) Audit

A full database inspection of `tabDocType` on site `shyamji` confirmed the submittability property for all 21 standard procurement DocTypes:

```python
# Live inspection query
frappe.db.get_value("DocType", doctype_name, "is_submittable")
```

| DocType Name | Checked-in JSON `is_submittable` | Live Database `is_submittable` | Submittable in UI? | Resulting Lifecycle State |
|---|---|---|---|---|
| **`GRN Note`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Weigh Bridge Measurement`**| `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Quality Check`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Gate Entry`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Gate Exit`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`RST Details`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`PPAS Transit Pass`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`PPAS Transit Pass Import`**| `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`PPAS Data Extraction`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Daily Planning`** | `0` | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Target Allocation`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Season Mapping`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Chhatni Assign`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Entry`** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **`Local Paddy Purchase Order`**| `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |
| **All Master DocTypes** | `0` (omitted/0) | `0` | **No** | Permanent Draft (`docstatus = 0`) |

**Finding**: There are **zero submittable DocTypes** in the procurement module. The live site exactly mirrors the checked-in repository schemas.

---

## 3. Effective Site Customizations: Custom Fields, Property Setters, and Workflows

### A. Custom Fields (`tabCustom Field`)
- **Query**:
  ```sql
  SELECT dt, fieldname, fieldtype, label 
  FROM `tabCustom Field` 
  WHERE dt IN ('GRN Note', 'Weigh Bridge Measurement', 'Quality Check', 'Gate Entry', 'RST Details', 'Season Mapping', 'Target Allocation', 'PPAS Transit Pass');
  ```
- **Live Result**: **Empty set (0 records)**.
- **Conclusion**: There are **no custom fields** injected into the procurement DocTypes via the Frappe UI or database fixtures.

### B. Property Setters (`tabProperty Setter`)
- **Query**:
  ```sql
  SELECT doc_type, field_name, property, value, property_type 
  FROM `tabProperty Setter` 
  WHERE doc_type IN ('GRN Note', 'Weigh Bridge Measurement', 'Quality Check', 'Gate Entry', 'RST Details', 'Season Mapping', 'Target Allocation', 'PPAS Transit Pass', 'Entry');
  ```
- **Live Results & Operational Impact**:

| DocType | Target Field Name | Property | Live Value | Operational Impact |
|---|---|---|---|---|
| **`GRN Note`** | `tp_fulfillment_section` | `hidden` | `1` | **Hides the TP & Chhatni fulfillment section** on the standard GRN form unless manipulated by JavaScript. |
| **`GRN Note`** | `tp_fulfillment_section` | `depends_on` | `None` | Clears any conditional display expression. |
| **`GRN Note`** | `qc_bag_details` | `hidden` | `1` | Hides the duplicated QC bag details table on GRN. |
| **`Quality Check`** | `qc_decision_section` | `hidden` | `1` | Hides the manual decision section on the QC form. |
| **`Weigh Bridge Measurement`** | `no_of_bags` | `read_only` | `1` | Prevents manual tampering; forces sync from QC bag details. |
| **`Weigh Bridge Measurement`** | `pass_unique_key` | `read_only` | `1` | Sets pass key read-only; forces selection via autocomplete. |
| **`Weigh Bridge Measurement`** | `transit_pass_no` | `hidden` | `0` | Explicitly unhides the transit pass number field. |
| **`Weigh Bridge Measurement`** | *(DocType Layout)* | `field_order` | `[...]` | Compacts form layout and reorders truck/load sections. |
| **`Weigh Bridge Measurement`** | `naming_series` | `default` | `WBM-.YYYY.-.#####` | Standardizes annual numbering series. |
| **`Gate Entry`** | *(DocType Layout)* | `field_order` | `[...]` | Compacts gate in/out fields and vehicle capture. |
| **`Gate Entry`** | `naming_series` | `default` | `GE-.YYYY.-.#####` | Standardizes annual numbering series. |
| **`Entry`** | `naming_series` | `default` | `EN-.YYYY.-.#####` | Standardizes annual numbering series. |
| **`Entry`** | `pacs_name` | `hidden` | `1` | Hides PACS name on farmer Entry form. |
| **`Entry`** | `transit_pass_no` | `width` | `50` | Adjusts field display width. |
| **`PPAS Transit Pass Import`** | `naming_series` | `default` | `PPI-.YYYY.-.#####` | Standardizes import numbering series. |

### C. Workflows (`tabWorkflow`)
- **Query**:
  ```sql
  SELECT name, document_type, is_active FROM `tabWorkflow` WHERE document_type IN ('GRN Note', 'Weigh Bridge Measurement', 'Quality Check');
  ```
- **Live Result**: **Empty set (0 records)**.
- **Conclusion**: There are **no workflows** configured on site `shyamji` for any procurement transaction. Documents do not undergo multi-state workflow transitions (e.g. Draft $\to$ Approved $\to$ Submitted).

---

## 4. Live Table Schema vs. JSON Definition Discrepancies

### The `rice_dispatched` Column Anomaly
- **Earlier Audit Statement**: Found references to `rice_dispatched` and stated it exists on `Season Mapping`.
- **Live Database Inspection**:
  - `tabSeason Mapping`: Column `rice_dispatched` **DOES NOT EXIST** (`MySQLdb.OperationalError: (1054, "Unknown column 'rice_dispatched'")`).
  - `tabSeason Mapping Collection Point` (Child Table): Column `rice_dispatched` **DOES EXIST**.
  - **Live Table State**: `tabSeason Mapping Collection Point` contains **0 rows**.
- **Impact**: The field `rice_dispatched` is exclusively a child-table column in a completely unpopulated child table. It is not an active scalar on the parent mapping.

### Table Schema Summary of Key Operational Tables:

```
tabGRN Note:
  name, creation, modified, modified_by, docstatus, idx,
  naming_series, grn_no, pass_unique_key, transit_pass_no,
  transit_pass_date, transit_pass_datetime, tp_quantity, pacs, ppc,
  mill_name, cmr_season, rst_no, weigh_bridge_measurement,
  gross_vehicle_weight, gross_weight, tare_weight, net_weight,
  deduction, gunny_type, gunny_weight, jute_bags, plastic_bags,
  total_bags, chhatni, quality_check, qc_datetime, qc_sample_no,
  no_of_bags, moisture, dust, unloader_name, unloading_point,
  ppc_name, is_farmer_or_agent, agent_name, paddy_type, paddy_quality,
  qc_decision, paddy_received_in_pkt, paddy_returned,
  gate_entry, arrival_datetime, gate_exit, gate_exit_datetime,
  vehicle_no, driver_name, mobile_no, party_name,
  is_local_procurement, local_purchase_order, purchase_order,
  local_procurement_note, receipt_datetime, receipt_date, receipt_time,
  arrival_date, arrival_time, gate_exit_date, gate_out_time,
  paddy_variety, received_quantity, tp_cumulative_received,
  tp_cumulative_deduction, chhatni_received_pct, tp_chhatni_balance,
  tp_fulfillment_status, chhatni_fulfillment_status, chhatni_fulfillment_remark
```
All columns in `tabGRN Note` directly correspond to checked-in fields. There are no missing columns or phantom columns.
