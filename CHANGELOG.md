# Changelog

Release notes are generated from this file. Keep changelog entries in English.

## Unreleased

### Features

- Add the initial Codex GPT Image skill and Codex OAuth image-generation CLI.
- Add Codex device-code login fallback for machines without an existing Codex auth file.

### Improvements

- Increase the default Codex Images request timeout to 600 seconds.
- Route Codex OAuth image requests through the Codex Images endpoints instead of the Responses image-generation tool. (#2)
- Add CLI options for moderation, output compression, edit masks, and end-user identifiers. (#2)
- Align image size, background, and moderation defaults with the official Images API. (#2)
- Make fixed-value image options explicit in CLI choices and allow overriding the Codex OAuth client id. (#2)
- Include the Codex image request originator and account headers when available. (#2)

### Fixes

- Derive the ChatGPT account header only from explicit Codex auth account fields. (#2)
- Allow `generate --dry-run` to validate request shape without loading Codex auth. (#2)
- Remove unsupported transparent backgrounds from the `--background` choices for `gpt-image-2`. (#2)

### Documentation

- Add Chinese and English installation and usage documentation.
- Add an OpenAI Images API parameter reference for agent workflows. (#2)
- Consolidate Images API parameters and Codex request-shape guidance into one reference. (#2)
- Improve README SEO wording for OpenClaw, Claude Code, Codex OAuth, and gpt-image-2 discovery.
- Remove legacy alternate-model guidance from the skill instructions. (#2)
- Replace concrete skill workflow examples with principle-based parameter guidance. (#2)
- Update install examples to use the canonical `ningzimu/codex-gpt-image` repository name.
- Remove stale transparent-background examples from the README files. (#2)
- Remove concrete size choices from README examples so the documented default stays `auto`. (#2)
- Clarify that the Codex Images backend path is not the recommended OpenAI API integration and may change. (#2)
