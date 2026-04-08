This repository helps you **build container images from a single repo** (for example for Kubernetes) **via CI/CD without rebuilding every image on every run**. Only services whose code or dependency tree changed are rebuilt; the rest can keep running with their existing tags.

## Goal

You can keep **multiple Docker images** and **multiple Python packages** in one repository and build them together from a **single Jenkinsfile**. That makes integration tests easier and works well with coding agents operating in one codebase.

## How it works

### Selective builds

- **`modules.json`** lists package paths and service paths, plus Docker registry names, image names, stage targets, and commands.
- **`ci_build_plan.py`** decides which services need a new image: it compares **Git tree hashes** for each path and follows **local package dependencies** (`requirements.txt` references to other packages in the repo). Services are rebuilt only if their own tree changed or a transitive local library dependency changed.
- Optional **`required_stack_services`** (names from `docker-compose.yml`) must be running before the pipeline can skip; the check uses the **Compose `image:`** line for those services.

### Image tags (two per built image)

Each Docker image that is built gets **two tags**:

1. **Software version** — `v{MAJOR}.{MINOR}.{BUILD}`  
   - If the repo has a semver Git tag `vX.Y.Z` (e.g. `v1.2.3`), **MAJOR** and **MINOR** are taken from the **latest** such tag, and **BUILD** is the number of commits on all branches **after** that tag (`git rev-list --count <tag>..HEAD`).  
   - If there is **no** such tag, the version defaults to **`v0.1.{BUILD}`** where **BUILD** is the total commit count on all branches (`git rev-list --all --count`).

2. **Tree short hash** — the first **5 characters** (hex, lower case) of the Git object id for the **path of that service or package** at `HEAD`: `git rev-parse HEAD:<path>`. This reflects the last commit that touched that subtree.

During `docker build`, each selected image is tagged as both `{registry}/{image}:{tree}` and `{registry}/{image}:{software_version}` (see `scripts/ci_docker_build.py`).

### Pipeline artifacts

- **`.jenkins_runtime.env`** — `SOFTWARE_VERSION` and `TREE_*` variables (from `ci_resolve_version.py`).  
- **`.jenkins_build_plan.env`** — which services to build (`BUILDSVC_*=1`).  
- **`.jenkins_last_trees`** — saved tree hashes for the next run; **archive this in Jenkins** if the workspace is always clean.

The **`Dockerfile`** is generated from `modules.json` (`ci_generate_dockerfile.py`). Local packages are copied as wheels only where referenced.

## How to use

1. **Copy or clone** this template as your repository root (or adapt paths if you nest it in a monorepo — see note below).

2. **Edit `modules.json`**: set `dir.packages` and `dir.services`, `docker.registry`, `images`, `containers`, `stage_targets`, `cmd`, and optionally `required_stack_services`.

3. **Adjust `docker-compose.yml`** so service names and `image:` values match what the scripts expect (`DOCKER_IMAGE_*` env vars are set from the build plan).

4. **Generate the Dockerfile** and commit it:
   ```bash
   python3.11 scripts/ci_generate_dockerfile.py
   git add Dockerfile
   git commit -m "Regenerate Dockerfile from modules.json"
   ```

5. **Run locally** (optional):
   ```bash
   python3.11 scripts/ci_resolve_version.py
   python3.11 scripts/ci_build_plan.py
   python3.11 scripts/ci_generate_dockerfile.py
   python3.11 scripts/ci_docker_build.py
   ```

6. **Jenkins**: use the provided `Jenkinsfile`. Ensure **Python 3.11+**, **Docker**, and **`docker-compose`** are on the agent. Configure `DOCKERHUB_CREDS_ID` (or change the credential id in the Jenkinsfile). **First run** builds all services (`BUILDSVC_*=1`) until `.jenkins_last_trees` exists.

7. **Versioning**: create Git tags `vX.Y.Z` when you want to bump **MAJOR**/**MINOR**; otherwise the build number increments from the last tag or from `v0.1.*` if there is no tag.

### Monorepo note

This template assumes the **Jenkinsfile lives at the repository root**. If the template lives in a **subfolder** of a larger monorepo, tree hashes are still relative to the Git root; `ci_docker_build.py` can build with context at the repo root and `-f <subfolder>/Dockerfile` — you may need to adjust the Jenkinsfile paths accordingly.

## Requirements

- Python **3.11+**
- Docker and **docker-compose** (standalone CLI)
- Optional Git tags `vX.Y.Z` for explicit major/minor versioning
