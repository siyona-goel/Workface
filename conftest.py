# Root conftest. Its mere presence puts the repo root on sys.path, so tests can
# `import packages...` and `import apps...` in both local runs and CI (where the
# test files live under tests/ with no __init__.py). Do not delete.
