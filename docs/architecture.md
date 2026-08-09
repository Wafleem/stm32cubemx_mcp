# Architecture

## Responsibility boundary

The Model Context Protocol (MCP) server is not the multimodal reasoning system.
The host agent interprets user requests, datasheets, schematics, pinout images,
and existing source code. It passes a structured hardware intent to the MCP.
The MCP then performs bounded, reproducible operations against local projects
and STM32 tools.

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

The supported CubeMX command-line interface (CLI) can load a microcontroller
unit (MCU) or board. It can load and save an `.ioc` file. It can select a
toolchain and generate a project. It does not provide commands for the full
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

## New IOC creation

The IOC creation tool accepts a board identifier or MCU identifier. It does
not accept a free-form CubeMX script. It uses this sequence:

```text
validate request -> create staging directory -> load board or MCU
                 -> save IOC -> relocate staging paths -> validate IOC
                 -> copy and verify IOC in the new output directory
```

The output directory must not exist. The tool removes the staging directory
after a failure.

## New-project generation

The generation tool only accepts a new output directory. It uses this sequence:

```text
read source IOC -> create staging directory -> set staged project identity
                -> validate staged IOC -> run CubeMX generation
                -> resolve all Eclipse linked resources
                -> verify required source, HAL, and CMSIS files
                -> relocate staging paths -> move the complete output container
```

The generated output can contain an Eclipse project below a larger container.
The tool preserves the complete container. It returns the container path and
the Eclipse project path as separate fields. The tool removes the staging
directory after a failure. It does not change the source IOC file.

Round-trip validation uses a temporary save-as filename. CubeMX can set the
temporary internal project name and filename from this save-as target. The
round-trip check permits these two changes. The generated-project check still
requires the requested project identity.

## Existing-project regeneration preview

The preview tool creates content manifests before and after staged regeneration.
Each manifest contains the relative path, file size, and SHA-256 hash. The tool
uses this sequence:

```text
scan source -> copy project -> validate an isolated IOC copy
            -> confirm source did not change -> regenerate project copy
            -> restore source path references -> scan copy -> compare files
            -> confirm source did not change -> return plan -> remove copy
```

The tool does not copy build-output directories or Git metadata. It rejects
symbolic links and Windows reparse points. It also applies configurable file
count and project size limits. A source-change diagnostic identifies each
added, modified, or deleted path.

CubeMX appends the internal project name to its project path. The preview
therefore stages the project below a temporary parent and passes the parent to
CubeMX. This layout regenerates the staged project root. It does not create a
second nested project.

## Path and process safety

- All project paths must resolve beneath configured allowed roots.
- Symlink/junction escapes are rejected after path resolution.
- Arbitrary raw CubeMX commands are not exposed as an MCP tool.
- External processes are launched with argument arrays, never shell strings.
- Package downloads, login, flashing, and debugging are outside the first
  release and require separate explicit tools.
- Stdio protocol output is isolated from logs and child-process output.
- Timeouts and captured-output limits apply to every external command.
- Successful process results contain a short captured-output tail.
- Nonfatal process warnings use structured diagnostics.

## Tool contract

Implemented foundation:

- `cubemx_environment()`
- `cubemx_list_ioc(root, recursive, limit)`
- `cubemx_inspect_ioc(path)`
- `cubemx_plan_ioc_changes(request)`
- `cubemx_apply_ioc_changes(request)`
- `cubemx_validate_ioc(path)`
- `cubemx_create_ioc(request)`
- `cubemx_generate_project(request)`
- `cubemx_plan_regeneration(request)`

Planned configuration and execution tools:

- `cubemx_plan_project(intent, existing_ioc=None)`
- `cubemx_preview_plan(plan_id)`
- `cubeide_build_project(request)`
- `cubeprogrammer_list_probes()`
- `cubeprogrammer_plan_flash(request)`
- `cubeprogrammer_flash(request)`

The intent format should describe capabilities rather than immediately forcing
pins. For example, a universal asynchronous receiver-transmitter (UART)
request includes role, baud rate, flow control, direct memory access (DMA),
interrupt, and preferred or forbidden pins. Pin assignment is a constraint
result with an explanation. It is not free-form text.

## First reference scenario

The first end-to-end fixture will target an STM32F4 Nucleo board and exercise:

- board/MCU selection;
- Serial Wire Debug (SWD) preservation;
- system clock configuration;
- general-purpose input/output (GPIO) light-emitting diode (LED) and button
  labels;
- one UART with optional DMA;
- STM32CubeIDE generation and build;
- CMake generation as the second build path.
