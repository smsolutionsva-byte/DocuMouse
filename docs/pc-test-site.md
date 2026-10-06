# A free test website from your Windows PC

This runs the existing website, API, SQLite database and CPU OCR on your PC.
Cloudflare's official `cloudflared` tool provides a temporary HTTPS address,
without a Cloudflare account, payment card or domain. Your PC must remain awake
and connected to the internet. See [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

**For a private pilot:** everyone given the access code shares the same document
library. Customer accounts, document ownership and billing are not implemented.
Quick Tunnels are intended for testing and development, have no uptime guarantee,
do not support SSE, and change their address on restart. Use a permanent server
or production tunnel before selling access to the service.

## One-time setup

Install Node.js, Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/)
if they are missing. In PowerShell, install Cloudflare's official tool:

```powershell
winget install --id Cloudflare.cloudflared --exact --source winget --scope user
```

From the repository root:

```powershell
python deploy/pc_test_site.py setup
```

This creates `backend/.venv`, installs the backend with `ocr` and `hosting` extras,
and builds the production frontend for the local API. The original Python
installation and its packages are preserved. The first OCR job downloads models
and can take several minutes; subsequent jobs reuse them.

## Start, check or stop

```powershell
backend/.venv/Scripts/python.exe deploy/pc_test_site.py start
backend/.venv/Scripts/python.exe deploy/pc_test_site.py status
backend/.venv/Scripts/python.exe deploy/pc_test_site.py stop
```

`start` creates a strong access code and checks the frontend and API login gates
before opening the public tunnel. It prints the HTTPS URL and the location of
the private code. Open `.local-hosting/access-code.txt` to copy the code into the
site's login form. Keep that code private or share it only with your test users.

The background services have no visible terminal windows. Closing the setup
terminal leaves them running. Windows restart, sleep, internet loss or `stop`
can make the website unavailable. The launcher does not install a Windows service
or change sleep settings; run `start` again when you want another test session.

The API listens only on `127.0.0.1:8787`, and the frontend only on
`127.0.0.1:3176`. Cloudflare publishes the frontend. Documents, SQLite data,
access code and logs stay in `.local-hosting/`, which Git ignores. OCR runs one
document at a time with paid LLM and second-reader calls disabled.

`stop` checks the saved process identities and stops only processes launched by
this helper. It preserves documents and the code. Back up `.local-hosting/` if
you need to keep the pilot's data; a public URL does not create cloud backups.

## Update

Stop the site, pull the source update, run `setup`, then `start` again. The access
code and document database persist; the public URL changes.

## Verification

Checked October 6, 2026 on Windows: the production frontend build and TypeScript
checks passed; the public login and stylesheet loaded; anonymous and incorrect
access codes were rejected; browser sign-in worked. A sample invoice uploaded
through the public URL was processed by PaddlePaddle 3.2.2 and PaddleOCR 3.7.0,
and its CSV export succeeded. Stop/restart preserved the document database and
access code and left an unrelated Python process running.

The SQLite timestamp handling was corrected so browser times retain UTC after
database reads. The timestamp regression and authentication checks passed.
This validates the test-site flow with one sample, not OCR accuracy on every
document type. Linux container and ARM deployment checks remain separate.
