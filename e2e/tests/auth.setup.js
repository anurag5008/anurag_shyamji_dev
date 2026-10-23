// Copyright (c) 2026, Profezzo and contributors
// Login once: reuse the saved login, or open the login page and wait for you to sign in.
// Your password is typed by you in the browser; only the session cookie is saved (.auth/, git-ignored).

const fs = require("fs");
const { test: setup, expect } = require("@playwright/test");

const AUTH_FILE = ".auth/user.json";

async function loggedInUser(request) {
	const response = await request.get("/api/method/frappe.auth.get_logged_user");
	if (!response.ok()) return null;
	return (await response.json()).message || null;
}

setup("log in to the ERP", async ({ browser, baseURL }) => {
	if (fs.existsSync(AUTH_FILE)) {
		const context = await browser.newContext({ baseURL, storageState: AUTH_FILE });
		const user = await loggedInUser(context.request);
		await context.close();
		if (user && user !== "Guest") {
			console.log(`Using saved login for ${user}.`);
			return;
		}
	}

	setup.skip(process.env.E2E_HEADLESS === "1", "No saved login. Run `npm run login` once with a visible browser.");

	const context = await browser.newContext({ baseURL });
	const page = await context.newPage();
	await page.goto("/login");
	console.log("\n>>> Please sign in in the browser window (you have 5 minutes). <<<\n");
	await page.waitForURL(/\/(desk|app)(\/|$)/, { timeout: 5 * 60_000 });

	const user = await loggedInUser(context.request);
	expect(user, "signed-in user").not.toBe("Guest");
	fs.mkdirSync(".auth", { recursive: true });
	await context.storageState({ path: AUTH_FILE });
	try {
		fs.chmodSync(AUTH_FILE, 0o600); // owner only; not supported on every Windows path
	} catch (error) {
		console.log(`Could not restrict ${AUTH_FILE}: ${error.message}`);
	}
	console.log(`Login saved for ${user}.`);
	await context.close();
});
