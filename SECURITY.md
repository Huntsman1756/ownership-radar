# Security Policy

## Supported versions

| Version      | Supported |
|--------------|-----------|
| 0.1.0-alpha.x | yes — alpha; fixes land on the next pre-release |

There is no stable release yet; nothing older than the latest
pre-release is supported.

## Reporting a vulnerability

Please report vulnerabilities **privately** through GitHub's
"Report a vulnerability" (private vulnerability reporting) on this
repository, or by opening a security advisory draft — do not file
public issues for unpatched vulnerabilities.

If private reporting is unavailable, open a minimal public issue
without exploit details and maintainers will make contact.

## Scope notes

- The **public API/CLI is read-only by design**: SQLite is opened
  `mode=ro` + `PRAGMA query_only`; no writes, no network access
  during queries.
- Ingestion (`ingest`, `poller`, `pipeline`) is a separate admin
  surface that talks to CNMV; treat it as privileged tooling.
- The dataset may contain names published in official regulatory
  disclosures — that is source data, not a leak. Conversely, please
  report any credentials, tokens or personal data *added by this
  project* found in the repository or packages.
