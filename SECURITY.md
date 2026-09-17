# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| Latest `0.1.0-alpha.x` pre-release | yes — fixes land on the next pre-release |

There is no stable release yet; only the latest published pre-release is
supported.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** flow if it is available on the
repository Security tab. If private vulnerability reporting is not
available, contact the maintainer through a private contact channel listed
on the maintainer's GitHub profile.

Do **not** include exploit details, credentials, personal data or an
unpatched proof-of-concept in a public issue. A minimal public issue saying
that private contact is needed is acceptable when no private channel is
available.

## Scope notes

- The **public API/CLI is read-only by design**: SQLite is opened
  `mode=ro` + `PRAGMA query_only`; no writes, no network access during
  queries.
- Ingestion (`ingest`, `poller`, `pipeline`) is a separate admin surface
  that talks to CNMV; treat it as privileged tooling.
- The crawler caps individual response bodies at 256 MB and records
  transient transport failures as retryable extraction errors.
- The dataset may contain names published in official regulatory
  disclosures — that is source data, not a leak. Conversely, please
  report any credentials, tokens or personal data *added by this project*
  found in the repository or packages.
