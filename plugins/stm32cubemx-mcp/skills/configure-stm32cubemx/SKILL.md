---
name: configure-stm32cubemx
description: Inspect, plan, validate, and generate STM32CubeMX IOC and STM32CubeIDE projects through the stm32cubemx MCP tools. Use for STM32 .ioc settings, pin assignments, peripherals, clocks, project settings, CubeMX validation, new CubeIDE generation, or existing-project regeneration previews.
---

# Configure STM32CubeMX

Use the MCP as the deterministic execution layer. Analyze datasheets,
schematics, images, and user requirements in the host agent before you create a
structured tool call.

## Workflow

1. Call `cubemx_environment`. Confirm that CubeMX is available. Review the
   allowed roots.
2. Call `cubemx_list_ioc` when the IOC path is not known. Call
   `cubemx_inspect_ioc` before you plan a change to an existing IOC file.
3. Resolve the requested MCU functions and pins from the available technical
   evidence. Do not state that the MCP read a datasheet or schematic.
4. Call `cubemx_plan_ioc_changes`. Use `pin_assignments` and
   `enabled_peripherals` for structural changes. Use `parameter_updates` only
   for known IOC parameter keys.
5. Show the planned changes, diagnostics, and source hash. Get user approval
   before you call `cubemx_apply_ioc_changes`, unless the user already gave
   explicit approval for that exact plan.
6. Apply the same plan request with `expected_source_sha256` from the approved
   plan. Keep CubeMX validation enabled. Do not set `skip_cubemx_validation`
   unless the user explicitly requests the bypass and accepts the risk.
7. Use `cubemx_generate_project` only for a new output directory. Use
   `cubemx_plan_regeneration` for an existing STM32CubeIDE project.

## Safety rules

- Preserve PA13 and PA14 SWD signals unless the user explicitly approves their
  reassignment.
- Stop if the source hash changes after the preview.
- Treat IOC validation, project generation, and compilation as different
  results.
- Do not state that an existing project was regenerated. The current tool only
  previews existing-project regeneration.
- Do not state that a project compiled. The MCP does not have a build tool yet.
- Report CubeMX diagnostics. Do not replace an unresolved configuration with a
  guessed setting.

## Typical sequence

For a request such as "Configure USART2 on PA2 and PA3," inspect the IOC, plan
the peripheral and pin changes, show the plan, apply the approved plan, and
then generate a new project or preview regeneration of the existing project.
