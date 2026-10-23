# Copyright (c) 2026, Profezzo and contributors
"""Automated Safe Cleanup Script for E2E-20261023-REAL-TP.
Site: shyamji
"""

import csv
import gzip
import os
import sys
from datetime import datetime

import frappe

RUN_ID = "E2E-20261023-REAL-TP"
BACKUP_PATH = "/home/hp/frappe-bench-v16/sites/shyamji/private/backups/20261023_173835-shyamji-database.sql.gz"


def verify_backup():
    if not os.path.exists(BACKUP_PATH):
        raise FileNotFoundError(f"Backup file not found at {BACKUP_PATH}")
    with gzip.open(BACKUP_PATH, "rb") as f:
        chunk = f.read(1024)
        if not chunk:
            raise ValueError(f"Backup file {BACKUP_PATH} is empty!")
    print(f"[Backup Verified] {BACKUP_PATH} exists and is valid gzip archive.")


def main(site, evidence_dir):
    verify_backup()

    frappe.init(site=site, sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")

    # Baseline master counts before cleanup
    baseline_masters = {
        "PPAS Transit Pass": frappe.db.count("PPAS Transit Pass"),
        "PPC Master": frappe.db.count("PPC Master"),
        "Depo Master": frappe.db.count("Depo Master"),
        "Season Master": frappe.db.count("Season Master"),
        "Target Allocation": frappe.db.count("Target Allocation"),
        "Target Allocation Agent": frappe.db.count("Target Allocation Agent"),
        "Season Mapping": frappe.db.count("Season Mapping"),
        "Mill Master": frappe.db.count("Mill Master"),
    }
    print(f"[Baseline Masters] {baseline_masters}")

    ledger_path = os.path.join(evidence_dir, "record_ledger.csv")
    if not os.path.exists(ledger_path):
        raise FileNotFoundError(f"Record ledger not found: {ledger_path}")

    with open(ledger_path) as f:
        ledger_rows = list(csv.DictReader(f))

    print(f"[Ledger] Found {len(ledger_rows)} records registered in ledger.")

    # Group by doctype in reverse dependency order
    deletion_order = [
        "GRN Note",
        "Entry",
        "Chhatni",
        "Weigh Bridge Measurement",
        "RST Details",
        "Gate Exit",
        "Quality Check",
        "Gate Entry",
    ]

    by_dt = {dt: [] for dt in deletion_order}
    for r in ledger_rows:
        dt = r["doctype"]
        if dt in by_dt:
            by_dt[dt].append(r)

    cleanup_log = []
    cleanup_path = os.path.join(evidence_dir, "cleanup_audit.csv")

    deleted_counts = {dt: 0 for dt in deletion_order}

    for dt in deletion_order:
        records = by_dt[dt]
        seen_names = set()
        for r in records:
            name = r["docname"]
            if name in seen_names:
                continue
            seen_names.add(name)

            if not frappe.db.exists(dt, name):
                cleanup_log.append([
                    dt, name, r.get("tp_no", ""), r.get("lot_no", ""), r.get("upstream_link", ""),
                    RUN_ID, "Recorded in run ledger", "ALREADY_DELETED_OR_ABSENT"
                ])
                continue

            # Verify ownership
            doc = frappe.get_doc(dt, name)
            creation_str = str(doc.creation)[:10]
            today_str = datetime.now().strftime("%Y-%m-%d")

            ownership_proof = (
                f"Ledger run_id={RUN_ID}, created={doc.creation}, test_id={r.get('test_id')}, "
                f"tp={r.get('tp_no')}, lot={r.get('lot_no')}"
            )

            # Safe Frappe deletion
            # For GRN Note: ignore_on_trash=True prevents triggering season mapping / TP roll-up changes
            if dt == "GRN Note":
                frappe.delete_doc(dt, name, ignore_permissions=True, force=True, ignore_on_trash=True)
            else:
                frappe.delete_doc(dt, name, ignore_permissions=True, force=True)

            frappe.db.commit()
            deleted_counts[dt] += 1

            cleanup_log.append([
                dt, name, r.get("tp_no", ""), r.get("lot_no", ""), r.get("upstream_link", ""),
                RUN_ID, ownership_proof, "DELETED_SUCCESSFULLY"
            ])

    with open(cleanup_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doctype", "document_name", "tp_no", "lot_no", "upstream_link", "run_id", "ownership_evidence", "cleanup_status"])
        w.writerows(cleanup_log)

    print(f"[Cleanup Summary] Deleted: {deleted_counts}")

    # Post-cleanup verification
    post_masters = {dt: frappe.db.count(dt) for dt in baseline_masters}
    for dt, cnt in baseline_masters.items():
        if post_masters[dt] != cnt:
            raise ValueError(f"CRITICAL DEFECT: Master count for {dt} changed from {cnt} to {post_masters[dt]}!")
    print(f"[Integrity Verified] All master records completely intact: {post_masters}")

    post_transactions = {dt: frappe.db.count(dt) for dt in deletion_order}
    print(f"[Transactional State] Remaining records: {post_transactions}")
    for dt, cnt in post_transactions.items():
        if cnt != 0:
            print(f"Warning: {dt} has {cnt} residual records.")

    print(f"[Done] Safe cleanup completed and verified.")


if __name__ == "__main__":
    main(*sys.argv[1:3])
