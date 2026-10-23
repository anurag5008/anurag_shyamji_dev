// Copyright (c) 2026, Profezzo and contributors
// Playwright config for ivri_od Procurement browser tests. See README.md.

const fs = require("fs");
const { defineConfig } = require("@playwright/test");

const AUTH_FILE = ".auth/user.json";

// Under WSL (WSLg), GPU drawing can leave the browser window blank: it shows only in the
// Windows taskbar. Software drawing fixes that. Override with E2E_CHROME_ARGS="".
const IS_WSL =
	process.platform === "linux" &&
	fs.existsSync("/proc/version") &&
	/microsoft/i.test(fs.readFileSync("/proc/version", "utf8"));
const CHROME_ARGS = (process.env.E2E_CHROME_ARGS ?? (IS_WSL ? "--disable-gpu" : "")).split(" ").filter(Boolean);
// Run from Windows (e.g. when WSLg windows do not open): use the installed Google Chrome,
// with a temporary profile (your own Chrome profile is not used).
const CHANNEL = process.env.E2E_CHANNEL || (process.platform === "win32" ? "chrome" : undefined);

module.exports = defineConfig({
	testDir: "./tests",
	// One browser, one test at a time, so a person can watch the run.
	fullyParallel: false,
	workers: 1,
	retries: 0,
	timeout: 90_000,
	expect: { timeout: 15_000 },
	reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
	use: {
		baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:8001",
		headless: process.env.E2E_HEADLESS === "1",
		channel: CHANNEL,
		viewport: { width: 1440, height: 900 },
		launchOptions: { slowMo: Number(process.env.E2E_SLOWMO ?? 250), args: CHROME_ARGS },
		screenshot: "on",
		trace: "retain-on-failure",
	},
	projects: [
		// Opens the login page; you sign in yourself. The login cookie is saved to .auth/.
		{ name: "setup", testMatch: /auth\.setup\.js/, timeout: 6 * 60_000 },
		// Read-only: views, clicks and unsaved forms. Safe on a live site.
		{
			name: "safe",
			testMatch: /(navigation|rst-ppc-status|forms)\.spec\.js/,
			dependencies: ["setup"],
			use: { storageState: AUTH_FILE },
		},
		// Full approved run from evidence/<run>/plan.json (E2E_RUN_DIR). Saves records; same write gate.
		{
			name: "fullrun",
			testMatch: /full-run\.spec\.js/,
			dependencies: ["setup"],
			use: { storageState: AUTH_FILE },
			timeout: 20 * 60_000,
		},
		// Saves records (Gate Entry -> GRN). Runs only on a test site with E2E_ALLOW_WRITES=1.
		{
			name: "workflow",
			testMatch: /workflow\.spec\.js/,
			dependencies: ["setup"],
			use: { storageState: AUTH_FILE },
			timeout: 5 * 60_000,
		},
	],
});
