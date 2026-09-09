import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Namespace of the vocabulary holding identifier types. Codes in this
# vocabulary are the only valid values for trn.identifier.type_id.
IDENTIFIER_TYPE_NAMESPACE = "urn:tpl:vocab:identifier-type"


class Identifier(models.Model):
    """An external identifier issued to a partner by some authority.

    Each identifier is typed by a vocabulary code — National ID, Passport,
    Student Number — so a deployment adds new identifier types through a data
    file rather than a schema change. This is why identifier values are not
    stored as fields on res.partner.

    Identifier values are personally identifying and are classified RESTRICTED
    by ADR-011. They must never be written to logs.
    """

    _name = "trn.identifier"
    _description = "Identifier"
    _order = "partner_id, type_id"
    _rec_name = "value"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
        required=True,
        ondelete="cascade",
        index=True,
        help="The person or organization this identifier was issued to",
    )
    type_id = fields.Many2one(
        comodel_name="trn.vocabulary.code",
        string="Identifier Type",
        required=True,
        ondelete="restrict",
        index=True,
        domain=[("namespace_uri", "=", IDENTIFIER_TYPE_NAMESPACE)],
        help="Kind of identifier, for example National ID or Student Number",
    )
    system_uri = fields.Char(
        string="Namespace",
        related="type_id.uri",
        store=True,
        index=True,
        help="Globally unique URI of the identifier type, denormalized so that "
        "lookups by type and value do not join the vocabulary table",
    )
    value = fields.Char(
        required=True,
        index=True,
        help="The identifier exactly as issued. Personally identifying — never log this value.",
    )
    active = fields.Boolean(
        default=True,
        help="Set to inactive to retire an identifier without deleting it",
    )

    # Two partners cannot hold the same identifier value for the same type.
    # Retired (inactive) identifiers still occupy their value: reissuing a
    # retired value to a different partner requires deleting the old record.
    _unique_value_per_system = models.Constraint(
        "UNIQUE(system_uri, value)",
        "This identifier value is already registered for this identifier type.",
    )

    def _compute_display_name(self):
        """Show the type alongside the value, since a bare value is ambiguous."""
        for rec in self:
            if rec.type_id and rec.value:
                rec.display_name = f"{rec.type_id.display}: {rec.value}"
            else:
                rec.display_name = rec.value or ""

    @api.constrains("value", "type_id")
    def _check_value_matches_type_pattern(self):
        """Enforce the identifier type's value pattern, when it defines one."""
        for rec in self:
            pattern = rec.type_id.id_validation
            if not pattern:
                continue
            try:
                matches = re.fullmatch(pattern, rec.value or "")
            except re.error as exc:
                # A malformed pattern is a configuration fault on the type,
                # not bad input from the user entering the identifier.
                raise ValidationError(
                    _(
                        "Identifier type '%(type)s' has an invalid value pattern and cannot "
                        "be used. Correct the pattern on the identifier type, then try again. "
                        "Error: %(error)s"
                    )
                    % {"type": rec.type_id.display, "error": exc}
                ) from exc
            if not matches:
                raise ValidationError(
                    _(
                        "The value entered does not match the format required for "
                        "'%(type)s'. Expected format: %(pattern)s"
                    )
                    % {"type": rec.type_id.display, "pattern": pattern}
                )

    @api.constrains("type_id", "partner_id")
    def _check_type_applies_to_partner(self):
        """Stop a person-only identifier landing on a company, and vice versa."""
        for rec in self:
            target = rec.type_id.target_type
            if target == "person" and rec.partner_id.is_company:
                raise ValidationError(
                    _(
                        "'%(type)s' can only be issued to a person, but '%(partner)s' is a "
                        "company. Choose an identifier type that applies to organizations."
                    )
                    % {"type": rec.type_id.display, "partner": rec.partner_id.name}
                )
            if target == "organization" and not rec.partner_id.is_company:
                raise ValidationError(
                    _(
                        "'%(type)s' can only be issued to an organization, but '%(partner)s' is "
                        "a person. Choose an identifier type that applies to people."
                    )
                    % {"type": rec.type_id.display, "partner": rec.partner_id.name}
                )

    @api.constrains("type_id")
    def _check_type_is_an_identifier_type(self):
        """Reject vocabulary codes that are not identifier types.

        The field domain guides the UI, but does not stop code or an import
        from assigning, say, a blood type as an identifier type.
        """
        for rec in self:
            if rec.type_id.namespace_uri != IDENTIFIER_TYPE_NAMESPACE:
                raise ValidationError(
                    _(
                        "'%(code)s' is not an identifier type. Identifier types belong to the "
                        "vocabulary '%(namespace)s'."
                    )
                    % {"code": rec.type_id.display, "namespace": IDENTIFIER_TYPE_NAMESPACE}
                )

    @api.model
    def find_partner(self, system_uri, value):
        """Return the partner holding this identifier, or an empty recordset.

        This is the intended lookup for scanning an ID at a counter: both
        columns are indexed, so it does not join the vocabulary table.
        """
        identifier = self.search(
            [("system_uri", "=", system_uri), ("value", "=", value)],
            limit=1,
        )
        return identifier.partner_id
