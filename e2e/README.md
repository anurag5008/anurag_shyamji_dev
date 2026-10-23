# ivri_od browser tests (Playwright)

End-to-end tests that drive the Procurement desk in a real browser.

| Test file | What it checks | Saves data? |
|---|---|---|
| `navigation.spec.js` | Procurement desk layout, shortcuts, cards, PPAS Details, Back navigation | No |
| `rst-ppc-status.spec.js` | RST TP status rules, PPC name + code matching, Season Code, RST Unique Key | No (unsaved forms) |
| `forms.spec.js` | Workflow lists open; empty forms are stopped by "Missing Fields" | No |
| `workflow.spec.js` | Gate Entry -> QC -> RST -> Weigh Bridge -> Gate Exit -> GRN | **Yes**, test site only |

Test data (season, Transit Pass, PPC) is read from the site at run time, so no client data is kept here.

## Prerequisites (one time)

1. Bench running (`bench start`), site at `http://127.0.0.1:8001`.
2. In this folder: `npm install` then `npx playwright install chromium`.
3. Ubuntu 24.04 needs one sound library for Chromium: `sudo apt install libasound2t64`.
4. Visible browser: if the WSL browser window only shows in the Windows taskbar and will not open,
   run the tests from Windows instead (needs Node.js and Google Chrome on Windows):

   ```bash
   npm run test:windows     # from WSL: Windows Node drives your installed Chrome (temporary profile)
   npm run report:windows   # open the HTML report in your Windows browser
   ```

   Or in Windows PowerShell, in this folder: `powershell -ExecutionPolicy Bypass -File run-windows.ps1 --project=safe`.

## Log in (once)

```bash
npm run login
```

A browser window opens at the login page. **Sign in yourself**; you have 5 minutes.
Only the login cookie is saved, in `.auth/user.json` (git-ignored, readable only by you).
Your password is never stored. Run `npm run login` again when the login expires.

## Run

```bash
npm test                 # read-only tests, visible browser (safe on the live site)
npm run test:headless    # same, no window
npm run report           # open the HTML report: pass/fail and screenshots per test
```

Slower or faster for watching: `E2E_SLOWMO=600 npm test` (milliseconds per action).
Another site: `E2E_BASE_URL=http://ivri-e2e.localhost:8001 npm test`.

## Saving workflow (test site only)

`workflow.spec.js` creates Gate Entry, Quality Check, RST, Gate Exit and GRN records tagged `E2E-<time>`.
It never deletes anything. It refuses to run unless **both**:

- `E2E_ALLOW_WRITES=1` is set, and
- the site is not in `E2E_PROTECTED_SITES` (default: `shyamji`).

```bash
E2E_BASE_URL=http://ivri-e2e.localhost:8001 E2E_ALLOW_WRITES=1 npm run test:workflow
```

The test site needs Season Masters with Start/End Dates and PPAS Transit Pass data.

## Reports

- `playwright-report/`: HTML report (pass/fail, named screenshots, traces of failures).
- `test-results/`: raw screenshots and traces.

Both are git-ignored.
