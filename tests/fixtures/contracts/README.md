# Walking Skeleton contract fixtures

`walking_skeleton/` is the deterministic, synthetic fixture corpus for Walking Skeleton Contract Addendum 1. The only normative source is the schema at architecture commit `4ad0b9fa6f3b4a20a8f3ea480724c2fbe3098c14`, SHA-256 `5b22d0a3e668244896483132d795794687b4b90379228c5815c0f32a1f7a1577`.

- `valid/` contains public payloads validated against the exact `$defs` recorded in `sequences/manifest.json`. Nested fixtures cover Money, Artifact metadata/reference, SourceReference, preview items/summaries, Task/Checkpoint/Failure state, balance positions and calculation metadata. The seven event types each have a typed event fixture.
- `invalid/` contains one-violation fixtures. Each must yield exactly one Draft 2020-12 validation error with the keyword recorded in the manifest.
- `sequences/` contains private test-harness scenario metadata for state transitions, idempotency, SSE replay, checkpoint resume, terminal failure, and the rule that no financial effect occurs before commit. These metadata fields are not public contract fields and must never be emitted by an API or event producer.
- `error-response-catalog.json` covers all 18 accepted error codes together with their exact HTTP and retryability semantics. Its response template plus each case must validate as `ErrorResponse`.

The corpus digest is computed by sorting all JSON paths relative to `walking_skeleton/` (excluding `sequences/manifest.json`), hashing each file, concatenating records as `relative-path<TAB>file-sha256<LF>`, then hashing that byte stream. The expected digest is stored in the manifest.

Validation requires JSON Schema Draft 2020-12 format checking. A fixture is not accepted if format checks are disabled, if a valid file produces any error, or if an invalid file produces anything other than its single documented error.
