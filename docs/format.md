# 1Password snapshot format

[schemas/onepassword/v1.json](../schemas/onepassword/v1.json) defines schema version `1.0`. The format is intended for a separate Cartography importer; no such importer is shipped by this repository.

## Identity and coverage

`provider` is `onepassword`; `account_id` is the UUID verified against the CLI's authenticated account. Consumers should identify entities by `(provider, account_id, entity kind, id)`, not by names, email addresses, or an unqualified item/vault ID. Relationship endpoints refer to the IDs in the same snapshot/account.

`scope.kind` is always `configured_vaults`, and `scope.vault_ids` lists the explicitly requested vaults. `scope.include_archived` is `true`. Only these vaults, their user/group grants, and their items are collected. The collector also lists all visible account users and groups, and collects memberships for **every listed group**, including groups that have no grant to a configured vault. Those arrays are supporting identity data; they do not declare account-wide authority for graph cleanup.

The snapshot contains:

| Field | Meaning |
| --- | --- |
| `users`, `groups` | Identity metadata returned by account listing commands |
| `group_memberships` | Separate `group_id` / `user_id` membership edges |
| `vaults` | Configured vault IDs; names only with `--include-titles` |
| `vault_user_grants` | Direct `user_id` / `vault_id` grants and permission strings |
| `vault_group_grants` | `group_id` / `vault_id` grants and permission strings |
| `items` | Item IDs, owning vault IDs, and available allowlisted metadata; titles only with `--include-titles` |

Keep direct grants and group-derived access separate. A user can have multiple access paths to the same vault. Resolve a group path by joining `group_memberships` with `vault_group_grants`, retaining that provenance. Preserve the permission strings; do not interpret `manage_vault`, group ownership, or administrative status as an explicit `read_items` grant. Account/user status and any additional 1Password policy can also affect effective access.

## Freshness and safe replacement

`status: "complete"` means the configured read operations completed and passed validation. It does not mean that every account vault was collected, or that the reads describe one transactional instant. CLI calls are sequential; memberships or grants can change during a run.

`collected_at` is the UTC time at collection completion, from the collector host's clock. `snapshot_id` is a unique run identifier, not a sortable sequence. `collector.name` and `collector.version` identify the producer. Consumers should validate the schema, expected account, declared scope, completeness, and freshness before changing graph state.

For each configured import stream:

1. Accept only a complete, newer snapshot with the same expected account and vault scope. Deduplicate snapshot IDs and track the last accepted timestamp. Apply an explicit freshness limit; arrival time alone does not make an old snapshot current.
2. Replace the stream's current vault-scoped items and grants as a unit. Do not merge historical snapshots into current access: doing so resurrects removed grants. Store history separately if needed.
3. Never globally clean users, groups, or vaults outside the declared scope. A missing entity is not evidence that an uncollected vault or an account-level identity was deleted. Cleanup must respect other producers and import streams.
4. Treat adding or removing configured vaults as an explicit scope change. In particular, shrinking the scope needs a policy for retaining or retiring the old scope's data; absence from the new snapshot cannot silently revoke it.

Avoid overlapping exporters for the same output/import stream. Timestamps and atomic object replacement do not make concurrent or sequential provider reads transactional. Clock skew and inconsistent provider reads require consumer policy; a consumer must not present stale data as a newly verified access state.

## Published sources and test fixtures

The fixtures in [collector tests](../tests/test_onepassword.py) and [CLI tests](../tests/test_cli.py) are synthetic. They are hand-written responses and canary values, not captured customer payloads. Their shape and interpretation are informed by these pinned public sources:

- [1Password reporting examples](https://github.com/1Password/solutions/blob/6e8656f786b11fb22428e434e8b784e36684b3a1/1password/reporting/README.md#L8-L41) distinguish directly assigned vault access from access through group membership. [The combined access report](https://github.com/1Password/solutions/blob/6e8656f786b11fb22428e434e8b784e36684b3a1/1password/reporting/vault-user-group-access-report.py) demonstrates joining those paths.
- [1Password's CLI wrapper types](https://github.com/1Password/op-js/blob/9ea073e6f7102ae8785e0cf9466ee19a7c803b75/src/index.ts#L180-L185) document account/user UUID fields. Its [vault user/group types](https://github.com/1Password/op-js/blob/9ea073e6f7102ae8785e0cf9466ee19a7c803b75/src/index.ts#L1209-L1224) document identity and permission arrays.
- [1Password's bulk field-update example](https://github.com/1Password/solutions/blob/6e8656f786b11fb22428e434e8b784e36684b3a1/1password/item-management/sdk-conceal-fields/bulk-update-fields-to-concealed.py#L233) handles permission lists/strings and user-ID aliases. This collector uses that response-shape evidence only; it does not perform the example's mutations.

These sources and passing synthetic tests do not establish compatibility with every CLI version, account permission model, or unattended token. [Authentication must still be validated](deployment.md) for the actual deployment.
