# Shared Run Manifest v1

## Purpose

PaperTrail keeps its existing project manifest for backward compatibility. `papertrail.shared_manifest.to_shared_manifest_v1` projects that record into the common top-level fields defined in the four-project upgrade plan. The JSON Schema and Python validator reject missing fields, unsupported fields, malformed hashes, invalid budgets, private paths, and inconsistent null provenance.

## Mapping rules

- `dataset_id` uses the source value. Legacy records without one use `sha256:<dataset_sha256>`, which identifies the frozen dataset without inventing a label.
- A missing model ID becomes `none` for an offline run. If that run has no recorded model cost, estimated model cost is `0`.
- Prompt, tool-schema, step, and token values remain `null` when not applicable. `field_status` records `not_applicable`; unknown values use `not_recorded`.
- `runtime_digest` is SHA-256 over canonical JSON for the recorded runtime descriptor. It is a descriptor digest, not a container image digest.
- Missing `span_id` remains `null` with `field_status=not_recorded`.
- The legacy `to_shared_manifest` name remains as an alias.

## Privacy and limits

Projection validates source and output against private-field and local-path patterns. It does not read documents or send data to a model. This common projection does not rewrite historical run records or claim that all four repositories already emit the same schema.

## Verification

```powershell
python -m pytest tests/test_shared_manifest.py -q
```

The tests cover legacy mapping, deterministic dataset identity, explicit null provenance, schema-to-projection field parity, invalid field values, and private data rejection. These are schema and fixture checks, not a live model evaluation.
