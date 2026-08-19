# Runbook: Common CI and Build Failures

## Failing test suite after a dependency bump

When check runs start failing immediately after a package version bump, the
most common cause is a breaking change in a transitive dependency's public
API, not a real logic regression. First step: check whether the failing
test's stack trace shows an `AttributeError` or `ImportError` rather than an
assertion failure — those two error types point at a dependency change.

## Flaky tests in CI only

Tests that pass locally but fail intermittently in CI are usually a race
condition tied to CI's higher parallelism or lower resource ceiling, not a
real code path bug. A single re-run passing is strong evidence it's
environmental rather than a genuine regression.

## Stale cache causing false-positive CI failures

If a CI failure disappears after clearing the build cache with no code
change, the cache itself was stale. This is common right after a build tool
version bump.

## Missing environment variable in CI

A check run failing only in CI (never locally) with a `KeyError` or "not
set"-style message on startup is almost always a missing secret or
environment variable in the CI environment, not an application bug.
