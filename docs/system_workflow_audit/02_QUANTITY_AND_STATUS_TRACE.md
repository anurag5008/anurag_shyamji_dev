# 03: Quantity, Weight, and Status Trace Analysis

## 1. Physical Weighment Tracing (Weighbridge Scale to WBM)

### A. Load Weight, Tare Weight, and Gross Paddy Weight
- **Source File**: `apps/ivri_od/ivri_od/procurement/doctype/weigh_bridge_measurement/weigh_bridge_measurement.py`
- **Method**: `WeighBridgeMeasurement._update_weights()`, lines 724–738
- **Fields Involved**:
  - `load_weight` (Float): Gross weight of loaded vehicle on scale (QTL).
  - `tare_weight` (Float): Tare weight of empty vehicle after unloading (QTL).
  - `gross_weight` (Float): Gross weight of paddy delivered (QTL).
- **Exact Code Logic**:
  ```python
  load_weight = flt(self.load_weight)
  tare_weight = flt(self.tare_weight)

  if load_weight and tare_weight:
      self.gross_weight = load_weight - tare_weight
  elif load_weight:
      self.gross_weight = load_weight
  else:
      self.gross_weight = 0
  ```
- **Analysis**:
  - When both `load_weight` and `tare_weight` are positive: $\text{gross\_weight} = \text{load\_weight} - \text{tare\_weight}$.
  - When `tare_weight` is 0 or missing (first weighment): $\text{gross\_weight} = \text{load\_weight}$.
  - **Safety Gate**: In `_ensure_grn_note_for_weigh_bridge()` (line 854), automatic GRN Note creation is strictly blocked until `flt(tare_weight) > 0`. This prevents generating commercial GRNs with un-tared truck weights.

---

### B. Gunny Bag Tare Weight
- **Source File**: `weigh_bridge_measurement.py`
- **Methods**: `_resolve_gunny_weight_qt()`, lines 703–721; `_gunny_weight_from_bag_table()`, lines 686–701
- **Fields Involved**:
  - `gunny_type` (Select): `"Gunny Gross"` or `"Gunny Cut"`.
  - Child Table `Weigh Bridge Bag Detail`:
    - `jute_bags` (Int), `weight_per_jute_kg` (Float)
    - `plastic_bags` (Int), `weight_per_plastic_kg` (Float)
  - Manual override field: `Weigh Bridge Measurement.gunny_weight` (Float).
- **Exact Code Logic**:
  ```python
  if self.gunny_type == "Gunny Gross":
      self.total_jute_empty_qt = 0
      self.total_plastic_empty_qt = 0
      return 0.0

  table_qt = self._gunny_weight_from_bag_table()
  manual = flt(self.gunny_weight)
  if manual > 0:
      return manual
  return table_qt
  ```
- **Child Table Formula**:
  $$\text{jute\_total\_qt} = \text{flt}\left(\frac{\text{weight\_per\_jute\_kg} \times \text{jute\_bags}}{100}, 3\right)$$
  $$\text{plastic\_total\_qt} = \text{flt}\left(\frac{\text{weight\_per\_plastic\_kg} \times \text{plastic\_bags}}{100}, 3\right)$$
  $$\text{gunny\_weight\_qt} = \text{jute\_total\_qt} + \text{plastic\_total\_qt}$$
- **Precedence Rule**:
  1. If `gunny_type == "Gunny Gross"`, gunny tare is forced to **0.000 QTL**.
  2. If `gunny_type == "Gunny Cut"`, if manual `gunny_weight` was entered $> 0$, manual takes precedence; otherwise child table sum is used.

---

### C. Final Net Paddy Weight
- **Source File**: `weigh_bridge_measurement.py:734-738`
- **Formula**:
  $$\text{net\_weight} = \max(\text{flt}(\text{gross\_weight}) - \text{gunny\_weight} - \text{deduction}, 0)$$
- **Precision**: Rounded to 3 decimal places using `flt(..., 3)`.
- **Quality Rejection Override**:
  In `weigh_bridge_measurement.py:75-77`:
  ```python
  if self.quality_test == REJECTED_QC:
      self.net_weight = 0
  ```
  If Quality Check resulted in a full return (`paddy_returned >= paddy_received_in_pkt`), the net weight is forced to 0 regardless of scale readings.

---

## 2. Multi-GRN Cumulative Rollup and Transit Pass Fulfillment

### A. The Cumulative Calculation Engine
- **Source File**: `apps/ivri_od/ivri_od/procurement/grn_tp_fulfillment.py`
- **Function**: `_refresh_tp_fulfillment_for_pass(pass_unique_key: str)`, lines 279–353
- **Trigger**: Fired on `after_insert`, `on_update`, and `on_trash` of both `Weigh Bridge Measurement` and `GRN Note`.
- **Eligibility Conditions**:
  - `pass_unique_key == pass_unique_key`
  - `is_local_procurement == 0`
  - `docstatus < 2` (Includes Drafts `docstatus=0` and Submitted `docstatus=1`; excludes Cancelled `docstatus=2`).
- **Sorting Order**:
  ```python
  order_by="receipt_datetime asc, receipt_date asc, receipt_time asc, creation asc"
  ```
  Ensures running totals reflect true chronological trip order.
- **Accumulation Formulas**:
  $$\text{tp\_cumulative\_received}_{i} = \sum_{j=1}^{i} \text{GRN}_{j}\text{.net\_weight}$$
  $$\text{tp\_cumulative\_deduction}_{i} = \sum_{j=1}^{i} \text{GRN}_{j}\text{.deduction}$$

---

### B. Transit Pass Fulfillment Status Rules
- **Source File**: `grn_tp_fulfillment.py:50-65`
- **Function**: `tp_fulfillment_status(tp_qty: float, cumulative_net_received: float) -> str`
- **Classification Rules**:
  ```python
  tp_qty = flt(tp_qty)
  cumulative = flt(cumulative_net_received)
  if cumulative <= 0:
      return "Pending"
  if tp_qty > 0 and cumulative >= tp_qty:
      return "TP Completed"
  return "In Progress"
  ```
- **Remaining Quantity**:
  $$\text{pending\_qty} = \max(\text{tp\_quantity} - \text{cumulative\_net\_received}, 0.0)$$
- **Excess Quantity**:
  $$\text{excess\_qty} = \max(\text{cumulative\_net\_received} - \text{tp\_quantity}, 0.0)$$

---

## 3. Discrepancy Matrix: Controllers vs. Reports vs. Helper Functions

| Calculation Domain | `grn_tp_fulfillment.py` (`_refresh_tp_fulfillment_for_pass`) | `grn_tp_fulfillment.py` (`calculate_tp_status_for_pass`) | `mandi_book.py` (Report) | `abstract_physical.py` (Report) | `season_mapping.py` (`get_grn_paddy_procured`) |
|---|---|---|---|---|---|
| **Document Status Filter** | `docstatus < 2` | `docstatus == 1` | `docstatus < 2` | `docstatus < 2` | `docstatus < 2` |
| **Paddy Weight Source** | `GRN.net_weight` | `GRN.net_weight` | `GRN.net_weight` | `GRN.net_weight` | `GRN.net_weight + Entry.entry_quantity` |
| **Pass Grouping Key** | `pass_unique_key` | `pass_unique_key` | `pass_unique_key` | `(Season, PPC Master)` | Split `pass_unique_key` by `"-"` |
| **Over-Receipt Capping** | No cap (excess tracked) | No cap | No cap (excess tracked) | No cap | **Capped at TP quantity** (`pass_limits`) |
| **Chhatni Denominator** | `tp_qty` | N/A | `tp_qty` | `tp_qty - entry_qty` | N/A |
| **Working in Live DB?** | **YES** | **NO (Returns Pending)** | **YES** | **YES** | **YES** |

### Critical Takeaway:
`mandi_book.py`, `abstract_physical.py`, and `_refresh_tp_fulfillment_for_pass` share a consistent `docstatus < 2` filtering model. The lone outlier is `calculate_tp_status_for_pass`, which is why it fails against live data.
