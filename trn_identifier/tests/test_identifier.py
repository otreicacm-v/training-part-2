from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestIdentifier(TransactionCase):
    """Behaviour of trn.identifier: typing, validation and lookup."""

    def setUp(self):
        super().setUp()
        partner_model = self.env["res.partner"].with_context(tracking_disable=True)
        self.person = partner_model.create({"name": "Test Person", "is_company": False})
        self.other_person = partner_model.create({"name": "Other Person", "is_company": False})
        self.company = partner_model.create({"name": "Test Company", "is_company": True})

        self.national_id = self.env.ref("trn_identifier.code_identifier_national_id")
        self.passport = self.env.ref("trn_identifier.code_identifier_passport")
        self.tax_id = self.env.ref("trn_identifier.code_identifier_tax_id")

    def test_system_uri_is_denormalized_from_type(self):
        """system_uri mirrors the type's URI so lookups avoid joining the vocabulary."""
        identifier = self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.national_id.id, "value": "ABC-123"}
        )
        self.assertEqual(identifier.system_uri, self.national_id.uri)

    def test_duplicate_value_for_same_type_is_rejected(self):
        """Two partners cannot hold the same identifier value for the same type."""
        self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.national_id.id, "value": "DUPLICATE-1"}
        )
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.env["trn.identifier"].create(
                {
                    "partner_id": self.other_person.id,
                    "type_id": self.national_id.id,
                    "value": "DUPLICATE-1",
                }
            )
            self.env.flush_all()

    def test_same_value_for_different_types_is_allowed(self):
        """The same string may legitimately be a national ID and a passport number."""
        shared_value = "SHARED123"
        self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.national_id.id, "value": shared_value}
        )
        passport = self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.passport.id, "value": shared_value}
        )
        self.assertEqual(passport.value, shared_value)

    def test_value_matching_type_pattern_is_accepted(self):
        """A value satisfying the type's pattern is stored unchanged."""
        identifier = self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.national_id.id, "value": "AB-123456"}
        )
        self.assertEqual(identifier.value, "AB-123456")

    def test_value_violating_type_pattern_is_rejected(self):
        """A value that breaks the type's pattern raises rather than being stored."""
        with self.assertRaises(ValidationError):
            self.env["trn.identifier"].create(
                {
                    "partner_id": self.person.id,
                    "type_id": self.passport.id,
                    "value": "has spaces and $ymbols",
                }
            )

    def test_pattern_must_match_the_whole_value(self):
        """A partial match is not enough — trailing junk is rejected."""
        with self.assertRaises(ValidationError):
            self.env["trn.identifier"].create(
                {
                    "partner_id": self.person.id,
                    "type_id": self.passport.id,
                    "value": "VALID123 trailing!",
                }
            )

    def test_type_without_pattern_accepts_any_value(self):
        """Types that define no pattern impose no format restriction."""
        birth_certificate = self.env.ref("trn_identifier.code_identifier_birth_certificate")
        self.assertFalse(birth_certificate.id_validation)
        identifier = self.env["trn.identifier"].create(
            {
                "partner_id": self.person.id,
                "type_id": birth_certificate.id,
                "value": "any / format $ allowed",
            }
        )
        self.assertTrue(identifier.id)

    def test_person_only_type_rejected_on_company(self):
        """A national ID cannot be issued to a company."""
        with self.assertRaises(ValidationError):
            self.env["trn.identifier"].create(
                {"partner_id": self.company.id, "type_id": self.national_id.id, "value": "NID-1"}
            )

    def test_type_for_both_accepted_on_company_and_person(self):
        """A tax ID applies to organizations and people alike."""
        company_tax_id = self.env["trn.identifier"].create(
            {"partner_id": self.company.id, "type_id": self.tax_id.id, "value": "TAX-COMPANY"}
        )
        person_tax_id = self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.tax_id.id, "value": "TAX-PERSON"}
        )
        self.assertTrue(company_tax_id.id)
        self.assertTrue(person_tax_id.id)

    def test_non_identifier_vocabulary_code_is_rejected_as_type(self):
        """A code from another vocabulary cannot be used as an identifier type."""
        gender_code = self.env.ref("trn_vocabulary.code_gender_female")
        with self.assertRaises(ValidationError):
            self.env["trn.identifier"].create({"partner_id": self.person.id, "type_id": gender_code.id, "value": "X"})

    def test_find_partner_returns_the_holder(self):
        """Lookup by namespace and value returns the partner holding it."""
        self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.national_id.id, "value": "FIND-ME"}
        )
        found = self.env["trn.identifier"].find_partner(self.national_id.uri, "FIND-ME")
        self.assertEqual(found, self.person)

    def test_find_partner_returns_empty_for_unknown_value(self):
        """An unknown value yields an empty recordset, not an error."""
        found = self.env["trn.identifier"].find_partner(self.national_id.uri, "NO-SUCH-VALUE")
        self.assertFalse(found)

    def test_find_partner_does_not_match_across_types(self):
        """The same value under a different type is not returned."""
        self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.passport.id, "value": "CROSSTYPE"}
        )
        found = self.env["trn.identifier"].find_partner(self.national_id.uri, "CROSSTYPE")
        self.assertFalse(found)

    def test_partner_returns_its_identifier_value(self):
        """get_identifier_value returns the value for the requested type."""
        self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.national_id.id, "value": "PARTNER-NID"}
        )
        self.assertEqual(
            self.person.get_identifier_value(self.national_id.uri),
            "PARTNER-NID",
        )

    def test_partner_without_identifier_returns_false(self):
        """A partner holding no identifier of that type returns False."""
        self.assertFalse(self.person.get_identifier_value(self.national_id.uri))

    def test_identifier_count_reflects_identifiers_held(self):
        """identifier_count counts the partner's identifiers."""
        self.assertEqual(self.person.identifier_count, 0)
        self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.national_id.id, "value": "COUNT-1"}
        )
        self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.passport.id, "value": "COUNT2"}
        )
        self.person.invalidate_recordset(["identifier_count"])
        self.assertEqual(self.person.identifier_count, 2)

    def test_display_name_includes_the_type(self):
        """A bare value is ambiguous, so the type is shown alongside it."""
        identifier = self.env["trn.identifier"].create(
            {"partner_id": self.person.id, "type_id": self.national_id.id, "value": "DISPLAY-1"}
        )
        self.assertEqual(identifier.display_name, "National ID: DISPLAY-1")

    def test_identifiers_are_removed_with_their_partner(self):
        """Deleting a partner deletes their identifiers rather than orphaning them."""
        identifier = self.env["trn.identifier"].create(
            {"partner_id": self.other_person.id, "type_id": self.national_id.id, "value": "CASCADE-1"}
        )
        identifier_id = identifier.id
        self.other_person.unlink()
        self.assertFalse(self.env["trn.identifier"].browse(identifier_id).exists())
