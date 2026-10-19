# Workflow diagrams

All diagrams are source-grounded summaries, not runtime proof. References are repository-relative.

## Index and overall context

```mermaid
flowchart LR
  cfg[Season / PPC / Mill / Agent masters] --> alloc[Target Allocation]
  alloc --> map[Season Mapping]
  ppas[PPAS extraction/import] --> tp[PPAS Transit Pass]
  tp --> rst[RST Details]
  rst --> gate[Gate Entry / Gate Exit]
  gate --> qc[Quality Check]
  qc --> wbm[Weigh Bridge Measurement]
  tp --> wbm
  rst --> wbm
  wbm --> grn[GRN Note]
  tp --> grn
  grn --> reports[Mandi Book / Abstract Physical / operational reports]
  grn --> map
  map -. rice due estimate only .-> cmr[CMR readiness fields; no transaction workflow found]
```

Evidence: `hooks.py`; Procurement DocType JSON/controllers; `season_mapping.py`; reports. Unknown: actual role permissions and runtime wiring.

## Procurement workflow

```mermaid
flowchart TD
  A[Configure Season Master, PPC, Mill, Agent] --> B[Target Allocation]
  B --> C[Season Mapping target and chhatni sync]
  D[PPAS file/extraction import] --> E[PPAS Transit Pass with pass_unique_key]
  E --> F[RST Details / vehicle arrival]
  F --> G[Gate Entry In / open vehicle visit]
  G --> H[Quality Check by vehicle]
  H --> I[WBM: TP + RST + QC + load/tare/bags]
  I --> J{QC accepted or partially accepted and tare > 0?}
  J -- yes, strict auto path --> K[GRN Note]
  J -- no --> L[Blocked from strict auto-GRN; correct QC/weighment]
  K --> M[After-commit TP rollup and report data]
  G --> N[Gate Exit]
  M --> O[Mandi Book / Abstract Physical]
```

Evidence: `grn_note.py:85-105, 430-489`; `weigh_bridge_measurement.py:290-323`; `gate_entry.py`, `gate_exit.py`, QC controller; reports. Gate/QC/WBM exact ordering admits exceptions; arrows express common route.

## TP -> Gate -> WBM/RST -> QC -> GRN

```mermaid
flowchart LR
  TP[PPAS Transit Pass] -->|pass_unique_key checked| WBM[Weigh Bridge Measurement]
  RST[RST Details: rst_no / vehicle] -->|resolved by RST / pass key| WBM
  Gate[Gate Entry: vehicle / open visit] -->|vehicle lookup / gate_entry link| QC[Quality Check]
  QC -->|quality_check and bag counts| WBM
  WBM -->|RST + key equality; copied weights| GRN[GRN Note]
  WBM -. on update may attempt GRN creation .-> GRN
  GRN -->|non-cancelled duplicate WBM guard| Save{valid draft/save?}
  Save -->|submit via Frappe lifecycle| S[Submitted receipt]
  Save -->|validation error| Fix[Correct links / QC / tare / key]
```

Evidence: WBM validation and GRN `_apply_weigh_bridge`; duplicate checks. Runtime auto-create availability unverified.

## Multiple GRN fulfillment decisions

```mermaid
flowchart TD
  A[TP key] --> B[Collect GRNs for exact key]
  B --> C{Aggregation selector}
  C -->|canonical helper docstatus=1| D[Submitted-only sum net_weight]
  C -->|stored rollup/report docstatus<2| E[Draft + submitted sum net_weight]
  D --> F{sum vs TP}
  E --> F
  F -->|<=0| P[Pending]
  F -->|0 < sum < TP| IP[In Progress; pending TP-sum]
  F -->|sum >= TP| Done[TP Completed; excess=max(sum-TP,0)]
  Done --> Ch[Chhatni status against assigned rate ±0.30 pp]
  F -. no hard excess rejection found .-> Done
```

Evidence: `grn_tp_fulfillment.py:50-137, 267-` and `mandi_book.py` aggregation. The selector divergence is deliberate to flag, not resolve.

## Weight / deduction lineage

```mermaid
flowchart LR
  QC[QC bag counts] --> bags[WBM bag detail × kg per bag / 100]
  load[Load weight] --> gross[Gross = load - tare if both truthy; else load]
  tare[Tare weight] --> gross
  gross --> net[Net=max(gross - gunny - deduction,0), 3 decimals]
  bags --> gunny[Gunny weight; manual positive override may win]
  gunny --> net
  ded[WBM deduction] --> net
  net --> grn[Copied GRN.net_weight]
  grn --> cumul[Per TP cumulative receipt]
  cumul --> ch[Excess %, chhatni, pending/excess]
  ded --> bal[TP chhatni balance = max(cumulative - TP - deductions,0)]
```

Evidence: `weigh_bridge_measurement.py:722-737`; `grn_note.py:430-489`; `grn_tp_fulfillment.py:24-47, 140-210`.

## Core relationships (ER)

```mermaid
erDiagram
  PPAS_TRANSIT_PASS ||--o{ GRN_NOTE : "pass_unique_key (code key)"
  PPAS_TRANSIT_PASS ||--o{ WEIGH_BRIDGE_MEASUREMENT : "pass_unique_key (code key)"
  RST_DETAILS ||--o| WEIGH_BRIDGE_MEASUREMENT : "demo_rst_data (declared link)"
  QUALITY_CHECK ||--o{ QUALITY_CHECK_BAG_DETAIL : "type_of_pkt (table)"
  QUALITY_CHECK ||--o{ QUALITY_CHECK_OLD_NEW_BAG_DETAIL : "child table"
  QUALITY_CHECK ||--o{ WEIGH_BRIDGE_MEASUREMENT : "quality_check (declared link)"
  GATE_ENTRY ||--o{ QUALITY_CHECK : "vehicle/lookup and possible link"
  GATE_ENTRY ||--o{ WEIGH_BRIDGE_MEASUREMENT : "gate_entry (declared link)"
  WEIGH_BRIDGE_MEASUREMENT ||--o| GRN_NOTE : "weigh_bridge_measurement (validated code link)"
  GRN_NOTE ||--o{ GRN_ENTRY_DETAIL : "entry_details (table)"
  TARGET_ALLOCATION ||--o{ TARGET_ALLOCATION_AGENT : "agent_details (table)"
  SEASON_MAPPING ||--o{ SEASON_MAPPING_COLLECTION_POINT : "collection_point_details (table)"
```

ER field cardinalities are conceptual; code checks do not establish DB uniqueness. Exact field declarations in inventory.

## Report lineage

```mermaid
flowchart LR
  TP[PPAS Transit Pass] --> key[pass_unique_key]
  WBM[WBM weights / bag details] --> GRN[GRN Note, docstatus<2]
  key --> GRN
  GRN --> mb[Mandi Book: group by pass key; sum net, fields from WBM]
  TA[Target Allocation] --> AP[Abstract Physical target map]
  TP --> AP
  GRN --> AP
  GED[GRN Entry Detail] --> AP
  mb -->|excess per pass reused| AP
```

Evidence: `mandi_book.py:148+`, `abstract_physical.py:80+`; Mandi Book and Abstract Physical both include drafts in seen GRNs.

## Existing CMR flow

```mermaid
flowchart LR
  GRN[GRN paddy receipt] --> read[Season Mapping procurement estimate]
  yield[Season Mapping rice_yield] --> due[rice_due_till_date estimate]
  read --> due
  target[Season Mapping season_quantity + collection proportion] --> balance[remaining_balance estimate]
  due --> balance
  dispatched[rice_dispatched field] -. no writer/workflow found .-> balance
  due -. no batch, delivery, acceptance, or reconciliation .-> absent[CMR transaction lifecycle absent]
```

## Proposed CMR completion (PROPOSED)

```mermaid
flowchart TD
  A[Confirm CMR meaning, obligation, units and eligibility rules] --> B[Approve custody and milling batch lifecycle]
  B --> C[Define production/yield/by-product and variance rules]
  C --> D[Define dispatch and agency acceptance/reject/return]
  D --> E[Define reconciliation, audit trail, permissions and integrations]
  E --> F[Design DocTypes/workflows/reports]
  F --> G[Implement after business approval and scenario tests]
```

No node after “confirm” is a claim about existing implementation. Decisions required in `06_CMR_READINESS_AND_ROADMAP.md`.
