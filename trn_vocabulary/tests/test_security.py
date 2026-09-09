from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestVocabularySecurity(TransactionCase):
    """Tests for vocabulary access control."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Vocabulary = cls.env["trn.vocabulary"]
        cls.Code = cls.env["trn.vocabulary.code"]

        cls.user_basic = cls.env["res.users"].create(
            {
                "name": "Basic User",
                "login": "vocab_basic",
                "group_ids": [
                    Command.set([cls.env.ref("base.group_user").id]),
                ],
            }
        )
        cls.user_officer = cls.env["res.users"].create(
            {
                "name": "Vocab Officer",
                "login": "vocab_officer",
                "group_ids": [
                    Command.set([cls.env.ref("trn_vocabulary.group_vocabulary_officer").id]),
                ],
            }
        )
        cls.user_manager = cls.env["res.users"].create(
            {
                "name": "Vocab Manager",
                "login": "vocab_manager",
                "group_ids": [
                    Command.set([cls.env.ref("trn_vocabulary.group_vocabulary_manager").id]),
                ],
            }
        )

    def test_basic_user_can_read_vocabulary(self):
        """Basic users can read vocabularies (needed for M2O dropdowns)."""
        vocabs = self.Vocabulary.with_user(self.user_basic).search([])
        self.assertTrue(vocabs)

    def test_basic_user_can_read_codes(self):
        """Basic users can read vocabulary codes."""
        codes = self.Code.with_user(self.user_basic).search([])
        self.assertTrue(codes)

    def test_basic_user_cannot_create_vocabulary(self):
        """Basic users cannot create vocabularies."""
        with self.assertRaises(AccessError):
            self.Vocabulary.with_user(self.user_basic).create(
                {
                    "name": "Unauthorized",
                    "namespace_uri": "urn:test:vocab:unauthorized",
                }
            )

    def test_officer_can_create_vocabulary(self):
        """Officers can create vocabularies."""
        vocab = self.Vocabulary.with_user(self.user_officer).create(
            {
                "name": "Officer Vocab",
                "namespace_uri": "urn:test:vocab:officer-create",
            }
        )
        self.assertTrue(vocab)

    def test_officer_can_create_code(self):
        """Officers can create codes in non-system vocabularies."""
        vocab = self.Vocabulary.with_user(self.user_officer).create(
            {
                "name": "Officer Code Test",
                "namespace_uri": "urn:test:vocab:officer-code",
            }
        )
        code = self.Code.with_user(self.user_officer).create(
            {
                "vocabulary_id": vocab.id,
                "code": "OC1",
                "display": "Officer Code",
            }
        )
        self.assertTrue(code)

    def test_officer_cannot_delete_vocabulary(self):
        """Officers cannot delete vocabularies."""
        vocab = self.Vocabulary.with_user(self.user_officer).create(
            {
                "name": "No Delete",
                "namespace_uri": "urn:test:vocab:officer-no-delete",
            }
        )
        with self.assertRaises(AccessError):
            vocab.with_user(self.user_officer).unlink()

    def test_manager_can_delete_vocabulary(self):
        """Managers can delete vocabularies."""
        vocab = self.Vocabulary.with_user(self.user_manager).create(
            {
                "name": "Delete Me",
                "namespace_uri": "urn:test:vocab:manager-delete",
            }
        )
        vocab.with_user(self.user_manager).unlink()
