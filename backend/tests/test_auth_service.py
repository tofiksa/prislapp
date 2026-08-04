from app.security.passwords import hash_password, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("SikkerPassord123!")
    assert verify_password("SikkerPassord123!", hashed) is True
    assert verify_password("FeilPassord", hashed) is False
