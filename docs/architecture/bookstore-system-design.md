# School Bookstore System — Design

Design for a bookstore sales system serving a school with 5,000+ enrolled students across 3 counters.

**Status:** Proposed — no implementation started
**Date:** 2026-09-09
**Related:** [ADR-023](decisions/ADR-023-bookstore-counter-on-sale-orders.md) — foundation decision

## 1. Purpose

The school bookstore sells textbooks, uniforms, supplies and merchandise to enrolled students and staff. This
document records what the system must do, how it is structured, and what remains unanswered.

The defining characteristic of this bookstore, and the fact that shapes the entire design: **the bookstore never
handles money.** Payment is collected by the school cashier's office, in a separate location, or billed to the
student's tuition statement. The bookstore records what is being bought and releases goods once payment is proven.

## 2. Business context

| Aspect | Detail |
|--------|--------|
| Buyers | Students and staff — every transaction is tied to an identified person |
| Counters | 3, operating simultaneously |
| Population | 5,000+ enrolled students |
| Peak load | Enrollment period; low and steady the rest of the year |
| Deployment | Real production system, no fixed go-live deadline |

## 3. Confirmed requirements

### 3.1 Buyer identification

Every transaction is attached to a specific student or staff member. Anonymous sales are not supported.

Student records originate in an **external student information system (SIS)**, which remains the source of truth.
Odoo receives them through a **scheduled file import** (CSV/Excel export from the SIS). The bookstore does not own
student data and does not create students as part of normal operation.

**Exception — provisional records.** During enrollment, a student may reach the counter before appearing in the
import. Clerks may create a provisional record on the spot (student number, name, grade level) so the queue keeps
moving. See [section 8.2](#82-provisional-records) for the safeguards this requires.

### 3.2 Payment routes

Two routes, neither of which involves money changing hands at the bookstore:

| Route | Flow |
|-------|------|
| **Cashier** | Bookstore records items and prints a charge slip → student pays at the school cashier → student returns with the official receipt → bookstore verifies and releases the goods |
| **Tuition charge** | The purchase is charged to the student's account and released immediately; the charge is later handed to the finance office to appear on the tuition statement |

Charging to tuition is **open to all identified buyers with no credit limit and no approval step**. This is a
deliberate business decision, and its risk is recorded in [section 12](#12-risks).

### 3.3 Products and stock

All items are physical, storable goods. No services, permits or ticketed items.

| Category | Notes |
|----------|-------|
| Textbooks / workbooks | Sold individually; ISBN barcodes usually present |
| Uniforms | Sized variants — needs product variant handling and per-size stock |
| School supplies / stationery | Ordinary unit-priced retail |
| Lanyards, merchandise | Ordinary unit-priced retail |
| Cloth | Unit of measure not yet confirmed — see [open question 2](#13-open-questions) |

The system manages the **full stock lifecycle**: supplier purchase orders → goods receipt → sale → physical count,
with on-hand quantities and reorder visibility.

**Stock is not reserved when a slip is printed.** Quantities move only when goods are physically released. This
avoids accumulating dead reservations from slips that are never paid, at the cost of a rarer failure described in
[section 12](#12-risks).

### 3.4 Pricing

A single price per product for every buyer. No student/staff tiers, no scholarship rates, no clerk-entered
discounts, no per-grade prescribed booklists.

Prices are **VAT-inclusive** — the displayed price is what the buyer pays, with the tax portion broken out for
accounting.

### 3.5 Roles

| Role | Can do |
|------|--------|
| Bookstore clerk | Work the counter: look up buyers, record items, print slips, verify payment, release goods |
| Stockroom staff | Purchase orders, goods receipt, physical counts — not the sales counter |
| Bookstore manager | Everything above, plus products, prices, stock adjustments, cancelling slips, reports |

No separate finance role was identified. The tuition billing handover therefore falls to the manager — see
[open question 4](#13-open-questions).

### 3.6 Reporting

- Daily sales / goods released, by clerk and payment route — the operational reconciliation report
- Charges to hand to tuition billing, per student, per period — the integration deliverable
- Stock on hand and movement — largely inherited from Odoo's inventory reporting

Per-student purchase history is not a required report, though the data exists and can be queried.

### 3.7 Hardware

Barcode scanners and ordinary PCs. **No receipt printer** — the charge slip is generated as a PDF and printed on a
standard office printer. The design must not assume thermal receipt hardware.

## 4. Explicitly out of scope

Recording these prevents them being reintroduced by assumption:

- Cash handling, cash drawers, cash counts and session close at the bookstore
- Returns, refunds and exchanges — all sales are final
- Prepaid wallets or stored-value balances
- Discounts, price overrides and multiple price tiers
- Prescribed booklists / per-grade product sets
- Credit limits and approval workflows on tuition charges
- Card and e-wallet payment at the bookstore counter

## 5. Module architecture

```
Layer 3: trn_bookstore_billing    Tuition charge export to the finance office
              |
Layer 2: trn_bookstore            Counter flow: slip -> verify payment -> release
              |
Layer 1: trn_school_base          Students, grade levels, SIS import
              |
Layer 0: sale, stock, purchase, account, product
```

### 5.1 Why three modules

**`trn_school_base` is separate** because students are not a bookstore concept. If the school later puts anything
else on Odoo — a library, a clinic, an events system — it inherits the same student records rather than a
bookstore-shaped copy of them. The SIS import belongs here for the same reason.

**`trn_bookstore_billing` is separate** because it is the one component whose shape is dictated by a system we have
not yet seen. When the finance office specifies the format they can load, exactly one module changes.

**`trn_bookstore` holds the counter flow**, which is the part that is genuinely specific to how this bookstore works.

### 5.2 Manifest settings

| Module | `application` | `auto_install` | Rationale |
|--------|--------------|----------------|-----------|
| `trn_school_base` | `False` | `False` | Foundation library, not a user-facing app |
| `trn_bookstore` | `True` | `False` | The app bookstore staff open |
| `trn_bookstore_billing` | `False` | `False` | Optional extension, installed when finance is ready |

## 6. Data model

### 6.1 Students on `res.partner`

Students extend `res.partner` rather than living in a parallel model. This follows the project's established
position (see [vision.md](vision.md) — "Extend `res.partner` for domain-specific entities") and is also forced by
the design: sale orders require a partner, and a parallel student model would mean maintaining a shadow partner for
every student anyway.

Fields added by `trn_school_base`:

| Field | Type | Notes |
|-------|------|-------|
| `is_student` | Boolean | Marks the partner as a student |
| `student_number` | Char | The SIS identifier; unique, indexed, the import merge key |
| `grade_level_id` | Many2one → `trn.grade.level` | |
| `section_id` | Many2one → `trn.school.section` | |
| `school_year_id` | Many2one → `trn.school.year` | |
| `enrollment_state` | Selection | `enrolled` / `not_enrolled` — never delete, only mark |
| `is_provisional` | Boolean | Clerk-created, awaiting confirmation from the SIS import |
| `last_import_date` | Datetime | When the SIS import last touched this record |

New models in `trn_school_base`:

| Model | Purpose |
|-------|---------|
| `trn.grade.level` | Grade / year level reference data |
| `trn.school.section` | Section or class within a grade level |
| `trn.school.year` | Academic year, with a current-year flag |
| `trn.student.import` | One record per import run — file, counts, errors, timestamp |

### 6.2 Counter transactions on `sale.order`

A counter transaction is a `sale.order`, extended by `trn_bookstore`:

| Field | Type | Notes |
|-------|------|-------|
| `is_bookstore_order` | Boolean | Distinguishes bookstore orders from any other sales |
| `bookstore_state` | Selection | The counter state machine — see [section 7](#7-counter-flow) |
| `payment_route` | Selection | `cashier` / `tuition_charge` |
| `slip_number` | Char | From an `ir.sequence`; printed on the slip as text and barcode |
| `payment_reference` | Char | The cashier's official receipt number |
| `payment_verified_by_user_id` | Many2one → `res.users` | Who released against which receipt |
| `payment_verified_date` | Datetime | |

`bookstore_state` is kept **separate from Odoo's own `state` field** rather than extending it. Sale order state is
load-bearing inside Odoo — reports, automated actions and the delivery mechanism all read it — and adding states to
it invites breakage on every upgrade. A parallel field costs one extra column and keeps our state machine ours.

The state names deviate from the project's standard vocabulary
([naming-conventions.md](../principles/naming-conventions.md)) because the domain names are clearer to the staff who
will use them. `draft` and `cancelled` follow the standard; `slip_issued`, `payment_verified` and `released` are
domain-specific and deliberate.

## 7. Counter flow

```
   draft  --confirm-->  slip_issued  --verify-->  payment_verified  --release-->  released
     |                       |                          |
     +--------------- cancelled <-----------------------+
```

| State | Meaning | What happens |
|-------|---------|--------------|
| `draft` | Clerk is building the transaction | Buyer attached, items scanned |
| `slip_issued` | Slip printed | Sale order confirmed, slip number allocated, PDF generated |
| `payment_verified` | Payment proven | Receipt number recorded against the slip |
| `released` | Goods handed over | Delivery validated, stock deducted |
| `cancelled` | Abandoned | No stock movement occurred, so nothing to reverse |

**Delivery is blocked until `payment_verified`** on the cashier route. This is the control that replaces a cash
drawer: goods cannot leave without proof of payment, enforced by the system rather than by the clerk's memory.

The tuition-charge route skips verification and moves from `slip_issued` straight to `released`, because there are
no limits or approvals to check. The charge accrues as an invoice for `trn_bookstore_billing` to export.

**The payment verification step is behind a hook.** Whether the clerk keys the receipt number by hand or scans it
against data from the cashier's system is still open ([question 1](#13-open-questions)); isolating that step means
answering it later changes one method, not the flow.

## 8. SIS import

### 8.1 Import behaviour

- Reads a CSV/Excel export from the SIS on a schedule, with a manual "run now" action for staff
- **Idempotent**, matching on `student_number` — reruns update, never duplicate
- Students absent from the export are marked `not_enrolled`, **never deleted**, because they may have historical
  transactions and account charges
- Each run creates a `trn.student.import` record with row counts and per-row errors, so a failed import is
  diagnosable without reading server logs
- A malformed row fails that row alone; the run continues

### 8.2 Provisional records

When a clerk creates a student at the counter:

- The record is flagged `is_provisional` and requires student number, name and grade level
- It appears in a manager-only **"Unconfirmed students"** view
- The next import matches on `student_number` and **promotes** the record — filling in the authoritative fields and
  clearing the flag — rather than creating a second one
- A student number already present on another partner is rejected at entry, catching the duplicate before it exists

This matters more than it appears. A duplicated student means a tuition charge landing on the wrong statement, or
splitting one family's charges across two records. The safeguards are cheap now and expensive to retrofit.

## 9. Security

| Group | Maps to |
|-------|---------|
| `group_bookstore_officer` | Clerk — counter operations only |
| `group_bookstore_manager` | Manager — products, prices, stock adjustments, cancellations, reports |
| Stockroom staff | Odoo's `stock.group_stock_user` + `purchase.group_purchase_user`, plus bookstore read access |

Stockroom staff reuse Odoo's own inventory and purchasing groups rather than getting a bespoke group, because their
work *is* Odoo's standard receiving and counting flow.

Requirements:

- Clerks cannot write to `product.template`, `product.product` price fields, or `stock.quant`
- Clerks cannot cancel a slip once it reaches `payment_verified` — that is a manager action, since it means goods
  were paid for and not released
- Every model gets `ir.model.access.csv` entries; per
  [access-rights.md](../principles/access-rights.md), related models are covered too, not just the headline ones
- Tests run as clerk and manager users, not as admin, so ACL gaps surface in CI rather than at the counter

## 10. Tuition billing export

`trn_bookstore_billing` collects tuition-route charges for a period and produces the file the finance office loads
into the student's statement.

The output format is unknown until the finance office specifies it, so the module is designed around a single
export method with the selection logic (which charges, which period, which students) separated from the formatting.
A change of format touches the formatter alone.

An export batch is recorded so the same charge is not handed over twice — the failure mode here is a student billed
twice for the same textbook, which is worth a table to prevent.

## 11. Non-functional considerations

**Counter speed.** Three counters at enrollment means queues. Lookup by scanned or typed `student_number` must be
immediate, which needs an index and a search view that does not load unnecessary related data. Product entry is by
barcode scan.

**Concurrency.** Because stock is not reserved, three clerks selling the same product do not contend for
reservations, which removes the most common source of POS-style lock contention. Stock deduction happens once at
release.

**Barcode coverage.** Textbooks carry ISBNs. Uniforms by size, cloth, lanyards and merchandise generally do not.
Someone must generate and apply labels before go-live, or the scanner delivers no benefit on precisely the items
where sizing mistakes are most likely. This is an operational task, not a coding one, and it needs an owner.

## 12. Risks

| Risk | Consequence | Mitigation |
|------|-------------|------------|
| Student pays at the cashier, item is gone on return | Money collected for goods that cannot be delivered, and no refund path exists at the bookstore | Show live on-hand quantity before the slip prints and warn on low stock. The policy for when it happens anyway is [open question 3](#13-open-questions) |
| Unlimited tuition charging | Uncollected balances the bookstore cannot control | Accepted business decision. Reporting on outstanding charges gives finance early visibility |
| Duplicate students from provisional records | Charges on the wrong tuition statement | Unique student number, promote-on-import, manager review queue ([section 8.2](#82-provisional-records)) |
| Stale SIS data at enrollment | Newly enrolled students blocked at the counter | Provisional records, plus the option of more frequent imports during enrollment |
| Barcode labelling not done before go-live | Counter is slower than the paper process it replaces | Identify the owner and start labelling well before launch |
| Manual receipt verification | A clerk can release goods against a receipt that was never paid | Recorded verifier and receipt number make it auditable; integrating with the cashier's system would remove it entirely |

## 13. Open questions

Each blocks a specific piece of work, not the project:

| # | Question | Blocks | Needs |
|---|----------|--------|-------|
| 1 | Does the cashier's office run on this same Odoo database, or separate software? | Final form of the payment verification step | Check with the cashier's office |
| 2 | Is cloth sold by length (decimal quantities) or as pre-cut packs? | Product and unit-of-measure setup | Check with the bookstore |
| 3 | What happens when a student has paid and the item is out of stock on return? | The release step's exception path | Business policy decision |
| 4 | Who owns the handover of charges to tuition billing, and in what format? | `trn_bookstore_billing` | Finance office |
| 5 | Is there an existing Odoo installation, and which edition? | Deployment planning | Check with school IT |

Question 5 does not block development: the design targets Odoo 19 Community, which also runs unchanged on Enterprise.

## 14. Build sequence

| Phase | Deliverable | Why this order |
|-------|-------------|----------------|
| 1 | `trn_school_base` — student model, grade levels, SIS import, provisional records | Everything depends on students existing; independently testable against a sample SIS export |
| 2 | `trn_bookstore` products and stock — categories, variants, barcodes, purchase and receiving | Stock must be real before sales against it mean anything |
| 3 | `trn_bookstore` counter flow — the state machine, slip PDF, payment verification, release | The core of the system; needs phases 1 and 2 in place |
| 4 | Security groups, access rights, record rules | Applied against the finished models, then tested as each role |
| 5 | Operational reports — daily sales, stock movement | Built once there is data to report on |
| 6 | `trn_bookstore_billing` | Waits on open question 4 |

Phase 4 is listed after the models exist, but access rights are written alongside each model as it is built — the
phase is where they are reviewed and tested as a whole, not where they are first considered.
