Choose the request that matches what you want to happen:

- **Add** a model or offering that does not yet exist.
- **Change** facts while keeping the same logical identity.
- **Revoke** an offering that should no longer grant permission.
- **Move** an offering when its stable identity must be replaced.
- **Batch** up to 25 related requests from one source and scope.

The GitHub forms ask for the subject, purpose, desired outcome, reason,
supporting observations and acceptance checks in plain language. Trusted
default-branch tooling validates those answers and adds the canonical JSON and
fingerprints to the issue automatically. You do not need to calculate them.

If an answer is incomplete or unsafe, one Modelo status comment explains what
to fix. Editing the issue runs the check again and replaces stale generated
data.

An issue records intent; it does not approve the change. Never include credentials, private commercial terms or provider agreement tokens.
