from apply_changes import (
    normalize,
    normalize_street,
    expected_care_type,
    same_current_facility,
    BELLHAVEN_PARENT_ID,
)


def test_normalize():
    assert normalize("Bellhaven & Nursing") == "bellhaven and nursing"


def test_street_normalization():
    assert normalize_street("1250 Northwest Franklin Street") == \
           normalize_street("1250 NW Franklin St")

    assert normalize_street("3313 Wilmington Pike") == \
           normalize_street("3313 Wilmington Pk")


def test_care_type_mapping():
    assert expected_care_type(
        "Short-Term Rehabilitation & Nursing"
    ) == "Skilled Nursing"

    assert expected_care_type(
        "Memory Support"
    ) == "Memory Care"

    assert expected_care_type(
        "Assisted Living"
    ) == "Assisted Living"


def test_multi_care_uses_primary_offering():
    assert expected_care_type(
        "Assisted Living | Memory Support"
    ) == "Assisted Living"


def test_same_current_facility():
    crm_account = {
        "name": "Bellhaven of Chesterton",
        "parent_id": BELLHAVEN_PARENT_ID,
        "billing_street": "1250 Northwest Franklin St",
        "billing_city": "Chesterton",
        "billing_state": "IN",
        "billing_zip": "46304",
    }

    website_payload = {
        "name": "Bellhaven of Chesterton",
        "parent_id": BELLHAVEN_PARENT_ID,
        "billing_street": "1250 NW Franklin Street",
        "billing_city": "Chesterton",
        "billing_state": "IN",
        "billing_zip": "46304",
    }

    assert same_current_facility(
        crm_account,
        website_payload
    )


def test_wrong_parent_is_not_current_bellhaven():
    crm_account = {
        "name": "Bellhaven of Tiffin",
        "parent_id": "SOME_OTHER_PARENT",
        "billing_street": "45 St Lawrence Dr",
        "billing_city": "Tiffin",
        "billing_state": "OH",
        "billing_zip": "44883",
    }

    website_payload = {
        "name": "Bellhaven of Tiffin",
        "parent_id": BELLHAVEN_PARENT_ID,
        "billing_street": "45 St Lawrence Dr",
        "billing_city": "Tiffin",
        "billing_state": "OH",
        "billing_zip": "44883",
    }

    assert not same_current_facility(
        crm_account,
        website_payload
    )