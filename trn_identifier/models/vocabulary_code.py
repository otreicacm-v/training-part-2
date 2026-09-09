import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class VocabularyCode(models.Model):
    """Adds identifier-specific configuration to vocabulary codes.

    These fields are only meaningful for codes in the identifier-type
    vocabulary. They live here rather than in trn_vocabulary so that the
    base vocabulary module stays free of identifier concerns.
    """

    _inherit = "trn.vocabulary.code"

    id_validation = fields.Char(
        string="Value Pattern",
        help="Regular expression that identifier values of this type must match, "
        "for example ^[0-9]{9}$. Leave empty to accept any value.",
    )
    target_type = fields.Selection(
        selection=[
            ("person", "Person"),
            ("organization", "Organization"),
            ("both", "Both"),
        ],
        default="both",
        help="Whether this identifier type can be issued to people, to organizations, or to either",
    )

    @api.constrains("id_validation")
    def _check_id_validation_is_valid_regex(self):
        """Reject a malformed pattern here, rather than when an identifier uses it."""
        for rec in self:
            if not rec.id_validation:
                continue
            try:
                re.compile(rec.id_validation)
            except re.error as exc:
                raise ValidationError(
                    _("'%(pattern)s' is not a valid regular expression: %(error)s")
                    % {"pattern": rec.id_validation, "error": exc}
                ) from exc
