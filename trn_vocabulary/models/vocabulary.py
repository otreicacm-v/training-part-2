import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class Vocabulary(models.Model):
    """A collection of codes with a namespace.

    Vocabularies represent standardized code lists used across modules.
    They can be based on international standards (ISO, WHO, UN) or
    project-specific definitions.
    """

    _name = "trn.vocabulary"
    _description = "Vocabulary"
    _order = "name"

    name = fields.Char(
        required=True,
        translate=True,
        help="Human-readable name: 'Gender', 'Civil Status'",
    )
    namespace_uri = fields.Char(
        string="Namespace URI",
        required=True,
        index=True,
        help="Globally unique URI. Examples:\n"
        "- urn:iso:std:iso:5218 (ISO Gender)\n"
        "- urn:tpl:vocab:{name} (project-defined)",
    )
    version = fields.Char(
        help="Version of the vocabulary (e.g., '2024')",
    )
    description = fields.Text(
        translate=True,
        help="Detailed description of this vocabulary and its purpose",
    )
    reference_url = fields.Char(
        string="Reference URL",
        help="Link to official documentation",
    )
    is_system = fields.Boolean(
        string="System Vocabulary",
        default=False,
        help="System vocabularies cannot have codes edited by users",
    )
    domain = fields.Selection(
        selection=[
            ("core", "Core"),
            ("operations", "Operations"),
            ("administrative", "Administrative"),
            ("identity", "Identity"),
            ("regulatory", "Regulatory"),
        ],
        default="core",
        required=True,
        index=True,
        help="Domain area this vocabulary belongs to",
    )
    code_ids = fields.One2many(
        comodel_name="trn.vocabulary.code",
        inverse_name="vocabulary_id",
        string="Codes",
        help="All codes within this vocabulary",
    )
    code_count = fields.Integer(
        string="Code Count",
        compute="_compute_code_count",
        help="Total number of codes in this vocabulary",
    )
    active = fields.Boolean(
        default=True,
        help="Set to inactive to disable this vocabulary without deleting it",
    )

    _unique_namespace = models.Constraint(
        "UNIQUE(namespace_uri)",
        "Namespace URI must be unique",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Check namespace_uri uniqueness before insert.

        Runs before super() so users see a friendly ValidationError
        instead of a raw DB IntegrityError from the UNIQUE constraint.
        """
        for vals in vals_list:
            ns_uri = vals.get("namespace_uri")
            if ns_uri:
                existing = self.with_context(active_test=False).search_count([("namespace_uri", "=", ns_uri)])
                if existing:
                    raise ValidationError(
                        _("Namespace URI '%(uri)s' is already used by another vocabulary.") % {"uri": ns_uri}
                    )
        return super().create(vals_list)

    def write(self, vals):
        """Check namespace_uri uniqueness before update."""
        ns_uri = vals.get("namespace_uri")
        if ns_uri:
            for rec in self:
                existing = self.with_context(active_test=False).search_count(
                    [("namespace_uri", "=", ns_uri), ("id", "!=", rec.id)]
                )
                if existing:
                    raise ValidationError(
                        _("Namespace URI '%(uri)s' is already used by another vocabulary.") % {"uri": ns_uri}
                    )
        return super().write(vals)

    @api.depends("code_ids")
    def _compute_code_count(self):
        """Compute the number of codes using _read_group for efficiency."""
        if not self.ids:
            for rec in self:
                rec.code_count = 0
            return

        code_data = self.env["trn.vocabulary.code"]._read_group(
            domain=[("vocabulary_id", "in", self.ids)],
            groupby=["vocabulary_id"],
            aggregates=["__count"],
        )
        count_map = {vocab.id: count for vocab, count in code_data}
        for rec in self:
            rec.code_count = count_map.get(rec.id, 0)

    def action_view_codes(self):
        """Open codes for this vocabulary."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Codes: %s") % self.name,
            "res_model": "trn.vocabulary.code",
            "view_mode": "list,form",
            "domain": [("vocabulary_id", "=", self.id)],
            "context": {"default_vocabulary_id": self.id},
        }
