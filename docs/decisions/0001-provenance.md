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
- **table**: the value is read from a table or chart image. Page, section (the exhibit
  name), and a locator (row and column); no quote.

Every metric a claim uses is defined once, in the spec's `metrics` block, with its own
source. A claim whose metric has no entry is rejected, so a number is never reported
without saying what it measures.

Specs are YAML, validated by `quaver validate-spec`. The paper is pinned by the SHA-256
of the exact PDF, so page numbers always refer to the same file.

## Reasons
- Quotes and page numbers can be checked against the PDF; the assumed count shows how
  much of a result rests on our own choices.

- Tables in PDFs are often images with no text layer, so there is nothing to quote. A
  locator replaces the quote: it says exactly which cell to look at. A quote check cannot
  confirm a table value, so a second independent reading replaces it:
  `quaver compare-readings` matches the two readings claim by claim (not by id) and lists
  every difference. `quaver check-quotes` skips table sources and says how many it skipped.
- Marking such values `inferred` was dishonest in the other direction: they are read, not
  inferred, and counting them with real inferences hides how many numbers rest on a reading
  nobody has yet confirmed.

## Rejected alternatives
- Free-text notes: not checkable, and no way to count or enforce them.
- A looser quote for tables (for example the row text): the text layer has none of it.
- Page numbers only: some parameters are not in the paper at all, so there is no page.

## Note
The fields are specific to momentum strategies for now. They will be generalised when a
second strategy family arrives, not before.
