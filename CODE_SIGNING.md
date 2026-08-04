# Code signing policy

WIMF intends to use free code signing provided by SignPath.io, with a
certificate issued by the SignPath Foundation, for official Windows native
release artifacts. Signing is not active until the project is accepted and the
release workflow reports a successful SignPath request. Unsigned CI artifacts
must not be represented as signed releases.

## Scope

Only binaries built from the official
[`benchware/WorstImageFormat`](https://github.com/benchware/WorstImageFormat)
repository by GitHub-hosted runners are eligible. The intended signed surface is
the Windows native SDK archive, including WIMF-owned DLL and executable files.
Vendored upstream binaries are not signed as WIMF components.

Every signing request must correspond to a published, non-prerelease GitHub
release whose tag is exactly `v<project.version>`. SignPath approval remains a
separate manual release decision.

## Team roles

- Committers and reviewers: repository collaborators with write or maintain
  permission.
- Approvers: repository owners authorized in the SignPath project.

Changes from contributors without direct write permission require review. The
SignPath policy, release workflow, and ownership rules require owner review.
Maintainers and signing approvers must enable multi-factor authentication for
GitHub and SignPath.

## Privacy

WIMF does not transfer information to networked systems unless the user
explicitly requests a network operation. Local encoding, decoding, Studio,
thumbnail, preview, metadata, and diagnostic operations remain local. GitHub,
PyPI, TestPyPI, and SignPath receive release or package data only when a
maintainer explicitly invokes the corresponding publishing workflow.

## Installation changes

Windows Explorer integration changes per-user file associations and shell
extension registration only when the user runs the registration script. The
matching unregistration script reverses those changes. See
[`docs/integrations.md`](docs/integrations.md).

## Verification

For an official signed artifact, inspect the Windows Authenticode signature and
confirm the signer, timestamp, file version, and product name. Compare the
archive SHA-256 digest with the release manifest. A signature establishes
provenance and integrity; it does not replace malware scanning or normal review.
