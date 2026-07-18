---
name: bash
description: POSIX-conscious Bash scripting patterns (set -euo pipefail, quoting, traps), debugging with shellcheck/set -x, performance, testing with Bats, and a code review checklist for reliable shell scripts and CLI tooling. Use this skill whenever the user is writing, reviewing, or debugging a shell/bash script, or asks about shell quoting, error handling, or shellcheck.
---

# Bash

POSIX-conscious Bash scripting for reliable automation and CLI tooling (coreutils, GNU Bash).

## Coding patterns

- Start scripts with `set -euo pipefail` so the script exits on errors, unset variable references, and failed pipeline stages instead of silently continuing
- Quote variable expansions as `"$var"` rather than bare `$var` to prevent word-splitting and pathname expansion on the value
- Use bash arrays (e.g. `local -a files=(...)`) instead of space-delimited strings to hold lists of filenames or arguments, especially when values may contain spaces
- Register a `trap 'cleanup' EXIT` (and often `INT TERM`) near the top of the script so temp files, locks, and background jobs are removed on every exit path, including errors
- Declare function-local state with `local` so functions don't leak or clobber variables in the caller's scope
- Use here-documents (`<<'EOF'` for literal text, `<<EOF` for interpolated text) to embed multi-line strings or generate config files inline
- Use parameter expansion defaults and guards like `${var:-default}` and `${var:?must be set}` instead of manual if-checks for optional or required variables
- Create temp files and directories with `mktemp`/`mktemp -d` instead of hardcoded paths under /tmp
- Use `$(command)` command substitution instead of legacy backticks, since it nests and quotes more predictably
- Prefer `[[ ... ]]` over `[ ... ]` for conditionals when the script is bash-only, since it supports `&&`/`||` internally, regex matching with `=~`, and avoids word-splitting pitfalls on unquoted variables

## Best practices

- Use `#!/usr/bin/env bash` as the shebang when relying on bash-specific features, rather than `#!/bin/sh`, which may resolve to dash or another POSIX shell
- Validate required arguments and external command dependencies (e.g. `command -v jq >/dev/null || exit 1`) at the top of the script before doing any work
- Keep scripts idempotent so re-running them after a partial failure doesn't duplicate work or corrupt state
- Favor small, single-purpose functions with descriptive names over one long linear script body
- Mark constants `readonly` after assignment so accidental reassignment fails loudly instead of silently changing behavior
- Avoid parsing `ls` output for filenames; use globs, `find ... -print0`, or `stat` instead, since filenames can contain spaces, newlines, or glob characters
- Send diagnostic and error messages to stderr (`>&2`) and reserve stdout for the script's actual output, so callers can pipe stdout cleanly
- Provide a `usage()`/`--help` function documenting flags, arguments, and exit codes for anyone maintaining or invoking the script later
- Use `getopts` for option parsing instead of ad hoc positional-argument checks that break when flag order changes
- Exit with distinct non-zero codes for distinct failure modes so calling scripts and CI systems can branch on why a script failed

## Debugging strategies

- Run `bash -x script.sh` (or wrap a suspect section in `set -x`/`set +x`) to print each command and its expanded arguments as it executes
- Set `PS4='+ ${BASH_SOURCE}:${LINENO}: '` before enabling `set -x` so trace output includes the file and line number of each traced command
- Use `bash -n script.sh` to check syntax without executing anything, as a fast pre-commit sanity check
- Run `shellcheck` on every script to catch unquoted expansions, unreachable code, and other static bugs before runtime
- Add `trap 'echo "error at line $LINENO" >&2' ERR` to report the exact failing line when a script aborts under `set -e`
- Use `declare -p varname` to print a variable's exact type (array, associative array, string) and current value for inspection
- Use `set -v` alongside `set -x` to see raw unexpanded source lines interleaved with their executed form, which helps isolate quoting bugs
- Isolate a failing pipeline stage by checking `${PIPESTATUS[@]}` after the pipeline instead of trusting only its overall exit code

## Performance and optimization

- Avoid invoking external processes like `cat`, `grep`, `sed`, or `awk` inside a per-line loop; operate on the whole file or stream at once instead of forking per iteration
- Prefer bash builtins such as `${var//pattern/repl}`, `[[ ]]`, and `(( ))` over forking `sed`, `expr`, or `test` for simple string and arithmetic work
- Use `[[ ]]` and `(( ))` instead of `[ ]` and `expr`, since the former are shell builtins and avoid spawning a subprocess per check
- Read files with `while IFS= read -r line; do ... done < file` rather than `cat file | while read line; do ... done`, avoiding an extra process and the subshell scoping a trailing pipe introduces
- Use parameter expansion (`${var#prefix}`, `${var%suffix}`, `${var//a/b}`) for simple trims and substitutions instead of piping through cut/sed/awk
- Batch external tool invocations, such as one `grep` over many files or `xargs -P` for parallelism, instead of invoking the tool once per item in a loop
- Use `mapfile -t arr < file` to load lines into an array in a single call instead of a manual append-in-loop pattern
- Measure hot scripts with `time` or timestamped `PS4` trace output to find which section actually dominates runtime before optimizing blindly

## Testing approach

- Use Bats (Bash Automated Testing System) to write `@test` blocks that assert on a script or function's exit status and output
- Structure scripts so logic lives in sourceable functions, letting Bats `source` the file and test functions directly rather than only exercising the whole script as a black box
- Run the test suite inside a clean, minimal container image to catch hidden dependencies on the developer's local PATH, aliases, or installed tools
- Use bats-assert and bats-support helpers (`assert_output`, `assert_success`, `assert_failure`) for readable, specific assertions instead of raw string comparisons
- Stub external commands by placing fake executables earlier in PATH during tests, so tests don't depend on real network calls or system state
- Explicitly test failure paths, such as missing files, bad arguments, or unset required variables, and assert the script exits non-zero with a useful message
- Run `shellcheck` as a fast static-analysis gate in CI before the slower Bats suite runs
- Emit `bats --tap` (or a JUnit formatter) output in CI so results integrate with standard test reporting dashboards

## Code review checklist

- Flag unquoted variable expansions (bare `$var` instead of `"$var"`) that can trigger unintended word-splitting or pathname expansion
- Flag any `eval` applied to input derived from arguments, environment variables, or external data; it is a command-injection vector
- Flag parsing of `ls` output (e.g. `for f in $(ls *.txt)`) instead of a glob or `find ... -print0`; filenames with spaces or newlines break it
- Flag missing error handling on critical commands: no `set -e`, no explicit `||` fallback, and no exit-status check after commands like `cd`, `rm`, or `mv`
- Flag `==` used inside `[ ]` in a script whose shebang declares POSIX `/bin/sh`; `==` is a bash extension and is not portable to dash or POSIX sh
- Flag scripts with no `set -euo pipefail` (or another deliberate, commented error-handling strategy) near the top
- Flag loops or command substitutions that iterate over unquoted output where filenames or values may contain spaces, newlines, or glob characters
- Flag temp files created at predictable hardcoded paths instead of via `mktemp`, which is vulnerable to symlink races
- Flag scripts that create temp files, lock files, or background processes without a matching `trap ... EXIT` cleanup handler
- Flag numeric comparison operators (`-eq`, `-lt`, `-gt`) applied to values that are actually strings, or `=` used where a numeric comparison was intended

## Documentation style

Prefix each script with a short header comment stating its purpose, usage, and required environment
or arguments; document each function with a comment above it noting its parameters, any globals it
reads or mutates, and its exit or return-value convention.
