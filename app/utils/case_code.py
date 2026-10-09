"""Secure, unpredictable public case codes such as WD-7K4P9X2M."""
import re
import secrets

# 30 characters: digits 2-9 and letters without I, L, O, U (nothing easily misread).
ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
PREFIX = "WD-"
CODE_LENGTH = 8  # 30**8 is about 6.6 x 10**11 combinations (~39 bits)

_PATTERN = re.compile(rf"^{PREFIX}[{ALPHABET}]{{{CODE_LENGTH}}}$")


def generate_case_code() -> str:
    """Uses the `secrets` module (OS CSPRNG), never `random`, and never a database ID."""
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalize_case_code(value: str) -> str:
    return value.strip().upper()


def is_valid_case_code(value: str) -> bool:
    return bool(_PATTERN.match(value))
