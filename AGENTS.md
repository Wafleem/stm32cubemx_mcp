# Project instructions

## Technical English

Use ASD-STE100 Technical English for all project communication.

This rule applies to these items:

- documentation;
- tool names and tool descriptions;
- messages and diagnostics;
- issue and pull request text;
- discussions with the user.

Use short sentences. Use the active voice. Give one instruction in each
sentence. Use one term for one meaning. Define each necessary acronym at its
first use. Do not use contractions. Do not use humor, idioms, or informal
phrases. Keep approved product names and source-code identifiers unchanged.

Review new user-facing text before you complete a change.

## Project safety

Do not change a user `.ioc` file without a preview and source hash check.
Validate staged `.ioc` changes with STM32CubeMX before file replacement. Do not
send child-process output to stdout when the server uses the stdio transport.

