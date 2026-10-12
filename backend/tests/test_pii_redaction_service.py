import pytest

from app.services.pii_redaction_service import redact_pii, redact_structured_value


def test_redacts_multiple_cv_pii_types_and_indonesian_identifiers():
    text = (
        "Name: Sinta Contoh\n"
        "Email: sinta@example.test\n"
        "Phone: +62 812-3456-7890\n"
        "Address: Jl. Melati No. 10, Bandung\n"
        "NIK: 3174012345678901\n"
        "NPWP: 12.345.678.9-012.000"
    )

    result = redact_pii(text)

    assert "[REDACTED_NAME]" in result.redacted_text
    assert "[REDACTED_EMAIL]" in result.redacted_text
    assert "[REDACTED_PHONE]" in result.redacted_text
    assert "[REDACTED_ADDRESS]" in result.redacted_text
    assert result.redacted_text.count("[REDACTED_GOVERNMENT_ID]") == 2
    assert result.detected_types == ("name", "government_id", "email", "phone", "address")
    assert result.replacement_count == 6
    for sensitive_value in (
        "Sinta Contoh", "sinta@example.test", "+62 812-3456-7890",
        "Jl. Melati No. 10, Bandung", "3174012345678901", "12.345.678.9-012.000",
    ):
        assert sensitive_value not in result.redacted_text


def test_text_without_detectable_pii_is_unchanged():
    text = (
        "Backend engineer with 5 years of experience. "
        "Built a Python 3.11 service in 2024; project code 12345678."
    )

    result = redact_pii(text)

    assert result.redacted_text == text
    assert result.detected_types == ()
    assert result.replacement_count == 0


def test_overlapping_address_and_contact_patterns_are_redacted():
    text = "Address: Jl. Mawar No. 4; email overlap@example.test"

    result = redact_pii(text)

    assert "Jl. Mawar No. 4" not in result.redacted_text
    assert "overlap@example.test" not in result.redacted_text
    assert "[REDACTED_ADDRESS]" in result.redacted_text
    assert "[REDACTED_EMAIL]" in result.redacted_text


@pytest.mark.parametrize(
    "text",
    [
        "NIK is a common label in Indonesian documents.",
        "Version 3.11; employment dates 2020-2024; 8 years of experience.",
        "The project identifier is 12345678 and the team has 12 members.",
    ],
)
def test_false_positive_prone_non_identifiers_are_preserved(text):
    assert redact_pii(text).redacted_text == text


def test_structured_values_are_recursively_redacted_without_mutating_input():
    source = {
        "experience": [{
            "company": "Example Labs",
            "description": "Contact cv@example.test at 0812-3456-7890",
        }],
        "metadata": ("Address: 10 Example Street, Jakarta",),
    }

    sanitized = redact_structured_value(source)

    assert sanitized["experience"][0]["company"] == "Example Labs"
    assert "[REDACTED_EMAIL]" in sanitized["experience"][0]["description"]
    assert "[REDACTED_PHONE]" in sanitized["experience"][0]["description"]
    assert "[REDACTED_ADDRESS]" in sanitized["metadata"][0]
    assert source["experience"][0]["description"] == "Contact cv@example.test at 0812-3456-7890"


def test_redactor_rejects_non_string_text():
    with pytest.raises(TypeError, match="text must be a string"):
        redact_pii(None)
