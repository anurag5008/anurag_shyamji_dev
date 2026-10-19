# 03: Formulas, Calculations, and Tolerance Rules Audit

This document details every mathematical formula, unit conversion, tolerance threshold, and aggregation rule reverse-engineered from Python controllers, JavaScript form scripts, SQL queries, and report definitions in `ivri_od`.

---

## 1. Weight and Physical Measurement Formulas

### Formula 1.1: Gross Paddy Weight (`gross_weight`)
- **Business Purpose**: Calculate the weight of paddy delivered by a truck, before deducting gunny packaging and quality deductions.
- **Source DocTypes & Inputs**:
  - `Weigh Bridge Measurement.load_weight` (Gross truck weight in QTL)
  - `Weigh Bridge Measurement.tare_weight` (Empty truck weight in QTL)
- **Output Field**: `Weigh Bridge Measurement.gross_weight`, synced to `GRN Note.gross_weight`.
- **Unit of Measurement**: Quintals (QTL).
- **Rounding & Precision**: Frappe Float / Database Decimal(18, 3) (rounded to 3 decimals).
- **Exact Code Implementation**:
  ```python
  # weigh_bridge_measurement.py:724-733
  load_weight = flt(self.load_weight)
  tare_weight = flt(self.tare_weight)

  if load_weight and tare_weight:
      self.gross_weight = load_weight - tare_weight
  elif load_weight:
      self.gross_weight = load_weight
  else:
      self.gross_weight = 0
  ```
- **Null / Missing / Edge Cases**:
  - If `tare_weight` is missing or 0, `gross_weight = load_weight`!
  - *Audit Note*: In intermediate states prior to second weighment, `gross_weight` temporarily reflects total truck weight. Automatic GRN creation protects against this by strictly requiring `flt(tare_weight) > 0`.
- **Worked Synthetic Example**:
  - $\text{load\_weight} = 206.400\text{ QTL}$
  - $\text{tare\_weight} = 80.000\text{ QTL}$
  - $\text{gross\_weight} = 206.400 - 80.000 = 126.400\text{ QTL}$.

---

### Formula 1.2: Gunny Bag Tare Weight (`gunny_weight`)
- **Business Purpose**: Deduct the tare weight of empty packing bags (jute and plastic) from gross paddy weight.
- **Source DocTypes & Inputs**:
  - `Weigh Bridge Measurement.gunny_type` (`"Gunny Gross"` or `"Gunny Cut"`)
  - Child table `Weigh Bridge Bag Detail`:
    - `jute_bags` (Count of jute bags, Int)
    - `weight_per_jute_kg` (Tare weight per jute bag in Kg, Float)
    - `plastic_bags` (Count of plastic bags, Int)
    - `weight_per_plastic_kg` (Tare weight per plastic bag in Kg, Float)
  - Manual override field: `Weigh Bridge Measurement.gunny_weight` (Float).
- **Output Field**: `Weigh Bridge Measurement.gunny_weight`, synced to `GRN Note.gunny_weight`.
- **Unit Conversion Constant**:
  $$\text{KG\_PER\_QUINTAL} = 100$$
- **Exact Code Implementation**:
  ```python
  # weigh_bridge_measurement.py:158-165, 686-720
  def _gunny_weight_from_bag_table(self) -> float:
      total_jute = 0.0
      total_plastic = 0.0
      for row in self.bag_weight_details or []:
          jute_qt = flt(flt(row.weight_per_jute_kg) * cint(row.jute_bags) / 100, 3)
          plastic_qt = flt(flt(row.weight_per_plastic_kg) * cint(row.plastic_bags) / 100, 3)
          row.jute_total_qt = _trim_qty(jute_qt)
          row.plastic_total_qt = _trim_qty(plastic_qt)
          row.gunny_weight_qt = _trim_qty(jute_qt + plastic_qt)
          total_jute += jute_qt
          total_plastic += plastic_qt
      self.total_jute_empty_qt = flt(total_jute, 3)
      self.total_plastic_empty_qt = flt(total_plastic, 3)
      return flt(total_jute + total_plastic, 3)

  # Resolution precedence:
  if self.gunny_type == "Gunny Gross":
      return 0.0
  manual = flt(self.gunny_weight)
  if manual > 0:
      return manual
  return table_qt
  ```
- **Worked Synthetic Example**:
  - `gunny_type` = "Gunny Cut"
  - `jute_bags` = 0
  - `plastic_bags` = 250
  - `weight_per_plastic_kg` = 0.400 kg/bag
  - $\text{plastic\_weight\_kg} = 250 \times 0.400 = 100\text{ kg}$
  - $\text{plastic\_total\_qt} = \frac{100\text{ kg}}{100\text{ kg/QTL}} = 1.000\text{ QTL}$
  - $\text{gunny\_weight} = 1.000\text{ QTL}$.

---

### Formula 1.3: Final Net Paddy Weight (`net_weight`)
- **Business Purpose**: Compute the official net received quantity of paddy credited to the government transit pass.
- **Source DocTypes & Inputs**:
  - `gross_weight` (QTL)
  - `gunny_weight` (QTL)
  - `deduction` (Quality/refraction deduction entered on WBM/RST in QTL)
- **Output Field**: `Weigh Bridge Measurement.net_weight`, synced to `GRN Note.net_weight`.
- **Unit of Measurement**: Quintals (QTL).
- **Exact Code Implementation**:
  ```python
  # weigh_bridge_measurement.py:734-738
  self.gunny_weight = flt(self._resolve_gunny_weight_qt(), 3)
  gunny_weight = flt(self.gunny_weight)
  deduction = flt(self.deduction)
  self.net_weight = flt(max(flt(self.gross_weight) - gunny_weight - deduction, 0), 3)
  ```
- **Worked Synthetic Example**:
  - $\text{gross\_weight} = 126.400\text{ QTL}$
  - $\text{gunny\_weight} = 1.000\text{ QTL}$
  - $\text{deduction} = 5.400\text{ QTL}$
  - $\text{net\_weight} = \max(126.400 - 1.000 - 5.400, 0) = 120.000\text{ QTL}$.

---

## 2. Transit Pass Fulfillment Formulas

### Formula 2.1: Canonical TP Fulfillment Status
- **Business Purpose**: Determine whether a Transit Pass is pending, in progress, or completely delivered across all linked GRNs.
- **Source Function**: `tp_fulfillment_status(tp_qty, cumulative_net_received)`.
- **Inputs**:
  - `tp_qty`: Stored transit pass quota in QTL.
  - `cumulative_net_received`: Sum of `net_weight` from all non-cancelled GRNs for this pass.
- **Output**: String status (`"Pending"`, `"In Progress"`, `"TP Completed"`).
- **Exact Code Implementation**:
  ```python
  # grn_tp_fulfillment.py:50-65
  def tp_fulfillment_status(tp_qty: float, cumulative_net_received: float) -> str:
      tp_qty = flt(tp_qty)
      cumulative = flt(cumulative_net_received)
      if cumulative <= 0:
          return "Pending"
      if tp_qty > 0 and cumulative >= tp_qty:
          return "TP Completed"
      return "In Progress"
  ```
- **Threshold Rule**:
  - $\text{cumulative} \le 0 \implies \mathbf{Pending}$
  - $0 < \text{cumulative} < \text{tp\_qty} \implies \mathbf{In\ Progress}$
  - $\text{cumulative} \ge \text{tp\_qty} \implies \mathbf{TP\ Completed}$

---

### Formula 2.2: Pending and Excess TP Quantities
- **Pending TP Quantity**:
  $$\text{pending\_tp\_quantity} = \max(\text{tp\_quantity} - \text{cumulative\_net\_received}, 0.0)$$
  *(Code: `grn_tp_fulfillment.py:117-129`)*
- **Excess TP Received Quantity**:
  $$\text{excess\_tp\_received\_quantity} = \max(\text{cumulative\_net\_received} - \text{tp\_quantity}, 0.0)$$
  *(Code: `grn_tp_fulfillment.py:131-138`)*
- **Worked Synthetic Example**:
  - Scenario A (Under-delivery):
    - $\text{tp\_quantity} = 250.000\text{ QTL}$
    - $\text{cumulative\_net\_received} = 180.000\text{ QTL}$
    - $\text{pending\_qty} = 250.000 - 180.000 = 70.000\text{ QTL}$
    - $\text{excess\_qty} = 0.000\text{ QTL}$
    - $\text{status} = \mathbf{In\ Progress}$.
  - Scenario B (Exact delivery):
    - $\text{cumulative\_net\_received} = 250.000\text{ QTL}$
    - $\text{pending\_qty} = 0.000\text{ QTL}$, $\text{excess\_qty} = 0.000\text{ QTL}$
    - $\text{status} = \mathbf{TP\ Completed}$.
  - Scenario C (Over-delivery):
    - $\text{cumulative\_net\_received} = 262.500\text{ QTL}$
    - $\text{pending\_qty} = 0.000\text{ QTL}$
    - $\text{excess\_qty} = 262.500 - 250.000 = 12.500\text{ QTL}$
    - $\text{status} = \mathbf{TP\ Completed}$.

---

## 3. Chhatni Calculations and Tolerance Rules

### Formula 3.1: Required Chhatni Quantity
- **Formula**:
  $$\text{required\_chhatni\_qtl} = \frac{\text{tp\_qty} \times \text{chhatni\_percentage}}{100}$$
  *(Code: `grn_tp_fulfillment.py:24-27`, rounded to 3 decimals)*.

---

### Formula 3.2: Received Chhatni Percentage
- **Formula**:
  $$\text{received\_chhatni\_pct} = \begin{cases} 0.0 & \text{if } \text{tp\_qty} \le 0 \text{ or } \text{received\_qty} \le \text{tp\_qty} \\ \left( \frac{\text{received\_qty} - \text{tp\_qty}}{\text{tp\_qty}} \right) \times 100 & \text{if } \text{received\_qty} > \text{tp\_qty} \end{cases}$$
  *(Code: `grn_tp_fulfillment.py:29-36`, rounded to 2 decimals)*.

---

### Formula 3.3: Chhatni Tolerance and Status Decision Logic
- **Tolerance Limit**:
  $$\text{CHHATNI\_TOLERANCE\_PCT} = 0.30\text{ percentage points}$$
- **Bounds**:
  $$\text{lower\_bound} = \text{assigned\_pct} - 0.30$$
  $$\text{upper\_bound} = \text{assigned\_pct} + 0.30$$
- **Decision Engine** (`calculate_chhatni_metrics`, `grn_tp_fulfillment.py:140-210`):
  1. If $\text{tp\_qty} \le 0 \implies \mathbf{Chhatni\ Not\ Received}$ (Remark: `"Transit pass (TP) quantity is missing or zero."`)
  2. If $\text{chhatni\_rate} \le 0 \implies \mathbf{Chhatni\ Pending}$ (Remark: `"Assigned chhatni rate is not set."`)
  3. If $\text{actual\_pct} > \text{upper\_bound} + 10^{-6} \implies \mathbf{Extra\ Chhatni\ Received}$
  4. If $\text{lower\_bound} - 10^{-6} \le \text{actual\_pct} \le \text{upper\_bound} + 10^{-6} \implies \mathbf{Chhatni\ Received}$
  5. If $\text{actual\_pct} < \text{lower\_bound} - 10^{-6} \implies \mathbf{Chhatni\ Not\ Received}$
- **Precondition Blocker**:
  If $\text{cumulative\_received} < \text{tp\_qty}$, Chhatni cannot be evaluated:
  `"Chhatni cannot be calculated because the transit pass (TP) quantity is not fully received yet."`
- **Worked Synthetic Examples**:
  Assume $\text{tp\_qty} = 300.000\text{ QTL}$, Assigned Chhatni Rate = $4.00\%$ ($4.0\text{ kg/QTL}$).
  Lower bound = $3.70\%$, Upper bound = $4.30\%$.
  - **Case 1 (In Progress)**: Cumulative received = $290.000\text{ QTL}$.
    $\implies$ TP not filled $\implies \mathbf{Chhatni\ Not\ Received}$.
  - **Case 2 (Under-delivered Chhatni)**: Cumulative received = $309.000\text{ QTL}$.
    $\text{actual\_pct} = \frac{309 - 300}{300} \times 100 = 3.00\%$.
    $3.00\% < 3.70\% \implies \mathbf{Chhatni\ Not\ Received}$ (Shortfall).
  - **Case 3 (Within Tolerance)**: Cumulative received = $312.000\text{ QTL}$.
    $\text{actual\_pct} = \frac{312 - 300}{300} \times 100 = 4.00\%$.
    $3.70\% \le 4.00\% \le 4.30\% \implies \mathbf{Chhatni\ Received}$.
  - **Case 4 (Extra Chhatni)**: Cumulative received = $314.000\text{ QTL}$.
    $\text{actual\_pct} = \frac{314 - 300}{300} \times 100 = 4.67\%$.
    $4.67\% > 4.30\% \implies \mathbf{Extra\ Chhatni\ Received}$.

---

## 4. Entry DocType Formulas

### Formula 4.1: Farmer Direct Purchase Total Amount
- **Formula**:
  $$\text{total\_amount} = \text{entry\_quantity} \times \text{entry\_price\_per\_quintal}$$
  *(Code: `entry.py:133-134`)*.
- **Worked Example**:
  $\text{entry\_quantity} = 50.000\text{ QTL}$, $\text{entry\_price} = ₹2,300.00/\text{QTL}$.
  $\text{total\_amount} = 50.0 \times 2300.0 = ₹115,000.00$.

### Formula 4.2: Available Entry Quota Validation
- **Formula**:
  $$\text{available} = \max(\text{tp\_quantity} - \sum \text{other\_entry\_quantity} - \sum \text{grn\_net\_weight}, 0)$$
  *(Code: `entry.py:111-125`)*.
- Throws validation exception if new $\text{entry\_quantity} > \text{available}$.

---

## 5. Season Mapping & CMR-Adjacent Formulas

### Formula 5.1: Proportional Paddy Procured
- **Formula**:
  $$\text{paddy\_procured\_till\_date} = \text{flt}\left(\text{paddy\_procured} \times \frac{\text{paddy\_proportion}}{100}, 3\right)$$
  *(Code: `season_mapping.py:68-70`)*.
- Where `paddy_procured` is calculated by `get_grn_paddy_procured()`, which aggregates:
  $$\text{paddy\_procured} = \sum_{\text{pass}} \min(\text{net\_weight} + \text{entry\_quantity}, \text{tp\_limit})$$

### Formula 5.2: Rice Due Till Date (CMR Calculation)
- **Formula**:
  $$\text{rice\_due\_till\_date} = \frac{\text{paddy\_procured\_till\_date}}{100} \times \text{rice\_yield}$$
  *(Code: `season_mapping.py:71`)*.
- **Unit**: Quintals of Custom Milled Rice (CMR).
- **Semantics**: For raw rice with standard statutory outturn ratio $67\%$, each 100 QTL of paddy generates 67 QTL of CMR due to OSCSC/FCI.

### Formula 5.3: Remaining Rice Target Balance
- **Formula**:
  $$\text{remaining\_balance} = \left( \frac{\text{season\_quantity}}{100} \times \text{rice\_yield} \times \frac{\text{paddy\_proportion}}{100} \right) - \text{rice\_due\_till\_date}$$
  *(Code: `season_mapping.py:72-79`)*.
- **Worked Synthetic Example**:
  - `season_quantity` (Target Paddy) = $5,000.000\text{ QTL}$
  - `paddy_proportion` = $20.0\%$
  - `rice_yield` = $67.0\%$
  - Target Paddy Allocated to Collection Point = $5000 \times 0.20 = 1,000.000\text{ QTL}$
  - Allocated CMR Rice Quota = $1000 \times 0.67 = 670.000\text{ QTL}$
  - If `paddy_procured` = $600.000\text{ QTL}$:
    - `paddy_procured_till_date` = $600 \times 0.20 = 120.000\text{ QTL}$
    - `rice_due_till_date` = $120.000 \times \frac{67}{100} = 80.400\text{ QTL}$ CMR Due
    - `remaining_balance` = $670.000 - 80.400 = 589.600\text{ QTL}$ CMR Remaining.

---

## 6. Report Specific Mathematical Divergences

### Divergence 6.1: Abstract Physical Chhatni Percentage Denominator
In `abstract_physical.py:253-257`:
$$\text{denom} = \text{tp\_quantity} - \text{entry\_qty}$$
$$\text{chhatni\_pct} = \begin{cases} \left( \frac{\text{chhatni\_quantity}}{\text{denom}} \right) \times 100 & \text{if } \text{denom} > 0 \\ 0.0 & \text{otherwise} \end{cases}$$
- **Discrepancy with Canonical Controller**:
  In `grn_tp_fulfillment.py`, the denominator for received Chhatni percentage is solely $\text{tp\_qty}$. In `Abstract Physical`, direct farmer purchase (`entry_qty`) is deducted from `tp_qty` before calculating the Chhatni percentage ratio.
