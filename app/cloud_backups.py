"""Backup remoto opcional: OAuth PKCE e pastas exclusivas de aplicativo.

Este módulo não modifica o SQLite ativo nem salva credenciais nos backups.
A configuração do cliente Desktop vem da compilação; tokens pessoais ficam no cofre.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qs, quote
from urllib.request import HTTPRedirectHandler, Request, build_opener
import base64
import json
import os
import secrets
import tempfile
import time
import webbrowser

from .backups import BACKUP_SUFFIX, backups_directory, read_backup

MAX_CLOUD_BYTES = 120 * 1024 * 1024
KEYRING_SERVICE = "AURORA-AutoFill-CloudBackup"
GOOGLE_CLIENT_SERVICE = KEYRING_SERVICE + ":google-desktop-client"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.appdata"
MICROSOFT_SCOPE = "Files.ReadWrite.AppFolder offline_access"
GOOGLE_CONFIGURATION_HELP = (
    "Não foi possível autenticar o AURORA no Google com a configuração desta versão. "
    "Atualize o aplicativo. Se o problema continuar, entre em contato com o suporte.")


class CloudBackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteBackup:
    identifier: str
    name: str
    size: int
    modified: str = ""


def client_id_for(provider: str) -> str:
    """Registered public client IDs, injected at runtime for development.

    Release builds can ship IDs in an optional cloud-oauth-clients.json asset.
    No private keys or refresh tokens may be bundled.
    """
    env = {"google": "AURORA_GOOGLE_CLIENT_ID",
           "onedrive": "AURORA_MICROSOFT_CLIENT_ID"}
    if provider not in env:
        raise CloudBackupError("Provedor desconhecido.")
    value = os.environ.get(env[provider], "").strip()
    if not value:
        resource = Path(__file__).resolve().parents[1] / "assets" / "cloud-oauth-clients.json"
        try:
            config = json.loads(resource.read_text(encoding="utf-8"))
            value = str(config.get(provider, "")).strip()
        except (OSError, ValueError, AttributeError):
            pass
    if not value or len(value) > 256 or any(c.isspace() for c in value):
        raise CloudBackupError(
            "Falta configurar o ID público do aplicativo OAuth para "
            + ("Google Drive." if provider == "google" else "OneDrive.")
            + " Consulte docs/backup-nuvem.md.")
    return value


def _secret_store():
    try:
        import keyring
        from keyring.errors import KeyringError
        backend = keyring.get_keyring()
        # Null/fail backends cannot protect refresh tokens. Never use plaintext.
        if getattr(backend, "priority", 0) <= 0:
            raise CloudBackupError(
                "Não há um cofre de credenciais disponível neste sistema. "
                "Configure o Gerenciador de Credenciais (Windows) ou Secret Service (Linux).")
        return keyring
    except ImportError as exc:
        raise CloudBackupError("Instale a dependência keyring para conectar sua conta.") from exc
    except CloudBackupError:
        raise
    except Exception as exc:
        raise CloudBackupError("Não foi possível acessar o cofre de credenciais.") from exc


def _read_refresh(provider: str, client_id: str) -> str:
    try:
        return _secret_store().get_password(KEYRING_SERVICE + ":" + provider, client_id) or ""
    except Exception as exc:
        raise CloudBackupError("Falha ao consultar a credencial protegida.") from exc


def _write_refresh(provider: str, client_id: str, value: str) -> None:
    if not value:
        raise CloudBackupError("O serviço não concedeu autorização para uso posterior.")
    try:
        _secret_store().set_password(KEYRING_SERVICE + ":" + provider, client_id, value)
    except Exception as exc:
        raise CloudBackupError("Falha ao guardar a autorização no cofre do sistema.") from exc


def _delete_refresh(provider: str, client_id: str) -> None:
    try:
        store = _secret_store()
        if store.get_password(KEYRING_SERVICE + ":" + provider, client_id):
            store.delete_password(KEYRING_SERVICE + ":" + provider, client_id)
    except Exception as exc:
        raise CloudBackupError("Não foi possível desconectar a conta localmente.") from exc


def _valid_client_secret(value) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 256
            and all(33 <= ord(char) <= 126 for char in value))


def _bundled_google_client_secret(client_id: str, *, allow_fixture=False) -> str:
    """Public desktop client metadata, supplied by the project during compilation.

    This is not a web-client secret or an account token. A native application
    cannot keep shared registration metadata confidential; PKCE remains required.
    PR fixtures must never be accepted by the regular authentication flow.
    """
    try:
        from ._cloud_oauth import (
            GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, IS_TEST_CONFIGURATION,
        )
    except ImportError:
        return ""
    if (GOOGLE_CLIENT_ID != client_id or
            (IS_TEST_CONFIGURATION and not allow_fixture) or
            not _valid_client_secret(GOOGLE_CLIENT_SECRET)):
        return ""
    return GOOGLE_CLIENT_SECRET


def verify_bundled_google_configuration(*, allow_fixture=False) -> None:
    """Packaging gate: require the compiled registration, never a local vault entry."""
    if not _bundled_google_client_secret(client_id_for("google"), allow_fixture=allow_fixture):
        raise CloudBackupError("A compilação não inclui a configuração Google Desktop esperada.")


def _google_client_secret(client_id: str) -> str:
    configured = _bundled_google_client_secret(client_id)
    if configured:
        return configured
    # Compatibility with the pilot already installed on the maintainer's PC.
    # New installations use the bundled registration and never import files.
    try:
        value = _secret_store().get_password(GOOGLE_CLIENT_SERVICE, client_id)
    except Exception:
        raise CloudBackupError(
            "Não foi possível acessar a configuração protegida do Google.") from None
    if value is None or value == "":
        return ""
    if not _valid_client_secret(value):
        raise CloudBackupError(GOOGLE_CONFIGURATION_HELP)
    return value


def _http_error_message(url: str, error: HTTPError) -> str:
    """Translate known OAuth failures without displaying provider text or tokens."""
    if url in ("https://oauth2.googleapis.com/token",
               "https://login.microsoftonline.com/common/oauth2/v2.0/token"):
        try:
            payload = error.read(8193)
            answer = json.loads(payload) if len(payload) <= 8192 else {}
            code = answer.get("error") if isinstance(answer, dict) else None
            description = answer.get("error_description", "") if isinstance(answer, dict) else ""
        except (OSError, ValueError):
            code, description = None, ""
        if url == "https://oauth2.googleapis.com/token":
            missing_secret = (code == "invalid_request" and isinstance(description, str)
                              and "client_secret" in description
                              and "missing" in description.lower())
            if missing_secret or code == "invalid_client":
                return GOOGLE_CONFIGURATION_HELP
        if code == "invalid_grant":
            return (
                "A autorização expirou ou foi revogada. Conecte a conta novamente "
                "e conclua o login no navegador.")
        if code == "invalid_scope":
            return "O provedor não aceitou a permissão de backup configurada no aplicativo."
        if code in ("invalid_request", "unauthorized_client", "invalid_client"):
            return (
                "Não foi possível concluir a autorização do aplicativo "
                f"(HTTP {error.code}; {code}). Confira o cadastro do aplicativo no provedor.")
    return (f"A nuvem recusou a operação (HTTP {error.code}). "
            "Confira autorização, espaço disponível e conexão.")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _https(url: str, hosts: set[str]) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or
            parsed.hostname.lower() not in hosts or parsed.username or parsed.password):
        raise CloudBackupError("O serviço retornou um endereço de rede não autorizado.")
    return url


def _call(url: str, token: str = "", *, method="GET", body=None,
          content_type="", allowed_hosts=None, response_limit=2*1024*1024,
          allow_redirect=False, extra_headers=None) -> tuple[bytes, dict, int]:
    hosts = allowed_hosts or {"www.googleapis.com", "graph.microsoft.com",
                              "oauth2.googleapis.com", "login.microsoftonline.com"}
    _https(url, hosts)
    headers = {"Accept": "application/json", "User-Agent": "AuroraAutoFill-Cloud/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if content_type:
        headers["Content-Type"] = content_type
    if extra_headers:
        headers.update(extra_headers)
    request = Request(url, data=body, headers=headers, method=method)
    opener = build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=45) as reply:
            blob = reply.read(response_limit + 1)
            if len(blob) > response_limit:
                raise CloudBackupError("Arquivo remoto ultrapassa o limite de segurança.")
            return blob, dict(reply.headers.items()), reply.status
    except HTTPError as exc:
        try:
            if allow_redirect and exc.code in (301, 302, 303, 307, 308):
                location = exc.headers.get("Location", "")
                host = (urlparse(location).hostname or "").lower()
                if (urlparse(location).scheme == "https" and
                        (host.endswith(".sharepoint.com") or host.endswith(".1drv.com")
                         or host.endswith(".blob.core.windows.net")
                         or host == "onedrive.live.com")):
                    # The redirected request must NOT carry Graph's bearer token.
                    return _call(location, allowed_hosts={host},
                                 response_limit=response_limit)
            raise CloudBackupError(_http_error_message(url, exc)) from None
        finally:
            exc.close()
    except (OSError, URLError) as exc:
        raise CloudBackupError("Falha de conexão com a nuvem.") from exc


def _json_call(url: str, token="", *, method="GET", body=None,
               content_type="", hosts=None) -> dict:
    blob, _, _ = _call(url, token, method=method, body=body,
                       content_type=content_type, allowed_hosts=hosts)
    try:
        result = json.loads(blob)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError) as exc:
        raise CloudBackupError("Resposta inválida do provedor de nuvem.") from exc


def validate_download(path: Path) -> None:
    """Run the existing backup validator before offering any restoration."""
    database, _ = read_backup(path)
    database.unlink(missing_ok=True)


class CloudBackupClient:
    def __init__(self, provider: str):
        if provider not in ("google", "onedrive"):
            raise CloudBackupError("Provedor desconhecido.")
        self.provider = provider
        self.client_id = client_id_for(provider)

    def connected(self) -> bool:
        return bool(_read_refresh(self.provider, self.client_id))

    def disconnect(self) -> None:
        # Local disconnect only. User can revoke access in Google/Microsoft.
        _delete_refresh(self.provider, self.client_id)

    def _oauth_urls(self):
        if self.provider == "google":
            return ("https://accounts.google.com/o/oauth2/v2/auth",
                    "https://oauth2.googleapis.com/token", GOOGLE_SCOPE)
        return ("https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                MICROSOFT_SCOPE)

    def _token_parameters(self) -> dict:
        parameters = {"client_id": self.client_id}
        if self.provider == "google":
            secret = _google_client_secret(self.client_id)
            if not secret:
                raise CloudBackupError(GOOGLE_CONFIGURATION_HELP)
            parameters["client_secret"] = secret
        return parameters

    def connect(self, cancelled=lambda: False, timeout=120):
        # Capture desktop configuration once, before opening the browser.
        # PKCE is still required; the desktop client secret does not replace it.
        client_parameters = self._token_parameters()
        auth_url, token_url, scope = self._oauth_urls()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
        result = {}

        class Callback(BaseHTTPRequestHandler):
            def do_GET(self):
                params = urlparse(self.path)
                query = parse_qs(params.query)
                if (params.path != "/callback" or
                        query.get("state", [""])[0] != state):
                    self.send_error(400, "Invalid callback")
                    return
                if "code" not in query and "error" not in query:
                    self.send_error(400, "Missing authorization result")
                    return
                result["code"] = query.get("code", [""])[0]
                result["error"] = query.get("error", [""])[0]
                html = ("<html><meta charset='utf-8'><body>"
                        "<h2>Autorização recebida.</h2>"
                        "Volte ao AURORA AutoFill para concluir.</body></html>")
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass  # Never log codes or query parameters.

        # The callback server listens only on loopback, never externally.
        with HTTPServer(("127.0.0.1", 0), Callback) as server:
            server.timeout = 0.5
            redirect = "http://127.0.0.1:" + str(server.server_port) + "/callback"
            # For Microsoft, register the localhost redirect URI with /callback.
            if self.provider == "onedrive":
                redirect = "http://localhost:" + str(server.server_port) + "/callback"
            options = {
                "client_id": self.client_id, "response_type": "code",
                "redirect_uri": redirect, "scope": scope, "state": state,
                "code_challenge": challenge, "code_challenge_method": "S256",
            }
            if self.provider == "google":
                options.update({"access_type": "offline", "prompt": "consent"})
            url = auth_url + "?" + urlencode(options)
            if not webbrowser.open(url):
                raise CloudBackupError("Não foi possível abrir o navegador para autorização.")
            deadline = time.monotonic() + timeout
            while not result and time.monotonic() < deadline:
                if cancelled():
                    raise CloudBackupError("Autorização cancelada.")
                server.handle_request()
        if not result:
            raise CloudBackupError("A autorização expirou. Tente novamente.")
        if result.get("error"):
            raise CloudBackupError("A conta não autorizou o acesso solicitado.")
        response = _json_call(token_url, method="POST",
                              body=urlencode({
                                  **client_parameters,
                                  "redirect_uri": redirect, "code": result["code"],
                                  "code_verifier": verifier, "grant_type": "authorization_code",
                              }).encode("ascii"),
                              content_type="application/x-www-form-urlencoded")
        if not response.get("access_token") or not response.get("refresh_token"):
            raise CloudBackupError("A autorização não forneceu acesso contínuo ao backup.")
        _write_refresh(self.provider, self.client_id, response["refresh_token"])

    def _access_token(self) -> str:
        refresh = _read_refresh(self.provider, self.client_id)
        if not refresh:
            raise CloudBackupError("Conecte a conta antes de acessar seus backups.")
        _, url, _ = self._oauth_urls()
        answer = _json_call(url, method="POST", body=urlencode({
            **self._token_parameters(), "refresh_token": refresh,
            "grant_type": "refresh_token",
            **({"scope": MICROSOFT_SCOPE} if self.provider == "onedrive" else {}),
        }).encode("ascii"), content_type="application/x-www-form-urlencoded")
        token = answer.get("access_token")
        if not isinstance(token, str) or not token:
            raise CloudBackupError("A autorização expirou. Conecte a conta novamente.")
        rotated = answer.get("refresh_token")
        if rotated and rotated != refresh:
            _write_refresh(self.provider, self.client_id, rotated)
        return token

    def _app_root(self, token: str) -> str:
        data = _json_call("https://graph.microsoft.com/v1.0/me/drive/special/approot",
                          token)
        folder = data.get("id")
        if not isinstance(folder, str) or not folder:
            raise CloudBackupError("OneDrive não disponibilizou a pasta do AURORA.")
        return quote(folder, safe="")

    def list_backups(self) -> list[RemoteBackup]:
        token = self._access_token()
        found = []
        if self.provider == "google":
            url = ("https://www.googleapis.com/drive/v3/files?"
                   + urlencode({"spaces": "appDataFolder", "pageSize": 100,
                                "fields": "nextPageToken,files(id,name,size,modifiedTime)",
                                "q": "trashed = false"}))
            for _ in range(20):
                page = _json_call(url, token)
                found.extend(page.get("files", []))
                cursor = page.get("nextPageToken")
                if not cursor:
                    break
                url = ("https://www.googleapis.com/drive/v3/files?"
                       + urlencode({"spaces": "appDataFolder", "pageSize": 100,
                                    "fields": "nextPageToken,files(id,name,size,modifiedTime)",
                                    "pageToken": cursor, "q": "trashed = false"}))
        else:
            root = self._app_root(token)
            url = ("https://graph.microsoft.com/v1.0/me/drive/items/" + root
                   + "/children?$select=id,name,size,lastModifiedDateTime,file&$top=100")
            for _ in range(20):
                page = _json_call(url, token)
                found.extend(page.get("value", []))
                nxt = page.get("@odata.nextLink")
                if not nxt:
                    break
                _https(nxt, {"graph.microsoft.com"})
                url = nxt
        backups = []
        for item in found:
            if not isinstance(item, dict):
                continue
            name, identifier = item.get("name"), item.get("id")
            if (isinstance(name, str) and name.startswith("aurora-cloud-")
                    and name.endswith(BACKUP_SUFFIX)
                    and isinstance(identifier, str) and identifier
                    and 0 <= int(item.get("size", 0)) <= MAX_CLOUD_BYTES):
                backups.append(RemoteBackup(identifier, name, int(item.get("size", 0)),
                                            item.get("modifiedTime") or
                                            item.get("lastModifiedDateTime") or ""))
        return sorted(backups, key=lambda item: item.modified, reverse=True)

    def upload_backup(self, path: Path) -> str:
        path = Path(path)
        if not path.is_file() or path.stat().st_size > MAX_CLOUD_BYTES:
            raise CloudBackupError("Backup ausente ou acima de 120 MiB.")
        validate_download(path)
        token = self._access_token()
        name = ("aurora-cloud-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                + "-" + secrets.token_hex(3) + BACKUP_SUFFIX)
        content = path.read_bytes()
        if self.provider == "onedrive":
            root = self._app_root(token)
            url = ("https://graph.microsoft.com/v1.0/me/drive/items/"
                   + root + ":/" + quote(name, safe="") + ":/content")
            _json_call(url, token, method="PUT", body=content,
                       content_type="application/zip")
        else:
            # Resumable works for both small and larger backups.
            metadata = json.dumps({"name": name, "parents": ["appDataFolder"]}).encode()
            url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
            _, headers, _ = _call(
                url, token, method="POST", body=metadata,
                content_type="application/json; charset=UTF-8",
                extra_headers={"X-Upload-Content-Type": "application/zip",
                               "X-Upload-Content-Length": str(len(content))})
            # Start requests must include size/type; headers below are also accepted
            # by Google even if the initial metadata request omits them.
            location = next((v for k, v in headers.items() if k.lower() == "location"), "")
            if not location:
                raise CloudBackupError("Google Drive não abriu a sessão de upload.")
            host = (urlparse(location).hostname or "").lower()
            if host != "www.googleapis.com":
                raise CloudBackupError("Endereço de upload do Google não autorizado.")
            _json_call(location, token, method="PUT", body=content,
                       content_type="application/zip")
        return name

    def download_backup(self, identifier: str) -> Path:
        available = {x.identifier: x for x in self.list_backups()}
        if identifier not in available:
            raise CloudBackupError("Backup não encontrado na conta conectada.")
        token = self._access_token()
        if self.provider == "google":
            url = ("https://www.googleapis.com/drive/v3/files/"
                   + quote(identifier, safe="") + "?alt=media")
        else:
            url = ("https://graph.microsoft.com/v1.0/me/drive/items/"
                   + quote(identifier, safe="") + "/content")
        raw, _, _ = _call(url, token, response_limit=MAX_CLOUD_BYTES, allow_redirect=True)
        if len(raw) != available[identifier].size:
            raise CloudBackupError("Download incompleto: o tamanho não corresponde à nuvem.")
        destination = backups_directory()
        destination.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination, prefix=".aurora-cloud-",
                                             suffix=".partial", delete=False) as file:
                temporary = Path(file.name)
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            validate_download(temporary)
            # Keep the downloaded file as an explicit local recovery copy, never
            # replace an existing backup nor the live database.
            final = destination / (datetime.now().strftime("aurora-recuperado-%Y%m%d-%H%M%S-")
                                   + secrets.token_hex(3) + BACKUP_SUFFIX)
            os.replace(temporary, final)
            temporary = None
            return final
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
