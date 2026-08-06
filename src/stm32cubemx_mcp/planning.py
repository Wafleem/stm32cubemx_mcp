from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import OrderedDict

from stm32cubemx_mcp.ioc import encode_ioc_text, load_ioc_document
from stm32cubemx_mcp.models import (
    Diagnostic,
    IocChangePlan,
    IocPlannedChange,
    IocPlanRequest,
)
from stm32cubemx_mcp.settings import Settings

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.+:/() -]+$")
_STRUCTURAL_KEY = re.compile(r"^Mcu\.(?:Pin|IP)\d+$")
_PROTECTED_DEBUG_SIGNALS = {
    "PA13": "SYS_JTMS-SWDIO",
    "PA14": "SYS_JTCK-SWCLK",
}


def _validate_key(key: str) -> None:
    if not _SAFE_KEY.fullmatch(key):
        raise ValueError(f"IOC key has invalid characters: {key!r}")
    if _STRUCTURAL_KEY.fullmatch(key) or key in {"Mcu.PinsNb", "Mcu.IPNb"}:
        raise ValueError(f"Use the structured pin or peripheral fields for key: {key}")


def _validate_value(name: str, value: str) -> None:
    if not value or len(value) > 2048 or "\n" in value or "\r" in value or "=" in value:
        raise ValueError(f"IOC value is invalid for {name!r}")


def _validate_token(name: str, value: str) -> None:
    _validate_value(name, value)
    if not _SAFE_TOKEN.fullmatch(value):
        raise ValueError(f"IOC token has invalid characters for {name!r}: {value!r}")


def _indexed_values(entries: OrderedDict[str, str], prefix: str) -> list[tuple[int, str]]:
    pattern = re.compile(rf"^Mcu\.{prefix}(\d+)$")
    result: list[tuple[int, str]] = []
    for key, value in entries.items():
        match = pattern.fullmatch(key)
        if match:
            result.append((int(match.group(1)), value))
    return sorted(result)


def prepare_ioc_changes(request: IocPlanRequest, settings: Settings) -> tuple[IocChangePlan, bytes]:
    """Create an IOC change plan and the planned file content."""
    path, source, document = load_ioc_document(request.path, settings)
    if any(item.code == "ioc.duplicate_key" for item in document.diagnostics):
        raise ValueError("The IOC file has duplicate keys. Correct them before a change plan.")

    updates: OrderedDict[str, str] = OrderedDict()
    reasons: dict[str, str] = {}

    def set_update(key: str, value: str, reason: str) -> None:
        previous_update = updates.get(key)
        if previous_update is not None and previous_update != value:
            raise ValueError(f"The request has conflicting values for IOC key: {key}")
        if document.entries.get(key) != value:
            updates[key] = value
            reasons[key] = reason

    indexed_peripherals = _indexed_values(document.entries, "IP")
    peripheral_names = {value for _, value in indexed_peripherals}
    next_peripheral_index = max((index for index, _ in indexed_peripherals), default=-1) + 1
    for peripheral in request.enabled_peripherals:
        _validate_token("peripheral", peripheral)
        if peripheral not in peripheral_names:
            set_update(
                f"Mcu.IP{next_peripheral_index}",
                peripheral,
                f"Enable peripheral {peripheral}.",
            )
            peripheral_names.add(peripheral)
            next_peripheral_index += 1
    if len(peripheral_names) != len(indexed_peripherals):
        set_update("Mcu.IPNb", str(len(peripheral_names)), "Update the peripheral count.")

    indexed_pins = _indexed_values(document.entries, "Pin")
    pin_names = {value for _, value in indexed_pins}
    next_pin_index = max((index for index, _ in indexed_pins), default=-1) + 1
    requested_pins: set[str] = set()
    for assignment in request.pin_assignments:
        _validate_token("pin", assignment.pin)
        _validate_token("signal", assignment.signal)
        if assignment.label is not None:
            _validate_token("label", assignment.label)
        if assignment.pin in requested_pins:
            raise ValueError(f"The request has more than one assignment for pin: {assignment.pin}")
        requested_pins.add(assignment.pin)

        protected_signal = _PROTECTED_DEBUG_SIGNALS.get(assignment.pin)
        current_signal = document.entries.get(f"{assignment.pin}.Signal")
        if (
            protected_signal
            and current_signal == protected_signal
            and assignment.signal != protected_signal
            and not request.allow_debug_pin_change
        ):
            raise ValueError(
                f"The request changes protected SWD pin {assignment.pin}. "
                "Set allow_debug_pin_change to true for this change."
            )

        if assignment.pin not in pin_names:
            set_update(
                f"Mcu.Pin{next_pin_index}",
                assignment.pin,
                f"Add pin {assignment.pin} to the configured pin list.",
            )
            pin_names.add(assignment.pin)
            next_pin_index += 1

        set_update(
            f"{assignment.pin}.Signal",
            assignment.signal,
            f"Assign signal {assignment.signal} to pin {assignment.pin}.",
        )
        if assignment.label is not None:
            set_update(
                f"{assignment.pin}.GPIO_Label",
                assignment.label,
                f"Set the label for pin {assignment.pin}.",
            )
        set_update(
            f"{assignment.pin}.Locked",
            str(assignment.locked).lower(),
            f"Set the lock state for pin {assignment.pin}.",
        )
    if len(pin_names) != len(indexed_pins):
        set_update("Mcu.PinsNb", str(len(pin_names)), "Update the pin count.")

    for key, value in request.parameter_updates.items():
        _validate_key(key)
        _validate_value(key, value)
        set_update(key, value, "Set a requested IOC parameter.")

    if request.project_name is not None:
        _validate_token("project_name", request.project_name)
        set_update("ProjectManager.ProjectName", request.project_name, "Set the project name.")
        set_update(
            "ProjectManager.ProjectFileName",
            f"{request.project_name}.ioc",
            "Set the project file name.",
        )
    if request.toolchain is not None:
        set_update("ProjectManager.ToolChain", request.toolchain, "Set the project toolchain.")

    rendered = document.render(updates)
    source_text = source.decode("utf-8-sig")
    diff = "\n".join(
        difflib.unified_diff(
            source_text.splitlines(),
            rendered.splitlines(),
            fromfile=str(path),
            tofile=f"{path}.planned",
            lineterm="",
        )
    )
    source_sha256 = hashlib.sha256(source).hexdigest()
    rendered_bytes = encode_ioc_text(rendered, source)
    planned_sha256 = hashlib.sha256(rendered_bytes).hexdigest()
    plan_data = {
        "path": str(path),
        "source_sha256": source_sha256,
        "updates": list(updates.items()),
    }
    plan_id = hashlib.sha256(
        json.dumps(plan_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]

    changes = [
        IocPlannedChange(
            key=key,
            before=document.entries.get(key),
            after=value,
            reason=reasons[key],
        )
        for key, value in updates.items()
    ]
    diagnostics = [
        *document.diagnostics,
        Diagnostic(
            severity="info",
            code="ioc.validation_required",
            message="CubeMX did not validate this plan. Validate the staged IOC.",
        ),
    ]
    plan = IocChangePlan(
        plan_id=plan_id,
        path=str(path),
        source_sha256=source_sha256,
        planned_sha256=planned_sha256,
        changes=changes,
        unified_diff=diff,
        diagnostics=diagnostics,
    )
    return plan, rendered_bytes


def plan_ioc_changes(request: IocPlanRequest, settings: Settings) -> IocChangePlan:
    """Create a deterministic IOC change plan. Do not write the source file."""
    plan, _ = prepare_ioc_changes(request, settings)
    return plan
