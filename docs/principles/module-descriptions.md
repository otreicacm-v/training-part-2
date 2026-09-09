# Module Descriptions

Best practices for writing `readme/DESCRIPTION.md` (or `.rst`) files for project modules.

## Audience

Three groups read module descriptions, each needing different things:

- **Developers** need model names, extension points, and dependency relationships to write code against the module.
- **Implementers** need configuration steps, menu paths, and security context to deploy and support the module.
- **AI agents** need structured, non-repetitive content to reason about module capabilities and generate accurate code.

All three groups are harmed by marketing language, repetition, and missing technical detail.

## Format

- File: `readme/DESCRIPTION.md` (Markdown) or `readme/DESCRIPTION.rst` (reStructuredText)
- Processed by the OCA README generator toolchain
- Keep total length between 25–60 lines. If you need more, the module may be doing too much.

## Template

Use this structure. Every section is expected unless marked optional.

```markdown
{One paragraph, 2–4 sentences. What the module does, who it serves, and what problem it solves. No adjectives like
"robust", "comprehensive", or "cutting-edge".}

### Key Capabilities

- {Capability}: {One sentence describing what it does concretely}
- ...

### Key Models

| Model              | Description            |
| ------------------ | ---------------------- |
| `trn.example`      | {One-line description} |
| `trn.example.line` | {One-line description} |

### Configuration

After installing:

1. Navigate to **Settings > Example > Configuration**
2. {Required setup step}
3. ...

### UI Location

- **Menu**: {App} > Example > Feature
- **Form**: Accessible from the main entity form under the "Example" tab

### Security

| Group                            | Access    |
| -------------------------------- | --------- |
| `trn_security.group_trn_officer` | Read      |
| `trn_security.group_trn_manager` | Full CRUD |

### Extension Points _(optional)_

- Override `_compute_example()` to customize calculation logic
- Inherit `trn.example` to add fields exposed through the API

### Dependencies

`base`, `mail`, `trn_security`, `trn_vocabulary`
```

## Principles

1. **Say it once.** Never repeat the same capability in multiple sections. The overview paragraph covers "what"; the
   capabilities list covers "how"; the models table covers "which objects". Each section has a distinct job.

2. **Name the models.** Every module introduces or extends models. List them by technical name (`trn.alert.rule`, not
   "alert rules"). Developers cannot use what they cannot find.

3. **Name the menu paths.** Tell implementers where features appear: `{App} > Orders > Order Types`. Do not
   assume they will search the menu tree.

4. **Name the security groups.** State which groups get which level of access. Do not say "authorized users" — name the
   XML ID.

5. **Be concrete.** Replace "enables robust management of..." with "stores X, computes Y, triggers Z". Every sentence
   should contain a noun a developer could grep for.

6. **No marketing language.** Ban these words and phrases: "comprehensive", "robust", "cutting-edge", "seamless",
   "significantly expands", "streamlines", "enhances", "leverages", "facilitates". Describe what the code does, not how
   impressed the reader should be.

7. **List dependencies, don't narrate them.** A flat list of technical module names is more useful than a paragraph per
   dependency explaining what each one "provides foundational capabilities" for.

8. **Include configuration steps.** If the module requires any setup after installation (cron jobs, system parameters,
   menu configuration), document the exact steps.

9. **Document extension points.** If the module exposes hook methods, inheritable models, or overridable computations,
   list them. This is what makes a description useful to downstream developers.

10. **Keep it short.** Target 25–60 lines. If the description exceeds 60 lines, look for repetition or narration that
    can be cut.

## Verification Rules (MUST follow)

These rules exist because automated and AI-generated descriptions frequently introduce specific categories of errors.
Every claim in a description **must be verified against the source code** before writing.

### Menu paths and UI Location

- **Read the actual `<menuitem>` XML records** to determine menu hierarchy. Trace `parent=` attributes up to the
  top-level menu to get the full path. Do NOT guess menu names from the module name or manifest summary.
- **If a module defines no `<menuitem>` records**, do not fabricate menu paths. State where the UI is actually accessed
  (e.g., "Accessed via stat button on the main form" or "No standalone menu; extends existing views").
- **Tab names must match the `string=` attribute** of `<page>` elements in view XML. Do not guess tab names. If
  relationships are inside `<page string="Identity">`, write "Identity tab", not "Relationships tab".
- **Stat buttons are not tabs.** If a view adds a `<button>` in the `button_box` div, describe it as a stat button, not
  a tab or page.
- **Configuration submenus must exist.** If a module defines a Configuration parent menu but no child `<menuitem>`
  records under it, do not list configuration submenus that don't exist. State "Configuration menu exists but has no
  submenus in this module" or omit the path.

### Dependencies

- **Copy the `depends` list exactly from `__manifest__.py`.** Do not add modules that are not listed (e.g., do not add
  `base` or `mail` just because they are commonly used — only list them if they appear in the manifest).
- **Do not remove modules** that are in the manifest's `depends` list.

### Security

- **Read `ir.model.access.csv`** for actual permission values (`perm_read`, `perm_write`, `perm_create`, `perm_unlink`).
- **Do not say "Full CRUD"** if `perm_unlink=0` in the CSV, or if the Python model overrides `unlink()` to block
  deletion. Say "Read/Write/Create (no delete)" instead.
- **Do not say "Read-only"** if the CSV grants write or create permissions. Report what the CSV actually says.
- **Only document groups that have ACL entries** in the module's CSV. Do not invent access levels for groups that have no
  entries.

### Models

- **Use the exact `_name` attribute** from the Python class. Do not abbreviate or rename models.
- **Do not list legacy/unused models** as "key models." If a model exists in the code but is not referenced by any other
  model in the module (no foreign keys point to it, no views reference it), note it as legacy or omit it.
- **Verify field names and selection values** before documenting states or workflows. If the code defines states as
  `draft`, `pending_validation`, `approved`, `cancelled`, do not write `distributed` or other values that don't exist.

### Capabilities

- **Only document implemented behavior.** If a field is defined but never read or used in any method, do not describe it
  as a capability. A defined-but-unused field is not a feature.
- **Do not claim escalation, notifications, or automation** unless the corresponding Python method actually contains
  logic (not just a placeholder field or empty hook).

## Anti-Patterns

### Repetition across sections

A hypothetical module description explains the same capability three times: once in the overview, once in the "Purpose"
bullets, and once in "Additional Functionality":

> **Before (3 sections all saying the same thing):**
>
> Overview: "provides robust cryptographic services... encryption, decryption, digital signing..."
>
> Purpose bullet: "Encrypts and Decrypts Data: Protects confidential information..."
>
> Additional Functionality: "Secure Data Protection (Encryption and Decryption): This feature allows the system to
> encrypt sensitive data..."
>
> **After (say it once):**
>
> Overview: "Provides encryption, decryption, digital signing, and key management using JWK/JWKS standards."
>
> Then list models and configuration — no further explanation of what encryption means.

### Marketing fluff

A module description ends with:

> "significantly expands the platform's capabilities... a comprehensive solution for managing a wider range of
> business workflows..."

This tells the reader nothing actionable. Replace with concrete details about what models exist and how to configure
them.

### Narrated dependencies

A module description devotes a paragraph to each dependency:

> **Before (paragraph per dependency):**
>
> "[Training Sample Vocabulary](trn_vocabulary): Leverages vocabulary-based lookups for status codes and other
> coded values, ensuring consistency in terminology management."
>
> _(more paragraphs follow)_
>
> **After (flat list):**
>
> `trn_vocabulary`, `trn_security`, `base`, `mail`

### Fabricated menu paths

A module description says:

> Navigate to **Operations > Configuration > Order Types**

But the actual XML menuitem has `parent="trn_order.trn_order_config_menu_root"`, which resolves to
**Orders > Configuration > Order Types**. The top-level menu name was guessed from context, not read from the
XML. Always trace `parent=` attributes to the root `<menuitem>` to build the full path.

### Invented tabs and UI elements

A module description says:

> Identifiers: Accessible from partner forms under "Identifiers" tab

But the actual view XML has `<page string="Identity">` — identifiers are inside the Identity tab. Another module
description says "Orders tab" when the actual implementation is a stat button in the `button_box`. Always check `<page
string="...">` for tab names and distinguish stat buttons from tabs.

### Overclaimed security permissions

A module description says the manager group has "Full CRUD on records" but the CSV has
`perm_unlink=0`. The `trn_vocabulary` description says managers have "Full CRUD on definitions" but system-protected
codes block deletion. Always cross-reference CSV permissions with Python `unlink()` overrides.

### Phantom dependencies

A module description lists `base` and `mail` as dependencies, but neither appears in the module's
`__manifest__.py` `depends` list. They may be available transitively, but the description must match the manifest
exactly.

### Missing technical names

A module description discusses "flexible user roles" and "granular geographic access control" across 90
lines but never names the models, security groups, or menu paths that implement these features. A developer reading this
description cannot write code against it without reading the source.

## Gold Standard Example

A complete description for a hypothetical `trn_order` module, demonstrating all sections:

```markdown
Manages orders from creation to fulfillment. Tracks order type, assigned user, line items, and
associated documents. Supports standard, urgent, and recurring workflows with vocabulary-based classification.

### Key Capabilities

- Create orders with submission/approval workflow
- Track order lifecycle: draft → submitted → approved → fulfilled
- Link line items, notes, and attachments to orders
- Classify orders by type and category using `trn.vocabulary`

### Key Models

| Model                   | Description                                        |
| ----------------------- | -------------------------------------------------- |
| `trn.order`         | An order with status tracking and user assignment |
| `trn.order.line`    | Individual line items belonging to an order        |

### Configuration

After installing:

1. Navigate to **{App} > Configuration > Order Types**
2. Define order types (standard, urgent, recurring)
3. Set up category-specific defaults under **{App} > Configuration > Categories**

### UI Location

- **Menu**: {App} > Orders > All Orders
- **Configuration**: {App} > Configuration > Order Types
- **Form**: Accessible from the main entity form via the "Orders" stat button

### Security

| Group                                | Access                             |
| ------------------------------------ | ---------------------------------- |
| `trn_security.group_order_viewer` | Read orders                    |
| `trn_security.group_order_officer`| Read/write/create orders       |
| `trn_security.group_order_manager`| Full CRUD on orders and config |

### Extension Points

- Override `_pre_submit_hook()` / `_post_approval_hook()` for custom workflow logic
- Inherit `trn.order` to add fields exposed through the API

### Dependencies

`base`, `mail`, `trn_security`, `trn_vocabulary`
```

This example is ~40 lines, names every model, includes menu paths, lists security groups by XML ID, and documents
extension points. A developer, implementer, or AI agent can each find what they need without reading the source code.
