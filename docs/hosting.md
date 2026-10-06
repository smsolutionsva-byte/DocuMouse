# Hosting DocuMouse with no monthly server bill

This setup runs the website, Python API, PaddleOCR, PostgreSQL and HTTPS proxy on
one server. It preserves the existing OCR engine and processes one document at
a time. It does not require Vercel, Hugging Face, Neon or R2 accounts.

If account verification is unavailable, use the [PC test-site launcher](pc-test-site.md)
for a temporary password-protected preview with no payment card.

**Use this for your private pilot.** DocuMouse currently has one shared access
code and one document library. Customer accounts, document ownership, usage
quotas and payment handling must be added before opening a shared paid service.
Hosting this version does not create those SaaS features.

## 1. Get a free server

For agent-assisted setup, install the official Oracle MCP server and CLI using
the [Oracle tools helper](oracle-tools.md). The tools still require a completed
Oracle account and a browser-authenticated session.

Sign up at [Oracle Cloud Free Tier](https://signup.cloud.oracle.com/). Oracle
requires a supported credit/debit card for identity verification and may place
a temporary authorization hold. Its FAQ says this is not an actual charge.

In your **home region**, open **Compute → Instances → Create instance**:

| Setting | Value |
| --- | --- |
| Name | `documouse` |
| Image | Canonical Ubuntu 24.04, ARM/AArch64, Always Free eligible |
| Shape | `VM.Standard.A1.Flex` |
| CPU | **2 OCPUs** |
| Memory | **12 GB** |
| Boot volume | **50 GB**, within the total free block-storage allowance |
| Networking | Public subnet with a public IPv4 address |
| SSH keys | Generate keys and download the private key |

Check the console's **Always Free eligibility** and cost estimate before
creating it. Stay within the aggregate allocation across all your instances.
The 30-day trial credits do not make an oversized instance permanently free.
Do not upgrade your account or choose a paid shape to resolve a capacity error.

Oracle currently documents 2 OCPUs and 12 GB for an Always Free tenancy. Capacity
is not guaranteed; if it says **out of host capacity**, try another availability
domain in your home region or try again later. Idle instances may be reclaimed;
keep database and document backups outside this server.

Sources checked October 6, 2026: [Oracle allocation and limitations](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[signup/card FAQ](https://www.oracle.com/cloud/free/faq/).

## 2. Open the web ports

On the instance's network security list or network security group, allow inbound
**TCP 80 and TCP 443** from the internet. Keep **TCP 22** for SSH restricted to
your own public IP. The database, frontend and API ports stay inside Docker.
Also check Ubuntu's host firewall: the same web ports must be allowed there.
Do not flush the firewall or remove the SSH rule.

From Windows PowerShell, connect using the private key you downloaded:

```powershell
ssh -i "C:\path\to\your-private-key.key" ubuntu@SERVER_PUBLIC_IP
```

Keep the private key on your computer. The server's public IP can be shared;
your key and passwords should stay private.

## 3. Pick a hostname

If you own a domain, point its DNS A record at the server's public IPv4 address.
For an initial private pilot, a free IP-based hostname can be used:

```text
documouse.SERVER_PUBLIC_IP.sslip.io
```

Replace `SERVER_PUBLIC_IP` with the actual dotted IPv4 address. The service
resolves IP-based hostnames without registering a domain. It is a third-party
free DNS service, so a domain you control is preferable once you have revenue.
Certificate issuance still depends on reachable ports and certificate-authority
rate limits; this hostname does not guarantee an HTTPS certificate.

See [sslip.io/nip.io](https://sslip.io/) and [Caddy's automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https).

## 4. Install Docker and get the app

On the Ubuntu server, install Docker Engine and the Compose plugin using
[Docker's official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
They support ARM64. Verify `sudo docker compose version` works.

Then run:

```bash
sudo apt-get update
sudo apt-get install -y git openssl
git clone https://github.com/smsolutionsva-byte/DocuMouse.git
cd DocuMouse
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
openssl rand -hex 32
openssl rand -hex 32
nano deploy/.env
```

In `deploy/.env`, set:

- `DOCUMOUSE_HOST` to your hostname, without `https://`.
- `DOCUMOUSE_DB_PASSWORD` to the first generated value.
- `DOCUMOUSE_AUTH_TOKEN` to the second generated value. This is your login code.

Do not commit this file. Do not change the database password after the database
has been initialized without also changing the PostgreSQL user's password.

## 5. Start it

From the repository root on the server:

```bash
sudo docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build
sudo docker compose --env-file deploy/.env -f deploy/compose.yml ps
sudo docker compose --env-file deploy/.env -f deploy/compose.yml logs --tail=100 backend caddy
```

The initial build installs OCR dependencies and attempts to download models.
It can take a while on the free CPU. If model preloading fails, the first OCR
job will need internet access to download the missing models.

Open `https://YOUR_HOSTNAME`, enter your access code and upload a sample receipt.
Verify that the image, extracted fields and CSV export work. Also verify that
an incorrect access code is rejected. `/api/health` confirms API availability;
it does not prove the OCR model can process a document.

The services restart after a server reboot. Documents and PostgreSQL data are
stored in named Docker volumes. Rebuilding containers preserves those volumes;
`docker compose down -v` deletes them and should not be used to update the app.

## Updates and moving to paid hosting

```bash
git pull --ff-only
sudo docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build
```

Keep off-server backups of both the PostgreSQL database and the uploaded
document volume. A free server has no uptime guarantee and its boot disk is not
an off-server backup. Schedule backups before storing customer documents.

When revenue covers hosting, the same containers can move to a paid server.
The frontend can also move to Vercel's commercial plan while the Python API and
OCR remain on a server. Vercel Hobby is restricted to personal, noncommercial
use: [Vercel Hobby rules](https://vercel.com/docs/plans/hobby).

## Verification status

The production frontend build and TypeScript checks passed. The generated
standalone server was started locally: the login page loaded, anonymous and
incorrect-code page requests redirected to login, and the correct code opened
the app. The Compose YAML was parsed and only the HTTPS proxy publishes ports.

Docker is unavailable on the setup machine, so Compose's own validation, image
builds and a real OCR request on ARM remain unverified. Run the complete Docker
build and the sample-document check on the server before using this deployment.
