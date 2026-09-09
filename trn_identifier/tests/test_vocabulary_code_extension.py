from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestVocabularyCodeExtension(TransactionCase):
    """Identifier configuration added to trn.vocabulary.code."""

    def setUp(self):
        super().setUp()
        self.identifier_vocabulary = self.env.ref("trn_identifier.vocab_identifier_type")

    def test_seed_types_belong_to_the_identifier_vocabulary(self):
        """Seeded identifier types carry the identifier-type namespace."""
        national_id = self.env.ref("trn_identifier.code_identifier_national_id")
        self.assertEqual(national_id.namespace_uri, "urn:tpl:vocab:identifier-type")

    def test_identifier_vocabulary_is_system_protected(self):
        """The vocabulary is a system one, so users cannot add types through the UI."""
        self.assertTrue(self.identifier_vocabulary.is_system)

    def test_invalid_regex_is_rejected(self):
        """A malformed pattern is caught on the type, not when an identifier uses it."""
        vocabulary = self.env["trn.vocabulary"].create(
            {"name": "Test Types", "namespace_uri": "urn:test:vocab:invalid-regex"}
        )
        with self.assertRaises(ValidationError):
            self.env["trn.vocabulary.code"].create(
                {
                    "vocabulary_id": vocabulary.id,
                    "code": "broken",
                    "display": "Broken Pattern",
                    "id_validation": "^[unclosed",
                }
            )

    def test_valid_regex_is_accepted(self):
        """A well-formed pattern is stored."""
        vocabulary = self.env["trn.vocabulary"].create(
            {"name": "Test Types", "namespace_uri": "urn:test:vocab:valid-regex"}
        )
        code = self.env["trn.vocabulary.code"].create(
            {
                "vocabulary_id": vocabulary.id,
                "code": "digits",
                "display": "Digits Only",
                "id_validation": "^[0-9]{9}$",
            }
        )
        self.assertEqual(code.id_validation, "^[0-9]{9}$")

    def test_target_type_defaults_to_both(self):
        """A type with no explicit target applies to people and organizations."""
        vocabulary = self.env["trn.vocabulary"].create(
            {"name": "Test Types", "namespace_uri": "urn:test:vocab:target-default"}
        )
        code = self.env["trn.vocabulary.code"].create(
            {"vocabulary_id": vocabulary.id, "code": "generic", "display": "Generic"}
        )
        self.assertEqual(code.target_type, "both")
