Choose the request that matches what you want to happen:

- **Add** a model or offering that does not yet exist.
- **Change** facts while keeping the same logical identity.
- **Revoke** an offering that should no longer grant permission.
- **Move** an offering when its stable identity must be replaced.
- **Batch** up to 25 related requests from one source and scope.

The form asks for a machine-readable JSON payload because CI must validate the request without guessing. Its `purpose`, `reason` and `acceptance` fields are the human explanation: what is needed, why it matters and how a reviewer can tell the result is correct.

An issue records intent; it does not approve the change. Never include credentials, private commercial terms or provider agreement tokens.
