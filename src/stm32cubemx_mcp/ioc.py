from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from stm32cubemx_mcp.models import (
    Diagnostic,
    IocFile,
    IocInspection,
    IocListResult,
    IocPin,
    IocSummary,
)
from stm32cubemx_mcp.settings import Settings

_IP_KEY = re.compile(r"^Mcu\.IP\d+$")
_PIN_KEY = re.compile(r"^Mcu\.Pin\d+$")
_CLOCK_KEY = re.compile(r"^(?:RCC\.)?.*(?:Freq|Frequency)(?:_Value)?$", re.IGNORECASE)
_TARGET_TOOLCHAIN_KEY = "ProjectManager.TargetToolchain"
_LEGACY_TOOLCHAIN_KEY = "ProjectManager.ToolChain"


@dataclass
class IocDocument:
    entries: OrderedDict[str, str]
    diagnostics: list[Diagnostic]
    lines: list[str]
    newline: str
    has_final_newline: bool
    key_lines: dict[str, list[int]]

    @classmethod
    def parse(cls, text: str) -> IocDocument:
        entries: OrderedDict[str, str] = OrderedDict()
        diagnostics: list[Diagnostic] = []
        lines = text.splitlines()
        newline = "\r\n" if "\r\n" in text else "\n"
        has_final_newline = text.endswith(("\n", "\r"))
        key_lines: dict[str, list[int]] = {}

        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in raw_line:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        code="ioc.malformed_line",
                        message="Ignored a non-comment line without '='.",
                        line=line_number,
                    )
                )
                continue

            key, value = raw_line.split("=", 1)
            key = key.strip()
            if not key:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        code="ioc.empty_key",
                        message="Ignored an entry with an empty key.",
                        line=line_number,
                    )
                )
                continue
            if key in entries:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        code="ioc.duplicate_key",
                        message=f"Duplicate key '{key}'; the final value is used.",
                        line=line_number,
                    )
                )
            entries[key] = value.strip()
            key_lines.setdefault(key, []).append(line_number - 1)

        return cls(
            entries=entries,
            diagnostics=diagnostics,
            lines=lines,
            newline=newline,
            has_final_newline=has_final_newline,
            key_lines=key_lines,
        )

    def render(self, updates: OrderedDict[str, str]) -> str:
        """Render updates and preserve all unrelated IOC lines."""
        duplicate_updates = [key for key in updates if len(self.key_lines.get(key, [])) > 1]
        if duplicate_updates:
            keys = ", ".join(duplicate_updates)
            raise ValueError(f"Cannot update duplicate IOC keys: {keys}")

        output = self.lines.copy()
        for key, value in updates.items():
            indexes = self.key_lines.get(key)
            if indexes:
                output[indexes[0]] = f"{key}={value}"
            else:
                output.append(f"{key}={value}")

        rendered = self.newline.join(output)
        if self.has_final_newline:
            rendered += self.newline
        return rendered


def _read_ioc(path: Path, max_bytes: int) -> tuple[bytes, IocDocument]:
    if path.suffix.lower() != ".ioc":
        raise ValueError(f"Expected an .ioc file: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"IOC file is {size} bytes; configured limit is {max_bytes} bytes")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"IOC file is not valid UTF-8: {path}") from error
    return raw, IocDocument.parse(text)


def load_ioc_document(raw_path: str | Path, settings: Settings) -> tuple[Path, bytes, IocDocument]:
    """Load an allowed IOC file and return its source data."""
    path = settings.resolve_allowed_path(raw_path)
    if not path.is_file():
        raise ValueError(f"IOC path is not a file: {path}")
    raw, document = _read_ioc(path, settings.max_ioc_bytes)
    return path, raw, document


def encode_ioc_text(text: str, source: bytes) -> bytes:
    """Encode IOC text and preserve a source UTF-8 byte-order mark."""
    prefix = b"\xef\xbb\xbf" if source.startswith(b"\xef\xbb\xbf") else b""
    return prefix + text.encode("utf-8")


def get_project_toolchain(entries: Mapping[str, str]) -> str | None:
    """Read the current CubeMX toolchain key with a legacy fallback."""
    return entries.get(_TARGET_TOOLCHAIN_KEY) or entries.get(_LEGACY_TOOLCHAIN_KEY)


def get_project_toolchain_key(entries: Mapping[str, str]) -> str:
    """Select the toolchain key that the IOC file already uses."""
    if _TARGET_TOOLCHAIN_KEY in entries:
        return _TARGET_TOOLCHAIN_KEY
    if _LEGACY_TOOLCHAIN_KEY in entries:
        return _LEGACY_TOOLCHAIN_KEY
    return _TARGET_TOOLCHAIN_KEY


def _ordered_values(entries: OrderedDict[str, str], pattern: re.Pattern[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for key, value in entries.items():
        if pattern.match(key) and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def _pins(entries: OrderedDict[str, str]) -> list[IocPin]:
    result: list[IocPin] = []
    for pin in _ordered_values(entries, _PIN_KEY):
        result.append(
            IocPin(
                pin=pin,
                signal=entries.get(f"{pin}.Signal"),
                label=entries.get(f"{pin}.GPIO_Label"),
                locked=entries.get(f"{pin}.Locked", "false").lower() == "true",
            )
        )
    return result


def _clock_values(entries: OrderedDict[str, str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in entries.items():
        if _CLOCK_KEY.match(key):
            try:
                result[key] = int(value, 0)
            except ValueError:
                continue
    return result


def inspect_ioc(raw_path: str | Path, settings: Settings) -> IocInspection:
    path, raw, document = load_ioc_document(raw_path, settings)
    entries = document.entries
    summary = IocSummary(
        path=str(path),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        mcu_name=entries.get("Mcu.Name") or entries.get("Mcu.UserName"),
        mcu_part_number=entries.get("Mcu.CPN"),
        mcu_family=entries.get("Mcu.Family"),
        mcu_package=entries.get("Mcu.Package"),
        board=entries.get("board") or entries.get("Board.PartNumber"),
        project_name=entries.get("ProjectManager.ProjectName"),
        toolchain=get_project_toolchain(entries),
        cubemx_version=entries.get("MxCube.Version"),
        database_version=entries.get("MxDb.Version"),
        peripherals=_ordered_values(entries, _IP_KEY),
        pins=_pins(entries),
        clock_values_hz=_clock_values(entries),
        entry_count=len(entries),
    )
    return IocInspection(summary=summary, diagnostics=document.diagnostics)


def list_ioc_files(
    raw_root: str | Path,
    settings: Settings,
    *,
    recursive: bool = True,
    limit: int = 100,
) -> IocListResult:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    root = settings.resolve_allowed_path(raw_root)
    if not root.is_dir():
        raise ValueError(f"IOC search root is not a directory: {root}")

    iterator = root.rglob("*.ioc") if recursive else root.glob("*.ioc")
    found: list[IocFile] = []
    truncated = False
    for path in sorted(iterator, key=lambda item: str(item).lower()):
        resolved = path.resolve()
        if not any(
            resolved.is_relative_to(allowed_root) for allowed_root in settings.allowed_roots
        ):
            continue
        if len(found) == limit:
            truncated = True
            break
        found.append(IocFile(path=str(resolved), size_bytes=resolved.stat().st_size))
    return IocListResult(root=str(root), files=found, truncated=truncated)
