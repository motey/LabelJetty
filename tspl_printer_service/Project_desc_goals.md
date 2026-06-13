# TSPL Label Printer — Project Description & Goals

## Vision

Turn a cheap, USB-only TSPL thermal label printer into a "smart", network-accessible
label printer that can be driven from a phone, a desktop, or another machine — running
on a small always-on computer (e.g. a Raspberry Pi) next to the printer.

There are two intertwined goals:

1. **Primary goal — Homebox label printing.**
   Make it trivial to print labels (QR code + item name/asset ID) for items managed in a
   self-hosted [Homebox](https://github.com/sysadminsmedia/homebox) inventory server.
   This is the concrete itch this project scratches.

2. **Side quest — a generic USB TSPL printer interface.**
   The Homebox use case sits on top of a general-purpose library + service that can drive
   *any* TSPL printer over USB and print PDFs, images, text, barcodes and QR codes. Useful
   on its own, independent of Homebox.

The development/reference hardware is a **Vretti USB Etikettendrucker (label printer) with
TSPL support**, ~203 dpi.

---

## Architecture

Three layers, lowest dependency footprint possible (talk to the printer directly over USB
rather than relying on CUPS/vendor drivers):

```
┌────────────────────────────────────────────────────┐
│  Web UI (mobile + desktop)        REST API (tokens)  │  ← interface layer
├────────────────────────────────────────────────────┤
│  Print service: job queue (sqlite) + worker process  │  ← service layer
├────────────────────────────────────────────────────┤
│  TSPLPrinter library (render → TSPL commands)         │  ← library layer
├────────────────────────────────────────────────────┤
│  TSPLPrinterConnectionUSB (pyusb send/receive)        │  ← connection layer
└────────────────────────────────────────────────────┘
                         │ USB
                   ┌───────────┐
                   │  Printer  │
                   └───────────┘
```

- **Connection layer** — raw USB endpoint I/O, device discovery, reconnect.
- **Library layer** — convert PDFs/PNGs/text/barcodes/QR into TSPL command streams; query
  status. No web/server concerns. Usable as a standalone Python library.
- **Service layer** — accept print jobs, persist them, serialize access to the single
  physical printer through a background worker so concurrent requests don't collide.
- **Interface layer** — Web UI for humans, REST API for machines.

---

## Library requirements

Goal: a clean, importable Python library that is the *only* thing that knows TSPL.

- Talk to the printer at the lowest practical level (pyusb) — no external print-system
  dependency (no CUPS, no vendor driver).
- Configurable label size (width/height in mm) and DPI; derive pixel dimensions from these.
- Support printing:
  - **PDF** — render page(s) to a bitmap sized to the label. *(not yet implemented)*
  - **PNG / images** — with optional auto-resize-to-fit (keep aspect ratio), dithering for
    thermal output. *(implemented)*
  - **Raw text** — render text to the label with sane wrapping. *(only via markdown today)*
  - **Simple markdown** — headings, bullets, bold. *(implemented, basic)*
  - **Numbers/strings as barcodes** — Code128, EAN, UPC, Code39, etc. *(implemented)*
  - **Text/URLs as QR codes** — with ECC level + auto-sizing. *(implemented)*
  - **Composite labels** — e.g. QR + text, barcode + text (the Homebox label shape).
    *(basic helpers exist)*
- Query printer status (ready / head open / paper out / ribbon out / paused / error) and
  expose a typed status object. *(parsing exists; the live status path has bugs — see Known
  issues)*
- A `dry_run` mode that prints the generated TSPL to stdout instead of the device, for
  development without hardware. *(implemented)*

### Known issues / cleanup in the library (to fix while reviving)

- `TSPLPrinter.receive()` references `self.device`, which doesn't exist (the connection is
  `self.connection`); this path is dead.
- `is_ready()` / `get_error_message()` do dict-style access (`status["ready"]`) on a Pydantic
  model that exposes attributes (`status.ready`) — will raise.
- `TSPLPrinterStatusMessage` has no `error` field, but callers read `status["error"]`.
- `get_status()` sends the literal string `"b'\x1b!?'"` rather than the status-query bytes.
- Decide and document the real TSPL status-query command for the Vretti and verify the
  status-byte bit map against the actual device.

---

## Print service requirements

- A persistent **job queue** (sqlite) so requests are decoupled from the physical print and
  survive restarts. *(implemented)*
- A **single worker** that owns the printer and processes jobs one at a time. *(implemented
  via multiprocessing + watchdog with retry/backoff)*
- Persist per-job: input file/payload, type, requested label size, timestamps
  (queued/started/finished), final printer status, and error. *(partly implemented — only
  PNG today)*
- Configurable retention: auto-delete old jobs and their stored files after N days.
  *(implemented; not yet scheduled to run)*
- Extend the job model beyond PNG to all supported payload types (pdf/text/markdown/
  barcode/qrcode/composite) with their parameters. *(TODO)*

---

## Web interface & API requirements

### Base

- Desktop **and** mobile friendly UI.
- Auth modes, selectable by configuration:
  - **Open mode** — no login (LAN-only convenience).
  - **Login mode** — one or more users configured via env vars.
  - **API tokens** — one or more tokens configured via env vars for machine-to-machine use.
  - *(Today only a single optional bearer token exists — needs extending to multi-token /
    multi-user.)*

### Features (UI + API parity)

- Print: PDF, PNG, raw text, simple markdown, a number as a barcode, or text/URL as a QR
  code.
- Pick label size per job; fall back to a configurable default label size (env var) when
  none is given.
- Show job history / queue status and printer status (ready, paper out, etc.).
- A label **preview** (render the bitmap and show it before printing) — saves wasted labels.
- API: documented OpenAPI spec (FastAPI already generates it; expose/ship it).

### API gaps to close

- `/print/png` is currently a stub: it never writes the uploaded bytes to disk and builds a
  filename from `uuid.uuid4` (the function object) instead of `uuid.uuid4()`.
- No endpoints yet for pdf/text/markdown/barcode/qrcode, job status, or printer status.

---

## Homebox integration (primary goal)

Homebox integration is a **self-contained, optional module**. The printer service works
fully on its own; when a Homebox URL + API key are configured (and the module enabled), an
extra "Homebox" section appears in the web UI. With nothing configured, there is no trace of
Homebox in the app. This keeps the side-quest (generic TSPL printer) cleanly separable from
the primary goal.

### Homebox API (v0.26.0+ — important)

As of **Homebox v0.26.0**, items and locations were merged into a single **entity** model.
The old `/v1/items*` and `/v1/locations*` endpoints are **gone**; integrations now use
`/v1/entities*`. Design against this from the start:

- **Auth:** static API keys (prefixed `hb_…`), sent as a bearer token
  (`Authorization: Bearer hb_…`). A key inherits the access level of the user who created
  it. The Homebox server admin must have set `HBOX_AUTH_API_KEY_PEPPER` (≥32 chars) for API
  keys to function at all.
- **Search items:** `GET /v1/entities?q=<query>` (returns items by default; paginated shape
  with an `items` array).
- **Search locations:** `GET /v1/entities?isLocation=true&q=<query>`.
- **Entity summary** carries what a label needs: `name`, `assetId`, and `parent`
  (the old `location` field is now `parent`). Subscribe to the `entity.mutation` WebSocket
  event if we ever want live updates.

The natural label is: **a QR code (linking to the entity's Homebox URL, or encoding the
asset ID) plus human-readable text (name / asset ID).**

### Integration paths

There are three ways to connect the two systems. **A** and **B** are the ones we build; **C**
is a documented fallback.

**A. Printer → Homebox (pull) — the in-app module.**
The web UI's Homebox section lets the user **search items and locations** (via
`/v1/entities`), pick one, preview, and print a label that *we* render — tuned to the
configured label stock (QR of the entity URL + name + asset ID). This is the richest,
most controllable path and the main deliverable of the module.

**B. External label service (push) — the blessed way to use Homebox's own print button.**
Homebox can delegate label *rendering* to an HTTP service via
`HBOX_LABEL_MAKER_LABEL_SERVICE_URL`: it sends a `GET` with `TitleText`, `DescriptionText`,
`URL`, `Width`, `Height`, `Dpi`, `ComponentPadding`, … and expects an `image/*` back. We
expose exactly such an endpoint, which:

1. renders the label with **our** engine, tuned to our stock (same renderer as path A), and
2. **enqueues the print as a side effect**, then returns the image to Homebox.

This is elegant: one mechanism renders *and* prints, requires no script deployed on the
Homebox host, and reuses our renderer for consistent output. Setup is a single env var on the
Homebox side (`HBOX_LABEL_MAKER_LABEL_SERVICE_URL` → our endpoint).

> **Caveat to verify before relying on the side-effect print:** confirm Homebox calls the
> label-service URL **only on an explicit print action**, not on label *preview* /
> regeneration. If it's also called for previews, side-effect printing would produce spurious
> labels — in that case, fall back to path C (which only fires on the print button) or gate
> our printing behind an explicit query flag. Also respect `HBOX_LABEL_MAKER_LABEL_SERVICE_TIMEOUT`
> (default 30s): we only *enqueue* within the request and return promptly; we never block on
> the physical print completing. If our service is down, Homebox's label creation/preview is
> affected (it depends on our URL).

**C. Print command (push, fallback) — `HBOX_LABEL_MAKER_PRINT_COMMAND`.**
Homebox's per-entity print action renders a `label.png` server-side and runs a configured
command with a `{{.FileName}}` placeholder. We make this turnkey with a **setup helper page**
that, given the printer service's hostname/port, **generates a ready-to-paste bash script**:

```sh
#!/usr/bin/env sh
# Set HBOX_LABEL_MAKER_PRINT_COMMAND to:  /path/to/this-script.sh {{.FileName}}
curl -fsS -X POST "http://<printer-host>:<port>/api/print/png" \
  -H "Authorization: Bearer <token-if-configured>" \
  -F "file=@$1"
```

Alongside the script, the helper shows the **Homebox env-var hints** to match our label
stock (all sized in **pixels**, derived from the user's mm + DPI):
`HBOX_LABEL_MAKER_WIDTH`, `HBOX_LABEL_MAKER_HEIGHT`, `HBOX_LABEL_MAKER_PADDING`,
`HBOX_LABEL_MAKER_FONT_SIZE`, and `HBOX_LABEL_MAKER_PRINT_COMMAND`.

Prefer C over B when: the user wants Homebox's **native** label layout (Homebox renders, we
just print the bytes); "print means print" semantics are required with zero risk of
preview-triggered prints; or our service should not be a hard dependency of Homebox's
label-creation flow. The trade-off is a small script deployed on the Homebox host.

### Open questions to settle before building

- Encode the entity's Homebox **URL** vs. the bare **asset ID** in the QR (URL is more useful
  on a phone; asset ID is shorter/offline-friendly). Make it configurable.
- A small, configurable **label template** for the Homebox label (which fields, font sizes,
  QR position) so it fits the user's actual label dimensions.
- Confirm the exact API base prefix on the target instance (`/api/v1/entities` vs
  `/v1/entities`) and pagination/response field names against the live OpenAPI spec.

---

## Configuration (env vars)

Already present: app name, log level, listen host/port, sqlite path, image storage dir,
single API token, job retention days, and a flexible `PRINTER_USB` selector
(`serial:` / `path:` / `port:` / `vid:pid:` / `bus:addr:`).

To add:
- `DEFAULT_LABEL_WIDTH_MM`, `DEFAULT_LABEL_HEIGHT_MM`, `DEFAULT_DPI`.
- Multi-token and multi-user auth config.
- **Homebox module:** an enable flag, plus `HOMEBOX_URL` and `HOMEBOX_API_KEY` (the `hb_…`
  key). The module activates only when these are set.
- QR content choice (entity URL vs asset ID) and default label-template settings.

---

## Current status (snapshot)

| Area | State |
|------|-------|
| USB connection layer | Works (multiple discovery strategies, reconnect) |
| PNG printing | Works |
| Markdown / barcode / QR / composites | Works (basic) |
| PDF printing | Not implemented |
| Raw-text helper | Only via markdown |
| Printer status (live) | Buggy / unverified against hardware |
| Job queue + worker | Works for PNG only |
| REST API | Only `/print/png`, and it's a stub |
| Web UI | Not started |
| Auth | Single optional token only |
| Homebox integration (modular) | Not started — design targets v0.26 `/v1/entities` API |

---

## Roadmap (suggested order)

1. **Stabilize the library:** fix the status/`receive` bugs, add a real `print_pdf` and a
   `print_text` helper, verify against the Vretti in `dry_run` and on-device.
    1B. Provide a testsetup to quickly test the library against the printer. We want find out if positioning, sizing and such stuff is correct.
2. **Finish the API:** make `/print/png` actually store + enqueue; add endpoints for
   pdf/text/markdown/barcode/qrcode; add job-status and printer-status endpoints.
3. **Generalize the job model** so the worker can handle every payload type.
4. **Web UI:** mobile-first page to print + preview + see queue/printer status.
5. **Homebox module (pull):** optional, config-gated feature — search `/v1/entities` for
   items/locations, select, preview, and print a label rendered to our stock.
6. **Homebox push path:** expose the external-label-service endpoint
   (`HBOX_LABEL_MAKER_LABEL_SERVICE_URL`) that renders to our stock + enqueues the print, and
   ship the fallback setup-helper page that generates the `HBOX_LABEL_MAKER_PRINT_COMMAND`
   script + shows the `HBOX_LABEL_MAKER_*` env-var hints.
7. **Auth:** multi-token + multi-user + open mode, selected by config.
8. **Packaging:** systemd unit / container image, udev rule for non-root USB access on the
   Pi, setup docs.

---

## Optional / stretch goals

- **Standard network-printer interface** so the printer can be used from native OS print
  dialogs. Feasibility assessment:
  - **Full IPP Everywhere (driverless) — treat as a separate project.** Showing up
    automatically in the OS "Add Printer" dialog with no driver requires a real IPP server
    (binary IPP attribute protocol: Get-Printer-Attributes, Create-Job, Send-Document,
    Get-Jobs, Cancel-Job…), `_ipp._tcp` mDNS/DNS-SD advertisement with correct TXT records,
    **and** decoding the raster formats clients actually send (PWG Raster / Apple Raster /
    PDF) before converting to TSPL. The raster decode + conformance to get the OS to accept
    us is the hard part. This is project-sized and pulls in dependencies that fight the
    "minimal" principle — keep it as its own optional module/repo, not part of the core.
  - **Raw port-9100 (JetDirect) socket — a cheap stepping stone.** A tiny TCP listener that
    pipes the incoming stream into the renderer/printer is easy to build, but the OS won't
    auto-discover it: the user must add it manually and deal with page size/driver, so it
    mostly serves power users. Reasonable as a low-effort interim if a native path is wanted
    before IPP exists.
- A small **TSPL playground** endpoint to send raw TSPL for debugging.
- Label **template library** (named, reusable layouts beyond the Homebox one).
- Multi-printer support (the architecture currently assumes one printer).

---

## Non-goals (for now)

- Replacing CUPS or being a full print spooler.
- Supporting non-TSPL printer languages (ZPL/EPL) — could be a future abstraction, not a
  current target.
- Cloud / multi-tenant hosting; this is a single-LAN, single-printer appliance.
