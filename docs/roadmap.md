# Roadmap

Where LabelJetty is heading. The core (library, REST API, job queue + worker, web UI, Homebox
integration, and multi-token / multi-user auth) is functional today; see [Design](design.md) for
how it all fits together. This page tracks what's planned next.

> This is an early project, still tested as a beta by the developer - priorities may shift.
> Feedback and pull requests are very welcome: open an [issue](../../issues).

## Recently shipped

- **Printer auto-discovery** - leave `PRINTER_USB` unset and LabelJetty auto-detects a
  connected TSPL printer (matching known vendor ids and USB printer-class devices). It uses
  the printer when exactly one is found, and lists candidates as copy-paste selectors when
  several are. Run `labeljetty-testbench list-printers` to see what it finds. See
  [Find your printer](setup.md#3-find-your-printer).

## Planned

### OIDC / SSO authentication

The auth layer is already built around a pluggable provider model and a `Principal` identity
(see [Design → Authentication](design.md#authentication)), specifically so that **OIDC slots in
as a third provider** alongside API tokens and local users - reusing the same session, with no
route changes. The plan is to add `AUTH_OIDC_*` settings and an OIDC callback so the service can
sit behind an identity provider for single sign-on.

### Config via UI

At the moment we need to configure the app userwide via env vars.
We could have settings per user or global forced setting via admin from a ui setting menu that overwrite Env vars.
This way the - experimental - prepared raspberry pi image would make more sense


## Possible / under consideration

These are ideas, not commitments (carried over from [Design → Non-goals](design.md#non-goals)):

- **Raw port-9100 (JetDirect) socket** so power users can add LabelJetty as a network printer
  manually. (Full IPP Everywhere / driverless discovery is project-sized and fights the "minimal
  dependency" principle - better as its own repo.)
- **Label template library** - named, reusable layouts beyond the Homebox one.
- **Multi-printer support** - the architecture currently assumes a single printer.
- **Broader hardware coverage** - verified support for printers other than the reference Vretti
  420B. This grows from user reports; see [Hardware](hardware.md) and please share your results.

## Explicit non-goals

See [Design → Non-goals](design.md#non-goals): replacing CUPS / being a full spooler, supporting
non-TSPL languages (ZPL/EPL), and cloud / multi-tenant hosting.
