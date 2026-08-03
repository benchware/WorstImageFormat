# Release checklist

## Before creating the release

- Update the version in `pyproject.toml` and add the dated changelog entry.
- Confirm the Git tag will be exactly `v<version>`.
- Require green Python, native C++, visual report, sanitizer, package, and benchmark jobs.
- Run the TestPyPI workflow and install its sdist/wheel in a clean environment.
- Confirm PyPI and TestPyPI trusted publishers reference the exact repository, workflow filename, and protected environment.
- Inspect the eight-panel codec report and distribution manifest.

## Publishing

- Create a non-prerelease GitHub release from the verified commit.
- Let `python-publish.yml` build all distributions from that release; do not upload local artifacts.
- Confirm the release preflight, 20-wheel matrix, sdist test, `twine check`, and OIDC publish job pass.

## After publishing

- Confirm the four clean-platform `pip install wimf` jobs pass.
- Verify the PyPI description, links, Python requirement, license, files, hashes, and provenance.
- Attach or link the distribution manifest and visual codec report in the GitHub release notes.
- If any artifact is wrong, publish a new patch version; PyPI files and versions cannot be replaced.
