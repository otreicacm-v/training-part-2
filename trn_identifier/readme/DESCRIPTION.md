External identifier infrastructure for trn modules.

Stores identifiers issued to a partner — National ID, Passport, Student Number —
as records rather than as fields on `res.partner`. Identifier types are vocabulary
codes, so a deployment adds a new type through a data file instead of a schema
change.

Each identifier carries the globally unique URI of its type, denormalized onto the
record so that lookup by type and value is an indexed search with no join.

### Key Capabilities

- Record any number of typed identifiers against a partner
- Add identifier types through data files, using `trn.vocabulary` codes
- Validate values against a per-type regular expression
- Restrict a type to people, to organizations, or allow both
- Look up a partner by identifier: `env["trn.identifier"].find_partner(system_uri, value)`
- Read one value from a partner: `partner.get_identifier_value(system_uri)`
- Ships four generic identifier types: National ID, Passport, Tax ID, Birth Certificate

### Key Models

- `trn.identifier` — one identifier issued to one partner
- `trn.vocabulary.code` — extended with `id_validation` and `target_type`
- `res.partner` — extended with `identifier_ids` and `identifier_count`

### Configuration

Identifier types are codes in the `urn:tpl:vocab:identifier-type` vocabulary, at
Settings > Vocabularies > Vocabularies. The vocabulary is a system vocabulary, so
types are added through module data files, not the UI.

### UI Location

Identifiers are recorded on the Identifiers tab of a partner form. A flat list for
searching across partners is added under `trn_vocabulary.menu_trn_configuration`,
the shared trn Configuration menu, and is restricted to `base.group_system` by that
parent menu. It moves under the app root menu once a project app module defines one.

### Security

- `group_identifier_viewer` — read identifiers. Granted explicitly rather than to
  `base.group_user`, because identifier values are personally identifying
- `group_identifier_officer` — create and edit identifiers
- `group_identifier_manager` — full access including delete

### Known Constraints

- A value is unique per identifier type. A retired identifier keeps its value
  reserved until the record is deleted, so reissuing a value to a different
  partner requires a manager to delete the old record first.
- Identifier values are classified RESTRICTED by ADR-011 and must never be logged.

### Extension Points

- `trn.identifier` can be extended via `_inherit` — for example to add validity
  dates or an issuing authority
- Form and partner views include invisible `<group>` elements
  (`additional_identifier`, `additional_identifiers`) for downstream modules

### Dependencies

- `trn_vocabulary` — identifier types are vocabulary codes
