# Architecture

## Responsibility boundary

The MCP is not the multimodal reasoning system. The host agent interprets user
requests, datasheets, schematics, pinout images, and existing source code. It
passes a structured hardware intent to the MCP. The MCP then performs bounded,
reproducible operations against local projects and STM32 tools.

This separation keeps the hard-to-test natural-language interpretation in the
agent and puts state changes behind typed, testable contracts.

## Layers

1. **MCP interface** exposes small tools with structured inputs and outputs.
2. **Intent and planning** resolves requested peripherals, clocks, pins,
   middleware, and project settings into a proposed plan.
3. **IOC model** parses and renders `.ioc` content while preserving unknown
   keys and CubeMX-owned ordering where possible.
4. **Transaction engine** creates a content-addressed preview, checks that the
   source did not change, stages edits, and records a rollback copy.
5. **CubeMX adapter** creates a version-specific command script and invokes the
   installed CubeMX launcher without a shell.
6. **Build adapters** invoke STM32CubeIDE headlessly or configure and build a
   generated CMake project.
7. **Diagnostics** normalize tool output into actionable messages for agents.

Operating-system-specific launcher discovery and invocation live only in the
adapter layer. Domain and IOC logic must remain platform-neutral.

## Why `.ioc` transactions are necessary

The supported CubeMX CLI can load an MCU or board, load/save an `.ioc`, select a
toolchain, and generate a project. It does not provide commands for the full
graphical pin and peripheral configurator. `.ioc` is therefore the practical
configuration interchange, but it is not a stable public schema.

The MCP must consequently:

- preserve keys it does not understand;
- associate behavior with detected CubeMX/database versions;
- preview every semantic and textual difference;
- validate a staged file by loading and re-saving it with CubeMX;
- reject unresolved conflicts instead of guessing;
- avoid writing the user's source file until validation succeeds.

## Mutation protocol

Planned write tools follow this sequence:

```text
inspect -> plan -> preview -> apply to staging -> CubeMX round-trip validation
        -> atomically replace IOC -> generate -> build -> report
```

A plan records the source file's SHA-256 digest. `apply` fails if the digest no
longer matches, preventing an agent from overwriting user or CubeMX changes made
after the preview.

Generation and building are separate operations. A valid `.ioc` should not
implicitly overwrite a generated project, and successful generation should not
be reported as a successful compile.

## Path and process safety

- All project paths must resolve beneath configured allowed roots.
- Symlink/junction escapes are rejected after path resolution.
- Arbitrary raw CubeMX commands are not exposed as an MCP tool.
- External processes are launched with argument arrays, never shell strings.
- Package downloads, login, flashing, and debugging are outside the first
  release and require separate explicit tools.
- Stdio protocol output is isolated from logs and child-process output.
- Timeouts and captured-output limits apply to every external command.

## Tool contract

Implemented read-only foundation:

- `cubemx_environment()`
- `cubemx_list_ioc(root, recursive, limit)`
- `cubemx_inspect_ioc(path)`
- `cubemx_plan_ioc_changes(request)`
- `cubemx_apply_ioc_changes(request)`
- `cubemx_validate_ioc(path)`

Planned configuration and execution tools:

- `cubemx_plan_project(intent, existing_ioc=None)`
- `cubemx_preview_plan(plan_id)`
- `cubemx_generate_project(path, toolchain)`
- `cubemx_build_project(project_path, configuration)`

The intent format should describe capabilities rather than immediately forcing
pins. For example, a UART request includes role, baud rate, flow control, DMA,
interrupt, and preferred/forbidden pins. Pin assignment is a constraint result
with an explanation, not free-form text.

## First reference scenario

The first end-to-end fixture will target an STM32F4 Nucleo board and exercise:

- board/MCU selection;
- SWD preservation;
- system clock configuration;
- GPIO LED and button labels;
- one UART with optional DMA;
- STM32CubeIDE generation and build;
- CMake generation as the second build path.
