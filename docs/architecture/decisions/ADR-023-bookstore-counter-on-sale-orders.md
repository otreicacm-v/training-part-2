# ADR-023: Bookstore Counter Built on Sale Orders, Not Point of Sale

## Status

Accepted

## Date

2026-09-09

## Context

The school bookstore needs a system to sell textbooks, uniforms, supplies and merchandise to 5,000+ enrolled
students across 3 counters. "Point of sale" is the obvious label for it, and Odoo 19 ships a mature
`point_of_sale` module: a touchscreen cashier interface, offline-capable sessions, cash drawer and thermal receipt
support, payment methods, session open/close with cash control, and journal entries into accounting.

The initial decision was to build on `point_of_sale`. Requirements gathering then established how the bookstore
actually operates, and the fit turned out to be poor:

1. **The bookstore never handles money.** Payment is collected either at the school cashier's office, in a
   different location, or by charging the student's tuition statement. There is no cash at the counter.
2. **The transaction has a gap in the middle.** The clerk records items and prints a charge slip; the student
   carries it to the cashier, pays, and returns with an official receipt; only then are goods released. The
   transaction spans two visits separated by minutes or hours.
3. **The slip is an A4 PDF on an ordinary office printer.** There is no receipt printer at the counter.
4. **Every buyer is identified**, looked up from student records imported from an external student information
   system.
5. **The full stock lifecycle is in scope** — supplier purchase orders, goods receipt, sale, physical counts.
6. **Money settles outside Odoo.** Cash is receipted by the cashier's office; tuition charges are handed to the
   finance office to appear on the student's statement.

Almost everything `point_of_sale` provides is therefore unused, while the things the bookstore does need —
a multi-stage document with an approval-like gate before goods move, integration with purchasing and inventory,
and an identified customer on every transaction — are things `point_of_sale` deliberately does not do, because a
retail POS optimises for the opposite case: anonymous buyers, immediate payment, immediate handover.

## Decision

Build the bookstore counter on Odoo's **sale order flow** (`sale`, `stock`, `purchase`, `account`) rather than on
`point_of_sale`.

A counter transaction is a `sale.order` carrying bookstore-specific fields, including a `bookstore_state` field
that holds the counter state machine separately from Odoo's own `state`.

### How the bookstore's flow maps onto sale orders

| Bookstore step | Odoo concept |
|----------------|--------------|
| Clerk records items for an identified student | Draft sale order with `partner_id` set |
| Charge slip printed and handed to the student | Confirmed sale order + QWeb PDF report |
| Student pays at the cashier and returns with a receipt | Payment verification step recording the receipt number |
| Goods released | Delivery (`stock.picking`) validated, stock deducted |
| Charge handed to tuition billing | Invoice (`account.move`), collected by the export module |
| Restocking the shelves | Purchase order, goods receipt, physical count |

The gap between slip and release — the part that has no equivalent in a retail POS — is an ordinary state on a
document that already knows how to sit and wait, which is what sale orders are for.

## Alternatives considered

### Extend `point_of_sale`

Keep the touchscreen interface for counter speed and suppress the parts that do not apply: hide payment methods,
disable cash control, bypass session close, and add the slip / verify / release stages on top.

**Rejected.** The suppressed parts are not peripheral to `point_of_sale`; taking payment in-session is its central
assumption, and session close with cash reconciliation is how it posts to accounting. Working against that means
carrying override code through every Odoo upgrade, in a module that changes substantially between versions. It also
does not connect naturally to `purchase` and `stock` for the full lifecycle that is in scope.

The one real cost of rejecting it is counter speed: the POS interface is faster than a backend form during the
enrollment rush. That is addressed directly — a focused counter view with barcode entry and indexed student lookup
— rather than by adopting a module whose remaining 90% is unusable here.

### Build a custom module from scratch

Model the sale, the slip and the release entirely in our own models with no `sale` dependency.

**Rejected.** It would reimplement delivery orders, stock moves, invoicing and purchasing — all of which are in
scope, all of which Odoo already does correctly, and all of which are expensive to get right.

## Consequences

### Positive

- The state machine, the document that waits, and the gate before goods move are all native concepts, not fought-for
  ones
- `purchase` and `stock` integrate without adapters, covering the full lifecycle requirement
- The invoice is the natural source for the tuition billing export
- No dead machinery to configure around: no payment methods, no cash control, no sessions to open and close
- Upgrade-safe: extension by `_inherit` and added fields, with no overrides of core payment or session behaviour
- No reservation contention across the 3 counters, since stock moves only at release

### Negative

- **No touchscreen interface out of the box.** A backend form is slower per transaction than the POS screen, and
  the enrollment rush is when that is felt. Mitigation: a purpose-built counter view, barcode product entry, and an
  indexed lookup on student number. If measurement later shows this is insufficient, a custom OWL counter screen
  over the same sale orders is the escalation — the data model does not change.
- **No offline capability.** `point_of_sale` can keep selling through a network outage; sale orders cannot. The
  bookstore is on campus with the server, so this is judged acceptable, but it is a genuine loss and the manual
  paper fallback should be part of the go-live plan.
- Sale orders carry fields the bookstore does not use (delivery terms, salesperson commissions, and similar), which
  must be hidden from the counter view to keep it uncluttered.

### Revisit this decision if

- The bookstore starts collecting payment directly at the counter, in which case `point_of_sale` becomes a genuine
  candidate again
- Measured counter throughput during enrollment proves inadequate even after the counter view is optimised, and the
  bottleneck is demonstrably the interface rather than the process

## Related

- [Bookstore System Design](../bookstore-system-design.md) — full design and requirements
- [Architecture Vision](../vision.md) — "Leverage stock module for inventory/supply chain", "Use accounting module
  for billing and invoicing"
- [Module Architecture Principles](../../principles/module-architecture.md) — Extension Over Duplication
