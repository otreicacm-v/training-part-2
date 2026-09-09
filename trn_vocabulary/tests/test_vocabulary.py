from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestVocabulary(TransactionCase):
    """Tests for the trn.vocabulary model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Vocabulary = cls.env["trn.vocabulary"]

    def test_create_vocabulary(self):
        """A vocabulary can be created with required fields."""
        vocab = self.Vocabulary.create(
            {
                "name": "Test Vocabulary",
                "namespace_uri": "urn:test:vocab:test-1",
            }
        )
        self.assertEqual(vocab.name, "Test Vocabulary")
        self.assertEqual(vocab.namespace_uri, "urn:test:vocab:test-1")
        self.assertEqual(vocab.domain, "core")
        self.assertTrue(vocab.active)
        self.assertFalse(vocab.is_system)

    def test_namespace_uniqueness(self):
        """Duplicate namespace_uri raises ValidationError."""
        self.Vocabulary.create(
            {
                "name": "First",
                "namespace_uri": "urn:test:vocab:unique-test",
            }
        )
        with self.assertRaises(ValidationError):
            self.Vocabulary.create(
                {
                    "name": "Second",
                    "namespace_uri": "urn:test:vocab:unique-test",
                }
            )

    def test_namespace_uniqueness_on_write(self):
        """Cannot update namespace_uri to an existing value."""
        self.Vocabulary.create(
            {
                "name": "First",
                "namespace_uri": "urn:test:vocab:write-test-1",
            }
        )
        second = self.Vocabulary.create(
            {
                "name": "Second",
                "namespace_uri": "urn:test:vocab:write-test-2",
            }
        )
        with self.assertRaises(ValidationError):
            second.write({"namespace_uri": "urn:test:vocab:write-test-1"})

    def test_code_count_computed(self):
        """code_count reflects the number of codes in the vocabulary."""
        vocab = self.Vocabulary.create(
            {
                "name": "Count Test",
                "namespace_uri": "urn:test:vocab:count-test",
            }
        )
        self.assertEqual(vocab.code_count, 0)

        self.env["trn.vocabulary.code"].create(
            {
                "vocabulary_id": vocab.id,
                "code": "A",
                "display": "Alpha",
            }
        )
        self.env["trn.vocabulary.code"].create(
            {
                "vocabulary_id": vocab.id,
                "code": "B",
                "display": "Beta",
            }
        )
        vocab.invalidate_recordset()
        self.assertEqual(vocab.code_count, 2)

    def test_seed_gender_vocabulary_exists(self):
        """Gender vocabulary is created by seed data."""
        vocab = self.Vocabulary.search([("namespace_uri", "=", "urn:iso:std:iso:5218")])
        self.assertTrue(vocab, "Gender vocabulary should exist")
        self.assertEqual(vocab.name, "Gender")
        self.assertTrue(vocab.is_system)

    def test_seed_civil_status_vocabulary_exists(self):
        """Civil status vocabulary is created by seed data."""
        vocab = self.Vocabulary.search([("namespace_uri", "=", "urn:un:unsd:pop-census:marital-status")])
        self.assertTrue(vocab, "Civil status vocabulary should exist")
        self.assertEqual(vocab.name, "Civil Status")
        self.assertTrue(vocab.is_system)

    def test_seed_blood_type_vocabulary_exists(self):
        """Blood type vocabulary is created by seed data."""
        vocab = self.Vocabulary.search([("namespace_uri", "=", "urn:tpl:vocab:blood-type")])
        self.assertTrue(vocab, "Blood type vocabulary should exist")
        self.assertEqual(vocab.name, "Blood Type")
        self.assertTrue(vocab.is_system)

    def test_domain_values(self):
        """All domain selection values are accepted."""
        for domain_val in ("core", "operations", "administrative", "identity", "regulatory"):
            vocab = self.Vocabulary.create(
                {
                    "name": f"Domain {domain_val}",
                    "namespace_uri": f"urn:test:vocab:domain-{domain_val}",
                    "domain": domain_val,
                }
            )
            self.assertEqual(vocab.domain, domain_val)

    def test_action_view_codes(self):
        """action_view_codes returns a valid action dict."""
        vocab = self.Vocabulary.create(
            {
                "name": "Action Test",
                "namespace_uri": "urn:test:vocab:action-test",
            }
        )
        action = vocab.action_view_codes()
        self.assertEqual(action["res_model"], "trn.vocabulary.code")
        self.assertEqual(action["domain"], [("vocabulary_id", "=", vocab.id)])
