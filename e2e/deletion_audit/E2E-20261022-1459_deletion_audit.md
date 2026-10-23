# E2E run E2E-20261022-1459: deletion audit

- Site: `shyamji`
- Deletion started: 2026-10-23 11:57:40.177021  |  finished: 2026-10-23 11:57:43.815523
- Documents deleted: **111** (planned 111); failures: **0**
- Backup taken before deletion: `sites/shyamji/private/backups/20261023_172447-shyamji-database.sql.gz` (gzip checked; contains all 111 documents and all protected records)
- Machine-readable log: `E2E-20261022-1459_deletion_log.jsonl` (same folder)

## How each record was confirmed as test-created

A document was deleted only if **all** of these held:

1. It is named in the run ledger (`e2e/evidence/E2E-20261022-1459/ledger.jsonl`) with its DocType and document name.
2. It exists in the database and was created between 2026-10-22 20:35 and 20:58 (checked inside a 20:30 to 21:00 window), docstatus 0.
3. Where the document carries the run marker (RST No, Weigh Bridge RST No, Gate Entry vehicle) it contains `E2E-20261022-1459`.
4. No document outside the run references it (all Link and Dynamic Link fields, including child tables, were scanned).
5. A census of everything created on 22 Oct 12:00 to 23:59 found no other Gate Entry, Quality Check, RST, Weigh Bridge, Gate Exit, GRN, Chhatni or Entry, so the failed first attempt left no partial records.
6. No other GRN, Weigh Bridge or Entry exists on the 14 Transit Passes the run used.

Naming patterns alone were not used.

## Method

- Supported `frappe.delete_doc`, one document at a time inside a savepoint, committed after each, with link checks on (no `force`).
- Order: GRN Note, Entry, Chhatni, Weigh Bridge Measurement, RST Details, Gate Exit, Quality Check, Gate Entry (RST and Weigh Bridge link to each other: Weigh Bridge first).
- Each document is archived in Deleted Document (not permanently erased).
- **Deviation, deliberate:** GRN Notes were deleted with Frappe's `ignore_on_trash=True`. A GRN's on-trash hook only schedules a Season Mapping and Transit Pass roll-up refresh. 6 of the 14 passes have no Season Mapping, so the hook would have created new Season Mapping records and rewritten 8 existing ones. Skipping it kept protected data untouched. Link checks and archiving still ran.
- No table was truncated, no broad SQL delete was used, no safeguard was disabled.

## Summary by DocType

| DocType | Deleted |
|---|---|
| GRN Note | 18 |
| Entry | 1 |
| Chhatni | 7 |
| Weigh Bridge Measurement | 17 |
| RST Details | 17 |
| Gate Exit | 17 |
| Quality Check | 17 |
| Gate Entry | 17 |
| **Total** | **111** |

## Rows that went with those documents (removed by Frappe, not listed individually below)

| Table | Rows |
|---|---|
| GRN Entry Detail | 1 |
| Quality Check Bag Detail | 35 |
| Quality Check Old New Bag Detail | 35 |
| Version | 2 |
| Weigh Bridge Bag Detail | 17 |

Child rows of the deleted documents (bag details, GRN entry detail) and the 2 Version rows of `GRN-2026-00083`.

## Verification after deletion

A before and after snapshot of every table on the site (769 DocTypes, 31,104 rows before, 31,125 after) was compared:

- All 111 ledger documents are gone; none remains.
- Removed rows: only the 111 documents, their child rows and the 2 Version rows above.
- Added rows: 111 Deleted Document archive entries and 111 "Deleted" Comment rows (one per deleted document).
- **Modified rows: none, in any table.**
- Protected data, removed / added / modified: PPAS Transit Pass 0/0/0 (648 records), Mill Master 0/0/0 (5), PPC Master 0/0/0 (48), District Master 0/0/0 (30), Agent Master 0/0/0 (7), Season Master 0/0/0 (2), Depo Master 0/0/0 (4), Target Allocation 0/0/0 (49), Target Allocation Agent 0/0/0 (50), Season Mapping 0/0/0 (49), Chhatni Assign 0/0/0 (48).
- Preserved untouched: the evidence folder, ledger, checks, screenshots, logs and application code. This audit folder is new and sits beside the evidence folder.

## Every deleted document

### GRN Note (18)

| # | Document | Test | Step | Created |
|---|---|---|---|---|
| 1 | GRN-2026-00083 | T01 | T01A GRN (auto after Gate Exit) | 2026-10-22 20:35:22 |
| 2 | GRN-2026-00084 | T01 | T01B GRN (auto after Gate Exit) | 2026-10-22 20:35:37 |
| 3 | GRN-2026-00085 | T02 | T02A GRN (auto after Gate Exit) | 2026-10-22 20:36:21 |
| 4 | GRN-2026-00086 | T03 | T03A GRN (auto after Gate Exit) | 2026-10-22 20:36:39 |
| 5 | GRN-2026-00087 | T04 | T04A GRN (auto after Gate Exit) | 2026-10-22 20:37:00 |
| 6 | GRN-2026-00088 | T05 | T05A GRN (auto after Gate Exit) | 2026-10-22 20:37:21 |
| 7 | GRN-2026-00089 | T06 | T06A GRN (auto after Gate Exit) | 2026-10-22 20:37:41 |
| 8 | GRN-2026-00090 | T07 | T07A GRN (auto after Gate Exit) | 2026-10-22 20:38:01 |
| 9 | GRN-2026-00091 | T08 | T08A GRN (auto after Gate Exit) | 2026-10-22 20:38:24 |
| 10 | GRN-2026-00092 | T09 | T09A GRN (auto after Gate Exit) | 2026-10-22 20:38:43 |
| 11 | GRN-2026-00093 | T09 | T09B GRN (auto after Gate Exit) | 2026-10-22 20:39:00 |
| 12 | GRN-2026-00094 | T09 | T09C GRN (auto after Gate Exit) | 2026-10-22 20:39:13 |
| 13 | GRN-2026-00095 | T10 | T10A GRN (auto after Gate Exit) | 2026-10-22 20:39:34 |
| 14 | GRN-2026-00096 | T11 | T11A GRN (auto after Gate Exit) | 2026-10-22 20:39:53 |
| 15 | GRN-2026-00097 | T12 | T12A GRN (auto after Gate Exit) | 2026-10-22 20:40:12 |
| 16 | GRN-2026-00098 | T13 | T13A GRN (auto after Gate Exit) | 2026-10-22 20:40:32 |
| 17 | GRN-2026-00099 | T14 | T14A GRN (auto after Gate Exit) | 2026-10-22 20:40:50 |
| 18 | GRN-2026-00100 | T14 | Duplicate GRN attempt | 2026-10-22 20:58:25 |

### Entry (1)

| # | Document | Test | Step | Created |
|---|---|---|---|---|
| 1 | EN-2026-00003 | T02 | Entry | 2026-10-22 20:36:07 |

### Chhatni (7)

| # | Document | Test | Step | Created |
|---|---|---|---|---|
| 1 | CH-2026-00001 | T01 | Chhatni | 2026-10-22 20:35:40 |
| 2 | CH-2026-00002 | T03 | Chhatni | 2026-10-22 20:36:43 |
| 3 | CH-2026-00003 | T04 | Chhatni | 2026-10-22 20:37:04 |
| 4 | CH-2026-00004 | T05 | Chhatni | 2026-10-22 20:37:26 |
| 5 | CH-2026-00005 | T06 | Chhatni | 2026-10-22 20:37:45 |
| 6 | CH-2026-00006 | T07 | Chhatni | 2026-10-22 20:38:06 |
| 7 | CH-2026-00007 | T09 | Chhatni | 2026-10-22 20:39:16 |

### Weigh Bridge Measurement (17)

| # | Document | Test | Step | Created |
|---|---|---|---|---|
| 1 | WBM-2026-00054 | T01 | T01A Weigh Bridge (created by RST) | 2026-10-22 20:35:19 |
| 2 | WBM-2026-00055 | T01 | T01B Weigh Bridge (created by RST) | 2026-10-22 20:35:34 |
| 3 | WBM-2026-00056 | T02 | T02A Weigh Bridge (created by RST) | 2026-10-22 20:36:18 |
| 4 | WBM-2026-00057 | T03 | T03A Weigh Bridge (created by RST) | 2026-10-22 20:36:35 |
| 5 | WBM-2026-00058 | T04 | T04A Weigh Bridge (created by RST) | 2026-10-22 20:36:57 |
| 6 | WBM-2026-00059 | T05 | T05A Weigh Bridge (created by RST) | 2026-10-22 20:37:17 |
| 7 | WBM-2026-00060 | T06 | T06A Weigh Bridge (created by RST) | 2026-10-22 20:37:38 |
| 8 | WBM-2026-00061 | T07 | T07A Weigh Bridge (created by RST) | 2026-10-22 20:37:58 |
| 9 | WBM-2026-00062 | T08 | T08A Weigh Bridge (created by RST) | 2026-10-22 20:38:20 |
| 10 | WBM-2026-00063 | T09 | T09A Weigh Bridge (created by RST) | 2026-10-22 20:38:40 |
| 11 | WBM-2026-00064 | T09 | T09B Weigh Bridge (created by RST) | 2026-10-22 20:38:57 |
| 12 | WBM-2026-00065 | T09 | T09C Weigh Bridge (created by RST) | 2026-10-22 20:39:10 |
| 13 | WBM-2026-00066 | T10 | T10A Weigh Bridge (created by RST) | 2026-10-22 20:39:31 |
| 14 | WBM-2026-00067 | T11 | T11A Weigh Bridge (created by RST) | 2026-10-22 20:39:50 |
| 15 | WBM-2026-00068 | T12 | T12A Weigh Bridge (created by RST) | 2026-10-22 20:40:09 |
| 16 | WBM-2026-00069 | T13 | T13A Weigh Bridge (created by RST) | 2026-10-22 20:40:28 |
| 17 | WBM-2026-00070 | T14 | T14A Weigh Bridge (created by RST) | 2026-10-22 20:40:47 |

### RST Details (17)

| # | Document | Test | Step | Created |
|---|---|---|---|---|
| 1 | E2E-20261022-1459-T01A | T01 | T01A RST Details | 2026-10-22 20:35:19 |
| 2 | E2E-20261022-1459-T01B | T01 | T01B RST Details | 2026-10-22 20:35:34 |
| 3 | E2E-20261022-1459-T02A | T02 | T02A RST Details | 2026-10-22 20:36:18 |
| 4 | E2E-20261022-1459-T03A | T03 | T03A RST Details | 2026-10-22 20:36:35 |
| 5 | E2E-20261022-1459-T04A | T04 | T04A RST Details | 2026-10-22 20:36:57 |
| 6 | E2E-20261022-1459-T05A | T05 | T05A RST Details | 2026-10-22 20:37:17 |
| 7 | E2E-20261022-1459-T06A | T06 | T06A RST Details | 2026-10-22 20:37:38 |
| 8 | E2E-20261022-1459-T07A | T07 | T07A RST Details | 2026-10-22 20:37:58 |
| 9 | E2E-20261022-1459-T08A | T08 | T08A RST Details | 2026-10-22 20:38:20 |
| 10 | E2E-20261022-1459-T09A | T09 | T09A RST Details | 2026-10-22 20:38:40 |
| 11 | E2E-20261022-1459-T09B | T09 | T09B RST Details | 2026-10-22 20:38:57 |
| 12 | E2E-20261022-1459-T09C | T09 | T09C RST Details | 2026-10-22 20:39:10 |
| 13 | E2E-20261022-1459-T10A | T10 | T10A RST Details | 2026-10-22 20:39:31 |
| 14 | E2E-20261022-1459-T11A | T11 | T11A RST Details | 2026-10-22 20:39:50 |
| 15 | E2E-20261022-1459-T12A | T12 | T12A RST Details | 2026-10-22 20:40:09 |
| 16 | E2E-20261022-1459-T13A | T13 | T13A RST Details | 2026-10-22 20:40:28 |
| 17 | E2E-20261022-1459-T14A | T14 | T14A RST Details | 2026-10-22 20:40:47 |

### Gate Exit (17)

| # | Document | Test | Step | Created |
|---|---|---|---|---|
| 1 | GX-2026-00012 | T01 | T01A Gate Exit | 2026-10-22 20:35:22 |
| 2 | GX-2026-00013 | T01 | T01B Gate Exit | 2026-10-22 20:35:37 |
| 3 | GX-2026-00014 | T02 | T02A Gate Exit | 2026-10-22 20:36:21 |
| 4 | GX-2026-00015 | T03 | T03A Gate Exit | 2026-10-22 20:36:39 |
| 5 | GX-2026-00016 | T04 | T04A Gate Exit | 2026-10-22 20:37:00 |
| 6 | GX-2026-00017 | T05 | T05A Gate Exit | 2026-10-22 20:37:21 |
| 7 | GX-2026-00018 | T06 | T06A Gate Exit | 2026-10-22 20:37:41 |
| 8 | GX-2026-00019 | T07 | T07A Gate Exit | 2026-10-22 20:38:01 |
| 9 | GX-2026-00020 | T08 | T08A Gate Exit | 2026-10-22 20:38:24 |
| 10 | GX-2026-00021 | T09 | T09A Gate Exit | 2026-10-22 20:38:43 |
| 11 | GX-2026-00022 | T09 | T09B Gate Exit | 2026-10-22 20:39:00 |
| 12 | GX-2026-00023 | T09 | T09C Gate Exit | 2026-10-22 20:39:13 |
| 13 | GX-2026-00024 | T10 | T10A Gate Exit | 2026-10-22 20:39:34 |
| 14 | GX-2026-00025 | T11 | T11A Gate Exit | 2026-10-22 20:39:53 |
| 15 | GX-2026-00026 | T12 | T12A Gate Exit | 2026-10-22 20:40:12 |
| 16 | GX-2026-00027 | T13 | T13A Gate Exit | 2026-10-22 20:40:32 |
| 17 | GX-2026-00028 | T14 | T14A Gate Exit | 2026-10-22 20:40:50 |

### Quality Check (17)

| # | Document | Test | Step | Created |
|---|---|---|---|---|
| 1 | QC-2026-81 | T01 | T01A Quality Check | 2026-10-22 20:35:15 |
| 2 | QC-2026-82 | T01 | T01B Quality Check | 2026-10-22 20:35:30 |
| 3 | QC-2026-83 | T02 | T02A Quality Check | 2026-10-22 20:36:14 |
| 4 | QC-2026-84 | T03 | T03A Quality Check | 2026-10-22 20:36:31 |
| 5 | QC-2026-85 | T04 | T04A Quality Check | 2026-10-22 20:36:53 |
| 6 | QC-2026-86 | T05 | T05A Quality Check | 2026-10-22 20:37:13 |
| 7 | QC-2026-87 | T06 | T06A Quality Check | 2026-10-22 20:37:34 |
| 8 | QC-2026-88 | T07 | T07A Quality Check | 2026-10-22 20:37:55 |
| 9 | QC-2026-89 | T08 | T08A Quality Check | 2026-10-22 20:38:16 |
| 10 | QC-2026-90 | T09 | T09A Quality Check | 2026-10-22 20:38:36 |
| 11 | QC-2026-91 | T09 | T09B Quality Check | 2026-10-22 20:38:52 |
| 12 | QC-2026-92 | T09 | T09C Quality Check | 2026-10-22 20:39:06 |
| 13 | QC-2026-93 | T10 | T10A Quality Check | 2026-10-22 20:39:26 |
| 14 | QC-2026-94 | T11 | T11A Quality Check | 2026-10-22 20:39:46 |
| 15 | QC-2026-95 | T12 | T12A Quality Check | 2026-10-22 20:40:05 |
| 16 | QC-2026-96 | T13 | T13A Quality Check | 2026-10-22 20:40:23 |
| 17 | QC-2026-97 | T14 | T14A Quality Check | 2026-10-22 20:40:43 |

### Gate Entry (17)

| # | Document | Test | Step | Created |
|---|---|---|---|---|
| 1 | GE-2026-00022 | T01 | T01A Gate Entry | 2026-10-22 20:35:12 |
| 2 | GE-2026-00023 | T01 | T01B Gate Entry | 2026-10-22 20:35:27 |
| 3 | GE-2026-00024 | T02 | T02A Gate Entry | 2026-10-22 20:36:10 |
| 4 | GE-2026-00025 | T03 | T03A Gate Entry | 2026-10-22 20:36:28 |
| 5 | GE-2026-00026 | T04 | T04A Gate Entry | 2026-10-22 20:36:49 |
| 6 | GE-2026-00027 | T05 | T05A Gate Entry | 2026-10-22 20:37:10 |
| 7 | GE-2026-00028 | T06 | T06A Gate Entry | 2026-10-22 20:37:31 |
| 8 | GE-2026-00029 | T07 | T07A Gate Entry | 2026-10-22 20:37:51 |
| 9 | GE-2026-00030 | T08 | T08A Gate Entry | 2026-10-22 20:38:12 |
| 10 | GE-2026-00031 | T09 | T09A Gate Entry | 2026-10-22 20:38:32 |
| 11 | GE-2026-00032 | T09 | T09B Gate Entry | 2026-10-22 20:38:49 |
| 12 | GE-2026-00033 | T09 | T09C Gate Entry | 2026-10-22 20:39:03 |
| 13 | GE-2026-00034 | T10 | T10A Gate Entry | 2026-10-22 20:39:23 |
| 14 | GE-2026-00035 | T11 | T11A Gate Entry | 2026-10-22 20:39:42 |
| 15 | GE-2026-00036 | T12 | T12A Gate Entry | 2026-10-22 20:40:01 |
| 16 | GE-2026-00037 | T13 | T13A Gate Entry | 2026-10-22 20:40:20 |
| 17 | GE-2026-00038 | T14 | T14A Gate Entry | 2026-10-22 20:40:39 |

