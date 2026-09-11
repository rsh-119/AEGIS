"""Preconditions that make the remaining dependency advisory non-exploitable.

pip-audit reports one unfixed advisory after the September 2026 upgrade pass:

    ecdsa 0.19.2 — PYSEC-2026-1325 (Minerva timing attack on ECDSA)
    Fix versions: none available

It arrives transitively through python-jose and is accepted rather than fixed,
because there is no fix to apply. The acceptance rests on two facts that are
properties of THIS application, not of the library — so they are asserted here
rather than written down and hoped for:

  1. Aegis signs and verifies with HS256 (symmetric HMAC). No ECDSA key is ever
     created, signed with, or verified against.
  2. python-jose loads its crypto backends lazily, so `ecdsa` is not imported
     at all on the HS256 path.

If either stops being true, this advisory becomes live and these tests fail
before anyone has to notice it in an audit report.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys

import pytest
from jose import jwt

from app.core.auth import ALGORITHM, create_access_token, decode_token
from app.core.config import get_settings

settings = get_settings()


def test_tokens_are_signed_with_a_symmetric_algorithm():
    assert ALGORITHM == "HS256", (
        f"token algorithm changed to {ALGORITHM!r}. If this is now an EC "
        "algorithm (ES256/ES384/ES512), the unfixed ecdsa advisory "
        "PYSEC-2026-1325 becomes reachable and must be re-assessed."
    )


_CLAIMS = {"sub": "1", "type": "access", "jti": "x"}


@pytest.mark.parametrize("alg", ["HS384", "HS512"])
def test_a_token_signed_with_another_hmac_algorithm_is_rejected(alg):
    """Behavioural counterpart to the source check: only HS256 is accepted.

    Anything else must fail closed — both because algorithm confusion is a
    vulnerability in its own right, and because an EC algorithm slipping
    through is precisely what would make the unfixed ecdsa advisory reachable.
    """
    token = jwt.encode(_CLAIMS, settings.jwt_secret_key, algorithm=alg)
    with pytest.raises(Exception):
        decode_token(token, expected_type="access")


def test_an_alg_none_token_is_rejected():
    """The classic unsigned-JWT forgery. It cannot be produced with
    jwt.encode() — the library refuses to emit one — so it is assembled by hand
    here, which is exactly how an attacker would send it. Skipping this case
    because the helper won't build it would leave the most important algorithm
    confusion variant untested."""
    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    header = b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = b64(json.dumps(_CLAIMS).encode())
    unsigned = f"{header}.{payload}."          # empty signature segment

    with pytest.raises(Exception):
        decode_token(unsigned, expected_type="access")


def test_the_ecdsa_module_is_not_imported_on_the_token_path():
    """python-jose loads backends lazily. Run in a clean interpreter so this
    measures the real import graph, not whatever the test session already
    pulled in."""
    code = (
        "import sys;"
        "from jose import jwt;"
        "t = jwt.encode({'sub':'1'}, 'k'*32, algorithm='HS256');"
        "jwt.decode(t, 'k'*32, algorithms=['HS256']);"
        "print('ecdsa' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False", (
        "the ecdsa module is now imported on the JWT path — PYSEC-2026-1325 "
        "can no longer be treated as unreachable"
    )


def test_a_real_token_still_round_trips():
    """Guard against the tests above passing because signing is broken."""
    token = create_access_token(4242, "sid-abc")
    assert decode_token(token, expected_type="access") == 4242
