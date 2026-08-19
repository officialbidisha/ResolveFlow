# Known Issues and Triage Patterns

## Feature requests referencing a related or duplicate issue

When an issue links to another issue number in its body (e.g. "see also
#625"), check whether the linked issue already tracks the same underlying
request before triaging this as new work — many "feature request" issues
are restatements of an existing open issue rather than something new.

## Vague bug reports without reproduction steps

Issues describing "it doesn't work" without a minimal reproduction,
expected-vs-actual behavior, or environment details cannot be diagnosed
from the issue text alone. These should be routed for a request-more-info
comment, not a fix attempt.

## Documentation gaps reported as bugs

Issues describing behavior that is actually correct but undocumented (the
reporter expected X, the tool does Y, and Y is intentional) should be
triaged as a documentation issue, not a code bug. Check the linked docs or
README before assuming code needs to change.

## Multi-framework support requests ("support framework X like you support framework Y")

These typically require investigating the existing implementation pattern
for the already-supported framework before any implementation plan can be
proposed — the fix is usually "add an equivalent code path for X," not a
small patch, so scope estimates should account for that.
