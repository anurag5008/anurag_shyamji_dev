const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const EVIDENCE_DIR = "/home/hp/frappe-bench-v16/apps/ivri_od/e2e/evidence/E2E-20261023-REAL-TP/screenshots";
const AUTH_FILE = path.join(__dirname, "..", ".auth", "user.json");

(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        storageState: fs.existsSync(AUTH_FILE) ? AUTH_FILE : undefined,
        viewport: { width: 1440, height: 900 }
    });
    const page = await context.newPage();

    console.log("1. Capturing Procurement Desk...");
    await page.goto("http://127.0.0.1:8001/desk/procurement");
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "procurement_desk.png"), fullPage: true });

    console.log("2. Capturing Weigh Bridge Measurement List View...");
    await page.goto("http://127.0.0.1:8001/desk/weigh-bridge-measurement");
    await page.waitForTimeout(4000);
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "wbm_list_view.png"), fullPage: true });

    console.log("3. Capturing Rice Dispatch Report...");
    await page.goto("http://127.0.0.1:8001/desk/query-report/Rice%20Dispatch");
    await page.waitForTimeout(4000);
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "rice_dispatch_report.png"), fullPage: true });

    console.log("4. Capturing GRN Note Print with Entry Details...");
    await page.goto("file:///home/hp/frappe-bench-v16/apps/ivri_od/e2e/evidence/E2E-20261023-REAL-TP/grn_print_with_entry.html");
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "grn_print_with_entry.png"), fullPage: true });

    console.log("5. Capturing GRN Note Print without Entry Details...");
    await page.goto("file:///home/hp/frappe-bench-v16/apps/ivri_od/e2e/evidence/E2E-20261023-REAL-TP/grn_print_without_entry.html");
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "grn_print_without_entry.png"), fullPage: true });

    console.log("6. Capturing Chhatni Document...");
    await page.goto("http://127.0.0.1:8001/desk/chhatni");
    await page.waitForTimeout(3000);
    const firstRow = page.locator(".list-subject a").first();
    if (await firstRow.isVisible().catch(() => false)) {
        await firstRow.click();
        await page.waitForTimeout(3000);
        await page.screenshot({ path: path.join(EVIDENCE_DIR, "chhatni_form.png"), fullPage: true });
    }

    console.log("All screenshots captured successfully!");
    await browser.close();
})();
