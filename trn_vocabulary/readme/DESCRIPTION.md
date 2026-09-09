Configurable vocabulary (code list) infrastructure for trn modules.

Provides two core models:

- **trn.vocabulary** — A named collection of codes with a globally unique namespace URI.
  Vocabularies can represent international standards (ISO 5218 for gender, UN marital status)
  or project-defined code lists (blood types, identifier types).

- **trn.vocabulary.code** — Individual codes within a vocabulary. Each code has a
  machine-readable code, human-readable display name, and a globally unique URI
  computed as `{namespace_uri}#{code}`.

System vocabularies (`is_system=True`) are protected from user modification —
codes can only be managed through module data files.

### Key Capabilities

- Define vocabularies with globally unique namespace URIs
- Manage codes within vocabularies with cached lookups
- System protection prevents user modification of seed data
- Ships with three seed vocabularies: Gender, Civil Status, Blood Type

### Key Models

- `trn.vocabulary` — vocabulary definition with namespace URI
- `trn.vocabulary.code` — individual code with computed URI

### Configuration

Settings > Vocabularies > Vocabularies

### UI Location

Settings > Vocabularies > Vocabularies (list and form views)
Settings > Vocabularies > Codes (flat list of all codes)

### Security

- `group_vocabulary_viewer` — extension point for record rules (read access comes from `base.group_user`)
- `group_vocabulary_officer` — create and edit vocabularies and codes
- `group_vocabulary_manager` — full access including delete

### Extension Points

- **Inheritable models**: `trn.vocabulary` and `trn.vocabulary.code` can be extended via `_inherit`
- **System protection bypass**: `_is_protection_bypassed()` method controls when system vocabularies can be modified
- **Cached lookups**: `get_code(namespace_uri, code)` and `resolve_by_uri(uri)` for efficient code resolution
- **View extension groups**: Form views include invisible `<group>` elements (`additional_description`, `additional_definition`) for downstream modules to inject fields

### Dependencies

- `base` — Odoo core
