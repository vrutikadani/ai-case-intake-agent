import pytest

from case_intake.normalization import case_key, grounded, normalize_customer_id, normalize_order_id


@pytest.mark.parametrize("raw", ["SO#038262", "SO 38262", "so-038262", "38262", "Order #38262", "Sales Order 038262",
                                 "Invoice 38262", "INV-038262", "  038262 "])
def test_order_formats_normalize_to_one_id(raw):
    assert normalize_order_id(raw) == "38262"


@pytest.mark.parametrize("raw", ["C-010442", "Cust #010442", "Customer 10442", "Account 10442", "acct no. 10442",
                                 "10442", "customer id: 010442"])
def test_customer_formats_normalize_to_one_id(raw):
    assert normalize_customer_id(raw) == "10442"


@pytest.mark.parametrize("raw", ["7O315", "SO#12", "ABC-12345", "", "12345678901", None, "38262-A"])
def test_malformed_order_ids_are_rejected(raw):
    assert normalize_order_id(raw) is None


def test_case_key_is_stable():
    assert case_key(normalize_customer_id("C-010442"), normalize_order_id("SO#038262")) == \
        case_key(normalize_customer_id("10442"), normalize_order_id("38262")) == "10442|38262"


def test_grounding_requires_the_digits_in_the_text():
    assert grounded("38262", "please fix SO#038262 today")
    assert not grounded("38262", "please fix SO#382620 today")      # different number
    assert not grounded("99999", "no identifiers here")
