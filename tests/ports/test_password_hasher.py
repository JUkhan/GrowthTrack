from ports.auth import PwdlibPasswordHasher


def test_hash_is_never_the_plaintext_password():
    hasher = PwdlibPasswordHasher()

    hashed = hasher.hash("correct-horse-battery-staple")

    assert hashed != "correct-horse-battery-staple"
    assert hashed.startswith("$2b$")


def test_verify_accepts_the_correct_password():
    hasher = PwdlibPasswordHasher()
    hashed = hasher.hash("correct-horse-battery-staple")

    assert hasher.verify("correct-horse-battery-staple", hashed) is True


def test_verify_rejects_the_wrong_password():
    hasher = PwdlibPasswordHasher()
    hashed = hasher.hash("correct-horse-battery-staple")

    assert hasher.verify("wrong-password", hashed) is False
