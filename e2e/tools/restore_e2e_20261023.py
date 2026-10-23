# Copyright (c) 2026, Profezzo and contributors
"""Dedicated Restoration Script for E2E-20261023-REAL-TP.
Site: shyamji
Restores all 119 transaction documents from tabDeleted Document while preserving
exact original document names, relationships, child tables, and master data integrity.
"""

import csv
import gzip
import json
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


def main(site="shyamji", evidence_dir="../apps/ivri_od/e2e/evidence/E2E-20261023-REAL-TP"):
    verify_backup()

    frappe.init(site=site, sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")

    # Baseline master counts before restoration
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

    cleanup_path = os.path.join(evidence_dir, "cleanup_audit.csv")
    if not os.path.exists(cleanup_path):
        raise FileNotFoundError(f"Cleanup audit not found: {cleanup_path}")

    with open(cleanup_path) as f:
        audit_rows = list(csv.DictReader(f))

    print(f"[Cleanup Audit] Found {len(audit_rows)} records to restore.")

    # Forward dependency restoration order
    restoration_order = [
        "Gate Entry",
        "Quality Check",
        "RST Details",
        "Weigh Bridge Measurement",
        "Gate Exit",
        "GRN Note",
        "Entry",
        "Chhatni",
    ]

    by_dt = {dt: [] for dt in restoration_order}
    for r in audit_rows:
        dt = r["doctype"]
        if dt in by_dt:
            by_dt[dt].append(r)
        else:
            print(f"Warning: Unknown doctype {dt} in cleanup audit.")

    restoration_log = []
    restored_counts = {dt: 0 for dt in restoration_order}

    for dt in restoration_order:
        records = by_dt[dt]
        seen_names = set()
        for r in records:
            name = r["document_name"]
            if name in seen_names:
                continue
            seen_names.add(name)

            # Check if document already exists
            if frappe.db.exists(dt, name):
                print(f"[Skip] {dt} {name} already exists in DB.")
                restoration_log.append([
                    dt, name, r.get("tp_no", ""), r.get("lot_no", ""), r.get("upstream_link", ""),
                    RUN_ID, "ALREADY_ACTIVE", "SKIPPED"
                ])
                continue

            # Find matching Deleted Document record
            dds = frappe.get_all(
                "Deleted Document",
                filters={"deleted_doctype": dt, "deleted_name": name, "restored": 0},
                fields=["name", "data", "creation"],
                order_by="creation desc"
            )

            if not dds:
                raise ValueError(f"CRITICAL: No unrestored Deleted Document found for {dt} {name}!")

            dd_info = dds[0]
            dd_doc = frappe.get_doc("Deleted Document", dd_info["name"])
            data = json.loads(dd_doc.data)

            doc = frappe.get_doc(data)

            # Insert parent table record
            doc.db_insert()

            # Insert child table records if any
            for child in doc.get_all_children():
                child.db_insert()

            # Record comment on document
            try:
                doc.add_comment("Edit", f"Restored {dd_doc.deleted_name} for test run {RUN_ID} (Option A)")
            except Exception:
                pass

            # Update Deleted Document tracking
            dd_doc.new_name = doc.name
            dd_doc.restored = 1
            dd_doc.db_update()

            restored_counts[dt] += 1
            restoration_log.append([
                dt, name, r.get("tp_no", ""), r.get("lot_no", ""), r.get("upstream_link", ""),
                RUN_ID, f"Restored from Deleted Document {dd_doc.name}", "RESTORED_SUCCESSFULLY"
            ])

    frappe.db.commit()
    print(f"[Restoration Summary] Successfully restored: {restored_counts}")
    print(f"[Total Restored] {sum(restored_counts.values())} documents restored.")

    # Save restoration audit log
    restoration_audit_path = os.path.join(evidence_dir, "restoration_audit.csv")
    with open(restoration_audit_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doctype", "document_name", "tp_no", "lot_no", "upstream_link", "run_id", "restoration_evidence", "restoration_status"])
        w.writerows(restoration_log)
    print(f"[Audit Saved] Saved restoration audit to {restoration_audit_path}")

    # Post-restoration master integrity verification
    post_masters = {dt: frappe.db.count(dt) for dt in baseline_masters}
    for dt, cnt in baseline_masters.items():
        if post_masters[dt] != cnt:
            raise ValueError(f"CRITICAL DEFECT: Master count for {dt} changed from {cnt} to {post_masters[dt]}!")
    print(f"[Integrity Verified] Master counts 100% unchanged: {post_masters}")

    # Post-restoration transactional counts
    post_transactions = {dt: frappe.db.count(dt) for dt in restoration_order}
    print(f"[Transactional State] Active records in DB: {post_transactions}")
    expected_totals = {
        "Gate Entry": 16,
        "Quality Check": 16,
        "RST Details": 22,
        "Weigh Bridge Measurement": 22,
        "Gate Exit": 16,
        "GRN Note": 16,
        "Entry": 1,
        "Chhatni": 10,
    }
    for dt, exp in expected_totals.items():
        if post_transactions[dt] != exp:
            print(f"Warning: Expected {exp} for {dt}, found {post_transactions[dt]}")

    print("[Done] Restoration process completed successfully.")


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "shyamji"
    evidence_dir = sys.argv[2] if len(sys.argv) > 2 else "../apps/ivri_od/e2e/evidence/E2E-20261023-REAL-TP"
    main(site, evidence_dir)
