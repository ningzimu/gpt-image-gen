# AGENTS.md

## Contribution Flow

- All non-trivial changes should go through a pull request.
- PR titles must follow Conventional Commit style, for example:
  - `feat: add image edit option`
  - `fix: handle expired Codex auth`
  - `docs: clarify Claude Code installation`
- Commit messages, PR titles, changelog entries, and release notes must be written in English.

## Changelog

- User-visible changes must update `CHANGELOG.md`.
- Add unreleased entries under `## Unreleased`.
- Use one of these sections:
  - `### Features`
  - `### Improvements`
  - `### Fixes`
  - `### Documentation`
- Changelog entries must be written in English.

## Release Process

- Versions use SemVer.
- Git tags must use a leading `v`, for example `v0.1.0`.
- GitHub Releases are generated from the matching `CHANGELOG.md` version section.
- Do not write GitHub Release notes manually unless updating an existing release body to match `CHANGELOG.md`.

## Verification

- Before opening a PR, verify changed GitHub workflow YAML parses when practical.
- For workflow shell snippets, run a syntax check such as `bash -n` when practical.
- For script changes, run `python3 -m py_compile skills/codex-gpt-image/scripts/codex_gpt_image.py`.
