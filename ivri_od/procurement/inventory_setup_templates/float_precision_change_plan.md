# Change plan: System Settings `float_precision` 2 -> 3

**Status: PROPOSED. Not applied.** Do not run until the user says: `approve float_precision 3`.

## Why
- ERPNext stock quantities (Stock Entry Detail, Stock Ledger Entry, Bin, Batch, Serial and Batch Entry) have no
  field-level precision. They follow `float_precision`.
- Weigh Bridge and GRN `net_weight` keep 3 decimals. At 2, ERPNext would store 71.188 as 71.19
  (`stock_entry.py:743,836`: `transfer_qty = flt(qty * conversion_factor, precision("transfer_qty"))`).
- Frappe's own fallback is 3 (`frappe/model/meta.py:922`). The site's 2 is an explicit setting.
- Stock UOM stays Quintal.

## Original value (recorded before any change)
- `tabSingles`: `System Settings` / `float_precision` = `'2'`
- `tabDefaultValue`: `__default` / `float_precision` = `'2'`
- Also `'2'` in the oldest backup `20261027_133816-shyamji-database.sql.gz` (System Settings last modified 2026-10-24).
  So 2 is the site's original value, not something set by the inventory work.
- Unchanged by this plan: `currency_precision` = 2, `number_format` = `#,##,###.##`, `rounding_method` = Banker's Rounding.

## Preconditions (all must be true)
1. The user approved with the exact words above.
2. Stock Posting Settings `enabled` = 0, and Stock Ledger Entry = 0 rows (nothing posted yet).
3. A fresh DB backup exists and passes `gzip -t` and `sha256sum` (take it right before: `bench --site shyamji backup`).
4. Git status recorded; staged Mill Master changes preserved.

## Change (one setting)
- Open System Settings in Desk, set **Float Precision** to `3`, Save. (Saving runs `on_update` -> `set_defaults()`,
  which writes only fields whose value changed, here `float_precision`, and clears the System Settings cache.)
- No migrate, no restart, no patch. Browsers need a refresh.

## Expected effects
- Stored data: none rewritten (columns hold 9 decimals). No recalculation.
- Stock Entry rows: `precision('qty')` and `precision('transfer_qty')` become 3, so 71.188 stays 71.188.
- Display and new rounding of every Float/Percent field without its own precision: ERPNext stock/manufacturing/selling/
  buying/accounts quantity fields, and 20 `ivri_od` fields (e.g. Target Allocation `target_quantity`,
  Season Mapping `season_quantity`, PPAS Transit Pass `quantity`, Rice Delivery Setup percentages). None of them holds a
  value beyond 2 decimals today, so they show one more decimal, nothing else.
- Currency and amounts: unaffected (they use `currency_precision`).
- Negative-stock tolerance in the ledger tightens from 0.005 to 0.0005 quintal.

## Validation (read-only, right after the change)
1. `frappe.db.get_default("float_precision")` = `3`, and `tabSingles` and `tabDefaultValue` both `'3'`.
2. In memory (no save): an unsaved Stock Entry row of 71.188 gives `transfer_qty` = 71.188.
3. GRN-2026-00123 (net 71.188) passes the receipt quantity check in `stock_posting.validate_stock_entry` in memory.
4. Row counts unchanged (Company 5, Warehouse 25, Item 0, Stock Entry 0, SLE 0), GRN/WBM `net_weight` values identical to before.
5. Test suites: `test_inventory_setup`, `test_inventory_foundation`, `test_stock_posting` OK; discovered suite identical to baseline.
6. Desk spot-check: GRN Note and Target Allocation open and display normally.
7. Rice Delivery Setup values are still 68 / 0 and 67 / 0.78 (this plan does not touch them).

## Rollback
- Set Float Precision back to `2` the same way and Save. Verify `get_default` = `2` in both stores.
- No data was rewritten, so nothing else needs undoing. The pre-change backup is the last resort only.
- If anything was posted at 3 decimals meanwhile, those ledger values stay (they are exact); only display and new rounding revert.

## Coupling with the driage value (do not skip)
- Frappe's float control rounds typed input to the field precision (`float.js:5`). At precision 2, typing 0.078 into
  Rice Delivery Setup gives 0.08. So 0.078 can only be entered after this change.
- The live Raw driage is 0.78. The DC Details sheet figures in `test_dc_details.py` imply 0.078. Verify the intended
  value first. This plan does not change it.
