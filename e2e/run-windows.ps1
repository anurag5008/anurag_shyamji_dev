# Run the browser tests with Windows Node and the installed Google Chrome (visible window).
# Use this when Linux browser windows from WSL do not open. Example:
#   powershell -ExecutionPolicy Bypass -File run-windows.ps1 --project=safe
# Calls Playwright's CLI with node directly: npx/npm go through cmd.exe, which cannot run in a \\wsl$ folder.
Set-Location -LiteralPath $PSScriptRoot
node node_modules/@playwright/test/cli.js test @args
exit $LASTEXITCODE
