from src.domain.matching import normalize_drug_name, build_shortage_index, find_shortage_match


def test_normalize_strips_punctuation_and_whitespace():
    assert normalize_drug_name("Cefotaxime Sodium Powder, for Solution") == \
        "cefotaxime sodium powder for solution"


def test_normalize_handles_none_and_empty():
    assert normalize_drug_name("") == ""
    assert normalize_drug_name(None) == ""


def test_build_shortage_index_extracts_rxcui_and_name_keys():
    items = [
        {
            "rxcui": "12345",
            "drug_name": "Cisplatin Injection",
            "severity": "Critical",
            "summary": "shortage",
            "item_id": "id-1",
            "citations": [{"url": "http://x"}],
        }
    ]
    rxcui_idx, name_idx = build_shortage_index(items)
    assert "12345" in rxcui_idx
    assert "cisplatin injection" in name_idx
    assert rxcui_idx["12345"]["severity"] == "Critical"


def test_find_shortage_match_prefers_rxcui_then_name():
    rxcui_idx = {"999": {"severity": "Watch", "summary": "x", "citation": None, "item_id": "i"}}
    name_idx = {"foo": [{"severity": "Critical", "summary": "y", "citation": None, "item_id": "j"}]}

    drug_rxcui_hit = {"rxcui_list": ["999"], "name": "Bar"}
    assert find_shortage_match(drug_rxcui_hit, rxcui_idx, name_idx)["severity"] == "Watch"

    drug_name_hit = {"rxcui_list": ["nope"], "name": "Foo"}
    assert find_shortage_match(drug_name_hit, rxcui_idx, name_idx)["severity"] == "Critical"

    drug_no_hit = {"rxcui_list": ["nope"], "name": "Nothing"}
    assert find_shortage_match(drug_no_hit, rxcui_idx, name_idx) is None
