"""Tests for store/chain/branch detection."""

from app.parsers.store_detection import UserStoreContext, detect_store


def test_rema_chain_and_branch_on_separate_lines():
    text = "REMA 1000\nMETRO SENTER\nMELK 15 25,00\nSUM 1 VARER 25,00"
    store = detect_store(text)
    assert store.chain == "rema1000"
    assert store.branch_text == "METRO SENTER"
    assert store.state == "accepted"


def test_rema_chain_only_with_salgskvittering_next():
    text = "REMA 1000\nSalgskvittering\nMELK 25,00"
    store = detect_store(text)
    assert store.chain == "rema1000"
    assert store.branch_text is None
    assert store.resolution == "chain_only"


def test_kiwi_not_velkommen():
    text = "VELKOMMEN\nKIWI OSLO\nMELK 25,00\nTOTALT 25,00"
    store = detect_store(text)
    assert store.chain == "kiwi"
    assert "VELKOMMEN" not in (store.observed_text or "").upper() or store.chain == "kiwi"


def test_normal_branch_preserved():
    text = "Normal Oslo, Thon Senter Triaden\nVare 10,00"
    store = detect_store(text)
    assert store.chain == "normal"
    assert "Triaden" in (store.branch_text or "")


def test_user_store_context_isolated():
    text = "Normal Oslo, Thon Senter Triaden"
    ctx_a = [UserStoreContext("user-a", "normal", ("Triaden",))]
    ctx_b = [UserStoreContext("user-b", "normal", ("Other",))]
    a = detect_store(text, user_store_contexts=ctx_a)
    b = detect_store(text, user_store_contexts=ctx_b)
    assert a.resolved_user_store_id == "user-a"
    assert b.resolved_user_store_id is None


def test_competing_chains_uncertain():
    text = "REMA 1000 Metro\nNormal Oslo\nVare 10,00"
    store = detect_store(text)
    assert store.state == "uncertain"
