Choose the request that matches what you want to happen:

- **Add** a model or offering that does not yet exist.
- **Change** facts while keeping the same logical identity.
- **Revoke** an offering that should no longer grant permission.
- **Move** an offering when its stable identity must be replaced.
- **Batch** up to 25 related requests from one source and scope.

The five cards below are the static operation chooser and remain the direct
route for every operation. If you are preparing an add or change, the
[interactive helper](#builder) can assemble a non-canonical draft of the issue
fields. It intentionally does not model revoke, move or batch.

The GitHub forms ask for the subject, purpose, desired outcome, reason,
supporting observations and acceptance checks in plain language. Trusted
default-branch tooling validates those answers and adds the canonical JSON and
fingerprints to the issue automatically. You do not need to calculate them.

The browser draft is not a MAC payload, approval or accepted evidence. The
trusted default-branch GitHub intake compiler remains authoritative for the
canonical request UUID, keys and digest.

If an answer is incomplete or unsafe, one Modelo status comment explains what
to fix. Editing the issue runs the check again and replaces stale generated
data.

An issue records intent; it does not approve the change. Never include credentials, private commercial terms or provider agreement tokens.
