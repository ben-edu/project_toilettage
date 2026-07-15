# CLAUDE.md — Toilettage Canin à Domicile (Orléans)

Guidance for Claude Code working in this repository on the management VM.
Read this fully before making changes.

---

## Project summary

Website for a **mobile dog-grooming service**: the groomer travels to the
client's home with equipment. Service area = Orléans + ~10 km around
**Place du Martroi** (`47.9027, 1.9086`), roughly 30 min by bike.
Language: **French only**. One groomer (single agenda).

- **Phase 1**: time-slot booking (no payment).
- **Phase 2 (later)**: online payment.

---

## Architecture (hybrid — "Voie A")

- **Frontend** → hosted on **Hestia (BM1)**, deployed to a document root via Jenkins.
- **Backend API** → **FastAPI** on **K3s (BM2)**, dedicated namespace.
- **Database** → existing **PostgreSQL** in the cluster.
- **Auth (admin panel)** → existing **Keycloak**, dedicated **realm** for this site.
  Public booking form needs NO login.

### Networking rule (do not violate)
- WireGuard (OPNsense) tunnel links BM1↔BM2 for **server-to-server** traffic.
- Browser API calls MUST go through the **public domain → Traefik → Service → Pod**.
  Never assume the browser can reach a private BM2 IP.

---

## Repository layout (target — adjust as it grows)

```text
.
├── CLAUDE.md                # this file
├── frontend/                # public French site (deployed to Hestia)
├── api/                     # FastAPI service (deployed to K3s)
│   ├── app/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── kubernetes/
│   └── toilettage/          # namespace, configmap, secret.example, deployment, service, ingress, README
├── Jenkinsfile              # multibranch pipeline
└── .env.example             # never commit real .env
```

> The exact frontend tech (static vs light framework) is confirmed in the design
> phase. Keep it performant, SEO-friendly, mobile-first.

---

## Branch & CI/CD conventions

Multibranch Jenkins pipeline, 3 branches:
- `feature/*` → feature work.
- `dev` → deployed to **staging subdomain** for testing.
- `main` → production, only via reviewed merge from `dev`.

Flow: `feature/*` → `dev` (staging) → validate → merge to `main` (prod).

- Hestia deploy: rsync to document root, **always `--exclude='.env'`** (never overwrite remote `.env`).
- K8s deploy: build image → push Harbor → apply manifests/Helm → verify rollout → ingress smoke test.

---

## Hard rules (from infra baseline + project)

- **Never commit secrets**: no real `.env`, no `.tfvars` with secrets, no K8s Secret
  manifests with real values, no tokens/passwords/keys. Use `*.example` files.
- **Never overwrite remote `.env`** during Hestia deployment.
- Validate target path before any `rsync`.
- Keep **staging and production** document roots separate.
- Public K8s traffic goes through **Traefik** (no arbitrary NodePort without a documented reason).
- BM1 and BM2 are **separate** Proxmox servers (both node-named `delfan`) — don't assume shared private routing beyond the WireGuard tunnel.
- **Live infra is the source of truth** — verify real state (kubectl, Hestia, OPNsense, Proxmox) before changing anything.
- Rotate any secret exposed in history/chat/Git.

---

## Booking domain model (initial — configurable in admin)

Services each have their own `duration_minutes`; dog **size** (small/medium/large)
applies a coefficient. A configurable **travel buffer** (default **30 min**) is
blocked after each booking. Slots are generated from daily working hours +
service duration + buffer, excluding overlaps.

Initial services (research not final — refine): bain (45 min),
tonte/toilettage (60–90 min by size), détartrage à la pince (30 min),
forfait complet (90–120 min).

Geo-check: geocode client address (Nominatim/OpenStreetMap), verify distance to
`47.9027, 1.9086`, refuse politely if outside configurable radius (default 10 km).

Email notifications: use **SORIA SMTP** for testing initially; dedicated email later.

---

## Design & marketing constraints (respect from the start)

Modern, warm, reassuring, slightly playful (not corporate). Mobile-first. Emotional
hero + single strong CTA ("Réserver"). Emphasize "à domicile" / "sans stress".
Include before/after gallery, reviews, 3-step process, coverage map. SEO from day
one: semantic HTML, French metadata ("toilettage canin à domicile Orléans"),
LocalBusiness structured data, high performance. Leave room for logo & social links.

---

## Working method

1. Code is written locally on the **management VM** first.
2. Claude Code (here) is connected to the whole infra via MCP + tools — use it to
   fetch real state (kubectl outputs, Hestia config, Keycloak, network) when needed
   instead of guessing.
3. Push to GitHub via Claude Code, then deploy via Jenkins.

---

## Before you commit / deploy — checklist

- [ ] No secrets staged (`git diff --cached`).
- [ ] `.env` excluded; only `.example` files committed.
- [ ] Correct branch for the target (feature/dev/main).
- [ ] API: tests pass, syntax OK.
- [ ] Frontend: builds, HTTP status OK after deploy.
- [ ] K8s: `kubectl apply` reviewed, rollout verified, ingress reachable.
