"""CI-only GitHub API authentication for published-release verification.

The desktop updater intentionally stays anonymous. GitHub Actions already
has a short-lived GITHUB_TOKEN; use it only for official release *metadata*
requests to avoid the 60 requests/hour anonymous rate limit. Installer and
checksum downloads still use the public, unauthenticated paths.
"""
from urllib.parse import urlparse


def authenticate_release_metadata(updater, token: str | None) -> None:
    """Decorate one updater module's own validated Request factory for CI.

    Supports the current updater and the immutable legacy updater that is
    dynamically imported in the compatibility test. Never patch urlopen or
    bypass _official_url validation, version checks or SHA256 verification.
    """
    if not token:
        return
    if not isinstance(token, str) or not token.strip() or any(
        character in token for character in ("\r", "\n")
    ):
        raise ValueError("Token de autenticação do CI inválido.")
    if getattr(updater, "_aurora_metadata_authenticated", False):
        return
    original_request = updater._request

    def authorized_request(url: str, *, json_response: bool = False):
        request = original_request(url, json_response=json_response)
        if json_response and urlparse(url).hostname == "api.github.com":
            # urllib does not forward unredirected headers to other hosts.
            request.add_unredirected_header("Authorization", f"Bearer {token}")
        return request

    updater._request = authorized_request
    updater._aurora_metadata_authenticated = True
