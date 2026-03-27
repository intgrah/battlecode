"""Feistel network symmetric encryption for u32 values.

A balanced Feistel cipher that encrypts/decrypts 32-bit unsigned integers.
Used to obfuscate marker values so that enemy bots cannot trivially decode
our communication protocol.

Properties:
- Bijective: every u32 maps to a unique u32. No collisions.
- Symmetric: decrypt(encrypt(x)) == x for all x in [0, 2^32).
- Deterministic: same input always produces same output (no randomness).
- Fixed key: the key is hardcoded at compile time.

Structure:
- 8-round balanced Feistel network on two 16-bit halves.
- Round function f(x, k) = rotl16(x + k, 5) XOR rotl16(x + k, 9).
- Round keys derived from a 64-bit master key by rotating and XORing
  with a fractional constant (golden ratio derivative).

This is NOT cryptographically secure. It is sufficient to prevent casual
reverse-engineering by opponents during a short competition game. The goal
is obfuscation, not security.
"""

__all__ = ["decrypt", "encrypt"]

_MASK16: int = 0xFFFF
_MASK32: int = 0xFFFFFFFF
_KEY: int = 0xB4FE0CE1247E6AF3
_ROUNDS: int = 8


def _rotl16(x: int, r: int) -> int:
    return ((x << r) | (x >> (16 - r))) & _MASK16


def _round_keys(key: int) -> list[int]:
    ks: list[int] = []
    k: int = key & 0xFFFFFFFFFFFFFFFF
    for i in range(_ROUNDS):
        ks.append(k & _MASK16)
        k = ((k >> 16) | (k << 48)) & 0xFFFFFFFFFFFFFFFF
        k ^= 0x9E3779B97F4A7C15 >> (i % 16)
    return ks


def _f(x: int, k: int) -> int:
    x = (x + k) & _MASK16
    return _rotl16(x, 5) ^ _rotl16(x, 9)


def encrypt(x: int) -> int:
    """Encrypt a u32 to a u32."""
    x &= _MASK32
    left: int = (x >> 16) & _MASK16
    right: int = x & _MASK16
    ks = _round_keys(_KEY)
    for k in ks:
        left, right = right, (left ^ _f(right, k)) & _MASK16
    return ((left << 16) | right) & _MASK32


def decrypt(x: int) -> int:
    """Decrypt a u32 to a u32."""
    x &= _MASK32
    left: int = (x >> 16) & _MASK16
    right: int = x & _MASK16
    ks = _round_keys(_KEY)
    for k in reversed(ks):
        left, right = (right ^ _f(left, k)) & _MASK16, left
    return ((left << 16) | right) & _MASK32
