from payroll_copilot.application.services.employee_fixed_document_extractor import (
    fixed_structured_has_usable_values,
    ground_id_card_values,
    is_valid_israeli_id,
    structured_from_semantic_payload,
)
from payroll_copilot.domain.enums import DocumentType

OCR = """
שם משפחה
שמולביץ
שם פרטי
יהודה
תאריך לידה
כ"ב בכסלו תשנ"ה
25.11.1994
מספר זהות
313366783
"""


def test_israeli_id_checksum():
    assert is_valid_israeli_id("313366783")
    assert not is_valid_israeli_id("123456789")


def test_grounding_rejects_hallucinated_latin_name_and_hebrew_date():
    grounded = ground_id_card_values(
        full_name="Noa Abel",
        national_id="313366783",
        birth_date='25 בשבט תשפ"ה',
        ocr_text=OCR,
    )
    assert grounded["full_name"] == ""
    assert grounded["national_id"] == "313366783"
    assert grounded["birth_date"] == ""


def test_grounding_accepts_combined_hebrew_name_and_gregorian_date():
    grounded = ground_id_card_values(
        full_name="יהודה שמולביץ",
        national_id="313366783",
        birth_date="25.11.1994",
        ocr_text=OCR,
    )
    assert grounded["full_name"] == "יהודה שמולביץ"
    assert grounded["national_id"] == "313366783"
    assert grounded["birth_date"] == "25.11.1994"


def test_semantic_payload_grounds_id_card_against_ocr():
    structured = structured_from_semantic_payload(
        DocumentType.NATIONAL_ID,
        {
            "full_name": "יהודה שמולביץ",
            "national_id": "313366783",
            "birth_date": "25.11.1994",
            "id_expiration_date": "should-be-ignored",
        },
        ocr_text=OCR,
    )
    fields = structured["additional_fields"]
    assert set(fields) == {"full_name", "national_id", "birth_date"}
    assert fields["full_name"]["value"] == "יהודה שמולביץ"
    assert fields["national_id"]["value"] == "313366783"
    assert fields["birth_date"]["value"] == "25.11.1994"
    assert fixed_structured_has_usable_values(structured)


def test_semantic_payload_discards_ungrounded_hallucinations():
    structured = structured_from_semantic_payload(
        DocumentType.NATIONAL_ID,
        {
            "full_name": "Noa Abel",
            "national_id": "000000000",
            "birth_date": '25 בשבט תשפ"ה',
        },
        ocr_text=OCR,
    )
    fields = structured["additional_fields"]
    assert fields["full_name"]["status"] == "MISSING"
    assert fields["national_id"]["status"] == "MISSING"
    assert fields["birth_date"]["status"] == "MISSING"
    assert not fixed_structured_has_usable_values(structured)


def test_appendix_semantic_payload_extracts_children_only():
    structured = structured_from_semantic_payload(
        DocumentType.ID_APPENDIX,
        {
            "children": [
                {"name": "נועה כהן", "birth_date": "12.03.2015"},
                {"name": "יוסי כהן", "birth_date": "01.01.2018"},
            ],
            "marital_status": {"value": "נשוי", "confidence": 0.8},
            "number_of_children": {"value": "2", "confidence": 0.7},
            "address": {"value": "ignored"},
        },
    )
    fields = structured["additional_fields"]
    assert set(fields) == {"children"}
    assert fields["children"]["value"] == [
        {"name": "נועה כהן", "birth_date": "12.03.2015"},
        {"name": "יוסי כהן", "birth_date": "01.01.2018"},
    ]
    assert fields["children"]["status"] == "FOUND"
    assert fixed_structured_has_usable_values(structured)


def test_appendix_semantic_payload_empty_children():
    structured = structured_from_semantic_payload(
        DocumentType.ID_APPENDIX,
        {"children": []},
    )
    fields = structured["additional_fields"]
    assert fields["children"]["value"] == []
    assert fields["children"]["status"] == "MISSING"
    assert not fixed_structured_has_usable_values(structured)


def test_project_fixed_structured_drops_legacy_appendix_scalars():
    from payroll_copilot.application.services.employee_document_form_schemas import (
        project_fixed_structured,
    )

    projected = project_fixed_structured(
        DocumentType.ID_APPENDIX,
        {
            "additional_fields": {
                "marital_status": {"value": "נשוי", "status": "FOUND"},
                "number_of_children": {"value": "2", "status": "FOUND"},
                "children": {
                    "value": [{"name": "נועה", "birth_date": "12.03.2015"}],
                    "status": "FOUND",
                },
            }
        },
    )
    fields = projected["additional_fields"]
    assert set(fields) == {"children"}
    assert fields["children"]["value"] == [{"name": "נועה", "birth_date": "12.03.2015"}]
