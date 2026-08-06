from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    allowed_roots: tuple[Path, ...]
    cubemx_path: Path | None = None
    max_ioc_bytes: int = 5 * 1024 * 1024
    cubemx_timeout_seconds: float = 120.0
    max_process_output_chars: int = 200_000
    allow_unvalidated_apply: bool = False

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        cwd: Path | None = None,
    ) -> Settings:
        values = os.environ if environ is None else environ
        working_directory = (cwd or Path.cwd()).resolve()

        roots_value = values.get("CUBEMX_MCP_ALLOWED_ROOTS", "").strip()
        if roots_value:
            roots = tuple(
                Path(part).expanduser().resolve()
                for part in roots_value.split(os.pathsep)
                if part.strip()
            )
        else:
            roots = (working_directory,)

        cubemx_value = values.get("CUBEMX_MCP_CUBEMX_PATH", "").strip()
        cubemx_path = Path(cubemx_value).expanduser().resolve() if cubemx_value else None

        max_ioc_bytes = int(values.get("CUBEMX_MCP_MAX_IOC_BYTES", 5 * 1024 * 1024))
        if max_ioc_bytes <= 0:
            raise ValueError("CUBEMX_MCP_MAX_IOC_BYTES must be a positive integer")

        timeout = float(values.get("CUBEMX_MCP_CUBEMX_TIMEOUT_SECONDS", "120"))
        if timeout <= 0:
            raise ValueError("CUBEMX_MCP_CUBEMX_TIMEOUT_SECONDS must be positive")

        bypass_value = values.get("CUBEMX_MCP_ALLOW_UNVALIDATED_APPLY", "false").lower()
        if bypass_value not in {"true", "false", "1", "0"}:
            raise ValueError("CUBEMX_MCP_ALLOW_UNVALIDATED_APPLY must be true or false")

        return cls(
            allowed_roots=roots,
            cubemx_path=cubemx_path,
            max_ioc_bytes=max_ioc_bytes,
            cubemx_timeout_seconds=timeout,
            allow_unvalidated_apply=bypass_value in {"true", "1"},
        )

    def resolve_allowed_path(self, raw_path: str | Path, *, must_exist: bool = True) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve(strict=must_exist)

        if not any(candidate.is_relative_to(root) for root in self.allowed_roots):
            roots = ", ".join(str(root) for root in self.allowed_roots)
            raise PermissionError(
                f"Path is outside configured allowed roots ({roots}): {candidate}"
            )
        return candidate
