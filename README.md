# SubImage Collectors

Open-source, customer-run collectors that export metadata for security graphs.

## Available collectors

| Collector | Description |
| --- | --- |
| [1Password](./1password) | Export selected vaults, access grants, group memberships, and item metadata. |

Each collector owns its source, dependencies, tests, schema, documentation, and deployment examples in its directory. Follow the collector's README for authentication and usage. Future collectors can use their own runtime and release cycle.

## Development

Run the full lint and test suite for every collector from this directory:

```sh
make test
```

To work on one collector:

```sh
cd 1password
uv sync --frozen --all-extras
make test
```

`make test_lint` and `make test_unit` run the individual checks. CI uses the same targets. See each collector's README for its prerequisites.

## License

Apache License 2.0; see [LICENSE](./LICENSE). Bundled third-party software retains its own license terms.
