# Changelog Fragments

This directory holds one small file per user-facing change. At release time
[towncrier](https://towncrier.readthedocs.io/) collects them into `CHANGELOG.md`
and deletes them.

## File naming

Files live **directly in this directory** (no subdirectories) and are named:

```
CHANGES/<pr-number>.<type>.rst
```

`<type>` is one of:

| Type      | Use for                        |
|-----------|--------------------------------|
| `feature` | New functionality              |
| `bugfix`  | Bug fixes                      |
| `doc`     | Documentation-only changes     |
| `removal` | Removed or deprecated features |
| `misc`    | Everything else (CI, tooling)  |

Examples:

- `CHANGES/48.feature.rst` for PR #48
- `CHANGES/55.misc.rst` for PR #55
- `CHANGES/+redis-cluster.feature.rst` when there is no PR or issue number yet
- `CHANGES/48.feature.1.rst` for a second entry about the same PR

## File content

One or two sentences in present tense, describing the change from the user's
point of view. The PR link is added automatically from the file name, so do not
repeat it in the text.

```rst
Add token bucket rate limiting algorithm.
```

## Checking locally

```bash
uvx towncrier check --compare-with origin/main   # same check CI runs on PRs
uvx towncrier build --draft --version 0.0.0      # preview the rendered changelog
```

A PR that needs no changelog entry (typo fixes, CI-only changes) can carry the
`skip news` label instead of a fragment.
