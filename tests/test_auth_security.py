from app.server.auth.security import (
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    encoded = hash_password("correct-horse-battery-staple")
    assert "correct-horse" not in encoded
    assert verify_password("correct-horse-battery-staple", encoded)
    assert not verify_password("wrong-password", encoded)


def test_signed_session_round_trip() -> None:
    token = create_session_token("default")
    assert decode_session_token(token) == "default"
    assert decode_session_token(f"{token}x") is None
