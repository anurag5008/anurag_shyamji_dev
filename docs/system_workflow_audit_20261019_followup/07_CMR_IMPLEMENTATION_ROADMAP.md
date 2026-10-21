# 07: CMR Phased Implementation Roadmap

## 1. Roadmap Architecture Overview

The Custom Milled Rice (CMR) module must be implemented as a clean, phased extension of the existing `ivri_od` procurement module. Each stage builds strictly on validated upstream transactions without modifying historical procurement data.

```mermaid
flowchart LR
    S1["Stage 1:\nAgreement & Quota"] --> S2["Stage 2:\nMilling Batches"]
    S2 --> S3["Stage 3:\nCMR Dispatch"]
    S3 --> S4["Stage 4:\nDepot Acceptance"]
    S4 --> S5["Stage 5:\nGunny & By-Products"]
    S5 --> S6["Stage 6:\nBilling & Claims"]
```

---

## 2. Stage 1: Agreement Foundation & Quota Management

### Objective
Establish the statutory framework governing the miller's relationship with OSCSC, tagged PPCs, milling targets, and financial security.

### Deliverables & Technical Specs:
1. **DocType `CMR Agreement` (Submittable)**:
   - Fields: `season` (Link Season Master), `mill` (Link Mill Master), `agreement_no`, `agreement_date`, `allocated_paddy_target` (QTL), `raw_rice_ratio` (default 68%), `parboiled_rice_ratio` (default 67%), `bank_guarantee_amount`, `security_deposit_status`.
   - Child Table `CMR Tagged PPC`: `ppc_code` (Link PPC Master), `distance_km`, `assigned_paddy_quota` (QTL).
2. **Validations & Logic**:
   - Total assigned paddy in tagged PPCs must not exceed `allocated_paddy_target`.
   - Auto-fetches cumulative paddy received from `GRN Note` for tagged PPCs.
3. **Reports**:
   - `CMR Agreement Fulfillment Summary`: Target vs Procured vs Milled vs Delivered.

---

## 3. Stage 2: Milling Batches & Production Tracking

### Objective
Record daily or batch milling operations, converting physical paddy inventory into milled rice and by-products based on official Out-Turn Ratios (OTR).

### Deliverables & Technical Specs:
1. **DocType `CMR Milling Batch` (Submittable)**:
   - Fields: `batch_id` (Naming Series), `posting_date`, `season`, `mill`, `paddy_type` (Raw / Parboiled), `paddy_variety` (Common / Grade A).
   - Input Fields: `paddy_issued_qty` (QTL), `bags_emptied` (Integer).
   - Output Fields (Computed):
     - `milled_rice_produced_qty` (QTL)
     - `actual_rice_yield_pct` = $(\text{rice\_produced} / \text{paddy\_issued}) \times 100$
     - `standard_yield_pct` (67% for Parboiled, 68% for Raw)
     - `yield_deviation_pct` = $\text{actual\_yield\_pct} - \text{standard\_yield\_pct}$
2. **Child Table `CMR Milling By-Product`**:
   - `item` (Rice Bran, Broken Rice, Husk), `quantity_qtl`, `recovery_pct`.
3. **Validations & Logic**:
   - `paddy_issued_qty` cannot exceed available un-milled paddy balance (`GRN Note` total minus previous batches).
   - Soft warning if `actual_rice_yield_pct` deviates by more than $\pm 1.0\%$ from statutory norm.

---

## 4. Stage 3: CMR Dispatch Challan & Gate Outward

### Objective
Control the dispatch of finished rice from the mill to government storage depots (OSCSC RRCs / FCI Godowns).

### Deliverables & Technical Specs:
1. **DocType `CMR Delivery Order` (Submittable)**:
   - Tracks official OSCSC Release/Delivery Order (DO No, validity date, destination depot, allocated rice quantity in QTL, variety).
2. **DocType `CMR Dispatch Challan` (Submittable)**:
   - Header: `challan_no`, `delivery_order` (Link CMR DO), `dispatch_date`, `destination_depot`, `miller`.
   - Transport Details: `vehicle_no`, `driver_name`, `driver_phone`, `gate_entry_reference`.
   - Weighment Details: `gross_vehicle_weight`, `tare_vehicle_weight`, `net_rice_weight` (QTL), `no_of_bags` (50kg bags), `stenciled_lot_number`.
   - Quality Parameters: `moisture_pct`, `broken_rice_pct`, `foreign_matter_pct`.
3. **Controller Hooks & Workflows**:
   - On submission: Decrements un-dispatched milled rice balance; links with Gate Entry/Exit system to ensure truck is logged outward.

---

## 5. Stage 4: Depot Acceptance & Acceptance Certificate (AC) Recording

### Objective
Capture physical handover and quality appraisal at the receiving OSCSC/FCI depot, establishing legal transfer of title.

### Deliverables & Technical Specs:
1. **DocType `CMR Acceptance Certificate` (Submittable)**:
   - Fields: `ac_number`, `ac_date`, `challan_reference` (Link CMR Dispatch Challan), `depot_name`, `receiving_officer`.
   - Weighment & Quality at Depot:
     - `depot_received_bags`, `depot_net_weight` (QTL)
     - `weight_transit_loss` = $\text{challan\_net\_weight} - \text{depot\_net\_weight}$
     - `moisture_cut_qty` (QTL deduction if moisture exceeds 14%)
     - `refraction_cut_qty` (QTL deduction for broken/damaged grains)
     - `net_accepted_quantity` (QTL)
2. **Reconciliation Logic**:
   - Updates `CMR Dispatch Challan.acceptance_status` ("Accepted", "Partially Accepted with Cuts", "Rejected").
   - Updates `CMR Delivery Order` pending balance.

---

## 6. Stage 5: Gunny Bag & By-Product Reconciliation

### Objective
Provide audit-proof inventory control for government gunny bags and commercial by-products.

### Deliverables & Technical Specs:
1. **DocType `CMR Gunny Reconciliation`**:
   - Reconciles 3 streams:
     1. Paddy Gunnies Received (from WBM/GRN Note `no_of_bags`).
     2. New CMR 50kg Gunnies Purchased/Issued by OSCSC.
     3. Bags Dispatched with CMR Rice (`CMR Dispatch Challan`).
   - Calculates gunny depreciation and balance retained by miller.
2. **DocType `CMR By-Product Register`**:
   - Tracks stock of Rice Bran, Broken Rice, and Husk.
   - Records local sale/disposal and reconciles against total paddy milled.

---

## 7. Stage 6: CMR Billing, Claims & Financial Settlement

### Objective
Automate statutory billing to the government based on accepted ACs and government-notified cost sheets.

### Deliverables & Technical Specs:
1. **DocType `CMR Bill` (Submittable)**:
   - Multi-select or table of linked `CMR Acceptance Certificate` records.
   - Automated Billing Lines:
     - **Milling Charges**: Net Accepted Rice (QTL) $\times$ Rate (e.g. ₹20/QTL).
     - **Mandi to Mill Transport**: Mandi distance tier $\times$ Paddy QTL.
     - **Mill to Depot Transport**: Depot distance tier $\times$ Rice QTL.
     - **Handling & Loading/Unloading**: Flat government rate per QTL.
     - **Gunny Bag Usage Charges / Cost Difference**.
   - Net Payable, TDS (194C / 194Q), and GST handling.
2. **Reports & Dashboards**:
   - `CMR Miller Master Ledger`: Comprehensive financial and physical reconciliation sheet.
