# 0001. Per-field provenance in strategy specs

## Context
QuaVer rebuilds strategies from papers and checks whether the published results hold.
A replication is only as checkable as its inputs: a reviewer must be able to see, for
every parameter, whether the paper says it or we chose it.

## Decision
Every value in a spec says where it came from:
- **stated**: the paper says it. Page and a short quote (at most 25 words).
- **inferred**: the paper implies it. Page and the reason for the inference.
- **assumed**: the paper does not say. A reason, and no page.

Specs are YAML, validated by `quaver validate-spec`. The paper is pinned by the SHA-256
of the exact PDF, so page numbers always refer to the same file.

## Reasons
- Quotes and page numbers can be checked against the PDF; the assumed count shows how
  much of a result rests on our own choices.

## Rejected alternatives
- Free-text notes: not checkable, and no way to count or enforce them.
- Page numbers only: some parameters are not in the paper at all, so there is no page.

## Note
The fields are specific to momentum strategies for now. They will be generalised when a
second strategy family arrives, not before.
