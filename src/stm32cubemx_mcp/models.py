from typing import Literal

from pydantic import BaseModel, Field


class Diagnostic(BaseModel):
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    line: int | None = None


class ExecutableInfo(BaseModel):
    name: str
    available: bool
    path: str | None = None
    version: str | None = None
    invocation_prefix: list[str] = Field(default_factory=list)


class EnvironmentReport(BaseModel):
    operating_system: str
    architecture: str
    python_version: str
    python_executable: str
    cubemx: list[ExecutableInfo]
    cubeide: list[ExecutableInfo]
    cmake: ExecutableInfo
    ninja: ExecutableInfo
    allowed_roots: list[str]
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class IocPin(BaseModel):
    pin: str
    signal: str | None = None
    label: str | None = None
    locked: bool = False


class IocSummary(BaseModel):
    path: str
    source_sha256: str
    size_bytes: int
    mcu_name: str | None = None
    mcu_part_number: str | None = None
    mcu_family: str | None = None
    mcu_package: str | None = None
    board: str | None = None
    project_name: str | None = None
    toolchain: str | None = None
    cubemx_version: str | None = None
    database_version: str | None = None
    peripherals: list[str] = Field(default_factory=list)
    pins: list[IocPin] = Field(default_factory=list)
    clock_values_hz: dict[str, int] = Field(default_factory=dict)
    entry_count: int = 0


class IocInspection(BaseModel):
    summary: IocSummary
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class IocFile(BaseModel):
    path: str
    size_bytes: int


class IocListResult(BaseModel):
    root: str
    files: list[IocFile]
    truncated: bool = False


class IocPinAssignment(BaseModel):
    pin: str = Field(description="MCU pin name, such as PA2.")
    signal: str = Field(description="CubeMX signal name, such as USART2_TX.")
    label: str | None = Field(default=None, description="Optional GPIO label.")
    locked: bool = Field(default=True, description="Lock the pin assignment in CubeMX.")


class IocPlanRequest(BaseModel):
    path: str
    pin_assignments: list[IocPinAssignment] = Field(default_factory=list)
    enabled_peripherals: list[str] = Field(default_factory=list)
    parameter_updates: dict[str, str] = Field(default_factory=dict)
    project_name: str | None = None
    toolchain: Literal["STM32CubeIDE", "CMake"] | None = None
    allow_debug_pin_change: bool = False


class IocPlannedChange(BaseModel):
    key: str
    before: str | None = None
    after: str
    reason: str


class IocChangePlan(BaseModel):
    plan_id: str
    path: str
    source_sha256: str
    planned_sha256: str
    changes: list[IocPlannedChange]
    unified_diff: str
    validation_status: Literal["not_run"] = "not_run"
    diagnostics: list[Diagnostic] = Field(default_factory=list)
