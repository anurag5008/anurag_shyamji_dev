# Business workflows

## Configuration and planning

| Step | Purpose / actor | Source and trigger | Preconditions / fields | Writes / next | Evidence |
|---|---|---|---|---|---|
| Season setup | Admin configures crop season/year | `Season Master`; save/validate | Crop season, year; controller normalizes name | canonical Season Master link used in mappings, imports, GRNs and reports | `season_master/season_master.py`; metadata |
| PPC/mill/party setup | Admin maintains PPC, Mill, Society, Agent, District masters | corresponding master DocTypes | code/name uniqueness/normalization where controllers define it | link targets for PPAS and allocations | JSON/controller files; exact fields in inventory |
| Target allocation | Allocation user records season/PPC/mill target, agents, chhatni | `Target Allocation`; validate/on_update | Duplicate agent rows rejected; uniqueness PPC+mill+season | syncs/creates `Season Mapping`, sets season quantity/agent/chhatni | `target_allocation.py` lines 16-96 and 115-150 |
| Daily planning | PPC planner forecasts trucks/paddy | `Daily Planning`; validate | planning date and PPC, observed pass counts | estimated quantity derived from trucks and configured/planned values; details in controller | `daily_planning.py` |

## Government procurement flow

1. **Import/maintain PPAS TP.** PPAS extraction/import normalizes scraped/file rows, maps season/PPC/miller/quantity/vehicle and acceptance metadata, then saves `PPAS Transit Pass` using an application-generated `pass_unique_key`. Whitelisted import methods are in `ppas_import.py`; data mapping in `ppas_field_mapping.py`. Import action and external PPAS credentials/runtime were not exercised.
2. **RST / vehicle arrival.** `RST Details` captures RST number, vehicle and pass/party context. Controller validates RST number uniqueness and resolves TP/mill/agent where possible; it can synchronize to WBM. `Gate Entry` handles arrival/inside-mill state and printed gate pass. Exact gate matching uses normalized vehicle numbers/open visits (`mill_gate.py`).
3. **Quality Check.** QC is associated to a vehicle/open Gate Entry, classifies accepted/partially accepted/rejected, records returned bags and package/bag rows, and synchronizes party/quality outcome to Gate Entry/WBM. Rejected/full-return QC drives WBM `quality_test=Rejected` and net weight zero. QC can be missing while an early WBM/RST exists; it gates GRN readiness.
4. **Weigh Bridge Measurement.** Validate resolves pass key to `PPAS Transit Pass`, captures RST/Gate Entry/QC, truck identity, load/tare, bag details, gunny type and deduction. WBM validates gunny type and bag constraints, copies QC bag counts, derives gross and net weights. New local farmer/agent mode is explicitly rejected, though code retains legacy branches.
5. **GRN Note.** Validate rejects local procurement for new documents; requires a valid TP key and RST-linked WBM; syncs TP identity/quantity, pass season, entry detail rows, QC, bag counts, vehicle, and WBM weights. Strict auto-GRN path requires QC Accepted/Partially Accepted and tare > 0. Duplicate non-cancelled GRN per WBM is rejected. Naming uses `GRN-<receipt year>-#####`. Save/update refreshes per-pass totals and rollups. The controller contains no explicit `on_submit`/`on_cancel` override; checked-in GRN JSON also lacks `is_submittable` and states. Thus normal Frappe submission is not configured in checked-in source. Runtime customizations/direct docstatus manipulation could differ, but are unverified.
6. **Gate exit and reports.** Gate Exit resolves open inside-mill visit by vehicle and updates movement. Mandi Book summarizes GRNs per TP; Pass/RST/WBM, movement and other reports are separate views. Reports are not operational stock/accounting transactions by themselves. Checked-in Procurement DocTypes define no submit workflow/state; status language in code therefore depends on runtime customization or direct status setting.

## Alternative paths and status

- Multiple GRNs per TP are supported because WBM uniqueness is per GRN and aggregates group by pass key. Each GRN is tied to one WBM; duplicate active GRNs for that WBM are blocked.
- Different TP key in RST/WBM/GRN is blocked by explicit equality checks (GRN vs WBM, WBM resolves a valid TP). Missing RST/WBM blocks GRN validation.
- Local procurement branch is present for legacy documents and RST/WBM/PO helpers, but new WBM/GRN local transactions are rejected. Do not treat this as a currently supported purchase path.
- Gate Entry and QC sequence is vehicle/open-visit oriented; no strict universal linear lifecycle is enforced solely by the diagram. WBM can be created after RST before QC/TP in supported legacy/awaiting-TP code branches; automatic GRN requires accepted QC and tare.

## Failure and recovery

Validation errors are raised with `frappe.throw`; users can correct a draft and save again. After-save hooks use `frappe.db.after_commit` for rollup synchronization. WBM and GRN `on_trash` callbacks refresh totals; cancellation handling is not equivalently explicit in the reviewed code, though status queries differ by filters. Updates to upstream WBM/QC/RST do not comprehensively prove downstream GRN refresh; copied GRN fields may become stale. No retries/queue task for rollups were found; they run in after-commit callbacks.

## Document lifecycle configuration

No Procurement DocType JSON contains `is_submittable` or configured `states`; ordinary lifecycle in checked-in metadata is draft-only. Code nevertheless branches on `docstatus=1/2` for GRNs. Live Workflow documents and Custom DocType metadata were not queried.

## Roles and permissions

Workspace and DocType metadata define navigation and some role permissions, but live `Role`, `Workflow`, `Custom DocType`, `Custom Field`, and Permission Manager records were not inspected. Responsible human roles cannot be asserted from source; use “operator/configurator” as process role only. No role-to-step assignment is verified.
