__all__ = ["decrypt", "encrypt"]

_KEY: int = 0x728BBCA2


def encrypt(x: int) -> int:
    return x ^ _KEY


def decrypt(x: int) -> int:
    return x ^ _KEY
