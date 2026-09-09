from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestIdentifierSecurity(TransactionCase):
    """Tests for identifier access control.

    Identifier values are personally identifying, so read access is granted
    by group rather than to every internal user.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Identifier = cls.env["trn.identifier"]
        cls.national_id = cls.env.ref("trn_identifier.code_identifier_national_id")

        cls.partner = cls.env["res.partner"].create({"name": "Security Test Person"})
        cls.identifier = cls.Identifier.create(
            {
                "partner_id": cls.partner.id,
                "type_id": cls.national_id.id,
                "value": "SECURITY-1",
            }
        )

        cls.user_basic = cls.env["res.users"].create(
            {
                "name": "Basic User",
                "login": "identifier_basic",
                "group_ids": [
                    Command.set([cls.env.ref("base.group_user").id]),
                ],
            }
        )
        cls.user_viewer = cls.env["res.users"].create(
            {
                "name": "Identifier Viewer",
                "login": "identifier_viewer",
                "group_ids": [
                    Command.set([cls.env.ref("trn_identifier.group_identifier_viewer").id]),
                ],
            }
        )
        cls.user_officer = cls.env["res.users"].create(
            {
                "name": "Identifier Officer",
                "login": "identifier_officer",
                "group_ids": [
                    Command.set([cls.env.ref("trn_identifier.group_identifier_officer").id]),
                ],
            }
        )
        cls.user_manager = cls.env["res.users"].create(
            {
                "name": "Identifier Manager",
                "login": "identifier_manager",
                "group_ids": [
                    Command.set([cls.env.ref("trn_identifier.group_identifier_manager").id]),
                ],
            }
        )

    def test_basic_user_cannot_read_identifiers(self):
        """Internal users without the viewer group cannot read identifier values."""
        with self.assertRaises(AccessError):
            self.Identifier.with_user(self.user_basic).search([])

    def test_viewer_can_read_identifiers(self):
        """Viewers can read identifiers."""
        identifiers = self.Identifier.with_user(self.user_viewer).search([])
        self.assertTrue(identifiers)

    def test_viewer_cannot_create_identifier(self):
        """Viewers are read-only."""
        with self.assertRaises(AccessError):
            self.Identifier.with_user(self.user_viewer).create(
                {
                    "partner_id": self.partner.id,
                    "type_id": self.national_id.id,
                    "value": "VIEWER-CREATE",
                }
            )

    def test_viewer_cannot_write_identifier(self):
        """Viewers cannot correct an identifier value."""
        with self.assertRaises(AccessError):
            self.identifier.with_user(self.user_viewer).write({"value": "VIEWER-WRITE"})

    def test_officer_can_create_identifier(self):
        """Officers record identifiers as part of their normal work."""
        identifier = self.Identifier.with_user(self.user_officer).create(
            {
                "partner_id": self.partner.id,
                "type_id": self.national_id.id,
                "value": "OFFICER-CREATE",
            }
        )
        self.assertTrue(identifier.id)

    def test_officer_can_write_identifier(self):
        """Officers can correct a mistyped identifier."""
        self.identifier.with_user(self.user_officer).write({"value": "OFFICER-WRITE"})
        self.assertEqual(self.identifier.value, "OFFICER-WRITE")

    def test_officer_cannot_delete_identifier(self):
        """Deleting frees a reserved value, so it is a manager action."""
        with self.assertRaises(AccessError):
            self.identifier.with_user(self.user_officer).unlink()

    def test_manager_can_delete_identifier(self):
        """Managers can delete identifiers."""
        identifier = self.Identifier.create(
            {
                "partner_id": self.partner.id,
                "type_id": self.national_id.id,
                "value": "MANAGER-DELETE",
            }
        )
        identifier.with_user(self.user_manager).unlink()
        self.assertFalse(identifier.exists())
