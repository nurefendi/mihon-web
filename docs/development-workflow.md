# Temporal development workflow

Development automation for Mihon Web is provided by an external Temporal worker service. It is separate from the Mihon Web runtime: the Go server, MariaDB, and Suwayomi engine described in [README.md](../README.md) neither host nor require Temporal. The worker accepts requests from a trusted operator and reports workflow state back to that operator.

## Workflow modes

- `inspect` is read-only. It may examine repository context and report findings, but it does not modify the repository.
- `implement` runs inside a disposable, networkless Docker tool sandbox. The sandbox runs as a non-root user with read-only Git metadata. Its output is a verified patch bound to the BaseSHA it was produced from, so the change cannot be applied silently to a different base.

## Starting a reviewed change

Only a trusted operator starts a publishing workflow. `start --publish-pr` waits for workflow completion, validates the returned artifact and the current base, pushes a new `temporal/` branch, and creates a draft GitHub pull request targeting `main`.

```sh
mihon-development start --title "Focused change" --prompt-file task.txt --mode implement --task-kind custom --budget 900 --publish-pr --repo /path/to/operator-clone
```

## Completing or retrying publication

- `publish --pr` publishes a workflow that has already completed with `patch_ready`.
- `pr --workflow-id` retries pull-request creation after a successful branch push, for example when the earlier request did not finish.

```sh
mihon-development publish --workflow-id <workflow-id> --pr --repo /path/to/operator-clone
mihon-development pr --workflow-id <workflow-id> --repo /path/to/operator-clone
```

## Success criteria and review boundary

A final success reports a verified `pr_url`, the `head` and `base` branches, and `commit_sha`. A `patch_ready` workflow alone is not a published pull request.

There is no automatic merge or deployment, and main remains unchanged until human review approves and merges the draft pull request.

## Verification boundary

Tests and builds run in GitHub Actions, not on the production server. Target runtime smoke checks are separate from that automated verification and are not implied by a successful workflow.
