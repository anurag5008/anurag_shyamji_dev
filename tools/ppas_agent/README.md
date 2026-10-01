# PPAS Agent (local Windows service)

Frappe talks to the PPAS Agent at `http://127.0.0.1:8765` while the user is logged into the PPAS portal in Chrome.

## Deploying fixes

The installed `PPAS Agent.exe` must be rebuilt from this folder after scraper changes:

1. Install dependencies: `flask`, `flask-cors`, `requests`, `pandas`, `beautifulsoup4`, `selenium`, `openpyxl`
2. Package `ppas_agent.py`, `ppas_scraper.py`, and `ppas_launcher.py` with PyInstaller (same layout as the handover installer).
3. Re-run **PPAS Agent Installer.exe** on each client PC.

## Recent scraper fixes

- Reads `millerId` from the logged-in PPAS page instead of using only the hardcoded fallback.
- Refreshes cookies from Chrome before extraction.
- Accepts `configuration_id` / `season_id` on `/extract` (Frappe sends this when seasons are loaded).

## Dev run (without the .exe)

```bash
cd apps/ivri_od/tools/ppas_agent
python ppas_agent.py
```
