# Worked example: fix a repository bug

This example is illustrative. Adapt file names, commands, and expected output to the actual repository.

## User request

“Fix the bug where searching files returns duplicate results. Add a regression test.”

## 1. Inspect

- Confirm the repository root and read project instructions.
- Check the working tree and preserve pre-existing changes.
- Find the search implementation and existing tests.
- Trace how results are collected, normalized, and returned.

## 2. Form a hypothesis

For example, two search paths may add the same file to the result list. Verify this in the implementation before changing code. Do not assume the hypothesis is true.

## 3. Plan

- Change the narrowest responsible function.
- Add a regression test that reproduces duplicate results.
- Preserve ordering and existing filtering semantics.
- Run the targeted test and relevant broader checks.

## 4. Implement and verify

- Make the minimal fix.
- Add a test that fails before the fix and passes after it.
- Run the targeted test.
- Run project formatter/linter or broader tests if practical.
- Inspect the final diff and ensure no unrelated files changed.

## 5. Report

A good final report states the established root cause, files changed, behavior corrected, exact checks run and outcomes, checks not run and why, and remaining risks.

Never invent a test result or claim a command ran when it did not.
