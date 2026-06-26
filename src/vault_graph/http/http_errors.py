from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vault_graph.errors import ResultExplanationError, VaultGraphError


@dataclass(frozen=True)
class HttpServerConfig:
    state_path: Path
    host: str = "127.0.0.1"
    port: int = 8765

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_path", self.state_path.expanduser().resolve())
        if self.host != "127.0.0.1":
            raise HttpRequestError(
                code="remote_http_not_supported",
                message="remote HTTP serving is not supported; use 127.0.0.1",
                status_code=400,
            )
        if self.port < 1 or self.port > 65535:
            raise HttpRequestError(
                code="invalid_http_port",
                message="port must be between 1 and 65535",
                status_code=400,
            )


@dataclass(frozen=True)
class HttpErrorPayload:
    code: str
    message: str
    recovery_hint: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "recovery_hint": self.recovery_hint,
            }
        }


class HttpRequestError(VaultGraphError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        recovery_hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.payload = HttpErrorPayload(code=code, message=message, recovery_hint=recovery_hint)
        self.status_code = status_code


def map_exception_to_http_error(exc: Exception) -> HttpRequestError:
    if isinstance(exc, HttpRequestError):
        return exc
    if isinstance(exc, ResultExplanationError):
        return _map_result_explanation_error(exc)
    if isinstance(exc, VaultGraphError):
        return HttpRequestError(
            code=_snake_case_error_code(type(exc).__name__),
            message=str(exc),
            status_code=400,
            recovery_hint="Check Vault Graph state with vg status.",
        )
    return HttpRequestError(
        code="internal_error",
        message="internal HTTP adapter error",
        status_code=500,
    )


def _map_result_explanation_error(exc: ResultExplanationError) -> HttpRequestError:
    code = _prefixed_domain_code(str(exc))
    if code == "result_explanation_not_found":
        return HttpRequestError(
            code=code,
            message="result explanation is not available for this result_id",
            status_code=404,
            recovery_hint="Rerun the original HTTP request and pass a result_id from the new response.",
        )
    if code == "invalid_result_id":
        return HttpRequestError(
            code=code,
            message="result_id is required",
            status_code=400,
            recovery_hint="Pass a non-empty result_id from a current Vault Graph response.",
        )
    return HttpRequestError(
        code="result_explanation_error",
        message=str(exc),
        status_code=400,
        recovery_hint="Rerun the original HTTP request and retry explain-result.",
    )


def _prefixed_domain_code(message: str) -> str | None:
    if ":" not in message:
        return None
    prefix = message.split(":", 1)[0].strip()
    if prefix in {"result_explanation_not_found", "invalid_result_id"}:
        return prefix
    return None


def _snake_case_error_code(class_name: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(class_name):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)
