# 1Password authentication

## Establish that the credential can collect access metadata

**Do not assume that a 1Password service account token supports this collector.** Reading vault items alone is insufficient. The same credential must be able to run all of these read operations for the configured account and vault scope:

| CLI command family | Required information |
| --- | --- |
| `op whoami` | Account UUID, checked against `--account-id` |
| `op user list` | Users and their status |
| `op group list` | Groups |
| `op group user list` | Group memberships |
| `op vault list` | Accessible vault identities |
| `op vault user list` | Direct user grants on each configured vault |
| `op vault group list` | Group grants on each configured vault |
| `op item list` | Item metadata, including archived items |

The collector fails when a required command is unsupported, denied, or returns an unexpected shape. It does not silently fall back to an item-only inventory. A local authenticated CLI user session is a starting point for validation, but this repository has not established that a generic service account token can run the complete workflow unattended.

Read the official [CLI authentication guide](https://developer.1password.com/docs/cli/sign-in/), [service account documentation](https://developer.1password.com/docs/service-accounts/), and [CLI command reference](https://developer.1password.com/docs/cli/reference/). Determine the minimum permissions that actually satisfy the read operations in your account. The collector never creates a credential or grants access.

For unattended use, first run the collector with the exact credential and CLI version you plan to use, in your own environment, and verify that it produces a complete local snapshot. Setting `OP_SERVICE_ACCOUNT_TOKEN` alone does not establish compatibility. If the credential cannot enumerate users, groups, memberships, or vault grants, unattended collection is not ready. An interactive session should not be copied into a scheduled job as a presumed long-lived credential.

## Define the collection boundary

Set the expected 26-character account UUID with `--account-id`, and explicitly list each vault UUID with `--vault-id`. `--account` is an optional CLI account selector, not a substitute for the expected UUID. Account identity is checked before collection.

The snapshot's scope is the configured vault set, not every vault in the account. Membership and grants preserve the permissions returned by 1Password. A management or ownership grant does not by itself establish the `read_items` permission. Archived items are included. Vault names and item titles require the explicit `--include-titles` option.

Treat the JSON as private security data even without secret values or titles. It describes who can access which resources. Keep bucket access limited to the collector's writer identity and the consumers you explicitly authorize.
