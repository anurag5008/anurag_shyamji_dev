# 07: Technical Workflow Diagrams & Visual Lineage

This document contains renderable Mermaid diagrams representing the real-world operational and technical architecture of `ivri_od`. Every diagram is grounded in inspected code files, schemas, and tested execution paths.

---

## Diagram Index

1. [Diagram A: System Context & High-Level Module Architecture](#diagram-a-system-context--high-level-module-architecture)
2. [Diagram B: End-to-End Procurement Lifecycle](#diagram-b-end-to-end-procurement-lifecycle)
3. [Diagram C: Operational Transit Pass to GRN Physical Flow](#diagram-c-operational-transit-pass-to-grn-physical-flow)
4. [Diagram D: Multi-GRN Fulfillment & Over-Receipt Decision Flow](#diagram-d-multi-grn-fulfillment--over-receipt-decision-flow)
5. [Diagram E: Mathematical Weight & Chhatni Lineage](#diagram-e-mathematical-weight--chhatni-lineage)
6. [Diagram F: Core DocType Entity-Relationship (ER) Diagram](#diagram-f-core-doctype-entity-relationship-er-diagram)
7. [Diagram G: Mandi Book & Abstract Physical Report Data Lineage](#diagram-g-mandi-book--abstract-physical-report-data-lineage)
8. [Diagram H: Existing CMR Implementation Footprint](#diagram-h-existing-cmr-implementation-footprint)
9. [Diagram I: Proposed CMR Execution Lifecycle (PROPOSED)](#diagram-i-proposed-cmr-execution-lifecycle-proposed)

---

## Diagram A: System Context & High-Level Module Architecture

```mermaid
flowchart TB
    subgraph External["External Interfaces"]
        OSCSC["Government (OSCSC / PPAS Portal)"]
        WB_HARDWARE["Physical Weighbridge Scale"]
    end

    subgraph IVRI_OD["ivri_od Application (Frappe v16)"]
        subgraph Mod_Master["Master & Target Management"]
            SM["Season Master"]
            PPC["PPC Master"]
            MM["Mill Master"]
            TA["Target Allocation"]
            CA["Chhatni Assign"]
            SMP["Season Mapping"]
        end

        subgraph Mod_Ingestion["PPAS Ingestion & Planning"]
            EXT["PPAS Data Extraction"]
            TP_IMP["PPAS Transit Pass Import"]
            TP["PPAS Transit Pass"]
            DP["Daily Planning"]
        end

        subgraph Mod_GateQC["Gate & Quality Control"]
            GE["Gate Entry (In)"]
            QC["Quality Check"]
            GX["Gate Exit (Out)"]
        end

        subgraph Mod_WeighGRN["Weighment & GRN"]
            RST["RST Details"]
            WBM["Weigh Bridge Measurement"]
            GRN["GRN Note"]
            EN["Entry (Farmer Direct)"]
        end

        subgraph Mod_Reports["Procurement Reports"]
            MB["Mandi Book"]
            AP["Abstract Physical"]
            AR["Abstract Report"]
            CT["Chhatni Tracking"]
        end
    end

    OSCSC -->|Scrape / Excel Import| EXT
    EXT --> TP_IMP
    TP_IMP --> TP
    TP --> WBM
    TP --> GRN

    GE --> QC
    QC --> WBM
    WB_HARDWARE --> RST
    RST --> WBM
    WBM -->|Auto-create| GRN
    GRN --> GX
    GRN --> MB
    GRN --> AP
    GRN --> CT
    SMP --> AR
```

- **Explanation**: Illustrates the system boundaries, data sources, internal module separation, and operational data flow from external portals down to statutory reports.
- **Source References**: `hooks.py`, `procurement_workspace.py`, `workspace/procurement/procurement.json`.

---

## Diagram B: End-to-End Procurement Lifecycle

```mermaid
flowchart TD
    Start([Procurement Season Opens]) --> SetupMaster[Configure Season, Mill, PPC, Agent Masters]
    SetupMaster --> SetChhatni[Record Chhatni Assign Rate]
    SetChhatni --> SetTarget[Create Target Allocation Quota per PPC]
    SetTarget --> SyncMapping[Auto-sync Target & Chhatni to Season Mapping]

    SyncMapping --> ImportTP[Import Transit Passes from PPAS Portal]
    ImportTP --> GenKey[Generate Pass Unique Key]

    GenKey --> TruckArrives[Paddy Truck Arrives at Mill]
    TruckArrives --> GateIn[Gate Entry 'In': inside_mill=1, going_to_weighment=1]
    GateIn --> QualityCheck[Perform Quality Check: moisture, dust, bags]

    QualityCheck --> QC_Decide{QC Decision?}
    QC_Decide -->|Full Return / Rejected| RejectLoad[Mark QC Rejected -> Tare recorded -> Net Wt=0 -> No GRN]
    QC_Decide -->|Accepted / Partial| FirstWeigh[Weighbridge 1st Weighment: Gross Load Weight]

    FirstWeigh --> Unload[Unload Paddy into Mill Sheds]
    Unload --> SecondWeigh[Weighbridge 2nd Weighment: Empty Tare Weight]

    SecondWeigh --> CalcNet[Calculate Net Weight = Load - Tare - Gunny - Deduction]
    CalcNet --> AutoGRN[Auto-generate GRN Note: Copy TP, WBM, QC, Gate Data]

    AutoGRN --> Rollup[grn_tp_fulfillment Engine Updates Pass]
    Rollup --> StatusCheck{Cumulative Net vs TP Qty?}
    StatusCheck -->|< TP Qty| InProgress[TP Status: In Progress]
    StatusCheck -->|>= TP Qty| Completed[TP Status: TP Completed -> Evaluate Chhatni Status]

    InProgress --> GateOut[Gate Exit 'Out': inside_mill=0 -> Close Visit]
    Completed --> GateOut
    GateOut --> EndVisit([Truck Departs Mill])
```

- **Explanation**: Step-by-step lifecycle from pre-season quota setup to truck arrival, quality gate, dual weighments, automatic GRN creation, and departure.
- **Source References**: `test_e2e_procurement.py:1-265`, `weigh_bridge_measurement.py:252-265`, `grn_note.py:85-107`.

---

## Diagram C: Operational Transit Pass to GRN Physical Flow

```mermaid
sequenceDiagram
    autonumber
    actor Driver as Truck Driver
    participant Gate as Gate Security
    participant QC as QC Inspector
    participant Scale as Weighbridge
    participant System as ivri_od ERP Engine
    participant Office as Procurement Office

    Driver->>Gate: Arrives at Gate with Paddy Truck & TP Slip
    Gate->>System: Creates Gate Entry (In), inside_mill=1
    Driver->>QC: Proceeds to Quality Shed
    QC->>System: Creates Quality Check (Moisture, Bags, Decision)
    System-->>Scale: QC decision auto-links to Vehicle visit
    Driver->>Scale: First Weighment (Truck + Paddy)
    Scale->>System: Weighbridge Measurement (Load Weight recorded)
    Driver->>Office: Unloads Paddy into Shed
    Driver->>Scale: Second Weighment (Empty Truck)
    Scale->>System: WBM Tare Weight recorded
    System->>System: Computes Net Weight = Load - Tare - Gunny - Deduction
    System->>System: Auto-creates GRN Note (copies TP, WBM, QC, Gate details)
    System->>System: Recomputes Pass Cumulative Total & Fulfillment Status
    Driver->>Gate: Exits Mill
    Gate->>System: Records Gate Exit (Gate In inside_mill set to 0)
    Office->>System: Prints Official GRN Note with QR Code
```

- **Explanation**: Interaction sequence between physical human actors (driver, security, inspector, scale operator) and the automated document generation hooks.
- **Source References**: `mill_gate.py:56-125`, `weigh_bridge_measurement.py:1105-1145`, `grn_note.py:1354-1367`.

---

## Diagram D: Multi-GRN Fulfillment & Over-Receipt Decision Flow

```mermaid
flowchart TD
    Trigger([GRN Note Saved / Updated / Trashed]) --> FetchGRNs[Query all GRNs for Pass Unique Key where docstatus < 2]
    FetchGRNs --> SortChron[Sort Chronologically: receipt_datetime asc, creation asc]
    SortChron --> Accumulate[Cumulative Received = Sum of net_weight<br>Cumulative Deduction = Sum of deduction]

    Accumulate --> CheckFulfill{Cumulative Received vs TP Qty}
    CheckFulfill -->|Cumulative == 0| SetPending[TP Fulfillment Status: 'Pending']
    CheckFulfill -->|0 < Cumulative < TP Qty| SetInProgress[TP Fulfillment Status: 'In Progress']
    CheckFulfill -->|Cumulative >= TP Qty| SetCompleted[TP Fulfillment Status: 'TP Completed']

    SetInProgress --> ChhatniBlocked[Chhatni Status: 'Chhatni Not Received'<br>Remark: TP not fully received yet]
    SetPending --> ChhatniBlocked

    SetCompleted --> ChhatniCalc[Calculate Actual Chhatni % = (Cumulative - TP Qty) / TP Qty * 100]
    ChhatniCalc --> ChhatniBounds[Bounds: Assigned % ± 0.30% Tolerance]

    ChhatniBounds --> ChhatniCheck{Actual % vs Tolerance Bounds}
    ChhatniCheck -->|Actual > Upper Bound| ExtraChhatni[Status: 'Extra Chhatni Received']
    ChhatniCheck -->|Lower Bound <= Actual <= Upper Bound| MatchedChhatni[Status: 'Chhatni Received']
    ChhatniCheck -->|Actual < Lower Bound| ShortfallChhatni[Status: 'Chhatni Not Received']

    ExtraChhatni --> WriteBack[Write Statuses directly to all peer GRNs via db.set_value]
    MatchedChhatni --> WriteBack
    ShortfallChhatni --> WriteBack
    ChhatniBlocked --> WriteBack
    WriteBack --> End([Fulfillment Complete])
```

- **Explanation**: Multi-trip accumulation and the mathematical branching governing Transit Pass completion and Chhatni status determination.
- **Source References**: `grn_tp_fulfillment.py:50-210`, `grn_tp_fulfillment.py:279-354`.

---

## Diagram E: Mathematical Weight & Chhatni Lineage

```mermaid
flowchart LR
    subgraph Inputs["Physical Inputs (Scale & QC)"]
        L_WT["Load Weight (QTL)"]
        T_WT["Tare Weight (QTL)"]
        J_BAGS["Jute Bags Count"]
        P_BAGS["Plastic Bags Count"]
        W_JUTE["Weight per Jute (Kg)"]
        W_PLASTIC["Weight per Plastic (Kg)"]
        DED["Deduction (QTL)"]
        TP_Q["TP Quantity (QTL)"]
        CH_RATE["Assigned Chhatni Rate (%)"]
    end

    subgraph GunnyCalc["Gunny Tare Calculation"]
        J_CALC["Jute Qt = (Jute Bags * W_Jute) / 100"]
        P_CALC["Plastic Qt = (Plastic Bags * W_Plastic) / 100"]
        G_WT["Gunny Weight = Jute Qt + Plastic Qt"]
    end

    subgraph NetWeightCalc["Net Weight Derivation"]
        GROSS["Gross Paddy Weight = Load - Tare"]
        NET["Net Weight = max(Gross - Gunny - Deduction, 0)"]
    end

    subgraph FulfillmentCalc["Fulfillment & Tolerance"]
        CUM_NET["Cumulative Net = Sum(Net Weight)"]
        ACT_CH_PCT["Actual Chhatni % = (Cum Net - TP Q) / TP Q * 100"]
        TOL_L["Lower Bound = Rate - 0.30%"]
        TOL_U["Upper Bound = Rate + 0.30%"]
        CH_STATUS["Chhatni Status Decision"]
    end

    L_WT --> GROSS
    T_WT --> GROSS
    J_BAGS --> J_CALC
    W_JUTE --> J_CALC
    P_BAGS --> P_CALC
    W_PLASTIC --> P_CALC
    J_CALC --> G_WT
    P_CALC --> G_WT
    GROSS --> NET
    G_WT --> NET
    DED --> NET

    NET --> CUM_NET
    CUM_NET --> ACT_CH_PCT
    TP_Q --> ACT_CH_PCT
    CH_RATE --> TOL_L
    CH_RATE --> TOL_U
    ACT_CH_PCT --> CH_STATUS
    TOL_L --> CH_STATUS
    TOL_U --> CH_STATUS
```

- **Explanation**: Detailed mathematical dependency graph tracing raw measurement inputs to final net weight, gunny bag deduction, cumulative rollups, and tolerance boundaries.
- **Source References**: `weigh_bridge_measurement.py:158-165, 724-738`, `grn_tp_fulfillment.py:140-210`.

---

## Diagram F: Core DocType Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    SEASON_MASTER ||--o{ TARGET_ALLOCATION : allocates
    SEASON_MASTER ||--o{ SEASON_MAPPING : maps
    PPC_MASTER ||--o{ TARGET_ALLOCATION : assigns
    MILL_MASTER ||--o{ TARGET_ALLOCATION : receives
    TARGET_ALLOCATION ||--o| CHHATNI_ASSIGN : "latest chhatni"
    CHHATNI_ASSIGN ||--o{ CHHATNI_ASSIGN_HISTORY : logs
    TARGET_ALLOCATION ||--o{ TARGET_ALLOCATION_AGENT : contains

    SEASON_MASTER ||--o{ PPAS_TRANSIT_PASS : imports
    PPC_MASTER ||--o{ PPAS_TRANSIT_PASS : origins
    MILL_MASTER ||--o{ PPAS_TRANSIT_PASS : delivers

    GATE_ENTRY ||--o| GATE_EXIT : closes
    GATE_ENTRY ||--o| QUALITY_CHECK : inspects
    QUALITY_CHECK ||--o{ QUALITY_CHECK_BAG_DETAIL : contains
    QUALITY_CHECK ||--o{ QUALITY_CHECK_OLD_NEW_BAG_DETAIL : contains

    GATE_ENTRY ||--o| WEIGH_BRIDGE_MEASUREMENT : tracks
    QUALITY_CHECK ||--o| WEIGH_BRIDGE_MEASUREMENT : qualifies
    RST_DETAILS ||--o| WEIGH_BRIDGE_MEASUREMENT : creates
    WEIGH_BRIDGE_MEASUREMENT ||--o{ WEIGH_BRIDGE_BAG_DETAIL : contains

    PPAS_TRANSIT_PASS ||--o{ GRN_NOTE : fulfills
    WEIGH_BRIDGE_MEASUREMENT ||--o| GRN_NOTE : converts
    QUALITY_CHECK ||--o| GRN_NOTE : copies
    GATE_ENTRY ||--o| GRN_NOTE : records
    ENTRY ||--o{ GRN_ENTRY_DETAIL : mirrors
    GRN_NOTE ||--o{ GRN_ENTRY_DETAIL : contains
```

- **Explanation**: Structural relationship entity-relationship model linking master entities, gate records, inspection sheets, weighment slips, and receipt vouchers.
- **Source References**: Checked-in `.json` schemas across `ivri_od/procurement/doctype/`.

---

## Diagram G: Mandi Book & Abstract Physical Report Data Lineage

```mermaid
flowchart TD
    subgraph RawData["Source Records"]
        GRN["GRN Note (net_weight, deduction, gross, tare, bags)"]
        TP["PPAS Transit Pass (quantity, season, ppc, miller)"]
        EN["Entry (entry_quantity, entry_price_per_quintal)"]
        TA["Target Allocation (target_quantity, chhatni)"]
    end

    subgraph MandiBookReport["Mandi Book Engine (mandi_book.py)"]
        MB_GRP["Group GRNs by Pass Unique Key"]
        MB_SUM["Sum: Gross Wt, Gunny Wt, Deductions, Received Qty"]
        MB_FULFILL["Call tp_fulfillment_status & calculate_chhatni_metrics"]
        MB_OUT["Mandi Book Line: Season, PPC, Mill, TP Qty, Net Qty, Pending, Excess, Status"]
    end

    subgraph AbstractPhysicalReport["Abstract Physical Engine (abstract_physical.py)"]
        AP_PPC["Aggregate by (Season, PPC Master)"]
        AP_TP["Sum TP Quantity"]
        AP_NET["Sum Physical Paddy Received"]
        AP_ENTRY["Sum Direct Entry Qty"]
        AP_CHHATNI["Fetch Excess Qty from Mandi Book"]
        AP_FORMULA["Chhatni % = Chhatni Qty / (TP Qty - Entry Qty) * 100"]
        AP_OUT["Abstract Physical Row: Season, PPC, TP Qty, Physical, Entry, Chhatni Qty, Chhatni %"]
    end

    GRN --> MB_GRP
    TP --> MB_GRP
    MB_GRP --> MB_SUM
    MB_SUM --> MB_FULFILL
    MB_FULFILL --> MB_OUT

    TP --> AP_TP
    GRN --> AP_NET
    EN --> AP_ENTRY
    MB_OUT -.->|Excess Qty per Pass| AP_CHHATNI
    AP_TP --> AP_FORMULA
    AP_ENTRY --> AP_FORMULA
    AP_CHHATNI --> AP_FORMULA
    AP_FORMULA --> AP_OUT
```

- **Explanation**: Data aggregation lineage illustrating how `Mandi Book` aggregates per transit pass and feeds downstream into `Abstract Physical` per PPC.
- **Source References**: `mandi_book.py:152-295`, `abstract_physical.py:80-277`.

---

## Diagram H: Existing CMR Implementation Footprint

```mermaid
flowchart LR
    subgraph Implemented["Currently Implemented in ivri_od"]
        TP[PPAS Transit Pass] -->|season| GRN[GRN Note.cmr_season]
        GRN -->|Sum Net Weight| SMP[Season Mapping.paddy_procured_till_date]
        TA[Target Allocation] -->|target_quantity| SMP_Q[Season Mapping.season_quantity]
        SMP -->|Formula: paddy * rice_yield / 100| RICE_DUE[Season Mapping.rice_due_till_date]
        SMP_Q -->|Formula: target * yield * proportion - due| RICE_BAL[Season Mapping.remaining_balance]
        SMP -.-> UNUSED[Field: rice_dispatched - Unused/Dead]
    end

    subgraph Absent["Operational Execution (ABSENT)"]
        M_BATCH[Milling Batch]
        DISP[CMR Dispatch Challan]
        AC_REC[Depot AC Acceptance]
        RECON[Ledger Reconciliation]
    end

    RICE_DUE -.-x M_BATCH
    UNUSED -.-x DISP
    DISP -.-x AC_REC
    AC_REC -.-x RECON
```

- **Explanation**: Highlights the minimal static estimation logic currently present in `Season Mapping` versus the operational milling and dispatch capabilities that are absent.
- **Source References**: `season_mapping.py:67-80`, `grn_note.py:383`.

---

## Diagram I: Proposed CMR Execution Lifecycle (PROPOSED)

> [!NOTE]
> This diagram represents a **PROPOSED architecture** designed to complete the CMR module. It contains no claims of existing implementation.

```mermaid
flowchart TD
    subgraph Proposed_Phase1["Phase 1: Custody Transfer"]
        GRN_CONFIRM[Formal Submitted GRN Note] --> PADDY_CUSTODY[Paddy In-Custody Inventory Account]
    end

    subgraph Proposed_Phase2["Phase 2: Milling Execution"]
        PADDY_CUSTODY --> ISSUE_HOPPER[Issue Paddy to Milling Hopper]
        ISSUE_HOPPER --> MILL_BATCH[CMR Milling Batch DocType]
        MILL_BATCH --> RECOVER_RICE[Record Finished Rice Produced: QTL & Bags]
        MILL_BATCH --> RECOVER_BYPROD[Record By-Products: Bran, Broken, Husk]
        MILL_BATCH --> YIELD_CHECK{Actual Recovery vs 67% Statutory Ratio}
    end

    subgraph Proposed_Phase3["Phase 3: CMR Dispatch"]
        RECOVER_RICE --> PACK_BAGS[Pack Rice in 50kg Gunny / HDPE Bags]
        PACK_BAGS --> CREATE_CHALLAN[CMR Delivery Challan DocType]
        CREATE_CHALLAN --> GATE_OUT_RICE[Gate Exit: Loaded Rice Truck Departs]
    end

    subgraph Proposed_Phase4["Phase 4: Depot Acceptance"]
        GATE_OUT_RICE --> FCI_DEPOT[Arrive at FCI / OSCSC Depot]
        FCI_DEPOT --> AC_INSPECT[Acceptance Committee Quality Inspection]
        AC_INSPECT --> AC_NOTE[CMR Depot Acceptance DocType]
        AC_NOTE -->|Record| AC_ACCEPTED[Accepted Rice Weight & AC Cert No]
        AC_NOTE -->|Record| AC_DEDUCT[Moisture Cut / Weight Shortage]
        AC_NOTE -->|Record| AC_REJECT[Rejected / Returned Rice Truck]
    end

    subgraph Proposed_Phase5["Phase 5: Reconciliation"]
        PADDY_CUSTODY --> RECON_LEDGER[CMR Reconciliation Ledger]
        AC_ACCEPTED --> RECON_LEDGER
        AC_DEDUCT --> RECON_LEDGER
        RECON_LEDGER --> BAL_OBLIGATION[Outstanding Rice Due to Government]
        RECON_LEDGER --> BILL_CLAIM[Generate Milling Subsidy & Charge Claim]
    end
```

- **Explanation**: Future-proof end-to-end technical blueprint for Custom Milled Rice operations, closing the gap between paddy intake, mill hoppers, finished rice delivery, and government subsidy settlement.
