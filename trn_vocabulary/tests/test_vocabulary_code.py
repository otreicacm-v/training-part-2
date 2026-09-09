from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestVocabularyCode(TransactionCase):
    """Tests for the trn.vocabulary.code model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Code = cls.env["trn.vocabulary.code"]
        cls.vocab = cls.env["trn.vocabulary"].create(
            {
                "name": "Test Vocab",
                "namespace_uri": "urn:test:vocab:codes",
            }
        )

    def test_create_code(self):
        """A code can be created with required fields."""
        code = self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "T1",
                "display": "Test One",
            }
        )
        self.assertEqual(code.code, "T1")
        self.assertEqual(code.display, "Test One")
        self.assertTrue(code.active)
        self.assertEqual(code.sequence, 10)

    def test_uri_computation(self):
        """URI is computed as namespace_uri#code."""
        code = self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "X1",
                "display": "X One",
            }
        )
        self.assertEqual(code.uri, "urn:test:vocab:codes#X1")

    def test_uri_globally_unique(self):
        """Two codes with the same computed URI raise ValidationError."""
        self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "DUP",
                "display": "First",
            }
        )
        # Same vocabulary + same code = same URI
        with self.assertRaises(ValidationError):
            self.Code.create(
                {
                    "vocabulary_id": self.vocab.id,
                    "code": "DUP",
                    "display": "Second",
                }
            )

    def test_code_unique_within_vocabulary(self):
        """Duplicate code within the same vocabulary is rejected."""
        self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "UNI",
                "display": "Unique One",
            }
        )
        with self.assertRaises(ValidationError):
            self.Code.create(
                {
                    "vocabulary_id": self.vocab.id,
                    "code": "UNI",
                    "display": "Unique Two",
                }
            )

    def test_same_code_different_vocabulary(self):
        """Same code value in different vocabularies is allowed."""
        other_vocab = self.env["trn.vocabulary"].create(
            {
                "name": "Other Vocab",
                "namespace_uri": "urn:test:vocab:other",
            }
        )
        code_a = self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "SHARED",
                "display": "In First",
            }
        )
        code_b = self.Code.create(
            {
                "vocabulary_id": other_vocab.id,
                "code": "SHARED",
                "display": "In Second",
            }
        )
        self.assertNotEqual(code_a.uri, code_b.uri)

    def test_get_code_lookup(self):
        """get_code returns the correct record by namespace + code."""
        self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "FIND",
                "display": "Findable",
            }
        )
        result = self.Code.get_code("urn:test:vocab:codes", "FIND")
        self.assertTrue(result)
        self.assertEqual(result.display, "Findable")

    def test_get_code_not_found(self):
        """get_code returns empty recordset for non-existent code."""
        result = self.Code.get_code("urn:test:vocab:codes", "NOPE")
        self.assertFalse(result)

    def test_resolve_by_uri(self):
        """resolve_by_uri returns the correct record."""
        self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "RES",
                "display": "Resolvable",
            }
        )
        result = self.Code.resolve_by_uri("urn:test:vocab:codes#RES")
        self.assertTrue(result)
        self.assertEqual(result.code, "RES")

    def test_resolve_by_uri_not_found(self):
        """resolve_by_uri returns empty recordset for non-existent URI."""
        result = self.Code.resolve_by_uri("urn:test:vocab:codes#MISSING")
        self.assertFalse(result)

    def test_display_name_format(self):
        """Display name is formatted as 'Display (code)'."""
        code = self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "DN",
                "display": "Display Name Test",
            }
        )
        self.assertEqual(code.display_name, "Display Name Test (DN)")

    def test_seed_gender_codes_count(self):
        """Gender vocabulary has exactly 4 codes."""
        gender_vocab = self.env["trn.vocabulary"].search([("namespace_uri", "=", "urn:iso:std:iso:5218")])
        self.assertEqual(len(gender_vocab.code_ids), 4)

    def test_seed_civil_status_codes_count(self):
        """Civil status vocabulary has exactly 6 codes."""
        vocab = self.env["trn.vocabulary"].search([("namespace_uri", "=", "urn:un:unsd:pop-census:marital-status")])
        self.assertEqual(len(vocab.code_ids), 6)

    def test_seed_blood_type_codes_count(self):
        """Blood type vocabulary has exactly 8 codes."""
        vocab = self.env["trn.vocabulary"].search([("namespace_uri", "=", "urn:tpl:vocab:blood-type")])
        self.assertEqual(len(vocab.code_ids), 8)

    def test_namespace_uri_stored_from_vocabulary(self):
        """namespace_uri is stored from the related vocabulary."""
        code = self.Code.create(
            {
                "vocabulary_id": self.vocab.id,
                "code": "NS",
                "display": "Namespace Check",
            }
        )
        self.assertEqual(code.namespace_uri, "urn:test:vocab:codes")
