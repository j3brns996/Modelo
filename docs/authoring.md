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
and is not the canonical MAC payload. After submission, trusted default-branch
adapter tooling validates the human fields: `modelo platform github-intake`
for GitHub or `modelo platform gitlab-intake` for GitLab. It derives a stable
UUIDv5 from the issue coordinate and computes the dedupe key, idempotency key
and payload digest.

Use the static card for revoke, move or batch because those operations require
shapes that the interactive draft does not compose.

For every operation, complete the governed Git-provider issue intake rather
than treating a local draft as a request. The browser helper prepares issue
fields; the two local helpers below separately prepare a neutral MAC payload or
an evidence envelope for inspection.

## Initialise a neutral MAC locally

`modelo dev mac-init` is useful when an author needs a schema-valid neutral JSON
payload before opening or updating an issue. Its JSON-valued arguments are
`--subjects`, `--candidate-evidence`, `--acceptance` and, for a batch,
`--batch-scope`. Supply JSON in one of these forms:

1. inline JSON, which is always tried first;
2. `@path/to/input.json`, which explicitly names a required file; or
3. a plain existing path, retained as a legacy fallback only when the argument
   is not valid inline JSON.

An `@` file that is missing or unreadable fails; it is not reinterpreted as
inline data. Prefer `@path` in scripts because it states the intent clearly.
All input files and their contents remain author-controlled.

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
content-addressed ID. It accepts exactly three source types:
`first-party-read-api`, `official-provider-documentation` and
`official-vendor-documentation`.

For an official documentation observation:

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
For both documentation source types, `--uri` is the only source-specific
argument. They reject API-only `--provider`, `--service`, `--operation`,
`--partition`, `--region` and `--sanitised-parameters` arguments instead of
silently discarding them.

The v0.1 helper supports AWS Bedrock as its only first-party API source. That
choice must be explicit, as must the retained request parameters:

```bash
uv run --locked modelo dev evidence-create \
  --source-type first-party-read-api \
  --provider aws \
  --service bedrock \
  --operation GetFoundationModel \
  --partition aws \
  --region eu-west-1 \
  --sanitised-parameters '{"modelIdentifier":"example.provider-model-v1"}' \
  --uri https://example.invalid/api-reference \
  --observed-at 2026-09-03T09:00:00Z \
  --retrieved-by cli \
  --scope '{"purpose":"authoring-example"}' \
  --projection '{"modelId":"example.provider-model-v1"}' \
  --visibility internal
```

Here `--uri` becomes the API source's `documentation_uri`. The API form
requires all six API arguments: `--provider aws`, `--service bedrock`,
`--operation`, `--partition`, `--region` and JSON
`--sanitised-parameters`. The latter preserves the sanitised request scope; it
must not contain credentials, private commercial terms or AWS agreement
`offerToken` values. Other provider/service pairs fail rather than being
labelled as AWS Bedrock.

`--projection`, `--scope` and `--sanitised-parameters` use the same inline,
explicit `@path`, then legacy existing-path JSON precedence described above.
Omit the optional `--output` to print JSON to standard output. The command
validates the envelope's schema shape and derives
`id` from its RFC 8785 canonical content, but it performs no network retrieval
and cannot decide that the source, scope, projection or freshness is truthful
or admissible. The author must obtain facts through an allowed read-only source,
remove credentials and private commercial data, and review the generated file.
Candidate issue evidence is not a catalogue evidence record.

Both local helpers validate and format the complete document before they write
it. If parsing or validation fails, an existing `--output` file is preserved
byte-for-byte and a missing target is not created. Successful output keeps the
existing two-space-indented UTF-8 JSON representation with a final newline,
whether it is sent to standard output or to the explicitly requested local
file.

## Keep issue observations distinct

All five Issue Forms—add, change, revoke, move and batch—allow candidate
observations to be left blank; trusted intake compiles a blank field to
`candidate_evidence: []`. Supplying the field is still strict: a malformed
nonblank observation line that does not match `URL | UTC time | sha256- digest`
fails compilation. Batch source, observation scope and inference-service scope
remain required even when candidate observations are blank. These issue hints
are not accepted catalogue evidence and do not relax the linked-issue,
validation or review gates.

## Finish the governed change

Move reviewed output into the schema-defined repository path on a topic branch,
read it back, run narrow checks and then run `modelo check`. Submit a change
request linked to the MAC issue. Only successful trusted `modelo/check` for the
exact current head plus the required independent review can accept a change.
Local commands and the public synthetic site are non-accepting. Production
catalogue records remain prohibited until T10 passes remotely.
