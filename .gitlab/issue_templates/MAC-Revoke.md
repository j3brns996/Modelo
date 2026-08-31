# MAC: revoke

Replace the object below with one complete `schemas/mac.schema.json` payload. Subject identities use lowercase ASCII canonical IDs. In v0.1 a revoke subject is one offering. Absence from discovery is not a revocation reason by itself.

```json
{ "schema_version": "0.1", "operation": "revoke", "replace": "with a complete schema-valid payload" }
```

Neutral payload digest: `sha256-...`

- [ ] The request does not infer revocation from a missing discovery result.
- [ ] I have not included credentials, tokens or private commercial terms.
