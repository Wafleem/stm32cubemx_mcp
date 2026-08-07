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
    pin: str = Field(description="Microcontroller unit pin name, such as PA2.")
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


class IocApplyRequest(BaseModel):
    plan_request: IocPlanRequest
    expected_source_sha256: str = Field(
        min_length=64,
        max_length=64,
        description="Source hash from the approved IOC change plan.",
    )
    skip_cubemx_validation: bool = Field(
        default=False,
        description="Skip CubeMX validation. The server must permit this bypass.",
    )


class IocApplyResult(BaseModel):
    plan_id: str
    path: str
    backup_path: str | None = None
    source_sha256: str
    applied_sha256: str
    changed: bool
    cubemx_validated: bool
    changed_keys: list[str] = Field(default_factory=list)


class CubeMXProcessResult(BaseModel):
    succeeded: bool
    exit_code: int | None = None
    timed_out: bool = False
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""


class IocValidationResult(BaseModel):
    path: str
    valid: bool
    source_sha256: str
    roundtrip_sha256: str | None = None
    cubemx: CubeMXProcessResult
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class IocCreateRequest(BaseModel):
    target_kind: Literal["board", "mcu"]
    target: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="CubeMX board or microcontroller unit identifier.",
    )
    output_directory: str
    project_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    board_mode: Literal["allmodes", "nomode"] = "allmodes"
    toolchain: Literal["STM32CubeIDE", "CMake"] = "STM32CubeIDE"


class IocCreateResult(BaseModel):
    succeeded: bool
    ioc_path: str
    project_path: str
    project_name: str
    target_kind: Literal["board", "mcu"]
    target: str
    board_mode: Literal["allmodes", "nomode"] | None = None
    toolchain: Literal["STM32CubeIDE", "CMake"]
    source_sha256: str | None = None
    validation: IocValidationResult | None = None
    cubemx: CubeMXProcessResult
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class ProjectGenerationRequest(BaseModel):
    ioc_path: str
    output_directory: str
    project_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    toolchain: Literal["STM32CubeIDE"] = "STM32CubeIDE"


class ProjectGenerationResult(BaseModel):
    succeeded: bool
    output_directory: str
    project_path: str
    project_name: str
    toolchain: Literal["STM32CubeIDE"]
    source_sha256: str
    validation: IocValidationResult
    cubemx: CubeMXProcessResult | None = None
    generated_files: list[str] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class RegenerationPlanRequest(BaseModel):
    project_directory: str
    ioc_path: str | None = None


class ProjectFileChange(BaseModel):
    path: str
    change: Literal["added", "modified", "deleted"]
    before_sha256: str | None = None
    after_sha256: str | None = None
    before_size: int | None = None
    after_size: int | None = None
    unified_diff: str | None = None


class RegenerationPlanResult(BaseModel):
    succeeded: bool
    plan_id: str | None = None
    project_path: str
    ioc_path: str
    source_manifest_sha256: str
    planned_manifest_sha256: str | None = None
    changes: list[ProjectFileChange]
    validation: IocValidationResult | None = None
    cubemx: CubeMXProcessResult | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
