# 1Password authentication

## Use a scoped service account

The collector requires `OP_SERVICE_ACCOUNT_TOKEN`. It uses the same token with the official 1Password CLI for inventory and the official Python SDK 0.4.1 for vault access grants. A desktop CLI user session does not replace this token.

Full local collection was validated with **1Password CLI 2.32.1** and **Python SDK 0.4.1**, using **Read Items** access to selected existing vaults. The tested token had no write, share, vault-creation, or environment access. Validate your intended account, scope, and runtime before scheduling collection.

The credential must support these read operations:

| Read operation | Required information |
| --- | --- |
| `op whoami` | Account UUID, checked against `--account-id`, and the authenticated service-account identity |
| `op user list`, `op group list` | User and group identities; metadata-only `user get` / `group get` can resolve identities referenced by grants but absent from these lists |
| `op group user list` | Group memberships |
| `op vault list` | Accessible vault identities |
| `op item list` | Item metadata, including archived items |
| SDK `vaults.get(..., accessors=True)` | Authoritative direct user and group grants, including permission bitmasks |

The SDK accessor response supplies permission data missing from CLI vault-grant listings. The collector fails if a required read is denied, unsupported, or malformed. It never fetches item contents or changes access.

## Create the service account

1. In the 1Password web app, open the account menu and select **Admin Dashboard**. Open **Developer > Directory > Access Tokens** and select **Service Account** to open the **Create a Service Account** wizard.
2. Enter a descriptive name on **Set up your service account**.
3. In **Vault access**, keep **Allow creation of new vaults** off. Select the existing intended vaults offered by the wizard. For each selected vault, open **Edit Access** and enable **Read Items** only; leave **Write Items** and **Share Items** off.
4. Continue to **Environment access** and leave environment access unselected. Check the name and vault scope, then select **Create Account**.
5. On **Save service account token**, securely store the token shown once. The page offers **Copy Service Account Auth Token** and **Save in 1Password**.
6. Return to **Developer > Service accounts** and open the account. Confirm it is active, the intended vaults show **Read**, environment access is absent, and vault creation is **Not allowed**.

The wizard states that the service account cannot be modified later. Newly created vaults are not automatically included: changing the vault scope requires an appropriately scoped replacement service account and updated `--vault-id` arguments. The built-in **Employee** and **Shared** vaults were not offered in the tested setup; do not assume that every account vault is available to a service account.

No expiry option was offered, and the account list showed **Token expiry: Doesn't expire**. Account details provide **Rotate Token** and **Revoke Token**. Revoke validation-only tokens after testing and remove their local copies.

Read Items permits access to secret values even though this collector does not retrieve them. Keep the token in your own environment, inject it as `OP_SERVICE_ACCOUNT_TOKEN` through approved secret handling, and keep it out of shell history and tracked files. See the official [service account documentation](https://developer.1password.com/docs/service-accounts/) and [CLI reference](https://developer.1password.com/docs/cli/reference/).

## Validate before scheduling

Use the exact credential and CLI version intended for deployment. Existing vaults and items are sufficient; a separate synthetic vault is optional. Follow [Run locally](../README.md#run-locally) with explicit account and vault UUIDs and a local output path.

- Validate the result against [schemas/v1.json](../schemas/v1.json), including formats. Check the expected account, complete status, configured vault set, and item/vault/user/group references.
- Confirm vault names and item titles are absent without `--include-titles`. If you use an optional synthetic canary item, confirm its UUID appears and its fake secret marker does not. Do not retrieve real secrets for this check.
- Repeat the run with the same scope and output. Check for a new snapshot ID and later collection time, with one complete snapshot replacing the previous file.
- Save a copy of the output, then use a deliberately incorrect, valid-format expected account UUID. Expect a nonzero exit and byte-for-byte unchanged output.

Keep snapshots and raw provider responses private. A local run verifies that credential and scope; validate container authentication and cloud publication separately before scheduling them.

## Define the collection boundary

Set the expected 26-character account UUID with `--account-id`, and explicitly list each vault UUID with `--vault-id`. Account identity is checked before collection; the token's access and the configured vault IDs both limit coverage.

The snapshot's scope is the configured vault set, not every vault in the account. Grant `permissions` contain known SDK flag names in lowercase; `permissions_bitmask` preserves the complete integer, including unknown bits. A management or ownership grant does not by itself establish `read_items`. Archived items are included. Vault names and item titles require `--include-titles`.

The authenticated service account can be absent from the user directory. In that case, its identity can contain only the ID verified through `op whoami` and its service-account type. Name, email, and state are included only when provided; missing metadata is not fabricated.

Treat the JSON as private security data even without secret values or titles. It describes who can access which resources. Keep bucket access limited to the collector's writer identity and the consumers you explicitly authorize.
