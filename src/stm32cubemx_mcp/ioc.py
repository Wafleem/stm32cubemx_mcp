from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
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


@dataclass
class IocDocument:
    entries: OrderedDict[str, str]
    diagnostics: list[Diagnostic]

    @classmethod
    def parse(cls, text: str) -> IocDocument:
        entries: OrderedDict[str, str] = OrderedDict()
        diagnostics: list[Diagnostic] = []

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
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

        return cls(entries=entries, diagnostics=diagnostics)


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
    path = settings.resolve_allowed_path(raw_path)
    if not path.is_file():
        raise ValueError(f"IOC path is not a file: {path}")

    raw, document = _read_ioc(path, settings.max_ioc_bytes)
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
        toolchain=entries.get("ProjectManager.ToolChain"),
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
