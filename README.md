# Arm Reference

A static reference for AArch64 instructions and Arm system registers, generated
from Arm’s XML and XSLT bundles. Inspired by [Jon’s Arm Reference by Jon Palmisciano](https://arm.jonpalmisc.com/).

This repository hosts only the site generator and its supporting files. The
build downloads the original XML and XSLT directly from Arm and generates the
reference pages locally.

## Build and serve

Install [uv](https://docs.astral.sh/uv/), `wget`, `sha256sum`, and GNU tar.
From the repository root, run:

```sh
./download.sh
uv run --locked python generate.py
uv run --locked python -m http.server --bind 127.0.0.1 --directory dist
```

Open [localhost:8000](http://localhost:8000/). Press **Ctrl+K** or **Cmd+K**
on macOS to focus search. To host the site elsewhere, serve the entire
`dist/` directory, including its `pagefind/` subdirectory.
