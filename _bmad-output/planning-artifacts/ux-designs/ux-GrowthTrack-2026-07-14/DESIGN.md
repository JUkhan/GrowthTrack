---
name: GrowthTrack
description: Administrator control-plane for GrowthTrack's WhatsApp sales reporting system. React + MUI on web; this DESIGN.md specifies the brand-layer delta on top of MUI defaults, not a from-scratch system.
status: final
updated: 2026-07-14
colors:
  # Brand overrides on top of MUI's default palette. All unlisted tokens
  # (background, paper, divider, text-primary, text-secondary, action-hover,
  # action-disabled) inherit MUI's default light/dark theme.
  primary: '#154D71'
  primary-foreground: '#FFFFFF'
  primary-dark: '#5B9BC4'
  primary-foreground-dark: '#08202E'
  accent: '#12966B'
  accent-foreground: '#FFFFFF'
  accent-dark: '#34D399'
  accent-foreground-dark: '#062018'
  status-success: '{colors.accent}'
  status-success-dark: '{colors.accent-dark}'
  status-warning: '#C77700'
  status-warning-foreground: '#FFFFFF'
  status-warning-dark: '#F2B84B'
  status-warning-foreground-dark: '#2B1B00'
  status-error: '#C0362C'
  status-error-foreground: '#FFFFFF'
  status-error-dark: '#F1817A'
  status-error-foreground-dark: '#2B0A07'
typography:
  # Body, label, caption inherit MUI's default Roboto ramp. Only the
  # dashboard-numeral role is overridden.
  stat-display:
    fontFamily: 'Roboto'
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.15'
    letterSpacing: '0em'
    note: 'font-variant-numeric: tabular-nums -- sales/currency columns must align vertically, this is a reporting tool first'
  stat-display-sm:
    fontFamily: 'Roboto'
    fontSize: 22px
    fontWeight: '600'
    lineHeight: '1.2'
    note: 'tabular-nums, same rationale as stat-display'
  heading:
    fontFamily: 'Roboto'
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.3'
rounded:
  sm: 4px
  md: 8px
  lg: 12px
  full: 9999px
spacing:
  # MUI's default 8px base unit inherited (theme.spacing(n) = n * 8px).
  mobile-margin: 16px
  desktop-margin: 24px
  gutter: 16px
components:
  button-primary:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    radius: '{rounded.md}'
  button-danger:
    background: '{colors.status-error}'
    foreground: '{colors.status-error-foreground}'
    radius: '{rounded.md}'
  status-badge:
    radius: '{rounded.full}'
    success:
      background: '{colors.status-success}'
      foreground: '{colors.accent-foreground}'
    warning:
      background: '{colors.status-warning}'
      foreground: '{colors.status-warning-foreground}'
    error:
      background: '{colors.status-error}'
      foreground: '{colors.status-error-foreground}'
    note: 'every variant pairs color with an icon (check / clock / alert-triangle) and a text label -- never color alone, see Accessibility Floor in EXPERIENCE.md'
  stat-tile:
    radius: '{rounded.md}'
    elevation: '0 (flat, bordered) -- see Elevation & Depth'
    numeral: '{typography.stat-display}'
  data-table-row:
    radius: '{rounded.sm}'
    hover-background: 'MUI action.hover (inherited)'
---

## Brand & Style

GrowthTrack is a **daily operating instrument**, not a marketing surface. Nobody browses it for pleasure — an Administrator opens it to check the numbers are right, fix a delivery problem, or push an urgent update, then leaves. Every visual decision optimizes for *fast, confident reading of business-critical numbers* over decoration. `[ASSUMPTION: interpreting user's "modern, trustworthy, efficient, no-nonsense" as: contemporary proportions and restraint, not minimalism-as-austerity — the Dashboard still needs to feel considered, not like an unstyled admin CRUD scaffold.]`

The closest reference class is the regional Sales-Force-Automation and WhatsApp-broadcast tooling GrowthTrack competes with (per market research) — this system should read as more credible and current than that set, without drifting into the dense, heavier enterprise-suite register (Veeva, Salesforce Life Sciences) that would fight "efficient" and "no-nonsense."

Concretely: flat surfaces over heavy shadows, one confident brand blue plus one growth-signaling green, generous but not loose spacing, numbers set for scanning (tabular alignment, clear hierarchy between headline figures and supporting detail), and — because this product's entire premise is "trust the log, not the promise" (SM-C1: silent-failure rate must stay at zero) — a hard rule that failure states are never visually softened to look less bad than they are.

## Colors

- **`{colors.primary}` — deep steel blue.** The system's one confident, serious color: primary buttons, active nav state, links, the brand mark. Chosen for "trustworthy" without tipping into corporate-bank navy — it's a working tool, not a financial institution. `[ASSUMPTION: exact hex pending a real logo/brand exercise if one ever happens outside this PRD's scope — treat as a strong placeholder, not a locked brand color.]`
- **`{colors.accent}` — growth green.** Reserved for *positive movement*: Growth % when positive, Top Brand tags, "opt-in active" state, delivery-succeeded badges. Deliberately tied to the product's own name and its core metric (Growth %) rather than picked arbitrarily. Never used for primary actions or navigation — if green meant both "the button to press" and "this number went up," the two meanings would blur.
- **`{colors.status-warning}` and `{colors.status-error}`** exist only for delivery/data states (pending retry, stale data, failed send, locked out) — not reused as decorative accents elsewhere. Keeping the semantic palette small and single-purpose is what makes a red genuinely mean "something needs you" the instant it appears.
- Everything else — backgrounds, surfaces, dividers, body text — inherits MUI's default light/dark theme unchanged. No reason to relitigate what MUI already gets right, and a smaller override surface is itself a "no-nonsense" choice.
- Dark mode is a first-class target (user requirement, not deferred): every brand token above has a `-dark` counterpart tuned for sufficient contrast against MUI's dark paper surface, not just a naive lightness flip.

## Typography

Roboto, inherited from MUI, for everything. `[ASSUMPTION: no display/brand font introduced — a bespoke typeface would work against "efficient" and "no-nonsense," and this product has no marketing surface where a distinct type voice would even be seen.]` The one addition is `{typography.stat-display}` / `{typography.stat-display-sm}`: the typographic treatment used for headline dashboard figures (Today's Sales, YTD, MTD, Achievement %, Growth %) and Daily Report numerals. Semi-bold at a size clearly larger than body text, set with tabular numerals so a column of Cr BDT figures lines up — a sales dashboard where the numbers visually wobble undermines "trustworthy" faster than any color choice could.

Body copy, labels, and captions use MUI's default Roboto scale and weights without modification.

## Layout & Spacing

Base unit is MUI's default 8px grid — no override. Two named tokens exist because this portal is explicitly mobile-solid (per requirement), not desktop-only: `{spacing.mobile-margin}` (16px) for phone-width layouts and `{spacing.desktop-margin}` (24px) once the viewport clears MUI's `md` breakpoint. `{spacing.gutter}` (16px) governs the gap between Dashboard stat tiles and table columns at every breakpoint.

Dashboard content is information-dense by requirement (FR-3's seven fields, plus Brand Performance) but never cramped: stat tiles keep enough internal padding that the headline number is the first thing the eye lands on, not the smallest thing on a busy screen.

## Elevation & Depth

Flat by default. Surfaces are distinguished with a 1px border (MUI's default divider color) rather than a drop shadow — shadows are reserved for things that are genuinely floating above the page: modals, the recipient-picker popover, toasts/snackbars, and the mobile nav drawer. A Dashboard built entirely of floating shadow-cards would read as generic SaaS filler; bordered flat tiles read as an instrument panel, which is the intent.

## Shapes

`{rounded.md}` (8px) is the default for buttons, inputs, and stat tiles — a step past MUI's boxier 4px default, enough to feel current without reading as playful. `{rounded.lg}` (12px) is reserved for modal/dialog containers, the one place a slightly softer container helps a floating surface feel less abrupt. `{rounded.full}` is for status badges/pills only — the one place a fully rounded shape earns its keep, since it's a well-established convention for "this is a status chip, not a button."

## Components

- **`button-primary`** — `{colors.primary}` fill, white text, `{rounded.md}`. Used for the single primary action per screen (Send, Save, Confirm). Never more than one per view.
- **`button-danger`** — reserved for destructive/blocking actions: deleting a recipient, deactivating the last-remaining-admin guard rail (FR-2), opting a recipient out. Always paired with a confirmation step (see EXPERIENCE.md State Patterns) — the color signals stakes, it doesn't replace the confirmation.
- **`status-badge`** — the single most important component in this system. Three variants (success / warning / error), each pairing a color, an icon, and a text label — e.g., a failed send is never "just red" — it's a red pill with an alert-triangle icon reading "Failed — retries exhausted." This is a direct design response to SM-C1 (silent-failure rate must stay 0): a status that's ambiguous at a glance is a design defect here, not a nice-to-have fix later.
- **`stat-tile`** — the Dashboard's core building block (Today's Sales, YTD, MTD, Achievement %, Growth %, per-team breakdown). Flat, bordered, `{typography.stat-display}` numeral, a small label above, optional trend indicator using `{colors.accent}` (up) or `{colors.status-error}` (down) — never color alone, always paired with an up/down glyph.
- **`data-table-row`** — Notification History, Recipient directory, Audit Log all share one dense, sortable, filterable table pattern. Hover state uses MUI's inherited `action.hover`; no custom striping — striping fights "efficient" scanning of a data-table by adding visual noise the eye has to filter out.

→ Applied reference: `../mockups/dashboard.html`, `../mockups/notifications-compose.html`, `../mockups/notification-history.html` (paths relative to this file's workspace). Spine wins on conflict with any mock.

## Do's and Don'ts

**Do:**
- Pair every status color with an icon and a text label, always.
- Keep the accent green scoped to "positive movement" only — never use it as a generic decorative color.
- Set every currency and percentage figure in tabular numerals.
- Show every one of the Dashboard's seven required fields (FR-3) every time, even under load-time pressure (SM-C2) — degrade gracefully with a skeleton/loading state, never by dropping a field.
- Use flat, bordered surfaces as the default; reserve shadows for things actually floating above the page.

**Don't:**
- Don't let a failed or retrying send *ever* visually resemble a succeeded one — no green-tinted "it'll probably be fine" ambiguity.
- Don't introduce a second accent color for "excitement" or seasonal/marketing purposes — this system has no marketing surface.
- Don't add decorative illustration, empty-state mascots, or stock photography — every screen here is a working tool, not a landing page.
- Don't rely on hue alone to distinguish states anywhere (accessibility floor, not just style) — color-blind Administrators must be able to read every status without guessing.
- Don't introduce a bespoke display typeface (see Typography).
