"""Python port of ``web/src/utils/format.ts`` — money/percentage formatting
for the Daily Report's WhatsApp content (Story 4.2).

``format.ts``'s own comment states this formatting logic must "live in one
place" so the Dashboard (Story 2.2) and the Daily Report never disagree on
these figures. That "one place" is TypeScript, which this Python-generated
report content cannot import — this module is the other half of that
stated intent, ported by hand rather than shared at runtime. Keep the
rounding behavior byte-for-byte identical to ``format.ts`` if either ever
changes.

One deliberate divergence from ``format.ts``'s own suffix:
``sample-whatsapp-report.md``'s literal reference text is "100 Cr BDT"
(with the currency code), while the Dashboard's bare rendering is
"100.0 Cr" — the numeric rounding is identical, only this module's suffix
differs (" Cr BDT", not " Cr").
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal


def _round_ties_up(value: Decimal, exponent: Decimal) -> Decimal:
    """Round ``value`` to a multiple of ``exponent`` (``Decimal("1")`` for
    whole numbers, ``Decimal("0.1")`` for one decimal place), with an
    exact tie rounding toward positive infinity — matching JavaScript's
    ``Math.round``/``toFixed`` semantics (code review, Story 4.2). Python's
    built-in ``round()``/``Decimal``'s default rounding both use
    round-half-to-even ("banker's rounding") instead, which silently
    diverges from ``format.ts`` on any value landing on an exact tie
    (e.g. ``round(Decimal("40.5")) == 40`` vs. JS's ``Math.round(40.5) ===
    41``) — exactly the figures this module exists to keep identical
    between the Dashboard and the Daily Report."""
    scaled = value / exponent
    return (scaled + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR) * exponent


def format_cr_bdt(amount: Decimal) -> str:
    crores = _round_ties_up(amount / Decimal("1e7"), Decimal("0.1"))
    return f"{crores:.1f} Cr BDT"


def format_percent(pct: Decimal) -> str:
    return f"{int(_round_ties_up(pct, Decimal('1')))}%"
