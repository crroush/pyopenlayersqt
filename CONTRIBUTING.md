# Contributing to pyopenlayersqt

Thank you for your interest in contributing to pyopenlayersqt! This document provides guidelines for contributing to the project.

## General Contributions

Contributions are welcome! Please feel free to submit issues or pull requests.

## Versioning and Releases

This project uses [Semantic Versioning](https://semver.org/) for version numbers (MAJOR.MINOR.PATCH).

### For Maintainers: Creating a Release

#### 1. Update the Version

Update the version number in `pyproject.toml`:

```toml
[project]
version = "X.Y.Z"  # e.g., "0.2.0"
```

#### 2. Commit the Version Change

```bash
git add pyproject.toml
git commit -m "Bump version to X.Y.Z"
git push origin main
```

#### 3. Create and Push a Git Tag

Create a tag matching the version number (with a `v` prefix):

```bash
git tag vX.Y.Z  # e.g., v0.2.0
git push origin vX.Y.Z
```

For pre-release versions, use a suffix:

```bash
git tag vX.Y.Z-alpha.1  # e.g., v0.2.0-alpha.1
git tag vX.Y.Z-beta.1   # e.g., v0.2.0-beta.1
git tag vX.Y.Z-rc.1     # e.g., v0.2.0-rc.1
git push origin vX.Y.Z-alpha.1
```

#### 4. Automated Publishing

Once the tag is pushed, GitHub Actions will automatically:
- Build the package using PEP 517 (`python -m build`)
- Publish to PyPI using trusted publishing (OIDC)

You can monitor the workflow at: https://github.com/crroush/pyopenlayersqt/actions

#### 5. Manual Workflow Trigger

You can also trigger the publish workflow manually from the GitHub Actions tab:
1. Go to https://github.com/crroush/pyopenlayersqt/actions
2. Select the "Publish to PyPI" workflow
3. Click "Run workflow"
4. Select the branch/tag to build from

### PyPI Setup Requirements

This project uses **PyPI Trusted Publishing** (OIDC), which is more secure than using API tokens.

#### Initial Setup (One-Time)

1. **Create a PyPI Account** (if you don't have one):
   - Go to https://pypi.org/account/register/

2. **Configure Trusted Publisher** on PyPI:
   - Go to https://pypi.org/manage/account/publishing/
   - Add a new pending publisher with these details:
     - **PyPI Project Name**: `pyopenlayersqt`
     - **Owner**: `crroush`
     - **Repository name**: `pyopenlayersqt`
     - **Workflow name**: `publish.yml`
     - **Environment name**: `pypi`

3. **After First Successful Publish**:
   - The pending publisher will be automatically converted to an active publisher
   - Future releases will publish automatically when you push a tag

#### Alternative: Using API Tokens

If trusted publishing is not available, you can use API tokens instead:

1. Generate a PyPI API token at https://pypi.org/manage/account/token/
2. Add it as a GitHub repository secret named `PYPI_API_TOKEN`
3. Update the workflow to use token-based authentication (see commented section in `.github/workflows/publish.yml`)

### Verification

After a release is published, verify it at:
- PyPI: https://pypi.org/project/pyopenlayersqt/
- Test installation: `pip install --upgrade pyopenlayersqt`
