# Oracle automation tools

DocuMouse can be managed through Oracle's official
[OCI Cloud MCP server](https://github.com/oracle/mcp/tree/main/src/oci-cloud-mcp-server)
and [OCI CLI](https://github.com/oracle/oci-cli). The MCP server exposes OCI SDK
operations for compute, networking, storage and other services. It uses the
permissions of the Oracle account that signs in.

## Install on Windows

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and the
[Codex CLI](https://developers.openai.com/codex/cli/) first if they are missing.
From the repository root in PowerShell:

```powershell
.\deploy\oci-tools.ps1 -Action Install
```

The helper installs pinned versions of `oci-cli` (3.94.2) and
`oracle.oci-cloud-mcp-server` (2.2.3) in isolated uv environments. The MCP package
requires Python 3.13; uv downloads the interpreter if needed. It registers the
stdio server as `oracle-oci-cloud` in the local Codex configuration and preserves
any existing server with that name. Restart that MCP server in Codex after
installation to load its tools.

A newly registered server receives a 90-second startup timeout because its
first Windows startup can exceed Codex's default ten seconds.

No credentials or machine-specific configuration are stored in this repository.

## Finish account signup

Create an account at [Oracle Cloud signup](https://signup.cloud.oracle.com/).
The signup page checked on October 6, 2026 does not offer Google sign-in. An
existing Google browser session cannot replace Oracle's email verification,
password creation and billing verification. Complete those private steps
yourself; do not send passwords or card details to an agent.

Oracle's [Free Tier FAQ](https://www.oracle.com/cloud/free/faq/) describes its card
requirements and temporary verification holds. Signup must succeed before these
tools can provision a server. Free compute capacity is not guaranteed.

The [signup documentation](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm)
says a supported debit card can be entered under **Credit Card**. It gives Visa,
Mastercard, Discover and American Express as examples and requires payments
without a PIN. These documents do not establish whether a plain RuPay card is
accepted; a RuPay Global partner logo also does not guarantee Oracle verification.

## Authenticate through a browser

Use the **home region identifier** and **cloud account/tenancy name** shown by
Oracle, replacing the placeholders below:

```powershell
.\deploy\oci-tools.ps1 -Action Login -Region YOUR_HOME_REGION -TenancyName YOUR_TENANCY_NAME
.\deploy\oci-tools.ps1 -Action Check
```

`Login` opens Oracle's browser authentication flow. It writes the `DOCUMOUSE`
profile, session token and signing key under your local `~/.oci` directory. The
MCP server explicitly uses `OCI_MCP_AUTH_TYPE=security_token` and that profile.
It does not fall back to a permanent API key.

Oracle sessions expire after one hour by default. If validation reports an
expired or invalid session, run `Login` again. See Oracle's
[browser session authentication documentation](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm).

`Check` verifies the CLI, expected MCP registration and, when a config exists,
the Oracle session. It does not prove that the MCP process has connected in the
current chat. Installation, MCP connection, Oracle authentication and website
deployment are separate states.

## Deploy DocuMouse

After authentication, use the [hosting guide](hosting.md): an Always Free eligible
A1 instance with **2 OCPUs, 12 GB RAM and a 50 GB boot volume**, within the total
free allowance in the home region. Check existing resource usage and eligibility
before creating anything. Do not upgrade the account or choose a paid shape to
work around unavailable capacity.

This helper installs and authenticates tools. It does not create cloud
resources, accept signup terms or deploy the website automatically. Deployment
can then be performed through the official MCP tools or CLI.
