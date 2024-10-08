# eodh-workflows

[![publish](https://github.com/EO-DataHub/eodh-workflows/actions/workflows/publish-pipeline.yaml/badge.svg)](https://github.com/EO-DataHub/eodh-workflows/actions/workflows/publish-pipeline.yaml)
[![docs](https://github.com/EO-DataHub/eodh-workflows/actions/workflows/docs-pipeline.yaml/badge.svg)](https://github.com/EO-DataHub/eodh-workflows/actions/workflows/docs-pipeline.yaml)

Workflows for Action Creator component on EOPro platform.

## Getting started

Create the environment:

```shell
make env
```

Run `pre-commit` hooks:

```shell
make pc
```

## Guides

Read more here:

- [Development env setup](docs/guides/setup-dev-env.md)
- [Contributing](docs/guides/contributing.md)
- [Makefile usage](docs/guides/makefile-usage.md)
- [Running tests](docs/guides/tests.md)

## Docs

To build project documentation run:

```shell
make docs
```

and then:

```shell
mkdocs serve
```
