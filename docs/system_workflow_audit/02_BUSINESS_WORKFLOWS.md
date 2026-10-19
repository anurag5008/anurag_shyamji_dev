# 02: Business Workflows Specification

## 1. End-to-End Workflow Map

The business workflow of `ivri_od` reflects the operational lifecycle of government paddy procurement under the Odisha State Civil Supplies Corporation (OSCSC) mandate. The physical process starts when procurement targets are allocated to a rice mill for designated Primary Procurement Centers (PPCs), continues as paddy transit passes (TPs) arrive on trucks at the mill gate, progresses through inspection, weighing, and goods receipt note (GRN) generation, and culminates in pass fulfillment tracking and operational reporting.

---

## 2. Detailed Step-by-Step Workflow Stages

### Stage 0: Master Data & Organizational Setup

#### Step 0.1: District & Season Setup
- **Business Purpose**: Register administrative districts and crop procurement seasons (e.g., Kharif 2025, Rabi 2026).
- **Responsible Role/User**: Procurement Manager / System Administrator.
- **Source DocTypes**: `District Master`, `Season Master`.
- **Trigger**: New fiscal or agricultural procurement cycle.
- **Preconditions & Validations**:
  - `Season Master.crop_season` must be "Kharif" or "Rabi".
  - Unique naming: `Season Master` autonames as `{crop_season} {year}` (e.g. `Kharif 2025`).
- **Fields Read/Written**:
  - Reads: User inputs `crop_season`, `year`, `is_active`.
  - Writes: `name` (e.g., `Kharif 2025`).
- **Next Steps**: PPC and Mill registration; Target Allocation.
- **Verification Status**: `VERIFIED IN CODE` (`season_master.py:10-45`).

#### Step 0.2: Mill Master & PPC Master Registration
- **Business Purpose**: Define the rice mills, miller codes, PPC collection points (PACS/LAMPCS), and authorized procurement agents.
- **Responsible Role/User**: Procurement Admin.
- **Source DocTypes**: `Mill Master`, `PPC Master`, `Society Master`, `Agent Master`.
- **Preconditions & Validations**:
  - Mill has an official miller code (e.g., `M051007`).
  - PPC has an official code (e.g., `S1050113`) and linked Society.
- **Next Steps**: Proceed to Target Allocation.
- **Verification Status**: `VERIFIED IN METADATA` and `VERIFIED IN CODE`.

---

### Stage 1: Quota Allocation & Chhatni Setup

#### Step 1.1: Chhatni Assignment (`Chhatni Assign`)
- **Business Purpose**: Record the government/mill agreed Chhatni allowance (in kg per quintal) applicable to a specific PPC, Mill, and Season.
- **Responsible Role/User**: Mill Manager / Procurement Incharge.
- **Source DocType**: `Chhatni Assign`.
- **Trigger**: Negotiation or notification of Chhatni terms before procurement commences.
- **Preconditions & Validations**:
  - `ppc_name`, `mill_name`, and `season` must be specified.
  - `chutney_quantity_kg_per_quintal` must be a valid float.
- **Fields Read**: `chutney_quantity_kg_per_quintal`.
- **Fields Written/Derived**:
  - `chutney_percentage = chutney_quantity_kg_per_quintal` ($1\text{ kg per quintal} = 1\%$).
  - `chhatni_history` (Child table `Chhatni Assign History` appends timestamp, user, previous value, new value).
- **Linked DocTypes**:
  - Automatically pushes values into matching `Target Allocation` records via `sync_target_allocations_from_chhatni_assign()`.
  - Cascades via `sync_season_mappings_from_allocation()` into `Season Mapping`.
- **Failure Paths**: Missing PPC, Mill, or Season raises validation error.
- **Verification Status**: `VERIFIED IN CODE` (`chhatni_assign.py:10-98`).

#### Step 1.2: Target Allocation (`Target Allocation`)
- **Business Purpose**: Set the maximum paddy quota (in QTL) allocated to the mill for a PPC in a season, and assign procurement agents.
- **Responsible Role/User**: Procurement Manager.
- **Source DocType**: `Target Allocation`.
- **Trigger**: OSCSC target allocation order release.
- **Preconditions & Validations**:
  - Unique composite constraint: Only one `Target Allocation` can exist per (`season`, `ppc_name`, `mill_name`). Duplicate raises `frappe.throw`.
  - `target_quantity` must be $> 0$.
  - Agents in `agent_details` child table must be unique.
- **Fields Read/Written**:
  - Reads: `season`, `ppc_name`, `mill_name`, `target_quantity`, `agent_details`.
  - Writes: `agent_name` (synced to first agent in table), `chhatni`, `latest_chutney_kg_per_quintal`, `latest_chutney_percentage`.
- **Downstream Actions**: `on_update` and `after_delete` hooks trigger `sync_season_mappings_from_allocation()` to update or create `Season Mapping`.
- **Verification Status**: `VERIFIED BY TEST` and `VERIFIED IN CODE` (`target_allocation.py:33-140`).

---

### Stage 2: PPAS Transit Pass Ingestion & Planning

#### Step 2.1: PPAS Transit Pass Ingestion
- **Business Purpose**: Ingest government Transit Passes issued on the Odisha PPAS portal into the mill ERP.
- **Methods of Ingestion**:
  1. **Direct Paste / Excel Import**: Via `PPAS Transit Pass Import`. User pastes raw tabular data or uploads Excel; clicking `Process & Save` parses rows into child table `PPAS Transit Pass Import Item`; clicking `Push to Transit Pass` calls `import_manual_ppas_valid_rows()`.
  2. **Automated Scraper**: `tools/ppas_agent` running locally queries PPAS portal session at `http://127.0.0.1:8765`, downloading data via `PPAS Data Extraction`.
- **Validations & Transformations**:
  - String cleaning: stripping whitespace, parsing PPAS date format `DD-Mon-YYYY HH:mm:ss`.
  - Generation of canonical **Pass Unique Key**:
    $$\text{pass\_unique\_key} = \text{\{miller\_code\}-\{ppc\_name(ppc\_code)\}-\{K/R\}\{YY\}-TP\{transit\_pass\_no\}}$$
    *(e.g., `M051007-DUDUKA(S1050113)-K25-TP138`)*.
  - Duplicate identity validation: `(season, ppc, transit_pass_no)` must be unique; `pass_unique_key` must be unique.
- **Resulting DocType**: `PPAS Transit Pass` (stores `quantity`, `bags`, `vehicle_no`, `driver_name`, `pacs`, `ppc`, `miller`).
- **Verification Status**: `VERIFIED IN CODE` (`ppas_transit_pass.py:21-108`, `pass_unique_key.py:100-111`).

#### Step 2.2: Daily Planning
- **Business Purpose**: Schedule truck dispatches to PPCs and estimate paddy procurement volume.
- **Source DocType**: `Daily Planning`.
- **Calculations**:
  - `trucks_loaded`: Counts existing `PPAS Transit Pass` rows matching `plan_date` and `ppc_name`.
  - `trucks_remaining`: $\max(\text{trucks\_sent} - \text{trucks\_loaded}, 0)$.
  - `estimated_paddy`: $\text{trucks\_sent} \times \text{average\_truck\_capacity}$ (default 250 QTL).
- **Verification Status**: `VERIFIED IN CODE` (`daily_planning.py:53-124`).

---

### Stage 3: Gate Entry (Arrival at Mill)

#### Step 3.1: Physical Vehicle Arrival
- **Business Purpose**: Security check and formal entry recording of the truck carrying paddy into the mill premises.
- **Responsible Role/User**: Gate Security Guard / Gate Clerk.
- **Source DocType**: `Gate Entry`.
- **Trigger**: Vehicle reaches the physical gate.
- **Preconditions & Validations**:
  - `in_out` is set to `"In"`.
  - `vehicle_no` must be normalized to uppercase without extra spaces.
  - **Open Visit Rule**: Vehicle must NOT already be inside the mill. If an open Gate In exists (`inside_mill == 1` and no matching Gate Out/Exit), the system blocks entry:
    `"Vehicle {vehicle_no} is already inside the mill (Gate In {open_visit}). Record Gate Out before a new Gate In."`
- **Fields Written/Derived**:
  - `inside_mill = 1`.
  - `going_to_weighment = 1` if `in_purpose in ('Paddy', 'Rice')`.
  - `entry_datetime`, `entry_date`, `entry_time` (auto-populated with current timestamp).
- **Next Possible Steps**: Vehicle proceeds to Quality Inspection or Weighbridge.
- **Verification Status**: `VERIFIED IN CODE` (`gate_entry.py:38-206`, `mill_gate.py:56-84`).

---

### Stage 4: Quality Inspection (QC)

#### Step 4.1: Sampling and Bag Inspection
- **Business Purpose**: Sample the incoming paddy truck, measure moisture, refraction/dust, record bag counts, and approve unloading.
- **Responsible Role/User**: Quality Inspector / Chemist.
- **Source DocType**: `Quality Check`.
- **Trigger**: Truck arrives at inspection bay after Gate In.
- **Preconditions & Validations**:
  - Vehicle must have an active, open Gate Entry In (`inside_mill == 1`). If the visit is closed, throws `"Visit Closed"`.
  - Exactly one `Quality Check` per Gate Entry visit. If another QC exists for this `gate_entry`, throws `"Duplicate Vehicle"`.
  - **Strict Table Row Constraint**: Child tables `old_new_bags` (`Quality Check Old New Bag Detail`) and `type_of_pkt` (`Quality Check Bag Detail`) must contain **exactly one row**. If multiple rows are entered, throws error.
- **Quality Outcome Logic**:
  - `paddy_received_in_pkt`: Total bags unloaded.
  - `paddy_returned`: Rejected/returned bags.
  - Decision Formula:
    ```python
    if paddy_returned <= 0:
        qc_decision = "Accepted"
    else:
        qc_decision = "Partially Accepted"
    ```
  - **Full Rejection Rule**: If $paddy\_returned \ge paddy\_received\_in\_pkt > 0$, `is_full_paddy_return_from_qc()` evaluates to `True`. When tare weight is later weighed, the weighbridge outcome becomes `"Rejected"` and net weight is forced to 0.
- **Controller Side-Effects**:
  - Updates `Gate Entry.party_name` with `Quality Check.staff_name` (or farmer name).
  - Calls `sync_weigh_bridge_quality_for_vehicle()` to immediately update any open `Weigh Bridge Measurement` for this vehicle.
- **Verification Status**: `VERIFIED IN CODE` (`quality_check.py:45-266`).

---

### Stage 5: Weighbridge Measurement & Weighment Slip (WBM / RST)

#### Step 5.1: Weighment Initiation (RST or Direct WBM)
- **Business Purpose**: Capture gross weight (truck + paddy) and tare weight (empty truck after unloading) to compute official net paddy weight.
- **Responsible Role/User**: Weighbridge Operator.
- **Source DocTypes**: `RST Details` and/or `Weigh Bridge Measurement`.
- **Workflow Branching**:
  - **Branch A (RST Slip Entry)**: Operator creates `RST Details` recording `rst_no`, `vehicle_no`, `gross_vehicle_weight_qt`, `tare_vehicle_weight_qt`, `gunny_weight_qt`, `deduction_qt`, `tp_no`. Saving automatically creates/updates linked `Weigh Bridge Measurement`.
  - **Branch B (Direct WBM Entry)**: Operator creates `Weigh Bridge Measurement` directly, selecting `Pass Unique Key` from autocomplete dropdown.
- **Automatic Auto-Sync from Gate & QC**:
  - `actual_truck_no` is validated against open Gate Entries inside the mill (`get_weighment_vehicles_inside_mill()`).
  - System automatically resolves linked `Quality Check` by vehicle or gate entry, copying `slno_of_qc`, `quality_test`, and bag counts.
- **Weight Calculations**:
  1. $\text{gross\_weight} = \text{load\_weight} - \text{tare\_weight}$ (if tare is entered; otherwise equals load weight).
  2. If `gunny_type == 'Gunny Gross'`: $\text{gunny\_weight} = 0$.
  3. If `gunny_type == 'Gunny Cut'`: derived from child table `bag_weight_details` or manual entry.
  4. $\text{net\_weight} = \max(\text{gross\_weight} - \text{gunny\_weight} - \text{deduction}, 0)$.
- **Verification Status**: `VERIFIED IN CODE` (`weigh_bridge_measurement.py:252-750`).

---

### Stage 6: Automatic GRN Generation

#### Step 6.1: Eligibility Gate & Creation
- **Business Purpose**: Formal receipt of goods into mill custody; primary transaction for financial, stock, and statutory compliance.
- **Responsible Role/User**: System automation (via WBM hooks) or GRN Clerk.
- **Source DocType**: `GRN Note`.
- **Trigger**: Fired automatically on `after_insert` and `on_update` of `Weigh Bridge Measurement` via `_ensure_grn_note_for_weigh_bridge()`.
- **Strict Eligibility Preconditions**:
  1. `tare_weight > 0` (Truck must have completed second weighment).
  2. `quality_test in ('Accepted', 'Partially Accepted')`.
  3. `pass_unique_key` and `rst_no` must be present.
  4. No prior non-cancelled GRN exists for this `weigh_bridge_measurement`.
- **Field Synchronization from Upstream Documents**:
  - From `PPAS Transit Pass`: `transit_pass_no`, `transit_pass_datetime`, `tp_quantity`, `pacs`, `ppc`, `mill_name`, `cmr_season`.
  - From `Weigh Bridge Measurement`: `gross_vehicle_weight`, `gross_weight`, `tare_weight`, `net_weight`, `deduction`, `gunny_type`, `gunny_weight`, `jute_bags`, `plastic_bags`, `total_bags`.
  - From `Quality Check`: `moisture`, `dust`, `unloader_name`, `unloading_point`, `paddy_type`, `paddy_quality`, `qc_decision`, `qc_datetime`, `qc_sample_no`, `old_new_bags`, `qc_bag_details`.
  - From `Gate Entry` / `Gate Exit`: `arrival_datetime`, `driver_name`, `mobile_no`, `party_name`, `gate_exit`, `gate_exit_datetime`.
  - From `Entry`: Child table `entry_details` populated with matching entry rows.
- **Chhatni Locking**: On initial insert (`self.is_new()`), `chhatni` is fetched from `Season Mapping`. On future resaves, it is locked.
- **Naming Series**: Autonamed sequentially per calendar year: `GRN-{YYYY}-.#####` (e.g. `GRN-2026-00001`).
- **Verification Status**: `VERIFIED BY TEST` and `VERIFIED IN CODE` (`grn_note.py:73-525`, `test_e2e_procurement.py:233-248`).

---

### Stage 7: Pass Fulfillment & Multi-GRN Reconciliation

#### Step 7.1: Cumulative Pass Rollup (`grn_tp_fulfillment.py`)
- **Business Purpose**: Track completion of a Transit Pass when fulfilled across one or multiple trips/GRNs.
- **Trigger**: Every save, update, or trash of a government `GRN Note` invokes `refresh_tp_fulfillment_for_pass()`.
- **Calculation Mechanism**:
  1. Fetches all GRNs sharing the same `pass_unique_key` where `docstatus < 2`.
  2. Orders GRNs chronologically: `receipt_datetime asc, creation asc`.
  3. Accumulates running net received weight and deductions:
     $$\text{tp\_cumulative\_received} = \sum \text{net\_weight}$$
     $$\text{tp\_cumulative\_deduction} = \sum \text{deduction}$$
  4. Computes fulfillment status:
     - If $\text{cumulative} \le 0$: `"Pending"`
     - If $0 < \text{cumulative} < \text{tp\_quantity}$: `"In Progress"`
     - If $\text{cumulative} \ge \text{tp\_quantity}$: `"TP Completed"`
  5. Computes Chhatni metrics and assigns statuses (`"Chhatni Received"`, `"Extra Chhatni Received"`, `"Chhatni Not Received"`).
  6. Writes calculated metrics directly back to each linked `GRN Note` via `frappe.db.set_value(..., update_modified=False)`.
- **Verification Status**: `VERIFIED BY TEST` and `VERIFIED IN CODE` (`grn_tp_fulfillment.py:264-353`).

---

### Stage 8: Gate Exit (Vehicle Departure)

#### Step 8.1: Gate Out Recording
- **Business Purpose**: Verify empty truck exit and close the open mill visit.
- **Responsible Role/User**: Gate Security Guard.
- **Source DocType**: `Gate Exit` (or `Gate Entry` with `in_out == 'Out'`).
- **Trigger**: Truck departs through gate.
- **Preconditions & Validations**:
  - `vehicle_no` must match an active Gate Entry In (`inside_mill == 1`).
  - No duplicate Gate Exit for the same `gate_entry_in`.
- **Effects**:
  - Updates `Gate Entry.inside_mill = 0`.
  - When viewed or printed, `GRN Note` links `gate_exit` and displays `gate_exit_datetime`.
- **Verification Status**: `VERIFIED IN CODE` (`gate_exit.py:14-73`, `gate_entry.py:71-117`).

---

### Stage 9: Operational & Statutory Reporting

#### Reports Executed:
1. **Mandi Book (`mandi_book.py`)**: Consolidates all GRNs grouped by `Pass Unique Key`. Displays season, PPC, mill, TP quantity, total gross weight, total gunny weight, total deductions, total net received, pending quantity, excess quantity, TP status, bag counts, and Chhatni status.
2. **Abstract Physical (`abstract_physical.py`)**: Compares PPC-level TP quotas against physical paddy received and farmer Entry purchases. Calculates Chhatni percentage using denominator $(TP_{qty} - Entry_{qty})$.
3. **Abstract Report (`abstract_report.py`)**: Generates the cross-tab matrix of Season + PPC vs. All Active Mills, showing Target, Received, and Balance for each mill and overall totals.
4. **Chhatni Tracking (`chhatni_tracking.py`)**: Audits assigned vs. actual Chhatni percentage per Transit Pass, flagging shortfall or excess deliveries beyond $\pm 0.30$ percentage points.
5. **Entry Report (`entry_report.py`)**: Tabulates direct PPC farmer purchase records with prices and amounts.

---

### Stage 10: CMR Execution (Custom Milled Rice) — Current State vs. Missing Gap

```mermaid
flowchart LR
    subgraph CurrentImplementation["Currently Implemented (ivri_od)"]
        GRN[GRN Note Paddy Received] --> SM_CALC[Season Mapping Calculation]
        SM_CALC -->|paddy * rice_yield %| RD[Rice Due Estimate]
        RD -.-> UNUSED[Unused Field: rice_dispatched]
    end

    subgraph MissingLifecycle["Missing Operational Capabilities (CMR)"]
        UNUSED -.-x MILL_BATCH[Milling Batch / Paddy Issue]
        MILL_BATCH -.-x RICE_PROD[Rice Production & By-Products]
        RICE_PROD -.-x DISPATCH[CMR Dispatch Challan / Gate Out]
        DISPATCH -.-x AC_DEPOT[FCI / OSCSC AC Acceptance]
        AC_DEPOT -.-x RECON[Paddy-to-Rice Reconciliation Ledger]
    end
```

- **Current Implementation**: Purely static mathematical estimation on `Season Mapping`. No transactions exist for milling, physical rice dispatch, quality acceptance committee (AC) certificates, or final delivery ledger reconciliation.
