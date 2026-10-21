# 04: Chhatni Rules, Tolerance, and Calculation Validation

## 1. Executive Summary & Verification Scope

In Odisha paddy procurement, **Chhatni** (छटनी / Deduction/Excess adjustment) represents the excess paddy received from Primary Agricultural Credit Societies (PACS) / Paddy Procurement Centres (PPC) to compensate for foreign matter, moisture, or milling losses, or conversely, deductions imposed.

This audit validates the exact business formulas, field semantics, tolerance limits, denominator selection, deduction interactions, and report implementations across the codebase and database on site `shyamji`.

---

## 2. Field Semantics: `chutney_percentage` vs `chutney_quantity_kg_per_quintal`

### Code Implementation (`chhatni_assign.py`)
In `apps/ivri_od/ivri_od/procurement/doctype/chhatni_assign/chhatni_assign.py` lines 10–14:
```python
def validate(self):
    kg = flt(self.chutney_quantity_kg_per_quintal)
    self.chutney_quantity_kg_per_quintal = kg
    # 1 quintal = 100 kg → kg per quintal equals percentage of total weight
    self.chutney_percentage = kg
```

### Business Interpretation
- **1 Quintal (QTL) = 100 Kilograms (KG)**.
- Therefore, $X\text{ kg per quintal} = \frac{X\text{ kg}}{100\text{ kg}} \times 100\% = X\%$.
- The two fields are **numerically and mathematically identical**.
- **Historical Typo in Schema**: The field is named `chutney_percentage` and `chutney_quantity_kg_per_quintal` in DocType `Chhatni Assign` and `Target Allocation` (colloquial spelling of "Chhatni").

---

## 3. Tolerance Rules: Percentage-Point Enforcement

### Code Constant & Definition (`grn_tp_fulfillment.py`)
In `apps/ivri_od/ivri_od/procurement/grn_tp_fulfillment.py` lines 16–17 & 179–198:
```python
# Chhatni tolerance in percentage points (0.30% point).
CHHATNI_TOLERANCE_PCT = 0.30
```

### Mathematical Enforcement
The tolerance is strictly evaluated as **absolute percentage points**, NOT a relative percentage of the assigned rate:
$$\text{Lower Bound} = \text{Assigned Rate} - 0.30$$
$$\text{Upper Bound} = \text{Assigned Rate} + 0.30$$

#### Numerical Example:
If assigned Chhatni is **2.50 kg/QTL (2.50%)**:
- **Acceptable Window**: $2.50\% \pm 0.30\% \implies [2.20\%, 2.80\%]$
- If Actual Received Excess % $\in [2.20\%, 2.80\%]$: Status = **`Chhatni Received`**
- If Actual Received Excess % $> 2.80\%$: Status = **`Extra Chhatni Received`**
- If Actual Received Excess % $< 2.20\%$: Status = **`Chhatni Not Received`**

### Where Enforced
1. **At Controller / Database level**: `calculate_chhatni_metrics()` in `grn_tp_fulfillment.py` during `refresh_tp_fulfillment_for_pass()`. Stored in `tabGRN Note.chhatni_fulfillment_status`.
2. **At Report level**: `apps/ivri_od/ivri_od/procurement/report/mandi_book/mandi_book.py` lines 230–243.
3. **Hard-coded Limitation**: `CHHATNI_TOLERANCE_PCT` is hard-coded in Python. There is currently no master configuration table or UI setting to adjust this threshold per season or mill.

---

## 4. Denominator Divergence: Transit Pass Quantity vs Net Quantity

A major discrepancy exists in how received Chhatni percentage is calculated across controllers and reports:

### Controller & Mandi Book Implementation (`grn_tp_fulfillment.py` & `mandi_book.py`)
```python
def received_chhatni_pct(received_qty: float, tp_qty: float) -> float:
    """Received Chhatni % = max(0, ((Total Qty Received - TP Qty) / TP Qty) * 100)."""
    if tp_qty <= 0 or received_qty <= tp_qty:
        return 0.0
    return flt(((received_qty - tp_qty) / tp_qty) * 100.0, 2)
```
- **Denominator**: `tp_qty` (Total Transit Pass Quantity).
- **Formula**:
  $$\text{Actual Chhatni \%} = \frac{\text{Cumulative Received} - \text{TP Qty}}{\text{TP Qty}} \times 100$$

### Abstract Physical Report Implementation (`abstract_physical.py`)
In `apps/ivri_od/ivri_od/procurement/report/abstract_physical/abstract_physical.py` lines 253–257:
```python
denom = tp_qty - entry_qty
if denom > 0:
    chhatni_pct = flt((chhatni_qty / denom) * 100.0, 2)
else:
    chhatni_pct = 0.0
```
- **Denominator**: `(tp_qty - entry_qty)`.
- `entry_qty` represents direct local Mandi/Entry records.
- **Divergence Impact**: If local `entry_qty > 0`, the denominator in Abstract Physical shrinks, yielding a **higher computed Chhatni percentage** than shown on the GRN Note and Mandi Book for the exact same physical delivery.

---

## 5. Critical Logic Flaw: Double-Deduction in Chhatni Balance

### Analysis of Weight & Deduction Lineage
1. In `GRN Note._update_weights()`:
   $$\text{net\_weight} = \text{gross\_weight} - \text{gunny\_weight} - \text{deduction}$$
2. In `grn_tp_fulfillment.py:324–326`:
   ```python
   received = grn_received_quantity(doc)  # returns doc.net_weight
   cumulative = flt(cumulative + received, 3)
   deduction_sum = flt(deduction_sum + flt(doc.deduction), 3)
   ```
   Here, `cumulative` is the sum of `net_weight`, which **has ALREADY subtracted `deduction`**.
3. In `grn_tp_fulfillment.py:38–47` (`tp_chhatni_balance_qt`):
   ```python
   def tp_chhatni_balance_qt(tp_qty: float, cumulative_received: float, total_deduction: float) -> float:
       value = flt(cumulative_received) - tp_qty - flt(total_deduction)
       return flt(max(value, 0), 3)
   ```

### Defect Demonstration:
- Let TP Quantity = $100.00\text{ QTL}$.
- Delivered Paddy (Gross less Gunny) = $105.00\text{ QTL}$.
- QC Quality Deduction = $2.00\text{ QTL}$.
- **Expected Net Paddy**: $103.00\text{ QTL}$.
- **Expected Excess/Chhatni Physical Balance**: $103.00 - 100.00 = 3.00\text{ QTL}$.
- **Actual Code Calculation**:
  $$\text{value} = \text{cumulative}(103.00) - \text{tp\_qty}(100.00) - \text{total\_deduction}(2.00) = 1.00\text{ QTL}$$
- **Impact**: The quality deduction is **subtracted twice**, reducing the stored Chhatni balance by an additional $2.00\text{ QTL}$.

---

## 6. Historical Rate Locking vs Dynamic Recalculation

### GRN Note Controller Behavior (`grn_note.py`)
In `apps/ivri_od/ivri_od/procurement/doctype/grn_note/grn_note.py` lines 103–104:
```python
if self.is_new():
    self._sync_chhatni_from_season_mapping()
```
- **Historical Lock on Document**: When a GRN Note is first inserted, `self.chhatni` is fetched from `Season Mapping` and saved on the record.
- If `Season Mapping` or `Chhatni Assign` is modified later, existing GRN records **retain their original `chhatni` field value**.

### Dynamic Rollup Overwrite (`refresh_tp_fulfillment_for_pass`)
In `grn_tp_fulfillment.py` lines 332–348:
```python
doc_chhatni = flt(doc.chhatni) or max((flt(r.chhatni) for r in rows), default=0.0)
chhatni_status, chhatni_remark = evaluate_chhatni_fulfillment(
    tp_qty,
    cumulative,
    doc_chhatni,
    deduction_sum,
)
```
- While the base assigned rate (`chhatni`) remains intact on each row, the fulfillment status (`chhatni_fulfillment_status`, `tp_chhatni_balance`, `chhatni_received_pct`) is **dynamically recalculated** whenever any GRN on the pass is saved or updated.
- In `mandi_book.py`, `_assigned_chhatni()` selects the rate from the document where `tp_fulfillment_status == 'TP Completed'`, or the maximum rate across all sibling GRNs.

---

## 7. Business Logic Matrix: Implementation vs Required Approvals

| Aspect | Current Implemented Code | Standard Odisha Food Supplies Rule | Status / Action Needed |
| :--- | :--- | :--- | :--- |
| **Rate Definition** | 1 kg/QTL = 1.0% | 1 kg/QTL = 1.0% | **Confirmed Consistent** |
| **Tolerance Limit** | Fixed $\pm 0.30$ percentage points | Varies by government order / season | **Business Decision Required**: Needs configurable parameter in Season Master or Procurement Settings |
| **Denominator** | Total TP Quantity (`tp_qty`) | Net TP Quantity delivered | **Confirmed Consistent in Procurement**; Abstract Physical discrepancy must be reconciled |
| **Deduction Impact** | Double-subtracted in `tp_chhatni_balance` | Deductions reduce gross paddy to net paddy once | **Confirmed Logic Defect**: Formula in `tp_chhatni_balance_qt` should be `cumulative_received - tp_qty` |
| **Chhatni Value in CMR** | Stored on GRN, unlinked to CMR | Affects Paddy Out-Turn Ratio (OTR) calculations | **Pending CMR Module Design** |
