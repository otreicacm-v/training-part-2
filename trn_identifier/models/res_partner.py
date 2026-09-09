import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    identifier_ids = fields.One2many(
        comodel_name="trn.identifier",
        inverse_name="partner_id",
        string="Identifiers",
        help="External identifiers issued to this partner",
    )
    identifier_count = fields.Integer(
        string="Identifier Count",
        compute="_compute_identifier_count",
        help="Number of active identifiers held by this partner",
    )

    @api.depends("identifier_ids")
    def _compute_identifier_count(self):
        """Count identifiers per partner in one query rather than one per record."""
        if not self.ids:
            for rec in self:
                rec.identifier_count = 0
            return

        identifier_data = self.env["trn.identifier"]._read_group(
            domain=[("partner_id", "in", self.ids)],
            groupby=["partner_id"],
            aggregates=["__count"],
        )
        count_map = {partner.id: count for partner, count in identifier_data}
        for rec in self:
            rec.identifier_count = count_map.get(rec.id, 0)

    def get_identifier_value(self, system_uri):
        """Return this partner's identifier value for the given type, or False.

        Where a partner holds more than one identifier of the same type — a
        renewed passport, for instance — the first by record order is returned.
        """
        self.ensure_one()
        match = self.identifier_ids.filtered(lambda identifier: identifier.system_uri == system_uri)
        return match[:1].value or False
