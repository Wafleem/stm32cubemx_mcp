# Study guide: Build the MCP from first principles

## Purpose

This guide teaches the architecture of `stm32cubemx-mcp` by reconstruction.
You will build a small learning server beside the production server. You will
implement one concept at a time. You will write a test for each safety rule.

The learning server will not replace the production server. It will use copied
fixtures and temporary directories. It will not change a user STM32CubeMX
project configuration (IOC) file.

This guide has two goals:

1. Understand why each layer exists.
2. Be able to explain the complete path from an agent request to a safe result.

## Learning result

At the end of the course, you will be able to explain and implement these
functions:

- expose a typed Model Context Protocol (MCP) tool;
- validate tool input and return structured output;
- restrict file access to configured roots;
- parse an IOC file without loss of unrelated data;
- inspect pins, peripherals, clocks, and project settings;
- create a deterministic change plan and text difference;
- detect a stale plan with a SHA-256 content hash;
- validate staged content before file replacement;
- create a backup and perform an atomic replacement;
- run STM32CubeMX without a command shell;
- validate a new STM32CubeIDE output container;
- preview regeneration without a source-project change;
- keep MCP standard input and standard output free of child-process data.

## First-principles model

An MCP server is an adapter between an agent and a deterministic system.

The agent handles ambiguous information. It reads natural language,
datasheets, schematics, images, and source code. The MCP server accepts a typed
request. It performs a bounded operation. It returns a typed result.

```text
user evidence and request
          |
          v
AI agent: interpret intent and resolve ambiguity
          |
          v
MCP tool: validate a structured request
          |
          v
domain code: inspect, plan, or apply
          |
          v
adapter: file system or STM32CubeMX
          |
          v
structured result and diagnostics
```

The server must not guess a hardware fact. It must reject an unresolved input.
It must make every file change observable and recoverable.

## The central safety invariant

The production server uses this invariant:

> Do not replace a user IOC file unless the user approved a plan for the exact
> source content and STM32CubeMX validated the staged result.

This invariant produces the main transaction:

```text
read -> hash -> parse -> plan -> show difference -> approve
     -> hash again -> stage -> validate -> back up -> atomically replace
     -> verify the applied hash
```

Each step removes one failure class. The course will make you identify that
failure class before you implement the step.

## How we will work together

Do not start all stages at one time. Give one of these marks when you are ready:

- `START STAGE 0`
- `START STAGE 1`
- `CHECK MY WORK`
- `GIVE ME A HINT`
- `EXPLAIN THIS FAILURE`
- `CONTINUE`

When you give `START STAGE 0`, I will create the separate learning directory
and the first test only. I will explain the concept. You will implement the
small task. I will review your result. We will run the tests. We will then make
a checkpoint commit.

I will not give the complete implementation before your first attempt. I can
give a small hint when you are blocked. After the stage passes, we will compare
your design with the production implementation.

## Study rules

1. Put all learning code below `learning/mcp_from_scratch/`.
2. Use only copied IOC fixtures.
3. Use temporary directories for write tests.
4. Use a fake STM32CubeMX runner before you use the installed application.
5. Write or read the failing test before you write implementation code.
6. State the safety invariant for the stage in your own words.
7. Do not copy production code before your first attempt.
8. Make one checkpoint commit after each completed stage.
9. Keep application and child-process output away from MCP standard output.
10. Stop after each teaching checkpoint.

## Planned learning directory

We will create this structure when you start:

```text
learning/mcp_from_scratch/
|-- README.md
|-- pyproject.toml
|-- src/learning_mcp/
|   |-- server.py
|   |-- models.py
|   |-- settings.py
|   |-- ioc.py
|   |-- planning.py
|   |-- transaction.py
|   |-- process.py
|   |-- validation.py
|   |-- generation.py
|   `-- regeneration.py
`-- tests/
    |-- fixtures/
    |-- test_server.py
    |-- test_settings.py
    |-- test_ioc.py
    |-- test_planning.py
    |-- test_transaction.py
    |-- test_process.py
    |-- test_validation.py
    |-- test_generation.py
    `-- test_regeneration.py
```

The names mirror the production layers. The learning implementations will be
smaller.

## Course map

Stage | Subject | Main question | Output
--- | --- | --- | ---
0 | System boundary | What work belongs to the agent and what work belongs to the MCP? | A request-to-result trace
1 | Message transport | How does one process call a tool in another process? | A small learning dispatcher
2 | Typed MCP tool | How does a Python function become an agent tool? | A read-only MCP server
3 | Configuration and path policy | How does the server limit its authority? | An allowed-root resolver
4 | IOC document model | How can we edit known keys and preserve unknown lines? | A loss-aware parser and renderer
5 | Semantic inspection | How do raw keys become hardware information? | An IOC summary
6 | Deterministic planning | How can a write become a reviewable read operation? | A change plan and text difference
7 | Safe apply transaction | How can a file replacement be approved, validated, and recoverable? | A guarded apply operation
8 | Process adapter | How can the server run CubeMX safely? | A bounded script runner
9 | CubeMX round-trip validation | What does validation prove? | A staged load-and-save check
10 | New IOC creation | How can generated content become visible only after validation? | A staged creation workflow
11 | New-project generation | What is a complete CubeIDE output? | A validated output container
12 | Regeneration preview | How can we compare regeneration without changing the source? | A file-manifest plan
13 | Plugin integration | How does Codex discover the skill and MCP server? | A validated plugin package

## Stage 0: Draw the responsibility boundary

### Principle

Natural-language interpretation is probabilistic. File and tool operations must
be deterministic. The boundary must be explicit.

### Your task

Trace this request on paper:

```text
Configure USART2 on PA2 and PA3. Preserve Serial Wire Debug. Show the change
before you modify the IOC file.
```

Classify each action as agent work or MCP work:

- interpret `USART2` as a peripheral requirement;
- confirm the alternate functions from technical evidence;
- inspect the current IOC file;
- build the requested pin assignments;
- calculate a source hash;
- produce a text difference;
- get approval;
- validate staged content with CubeMX;
- replace the source file;
- report diagnostics.

### Exit test

You can explain why the MCP does not read the schematic by itself. You can also
explain why the agent does not write the IOC file directly.

### Production reference after your attempt

- `src/stm32cubemx_mcp/server.py`
- `docs/architecture.md`

### Checkpoint commit

`study: document the agent and MCP boundary`

## Stage 1: Build a small message dispatcher

### Principle

Two processes need a message format, a transport, a tool name, arguments, a
result, and an error form.

JavaScript Object Notation Remote Procedure Call (JSON-RPC) supplies these
ideas. MCP adds initialization, tool discovery, tool schemas, and standard
message rules.

### Your task

Build a learning-only line dispatcher with the Python standard library. Read
one JSON object from standard input. Dispatch a `ping` method. Write one JSON
result to standard output.

This dispatcher is not a complete MCP implementation. Do not use it in the
production plugin. Its only purpose is to expose the transport concepts.

### Tests

- A valid `ping` request returns a result with the same request identifier.
- An unknown method returns a structured error.
- A log message goes to standard error.
- Standard output contains only one protocol message.

### Questions

1. Why does a normal `print()` call break a standard-input MCP server?
2. Why must the response contain the request identifier?
3. What problems remain when the dispatcher does not publish a schema?

### Checkpoint commit

`study: implement a minimal message dispatcher`

## Stage 2: Replace the dispatcher with a typed MCP tool

### Principle

The MCP software development kit (SDK) handles protocol framing and tool
discovery. Python type annotations and Pydantic models produce the tool schema.

### Your task

Create a small MCP server with one tool named `lab_environment`. Return the
operating system, Python version, and current working directory. Do not call
STM32CubeMX.

### Tests

- The MCP client can list `lab_environment`.
- The tool input schema has no required arguments.
- The result has the expected typed fields.
- The server does not write a log to standard output.

### Questions

1. What does the decorator register?
2. Which code runs at import time?
3. Which code runs for each tool call?
4. Why should the tool wrapper remain small?

### Production reference after your attempt

- `src/stm32cubemx_mcp/server.py`
- `src/stm32cubemx_mcp/models.py`
- `tests/test_server.py`

### Checkpoint commit

`study: expose a typed MCP environment tool`

## Stage 3: Limit file authority

### Principle

A useful local tool needs file access. It must not receive authority over the
complete file system.

An allowed root is a directory below which the server can read or write. Path
resolution must occur before the containment check. This prevents `..`, a
symbolic link, or a Windows junction from escaping the root.

### Your task

Implement a frozen settings object. Read one or more allowed roots from an
environment variable. Implement `resolve_allowed_path()`.

### Tests

- An absolute path below the root is accepted.
- A relative path below the root is accepted.
- A path above the root is rejected.
- A missing output path can be checked with `must_exist=False`.
- A resolved link that leaves the root is rejected.
- A nonpositive size or timeout limit is rejected.

### Questions

1. Why must the code resolve the path before it tests containment?
2. Why is the current directory a useful default root?
3. Why must input paths and output paths use the same policy?

### Production reference after your attempt

- `src/stm32cubemx_mcp/settings.py`
- `tests/test_settings.py`

### Checkpoint commit

`study: enforce allowed project roots`

## Stage 4: Parse and render an IOC document

### Principle

An IOC file is a key-value document, but it is not a stable public schema. The
server knows some keys. CubeMX can add other keys. A safe editor must preserve
data that it does not understand.

### Your task

Build an `IocDocument` type. Store these items:

- ordered key-value entries;
- original lines;
- newline style;
- final-newline state;
- line locations for each key;
- diagnostics for malformed lines and duplicate keys.

Implement a renderer that updates selected keys. Preserve all unrelated lines.
Append a new key when it does not exist.

### Tests

- Comments and blank lines remain unchanged.
- An unknown key remains unchanged.
- The original newline style remains unchanged.
- A UTF-8 byte-order mark remains present.
- The final-newline state remains unchanged.
- A duplicate key produces a diagnostic.
- The renderer refuses to update a duplicate key.

### Questions

1. Why is `dict(parse(file))` not a lossless document model?
2. Why is a duplicate key unsafe for an edit?
3. Why should parsing return diagnostics instead of silently ignoring all bad
   data?

### Production reference after your attempt

- `src/stm32cubemx_mcp/ioc.py`
- `tests/test_ioc.py`

### Checkpoint commit

`study: implement a loss-aware IOC document`

## Stage 5: Convert raw IOC keys to a semantic summary

### Principle

The agent needs hardware meaning. It should not search raw lines for every
question.

### Your task

Implement a read-only inspector. Extract these values:

- MCU name and part number;
- board identifier;
- project name and toolchain;
- CubeMX and database versions;
- configured peripherals;
- configured pins, signals, labels, and lock states;
- known clock-frequency values;
- file size and SHA-256 hash.

### Tests

- Indexed peripheral keys retain their document order.
- Duplicate peripheral values appear once.
- Pin metadata joins on the pin name.
- Invalid clock text does not become a number.
- The source hash changes when one source byte changes.

### Questions

1. Why is inspection read-only?
2. Why does the result include the source hash?
3. Why must the code support current and legacy toolchain keys?

### Production reference after your attempt

- `src/stm32cubemx_mcp/ioc.py`
- `tests/fixtures/nucleo_f401re.ioc`

### Checkpoint commit

`study: summarize IOC hardware state`

## Stage 6: Turn a write request into a deterministic plan

### Principle

A safe write begins as a read operation. The plan must fully describe the
proposed change without changing the source.

### Your task

Implement a plan request for pin assignments, enabled peripherals, known
parameter updates, project name, and toolchain. Return these values:

- source hash;
- planned hash;
- stable plan identifier;
- changed keys with before and after values;
- reason for each change;
- unified text difference;
- diagnostics.

Protect PA13 and PA14 Serial Wire Debug (SWD) assignments by default. Reject a
pin or peripheral structural key in the generic parameter map.

### Tests

- The plan does not write the source file.
- Equal inputs produce the same plan identifier.
- Request order does not create an unstable identifier where order has no
  meaning.
- A new peripheral updates its index and count.
- A new pin updates its index and count.
- A duplicate pin request is rejected.
- A protected SWD change is rejected without an explicit override.
- Invalid newlines and `=` characters are rejected in values.

### Questions

1. What makes a plan deterministic?
2. Why does the plan include both a semantic list and a text difference?
3. Why is a generic key-value update less safe than a typed pin assignment?

### Production reference after your attempt

- `src/stm32cubemx_mcp/planning.py`
- `tests/test_planning.py`

### Checkpoint commit

`study: create deterministic IOC plans`

## Stage 7: Apply an approved plan safely

### Principle

Approval applies to exact content. It does not apply to a filename for all
future content.

The source hash is an optimistic concurrency check. It detects a change between
preview and apply.

### Your task

Implement this transaction:

1. Recreate the plan from the request.
2. Compare its source hash with the approved source hash.
3. Stop if the hashes differ.
4. Validate the planned bytes through an injected fake validator.
5. Create a content-addressed backup.
6. Write the planned bytes to a temporary file in the source directory.
7. flush and synchronize the temporary file;
8. atomically replace the source file;
9. calculate the applied hash;
10. restore the backup if the applied hash is wrong.

### Tests

- A stale source hash stops before validation and write.
- Failed validation leaves the source unchanged.
- A successful apply creates a backup.
- An existing correct backup is reused.
- An existing incorrect backup stops the apply.
- An apply with no changes does not create a backup.
- A simulated post-replacement hash failure restores the source.

### Questions

1. Why does apply recreate the plan?
2. Why must the temporary file be in the same directory as the source?
3. What does atomic replacement protect against?
4. What does atomic replacement not protect against?

### Production reference after your attempt

- `src/stm32cubemx_mcp/apply.py`
- `tests/test_apply.py`

### Checkpoint commit

`study: apply approved IOC plans atomically`

## Stage 8: Build a bounded process adapter

### Principle

External process execution is a trust boundary. The server must control the
executable, argument list, working directory, time limit, and captured output.

### Your task

Implement a generic learning runner. Then adapt it to a typed CubeMX script.
Use an argument array. Do not use a shell. Require the script to end with
`exit`. Reject a command that contains a line break.

Return these values:

- success state;
- exit code;
- timeout state;
- duration;
- bounded standard output;
- bounded standard error.

### Tests

- The runner passes an argument array to the process API.
- The runner uses `shell=False`.
- A timeout returns a structured failure.
- Long output is bounded.
- The command-script file is removed after success and failure.
- Child-process output does not pass directly to MCP standard output.

### Questions

1. Why is an argument array safer than one command string?
2. Why must output have a limit?
3. Why can exit code zero still require a warning diagnostic?

### Production reference after your attempt

- `src/stm32cubemx_mcp/discovery.py`
- `src/stm32cubemx_mcp/cubemx.py`
- `tests/test_cubemx.py`

### Checkpoint commit

`study: run bounded CubeMX scripts`

## Stage 9: Validate by CubeMX round trip

### Principle

Parsing proves that the server can read text. A CubeMX round trip proves that
CubeMX can load and save staged content. It also shows whether CubeMX preserves
required settings.

### Your task

Copy the candidate bytes to an isolated temporary directory. Run these logical
commands through an injected runner:

```text
config load <staged input>
project path <temporary directory>
config saveas <roundtrip.ioc>
exit
```

Compare the required semantic entries with the round-trip document. Do not
require the temporary project name and filename to remain equal. CubeMX can set
them from `roundtrip.ioc`.

### Tests

- Validation occurs outside the source project.
- Process failure returns an error diagnostic.
- Missing CubeMX confirmations fail validation.
- A missing round-trip file fails validation.
- A changed required pin signal fails validation.
- A save-as identity change does not fail validation.
- A Java preferences message becomes a nonfatal structured warning.

### Questions

1. What does round-trip validation prove?
2. What does it not prove?
3. Why are project identity fields a special case during save-as?

### Production reference after your attempt

- `src/stm32cubemx_mcp/cubemx.py`
- `tests/test_cubemx.py`

### Checkpoint commit

`study: validate staged IOC content with a round trip`

## Stage 10: Create a new IOC file with staged publication

### Principle

An incomplete output must not appear at the requested destination.

### Your task

Accept a typed board or MCU identifier. Create an IOC file in a temporary
directory. Validate it. Publish one new output directory only after success.
Reject an output directory that already exists.

### Tests

- Board and MCU requests produce different typed load commands.
- Free-form script text is rejected.
- An existing destination is rejected.
- Failed creation removes the stage.
- Failed validation removes any owned incomplete destination.
- Successful creation publishes one verified IOC file.

### Questions

1. Why does the tool not expose a raw CubeMX script argument?
2. Why must the destination not exist?
3. What state must the tool remove after each failure branch?

### Production reference after your attempt

- `src/stm32cubemx_mcp/creation.py`
- `tests/test_creation.py`

### Checkpoint commit

`study: publish validated IOC creation output`

## Stage 11: Validate a complete STM32CubeIDE project

### Principle

Process success does not prove artifact success. A generated project can have
an Eclipse project root below a larger output container.

### Your task

Generate in a temporary container. Find exactly one directory that contains
`.project` and `.cproject`. Parse the Eclipse `.project` file. Resolve every
linked resource. Reject a linked resource that leaves the container.

Require these artifacts:

- `main.c`;
- `main.h`;
- a Cortex Microcontroller Software Interface Standard (CMSIS) core header;
- a Hardware Abstraction Layer (HAL) source file;
- the requested IOC filename and internal project identity.

Return `output_directory` for the complete container. Return `project_path` for
the Eclipse project root. Do not assume that the two paths are equal.

### Tests

- A flat project layout succeeds.
- A valid nested project layout succeeds.
- A missing linked resource fails.
- A linked-resource escape fails.
- A missing required source file fails.
- An IOC identity mismatch fails.
- A failed result does not publish the destination.
- The source IOC hash remains unchanged.

### Questions

1. Why is exit code zero insufficient?
2. Why must the complete output container be preserved?
3. Why are `output_directory` and `project_path` separate fields?

### Production reference after your attempt

- `src/stm32cubemx_mcp/generation.py`
- `tests/test_generation.py`

### Checkpoint commit

`study: validate complete CubeIDE output`

## Stage 12: Preview existing-project regeneration

### Principle

A preview must measure a proposed state without changing the source state.

### Your task

Create a bounded project manifest. Store each relative path, file size, and
SHA-256 hash. Ignore known build-output directories. Reject symbolic links and
Windows reparse points.

Use this sequence:

```text
scan source -> copy project -> compare copy manifest
            -> validate an isolated IOC copy -> scan source again
            -> regenerate staged project -> scan staged project
            -> scan source again -> report added, modified, and deleted files
```

Stage the project below a temporary parent. Pass the parent to CubeMX. CubeMX
appends the internal project name to its project path.

### Tests

- A source file modification appears in the plan.
- An added file appears in the plan.
- A deleted file appears in the plan.
- A text file includes a bounded unified difference.
- A binary file does not require a text difference.
- A source change during copy stops the preview.
- A source change during validation stops the preview and reports the path.
- A source change during regeneration stops the preview.
- The preview does not create a second nested project.
- The source manifest is equal before and after a successful preview.

### Questions

1. Why must the code scan the source more than once?
2. Why does the project manifest include size and hash?
3. Why are build directories excluded?
4. Why is regeneration preview not regeneration apply?

### Production reference after your attempt

- `src/stm32cubemx_mcp/regeneration.py`
- `tests/test_regeneration.py`
- `tests/integration/test_real_cubemx.py`

### Checkpoint commit

`study: preview project regeneration without source writes`

## Stage 13: Package the tool for Codex

### Principle

The Python package supplies the executable server. The Codex plugin supplies
the MCP launch configuration and agent workflow guidance. The skill tells the
agent when and how to use the tools.

### Your task

Trace these files:

- `pyproject.toml` defines the `stm32cubemx-mcp` command;
- `plugins/stm32cubemx-mcp/.mcp.json` defines how Codex starts the command;
- `plugins/stm32cubemx-mcp/.codex-plugin/plugin.json` defines plugin metadata;
- `plugins/stm32cubemx-mcp/skills/configure-stm32cubemx/SKILL.md` defines the
  agent workflow;
- `.agents/plugins/marketplace.json` publishes the repository plugin.

Build a learning plugin that exposes the read-only learning tools. Do not add
write tools until their transaction tests pass.

### Tests

- Plugin validation passes.
- Codex can list the learning server.
- A new Codex task can call the read-only tool.
- The MCP process waits for protocol input without normal output.

### Questions

1. Why are the Python package and plugin separate?
2. Why does a plugin update need a new cache suffix?
3. Why must a new Codex task load an updated tool schema?

### Checkpoint commit

`study: package the learning MCP for Codex`

## Test strategy

Use four test levels.

### Level 1: Pure unit tests

Use in-memory text, copied fixtures, fake runners, and temporary directories.
These tests cover most logic. They must be fast.

### Level 2: MCP contract tests

Connect an MCP client to the server in memory. List tools. Check schemas. Call
read-only tools. These tests prove the public contract.

### Level 3: Fake-adapter workflow tests

Inject a fake CubeMX runner. Make it create expected files or controlled
failures. These tests exercise complete workflows without installed STM32
software.

### Level 4: Real STM32CubeMX integration test

Use the installed application only after the first three levels pass. Use a
temporary directory. Apply the memory safety gate. Confirm that the source hash
does not change. Keep generation and compilation as separate results.

## Stage review format

At every checkpoint, you will answer these five questions:

1. What input does this stage trust?
2. What output does this stage guarantee?
3. What persistent state can this stage change?
4. What failure can occur halfway through the stage?
5. Which test proves the main safety invariant?

I will review your answer and implementation. I will then explain how the
production code handles the same problem.

## Capstone

The capstone is a small MCP server with these four tools:

- `lab_environment`;
- `lab_inspect_ioc`;
- `lab_plan_ioc_changes`;
- `lab_apply_ioc_changes`.

The capstone must use allowed roots, typed models, deterministic plans, source
hash approval, injected validation, backups, and atomic replacement. It must
pass all unit and MCP contract tests before it uses real STM32CubeMX.

After the capstone, you will add one read-only project-generation validation
exercise. CMake generation remains a planned production capability. It is not
part of the first capstone.

## Completion criteria

You complete the course when you can do these tasks without reading the
production implementation:

- draw the request path and trust boundaries;
- implement a loss-aware IOC update;
- explain and demonstrate stale-plan rejection;
- explain the difference between validation, generation, and compilation;
- identify the output container and Eclipse project root;
- prove that a regeneration preview did not change the source;
- add a typed read-only MCP tool with contract tests.

## Start mark

When you are ready, send:

```text
START STAGE 0
```

I will create only the Stage 0 learning files. I will then guide you through the
boundary trace and wait for your answer.
