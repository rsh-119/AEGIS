"""What the Docker build context is allowed to carry into the image.

A `.gitignore` entry does NOT keep a file out of a Docker image. The build
context is filtered by `.dockerignore` alone, and there was none — so
`COPY . .` baked backend/.env, a file that is correctly gitignored and has
never been committed, into every image at /app/.env. That single file held
GROQ_API_KEY, GEMINI_API_KEY, NVIDIA_API_KEY, OPENROUTER_API_KEY,
INDIANAPI_KEY, ADMIN_API_KEY, the DATABASE_URL with its password, and —
worst of the set — JWT_SECRET_KEY (forge any user's session) and
TOTP_ENCRYPTION_KEY (decrypt every user's 2FA secret at rest).

The previous validation reported "no secrets in any tracked file", which was
true and is not the same property: it scanned `git ls-files`, and the Docker
build context is a different set of files.

These tests assert on the rules rather than on a built image, so they run in
the normal suite with no Docker daemon. The image itself is verified separately
during release checks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"


def _rules(dockerignore: Path) -> list[str]:
    assert dockerignore.is_file(), (
        f"{dockerignore.relative_to(REPO)} is missing. Without it `COPY . .` "
        f"copies everything in the build context — .env included — into the "
        f"image, regardless of .gitignore."
    )
    return [
        ln.strip()
        for ln in dockerignore.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


@pytest.mark.parametrize("service", ["backend", "frontend"])
def test_a_dockerignore_exists(service):
    _rules(REPO / service / ".dockerignore")


@pytest.mark.parametrize("service", ["backend", "frontend"])
def test_env_files_are_excluded_from_the_build_context(service):
    rules = _rules(REPO / service / ".dockerignore")
    assert ".env" in rules, f"{service}/.dockerignore does not exclude .env"
    assert ".env.*" in rules, (
        f"{service}/.dockerignore excludes .env but not .env.* — a .env.local "
        f"or .env.production would still be copied in"
    )


def test_the_example_env_is_still_allowed_through():
    """Excluding .env.* must not also remove the documentation file."""
    rules = _rules(BACKEND / ".dockerignore")
    assert "!.env.example" in rules


def test_local_virtualenvs_are_excluded():
    """venv/ is 1.3 GB of Python 3.10 packages; the image is Python 3.12. It
    doubled the image size and shipped a second, mismatched dependency tree."""
    rules = _rules(BACKEND / ".dockerignore")
    for pattern in ("venv/", ".venv/"):
        assert pattern in rules, f"backend/.dockerignore does not exclude {pattern}"


def test_frontend_node_modules_is_excluded():
    """`npm ci` rebuilds it inside the image anyway, and a host-built tree can
    carry native bindings for the wrong platform."""
    assert "node_modules/" in _rules(FRONTEND / ".dockerignore")


def test_the_real_env_file_is_not_tracked_by_git():
    """Belt and braces: .dockerignore covers the image, .gitignore covers the
    repository. Both must hold."""
    import subprocess

    out = subprocess.run(
        ["git", "ls-files", "backend/.env", "frontend/.env.local"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.stdout.strip() == "", f"a real .env file is tracked: {out.stdout!r}"


def test_dockerfile_still_copies_the_whole_context():
    """The exclusions above are only load-bearing while the Dockerfile uses a
    broad COPY. If it is ever narrowed to explicit paths, these tests should be
    revisited rather than silently kept as dead weight."""
    text = (BACKEND / "Dockerfile").read_text()
    assert "COPY --chown=aegis:aegis . ." in text, (
        "backend/Dockerfile no longer does a whole-context COPY — re-check "
        "whether .dockerignore is still what keeps .env out of the image"
    )
