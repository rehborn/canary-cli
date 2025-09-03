<div align="center">

[![CanaryCD](https://docs.rehborn.dev/assets/canary-cd.png)](http://docs.rehborn.dev)

**command line interface for [canary-cd](https://github.com/rehborn/canary-cd)**

[Source](https://github.com/rehborn/canary-cli) &middot; [Documentation](http://docs.rehborn.dev) 

[![PyPI-Badge]](https://pypi.org/project/canary-cli/)
![Python-Badge]
[![License-Badge]](https://github.com/rehborn/canary-cli/blob/main/LICENSE)

[PyPI-Badge]:
https://img.shields.io/pypi/v/canary-cli?style=flat-square&color=306998&label=PyPI&labelColor=FFD43B
[Python-Badge]:
https://img.shields.io/pypi/pyversions/canary-cli?style=flat-square&color=306998&label=Python
[License-Badge]:
https://img.shields.io/github/license/rehborn/canary-cli?style=flat-square&label=License
</div>

# Documentation
- [Setup](http://docs.rehborn.dev/cli/)
- [Usage](http://docs.rehborn.dev/cli/usage/)

# Setup

```shell
pipx install canary-cli
```

# Development

```shell
uv sync
canary-cli --install-completion
source $HOME/.bash_completions/canary-cli.sh
```

**Run with typer**
```shell
uv run typer ./canary_cli/main.py run 
```

### Linter
```shell
uv run ruff check
```

### Static Type Checker
```shell
uv run ty check
```
