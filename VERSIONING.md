# Project versioning

`[project].version` in `pyproject.toml` is the WhereToLive.LA version.
The MCP server reports it through the installed Python package metadata.

## When to bump

The bump levels follow [Semantic Versioning](https://semver.org/). For this
project, apply compatibility rules to supported interfaces such as MCP tool
names, arguments, and response formats. Map features and fixes also count
toward the app release.

Bump once for a release. Choose the highest level warranted by all changes
since the previous release. Ordinary feature and fix commits can accumulate
without changing the version.

| Level | When to use it |
| --- | --- |
| Major | A breaking change to a supported interface, such as removing an MCP tool, adding a required argument to an existing tool, or changing a response incompatibly. Reset minor and patch to zero. |
| Minor | A backward-compatible feature or substantial improvement, such as adding a map filter or an MCP tool. Reset patch to zero. |
| Patch | A backward-compatible fix, such as correcting map behavior, fixing an MCP response to match its documented behavior, or resolving a security issue. |

Routine listing refreshes, dependency updates, internal refactors, tests, and
documentation edits can ship without a bump. If one of those changes delivers
a feature, fixes a bug, or breaks a supported interface, classify it by that
effect. Dependency version numbers do not determine the project version.

## Examples

These examples start from the `1.6.0` baseline.

| Change | Next version |
| --- | --- |
| Make an optional MCP tool argument required. Existing clients can fail on previously valid requests. | `2.0.0` |
| Add a map filter or an MCP tool while preserving existing behavior. | `1.7.0` |
| Fix cluster clicks that open the wrong listing popup, as in commit `2a73cc4`. | `1.6.1` |
| Refresh the weekly listing spreadsheets, as in commit `06b3200`. | Keep `1.6.0` |
| Release a new filter and the popup fix together. The filter sets the bump level. | `1.7.0` |

## How to bump

1. Update `[project].version` in `pyproject.toml` using `MAJOR.MINOR.PATCH`.
2. Run `uv lock` to update the local project entry in `uv.lock`. The Docker
   build installs from this lockfile with `uv sync --frozen`.
3. Run `uv lock --check` and review the diff. Confirm that the
   `wheretolive-la` entry matches the new version and that any dependency
   changes are intended. Include both files in the version bump.
