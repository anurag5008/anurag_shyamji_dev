# 04: Relationships and Data Lineage Specification

## 1. DocType Relationship Dependency Map

This map defines every explicit relationship between DocTypes in `ivri_od`, categorizing each as:
- **`[DECLARED IN METADATA]`**: Defined as a Link or Table field in checked-in DocType JSON schemas.
- **`[CODE-POPULATED]`**: Dynamically resolved and set via Python controller logic or JavaScript form scripts.
- **`[BUSINESS TEXT KEY]`**: Linked through composite string identifiers (e.g. `pass_unique_key`, `rst_no`, vehicle number) rather than native foreign key ID pointers.

---

### A. Core Operational Relationships

```
Source DocType.fieldname                           -> Target DocType.name                    [Type / Evidence]
-----------------------------------------------------------------------------------------------------------------
Agent Master.district                              -> District Master.name                   [DECLARED IN METADATA]
Chhatni Assign.ppc_name                            -> PPC Master.name                        [DECLARED IN METADATA]
Chhatni Assign.mill_name                           -> Mill Master.name                       [DECLARED IN METADATA]
Chhatni Assign.season                              -> Season Master.name                     [DECLARED IN METADATA]
Chhatni Assign.chhatni_history                     -> Chhatni Assign History (child)         [DECLARED IN METADATA]
Chhatni Assign History.changed_by                  -> User.name                              [DECLARED IN METADATA]

Daily Planning.ppc_name                            -> PPC Master.name                        [DECLARED IN METADATA]
Daily Planning.season_name                         -> Season Master.name                     [DECLARED IN METADATA]

Entry.season                                       -> Season Master.name                     [DECLARED IN METADATA]
Entry.ppc_name                                     -> PPC Master.name                        [DECLARED IN METADATA]
Entry.pass_unique_key                              -> PPAS Transit Pass.pass_unique_key      [BUSINESS TEXT KEY / CODE-POPULATED]

Gate Entry.gate_entry_in                           -> Gate Entry.name                        [DECLARED IN METADATA]
Gate Entry.vehicle_no                              -> (Physical truck identifier)            [NORMALIZED STRING]

Gate Exit.gate_entry_in                            -> Gate Entry.name                        [DECLARED IN METADATA]
Gate Exit.vehicle_no                               -> Gate Entry.vehicle_no                  [CODE-POPULATED / VALIDATED]

Mill Master.district                               -> District Master.name                   [DECLARED IN METADATA]
Mill Master.mill_codes                             -> Mill Code Detail (child)               [DECLARED IN METADATA]

PPC Master.district                                -> District Master.name                   [DECLARED IN METADATA]
PPC Master.society                                 -> Society Master.name                    [DECLARED IN METADATA]
PPC Master.agent                                   -> Agent Master.name                      [DECLARED IN METADATA]

Quality Check.gate_entry                           -> Gate Entry.name                        [DECLARED IN METADATA]
Quality Check.vehicle_no                           -> Gate Entry.vehicle_no                  [CODE-POPULATED / VALIDATED]
Quality Check.type_of_pkt                          -> Quality Check Bag Detail (child)       [DECLARED IN METADATA]
Quality Check.old_new_bags                         -> Quality Check Old New Bag Detail (ch)  [DECLARED IN METADATA]

RST Details.weigh_bridge_measurement              -> Weigh Bridge Measurement.name          [DECLARED IN METADATA]
RST Details.local_purchase_order                   -> Local Paddy Purchase Order.name        [DECLARED IN METADATA - DISABLED]
RST Details.pass_unique_key                        -> PPAS Transit Pass.pass_unique_key      [BUSINESS TEXT KEY / CODE-POPULATED]

Season Mapping.season                              -> Season Master.name                     [DECLARED IN METADATA]
Season Mapping.ppc_name                            -> PPC Master.name                        [DECLARED IN METADATA]
Season Mapping.mill_name                           -> Mill Master.name                       [DECLARED IN METADATA]
Season Mapping.collection_point_details            -> Season Mapping Collection Point (ch)   [DECLARED IN METADATA]

Target Allocation.season                           -> Season Master.name                     [DECLARED IN METADATA]
Target Allocation.ppc_name                         -> PPC Master.name                        [DECLARED IN METADATA]
Target Allocation.mill_name                        -> Mill Master.name                       [DECLARED IN METADATA]
Target Allocation.latest_chutney_assign            -> Chhatni Assign.name                    [DECLARED IN METADATA]
Target Allocation.agent_details                    -> Target Allocation Agent (child)        [DECLARED IN METADATA]

Weigh Bridge Measurement.gate_entry                -> Gate Entry.name                        [DECLARED IN METADATA]
Weigh Bridge Measurement.quality_check             -> Quality Check.name                     [DECLARED IN METADATA]
Weigh Bridge Measurement.demo_rst_data             -> RST Details.name                       [DECLARED IN METADATA]
Weigh Bridge Measurement.pass_unique_key           -> PPAS Transit Pass.pass_unique_key      [BUSINESS TEXT KEY / LINK IN METADATA]
Weigh Bridge Measurement.bag_weight_details        -> Weigh Bridge Bag Detail (child)        [DECLARED IN METADATA]

GRN Note.weigh_bridge_measurement                  -> Weigh Bridge Measurement.name          [DECLARED IN METADATA]
GRN Note.quality_check                             -> Quality Check.name                     [DECLARED IN METADATA]
GRN Note.gate_entry                                -> Gate Entry.name                        [DECLARED IN METADATA]
GRN Note.gate_exit                                 -> Gate Exit.name                         [DECLARED IN METADATA]
GRN Note.pass_unique_key                           -> PPAS Transit Pass.pass_unique_key      [BUSINESS TEXT KEY / LINK IN METADATA]
GRN Note.entry_details                             -> GRN Entry Detail (child)               [DECLARED IN METADATA]
GRN Note.qc_bag_details                            -> Quality Check Bag Detail (child copy)  [DECLARED IN METADATA]
GRN Note.old_new_bags                              -> Quality Check Old New Bag Detail (cp)  [DECLARED IN METADATA]
```

---

## 2. Structural Dependencies and Data Integrity Hazards

### A. The "Pass Unique Key" Business Identifier
Rather than linking records by Frappe document primary keys (`name`), the procurement workflow joins documents across modules using the composite string **`pass_unique_key`**:
$$\text{\{miller\_code\}-\{ppc\_name(ppc\_code)\}-\{season\_code\}-TP\{transit\_pass\_no\}}$$
- **Risk**: Any variation in spacing, uppercase/lowercase, parenthesis formatting, or season abbreviation (e.g., `Kharif 2025` vs `K25` vs `Kharif(2025)`) breaks resolution unless normalized by helper functions.
- **Mitigation in Code**: `ivri_od` implements heavy normalization layers (`transit_pass_resolve.py`, `pass_unique_key.py`, `ppc_pass_metrics.py`), but raw SQL joins in reports still risk dropping rows if format deviates.

### B. Denormalized and Stale Copied Fields
`GRN Note` copies over 25 fields from upstream documents (`gross_weight`, `tare_weight`, `gunny_weight`, `moisture`, `dust`, `unloader_name`, `arrival_datetime`, etc.):
- **Risk**: If an upstream `Quality Check` or `Weigh Bridge Measurement` is amended or modified after GRN insertion, the GRN becomes out of sync unless explicitly re-saved or refreshed via `sync_grn_from_weigh_bridge()`.
- **Chhatni Rate Invariance**: While weight fields are refreshed via `sync_grn_from_weigh_bridge()`, the `chhatni` rate is intentionally locked on initial insert (`if self.is_new()`) to preserve the historical contractual rate.

### C. Circular Trigger Paths
- `RST Details.on_update` creates/updates `Weigh Bridge Measurement`.
- `Weigh Bridge Measurement.after_insert` / `on_update` creates/updates `GRN Note`.
- `GRN Note.on_update` triggers `refresh_tp_fulfillment_for_pass()`, which performs raw SQL writes (`db.set_value(..., update_modified=False)`) back to all peer GRNs on the same pass.
- System guards against infinite loops using thread-local flags:
  ```python
  frappe.local._refreshing_tp_pass = key
  frappe.local.syncing_grn_from_wbm = wbm_name
  ```

---

## 3. Backward Data Lineage for Key Report Metrics

### Metric 1: Mandi Book — `Total Qty Received`
$$\text{Total Qty Received} \longleftarrow \sum \text{grn\_received\_quantity(doc)}$$
- **Originating Field**: `GRN Note.net_weight` (or `GRN Note.received_quantity`).
- **Source DocType**: `GRN Note` where `is_local_procurement == 0` and `docstatus < 2`.
- **Originating Calculation**: Computed in `Weigh Bridge Measurement._update_weights()`:
  $$\text{net\_weight} = \max((\text{load\_weight} - \text{tare\_weight}) - \text{gunny\_weight} - \text{deduction}, 0)$$
- **Originating Event**: Second weighment of empty truck on weighbridge.

---

### Metric 2: Mandi Book — `TP Status`
$$\text{TP Status} \longleftarrow \text{tp\_fulfillment\_status(tp\_qty, total\_received)}$$
- **Originating Fields**:
  - `tp_qty`: Stored `PPAS Transit Pass.quantity`.
  - `total_received`: Chronological sum of `GRN Note.net_weight` for all non-cancelled GRNs matching `pass_unique_key`.
- **Classification Engine**: `grn_tp_fulfillment.py:50-65`:
  - $0 \implies \mathbf{Pending}$
  - $0 < \text{received} < \text{tp\_qty} \implies \mathbf{In\ Progress}$
  - $\text{received} \ge \text{tp\_qty} \implies \mathbf{TP\ Completed}$.

---

### Metric 3: Mandi Book — `Chhatni Status`
$$\text{Chhatni Status} \longleftarrow \text{evaluate\_chhatni\_fulfillment(tp\_qty, total\_received, chhatni\_assigned, total\_deduction)}$$
- **Originating Fields**:
  - `chhatni_assigned`: `GRN Note.chhatni`, originating from `Chhatni Assign.chutney_quantity_kg_per_quintal` through `Target Allocation` and `Season Mapping`.
  - `total_received`: Cumulative GRN net weight.
  - `tp_qty`: `PPAS Transit Pass.quantity`.
- **Originating Engine**: Evaluated when $\text{total\_received} \ge \text{tp\_qty}$ against threshold $\pm 0.30$ percentage points.

---

### Metric 4: Abstract Physical — `Chhatni %`
$$\text{Chhatni \%} \longleftarrow \left( \frac{\text{Chhatni Quantity (Mandi Excess)}}{\text{TP Quantity} - \text{Entry Qty}} \right) \times 100$$
- **Originating Fields**:
  - `Chhatni Quantity`: Sum of `excess_received_qty` from `mandi_book.py` across all TPs for this PPC in the season.
  - `TP Quantity`: Sum of `PPAS Transit Pass.quantity` for the PPC in the season.
  - `Entry Qty`: Sum of direct farmer purchase records from `Entry.entry_quantity`.
- **Originating DocTypes**: `PPAS Transit Pass`, `GRN Note`, `Entry`.
- **Note on Lineage Divergence**: This metric is an aggregate ratio across the entire PPC, whereas Mandi Book evaluates Chhatni pass-by-pass.

---

### Metric 5: Abstract Report — `Mill Target, Received, and Balance`
For each Mill column:
$$\text{Target} = \text{Target Allocation.target\_quantity}$$
$$\text{Received} = \sum_{\text{pass}} \min(\text{GRN.net\_weight}, \text{TP.quantity})$$
$$\text{Balance} = \text{Target} - \text{Received}$$
- **Originating DocTypes**: `Target Allocation`, `PPAS Transit Pass`, `GRN Note`, `Season Mapping`.
- **Cross-Verification**: Matches the business Excel matrix structure used by mill management for tracking fulfillment against government allocation orders.
