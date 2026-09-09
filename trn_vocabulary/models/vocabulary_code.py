import logging

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class VocabularyCode(models.Model):
    """A single code within a vocabulary.

    Represents individual values within a vocabulary (e.g., 'Male' in Gender,
    'A+' in Blood Type). Each code has a globally unique URI for
    interoperability.
    """

    _name = "trn.vocabulary.code"
    _description = "Vocabulary Code"
    _order = "sequence, code"
    _rec_name = "display"

    def _is_protection_bypassed(self):
        """Check if system vocabulary protection should be bypassed.

        Protection is bypassed during:
        - XML data loading (install_xmlid context)
        - Test fixtures with explicit bypass flag
        """
        return "install_xmlid" in self.env.context or self.env.context.get("_test_bypass_system_protection")

    vocabulary_id = fields.Many2one(
        comodel_name="trn.vocabulary",
        string="Vocabulary",
        required=True,
        ondelete="restrict",
        index=True,
        help="The vocabulary this code belongs to",
    )
    namespace_uri = fields.Char(
        string="Namespace URI",
        related="vocabulary_id.namespace_uri",
        store=True,
        index=True,
        help="Globally unique namespace URI from vocabulary",
    )
    code = fields.Char(
        required=True,
        index=True,
        help="Machine-readable code (e.g., '1', 'M', 'A+')",
    )
    display = fields.Char(
        string="Display Label",
        required=True,
        translate=True,
        help="Human-readable label",
    )
    definition = fields.Text(
        translate=True,
        help="Formal definition of what this code means",
    )
    sequence = fields.Integer(
        default=10,
        help="Order of display - lower values appear first",
    )
    uri = fields.Char(
        string="Code URI",
        compute="_compute_uri",
        store=True,
        readonly=False,
        index=True,
        help="Globally unique URI for this code (computed by default, can be overridden)",
    )
    active = fields.Boolean(
        default=True,
        help="Set to inactive to disable this code without deleting it",
    )
    _unique_code = models.Constraint(
        "UNIQUE(vocabulary_id, code)",
        "Code must be unique within vocabulary",
    )
    _unique_uri = models.Constraint(
        "UNIQUE(uri)",
        "URI must be globally unique",
    )

    @api.depends("vocabulary_id.namespace_uri", "code")
    def _compute_uri(self):
        """Compute the globally unique URI for this code.

        Format: {vocabulary.namespace_uri}#{code}
        """
        for rec in self:
            if rec.vocabulary_id and rec.code:
                rec.uri = f"{rec.vocabulary_id.namespace_uri}#{rec.code}"
            else:
                rec.uri = False

    def _compute_display_name(self):
        """Return display name with code in parentheses."""
        for rec in self:
            if rec.display and rec.code:
                rec.display_name = f"{rec.display} ({rec.code})"
            else:
                rec.display_name = rec.display or rec.code or ""

    @api.model_create_multi
    def create(self, vals_list):
        """Protect system vocabularies and check uniqueness before insert.

        The duplicate check runs before super() so users see a friendly
        ValidationError instead of a raw DB IntegrityError from the
        UNIQUE(vocabulary_id, code) constraint.
        """
        if not self._is_protection_bypassed():
            for vals in vals_list:
                vocab_id = vals.get("vocabulary_id")
                if vocab_id:
                    vocab = self.env["trn.vocabulary"].browse(vocab_id)
                    if vocab.is_system:
                        raise UserError(
                            _(
                                "Cannot add codes to system vocabulary '%(vocab)s'. "
                                "Modify through module data instead."
                            )
                            % {"vocab": vocab.name}
                        )

        for vals in vals_list:
            vocab_id = vals.get("vocabulary_id")
            code = vals.get("code")
            if vocab_id and code:
                existing = self.with_context(active_test=False).search_count(
                    [("vocabulary_id", "=", vocab_id), ("code", "=", code)]
                )
                if existing:
                    vocab = self.env["trn.vocabulary"].browse(vocab_id)
                    raise ValidationError(
                        _("Code '%(code)s' already exists in vocabulary '%(vocab)s'.")
                        % {"code": code, "vocab": vocab.name}
                    )

        records = super().create(vals_list)
        self.env.registry.clear_cache()
        return records

    def write(self, vals):
        """Protect system vocabulary codes from modification."""
        if not self._is_protection_bypassed():
            for rec in self:
                if rec.vocabulary_id.is_system:
                    allowed_fields = {"active", "sequence"}
                    disallowed = set(vals.keys()) - allowed_fields
                    if disallowed:
                        raise UserError(
                            _(
                                "Cannot modify system vocabulary codes. "
                                "Only active and sequence fields can be changed. "
                                "Attempted to change: %(fields)s"
                            )
                            % {"fields": ", ".join(sorted(disallowed))}
                        )

        # Check code uniqueness before DB write to provide user-friendly error
        new_code = vals.get("code")
        new_vocab_id = vals.get("vocabulary_id")
        if new_code or new_vocab_id:
            for rec in self:
                check_vocab = new_vocab_id or rec.vocabulary_id.id
                check_code = new_code or rec.code
                existing = self.with_context(active_test=False).search_count(
                    [
                        ("vocabulary_id", "=", check_vocab),
                        ("code", "=", check_code),
                        ("id", "!=", rec.id),
                    ]
                )
                if existing:
                    vocab = self.env["trn.vocabulary"].browse(check_vocab)
                    raise ValidationError(
                        _("Code '%(code)s' already exists in vocabulary '%(vocab)s'.")
                        % {"code": check_code, "vocab": vocab.name}
                    )

        result = super().write(vals)
        if "code" in vals or "active" in vals or "uri" in vals:
            self.env.registry.clear_cache()
        return result

    def unlink(self):
        """Protect system vocabulary codes from deletion."""
        if not self._is_protection_bypassed():
            for rec in self:
                if rec.vocabulary_id.is_system:
                    raise UserError(
                        _("Cannot delete codes from system vocabulary '%(vocab)s'.") % {"vocab": rec.vocabulary_id.name}
                    )
        result = super().unlink()
        self.env.registry.clear_cache()
        return result

    @api.constrains("vocabulary_id", "code")
    def _check_code_unique(self):
        """Raise a user-friendly error instead of a raw DB IntegrityError."""
        for rec in self:
            duplicate = self.with_context(active_test=False).search_count(
                [
                    ("vocabulary_id", "=", rec.vocabulary_id.id),
                    ("code", "=", rec.code),
                    ("id", "!=", rec.id),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _("Code '%(code)s' already exists in vocabulary '%(vocab)s'.")
                    % {"code": rec.code, "vocab": rec.vocabulary_id.name}
                )

    @api.model
    @tools.ormcache("namespace_uri", "code")
    def _get_code_id(self, namespace_uri, code):
        """Cached lookup by namespace + code.

        Returns record ID if found, False otherwise.
        """
        rec = self.search(
            [
                ("namespace_uri", "=", namespace_uri),
                ("code", "=", code),
                ("active", "=", True),
            ],
            limit=1,
        )
        return rec.id if rec else False

    @api.model
    def get_code(self, namespace_uri, code):
        """Get code record by namespace URI and code value.

        Returns code record if found, empty recordset otherwise.
        """
        code_id = self._get_code_id(namespace_uri, code)
        return self.browse(code_id) if code_id else self.browse()

    @api.model
    @tools.ormcache("uri")
    def _get_code_id_by_uri(self, uri):
        """Cached lookup by URI.

        Returns record ID if found, False otherwise.
        """
        rec = self.search(
            [
                ("uri", "=", uri),
                ("active", "=", True),
            ],
            limit=1,
        )
        return rec.id if rec else False

    @api.model
    def resolve_by_uri(self, uri):
        """Resolve a code by its URI.

        Returns code record if found, empty recordset otherwise.
        """
        code_id = self._get_code_id_by_uri(uri)
        return self.browse(code_id) if code_id else self.browse()
