# Authoring proposals and evidence

Modelo provides local conveniences for preparing a change. They create drafts;
they do not open a linked issue, retrieve provider facts, approve a record or
produce trusted CI evidence. Start governed work from a linked MAC issue and
treat every local input and output path as author-controlled.

## Choose an intake path

The published `/propose/` page has five static cards—add, change, revoke, move
and batch—whose destinations come from `repository.web_routes.mac_intake` in
`modelo.yaml`. Those links remain usable without JavaScript.

With JavaScript enabled, the same page can prepare an add or change draft and
prefill the configured form for that operation. The displayed issue-field
summary is only a convenience: it has no `request_id`, keys or payload digest
and is not the canonical MAC payload. After the issue is submitted, trusted
default-branch `modelo platform github-intake` tooling validates the human
fields, derives a stable UUIDv5 from the issue coordinate and computes the
dedupe key, idempotency key and payload digest.

Use the static card for revoke, move or batch because those operations require
shapes that the interactive draft does not compose.

## Initialise a neutral MAC locally

`modelo dev mac-init` is useful when an author needs a schema-valid neutral JSON
payload before opening or updating an issue. JSON arguments may be inline
values or paths to author-controlled JSON files.

```bash
uv run --locked modelo dev mac-init \
  --operation add \
  --purpose 'Register a reviewed model identity' \
  --subjects '[{"kind":"model","identity":"example-model"}]' \
  --requested-outcome 'A validated model record is proposed.' \
  --reason 'The governed workload needs an explicit model identity.' \
  --candidate-evidence '[]' \
  --acceptance '["The proposed record passes Modelo validation."]' \
  --output /tmp/example-mac.json
```

`--output` is optional: omit it to write JSON to standard output. The command
validates the neutral payload, creates a fresh random UUIDv4
`request_id`, and computes its dedupe and idempotency keys. It does not create
or bind a Git-provider issue, check reservations, gather evidence, create an
approval or make a catalogue change. The output is therefore not a substitute
for the trusted issue compiler or exact-head CI metadata.

## Create an evidence envelope locally

`modelo dev evidence-create` formats one evidence envelope and computes its
content-addressed ID. For an official documentation observation:

```bash
uv run --locked modelo dev evidence-create \
  --source-type official-provider-documentation \
  --uri https://example.invalid/official-provider-document \
  --observed-at 2026-09-03T09:00:00Z \
  --retrieved-by manual \
  --scope '{"purpose":"authoring-example"}' \
  --projection '{"modelId":"example.provider-model-v1"}' \
  --visibility internal \
  --output /tmp/example-evidence.json
```

The URI and projection above are placeholders, not catalogue facts; replace
them with one observed admissible source and its exact retained projection.
Omit the optional `--output` to print the JSON to standard output. For
`first-party-read-api`, also supply the exact `--operation`, `--partition` and
`--region`; the v0.1 helper's API source is AWS Bedrock only. The command
validates the envelope's schema shape and derives
`id` from its RFC 8785 canonical content, but it performs no network retrieval
and cannot decide that the source, scope, projection or freshness is truthful
or admissible. The author must obtain facts through an allowed read-only source,
remove credentials and private commercial data, and review the generated file.
Candidate issue evidence is not a catalogue evidence record.

## Finish the governed change

Move reviewed output into the schema-defined repository path on a topic branch,
read it back, run narrow checks and then run `modelo check`. Submit a change
request linked to the MAC issue. Only successful trusted `modelo/check` for the
exact current head plus the required independent review can accept a change.
Local commands and the public synthetic site are non-accepting. Production
catalogue records remain prohibited until T10 passes remotely.
