from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSystemProtection(TransactionCase):
    """Tests for system vocabulary protection."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Code = cls.env["trn.vocabulary.code"]
        # Gender is a system vocabulary from seed data
        cls.gender_vocab = cls.env["trn.vocabulary"].search([("namespace_uri", "=", "urn:iso:std:iso:5218")])
        cls.gender_male = cls.Code.get_code("urn:iso:std:iso:5218", "1")

    def test_system_vocab_blocks_code_create(self):
        """Cannot create codes in a system vocabulary via normal operation."""
        with self.assertRaises(UserError):
            self.Code.create(
                {
                    "vocabulary_id": self.gender_vocab.id,
                    "code": "99",
                    "display": "Custom Gender",
                }
            )

    def test_system_vocab_blocks_code_write(self):
        """Cannot modify core fields on system vocabulary codes."""
        with self.assertRaises(UserError):
            self.gender_male.write({"display": "Hombre"})

    def test_system_vocab_allows_sequence_write(self):
        """Can modify sequence on system vocabulary codes."""
        self.gender_male.write({"sequence": 99})
        self.assertEqual(self.gender_male.sequence, 99)

    def test_system_vocab_allows_active_write(self):
        """Can modify active on system vocabulary codes."""
        self.gender_male.write({"active": False})
        self.assertFalse(self.gender_male.active)
        # Restore for other tests
        self.gender_male.write({"active": True})

    def test_system_vocab_blocks_code_delete(self):
        """Cannot delete codes from a system vocabulary."""
        with self.assertRaises(UserError):
            self.gender_male.unlink()

    def test_non_system_vocab_allows_crud(self):
        """Non-system vocabularies allow full CRUD on codes."""
        vocab = self.env["trn.vocabulary"].create(
            {
                "name": "Custom Vocab",
                "namespace_uri": "urn:test:vocab:custom-crud",
                "is_system": False,
            }
        )
        code = self.Code.create(
            {
                "vocabulary_id": vocab.id,
                "code": "C1",
                "display": "Custom One",
            }
        )
        code.write({"display": "Updated"})
        self.assertEqual(code.display, "Updated")
        code.unlink()

    def test_bypass_with_install_xmlid_context(self):
        """System protection is bypassed with install_xmlid context."""
        code = self.Code.with_context(install_xmlid="test").create(
            {
                "vocabulary_id": self.gender_vocab.id,
                "code": "88",
                "display": "Bypass Test",
            }
        )
        self.assertTrue(code)
        # Clean up
        code.with_context(_test_bypass_system_protection=True).unlink()
