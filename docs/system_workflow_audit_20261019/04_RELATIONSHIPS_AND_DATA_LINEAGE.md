# Relationships and data lineage

## Exact declared links / child tables (checked-in DocType metadata)

Full Link/Table fields, exact fieldname, target options and child field definitions are in `01_DOCTYPE_INVENTORY.md`. Declared relationships verified directly from JSON include:

- `Mill Master.company -> Company.name`
- `PPC Master.district -> District Master.name`; `PPC Master.agent -> Agent Master.name`
- `Target Allocation.season -> Season Master.name`; `.ppc_name -> PPC Master.name`; `.mill_name -> Mill Master.name`; `.agent_details -> Target Allocation Agent` (Table); child `Target Allocation Agent.agent_name -> Agent Master.name`; `.latest_chutney_assign -> Chhatni Assign.name`
- `Season Mapping.season -> Season Master.name`; `.ppc_name -> PPC Master.name`; `.mill_name -> Mill Master.name`; `.collection_point_details -> Season Mapping Collection Point` (Table)
- `PPAS Transit Pass Import.season -> Season Master.name`; `.import_items -> PPAS Transit Pass Import Item` (Table). `PPAS Transit Pass` itself has no declared Link fields in checked-in JSON; its `pass_unique_key` is its document name (`autoname: field:pass_unique_key`).
- `RST Details.agent_name -> Agent Master.name`; `.local_purchase_order -> Local Paddy Purchase Order.name`; `.weigh_bridge_measurement -> Weigh Bridge Measurement.name`
- `Gate Exit.gate_entry_in -> Gate Entry.name`; `Gate Entry.gate_entry_in -> Gate Entry.name` (self-link field per metadata)
- `Quality Check.gate_entry -> Gate Entry.name`; `.type_of_pkt -> Quality Check Bag Detail` (Table); `.old_new_bags -> Quality Check Old New Bag Detail` (Table)
- `Weigh Bridge Measurement.demo_rst_data -> RST Details.name`; `.agent_name -> Agent Master.name`; `.local_purchase_order -> Local Paddy Purchase Order.name`; `.quality_check -> Quality Check.name`; `.gate_entry -> Gate Entry.name`; `.bag_weight_details -> Weigh Bridge Bag Detail` (Table)
- `GRN Note.gate_entry -> Gate Entry.name`; `.gate_exit -> Gate Exit.name`; `.agent_name -> Agent Master.name`; `.local_purchase_order -> Local Paddy Purchase Order.name`; `.weigh_bridge_measurement -> Weigh Bridge Measurement.name`; `.quality_check -> Quality Check.name`; `.old_new_bags -> Quality Check Old New Bag Detail` (Table); `.qc_bag_details -> Quality Check Bag Detail` (Table); `.entry_details -> GRN Entry Detail` (Table). `GRN Entry Detail.entry -> Entry.name`.
- `Chhatni Assign.ppc_name -> PPC Master.name`; `.season -> Season Master.name`; `.mill_name -> Mill Master.name`; `.chhatni_history -> Chhatni Assign History` (Table); child `Chhatni Assign History.changed_by -> User.name`.
- `Daily Planning.ppc_name -> PPC Master.name`; `.season_name -> Season Master.name`. `Entry.season -> Season Master.name`; `.ppc_name -> PPC Master.name`.

No Dynamic Link field was discovered in these procurement DocType JSON files.

## Populated by code, not necessarily declared Link

`pass_unique_key` is the central business key for TP, WBM, GRN and aggregate reports. Several definitions use Data/Autocomplete because the key differs from PPAS document `name`. Controllers validate key existence and copy TP fields. `rst_no` is text and is matched across RST/WBM/GRN. Vehicle matching normalizes text. These relationships are not enforced as relational foreign keys.

## Report lineage

- **Mandi Book:** `GRN Note (nonlocal, docstatus < 2)` grouped by `pass_unique_key`; uses max TP quantity across the group, sum net weights, deductions, chhatni; resolves linked WBM for gross/load/tare/bags and GRN Entry Detail rows per pass. Metric lineage `total_received -> sum(GRN.net_weight) -> WBM-derived copied net -> TP/RST/WBM/GRN`. This includes drafts, excludes cancelled. See `mandi_book.py:148-230+`.
- **Abstract Physical:** master PPC list, seasons, `Target Allocation`, all PPAS TPs, government noncancelled GRNs and GRN Entry Detail; aggregates by `(canonical season, PPC Master)`. TP totals include all fetched TP rows; physical paddy sums GRN net; entry amount quantities prioritize GRN entry_qty/entry_quantity then child sum. Reuses Mandi Book excess. It only renders PPCs with positive target allocation. Draft GRNs included; malformed/missing PPC/season rows skipped. See `abstract_physical.py:80-`.
- **TP status:** submitted-only helper (`calculate_tp_status_for_pass`) and separate per-GRN rollup differ as noted.
- **Chhatni Tracking:** aggregates GRNs/pass and compares assigned/current chhatni from targets/season mapping. Source implementation in `report/chhatni_tracking/chhatni_tracking.py`; not a separate business ledger.

Filters, permission behavior, grouping, rounding, missing link handling, and statuses differ per report. Report definitions (`*.json`) identify report type but runtime permission query conditions were not DB-inspected.

## Relationship risks

- Text business keys can be changed/duplicated independently of target document `name`; unique key constraints/indexes are unknown without live schema.
- Copied values (TP quantity, PPC/mill/season, WBM weights, QC details) can diverge after upstream edit.
- Multiple sources for paddy amount: TP quantity, GRN net, entry child quantities, and season mapping cap logic.
- GRN `on_trash`/WBM callbacks refresh some aggregates; missing-link repair and all upstream mutation cascades are not proven.
