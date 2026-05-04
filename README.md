# yodacheck

AST-based linter that detects and auto-fixes **Yoda conditions** in Python source files.

A Yoda condition is a comparison where the literal is on the **left** side:

```python
# Yoda — flagged
if 5 == x: ...
if None == obj: ...
if True == flag: ...

# Normal — not flagged
if x == 5: ...
if obj is None: ...
if flag is True: ...
```

## Features

- Detects all Yoda patterns (`==`, `!=`, `<`, `<=`, `>`, `>=`, `is`, `is not`)
- Smart fixes: `None ==` → `is None`, `True/False ==` → `is True/False`, all else → swap
- Auto-fix with timestamped `.bak` backup before writing
- Chained comparisons (`1 < x < 3`) flagged but not auto-fixed (ambiguous)
- `in` / `not in` with literal on left intentionally ignored (normal membership syntax)
- Output formats: `pretty` (default), `plain`, `json`
- Color auto-detected (TTY), forced via `--color` / `--no-color`
- Default excludes: `.venv`, `__pycache__`, `.git`, `build`, `dist`

## Installation

```bash
pip install .
```

After install the `yodacheck` command is available globally. Without installing, use `python yodacheck.py` directly.

## Usage

```bash
# Scan file or directory
yodacheck path/to/file.py
yodacheck src/

# Multiple paths
yodacheck src/ tests/ setup.py

# Show N context lines per issue
yodacheck src/ --context 2

# Auto-fix (creates .bak backup first)
yodacheck src/ --fix

# Exclude paths (glob or dir name, repeatable)
yodacheck . --exclude "migrations/*" --exclude vendor/

# Output format
yodacheck src/ --format plain
yodacheck src/ --format json

# Color
yodacheck src/ --color
yodacheck src/ --no-color
```

## Output

```
3 issues · 1 file

  src/auth.py
  42:3   None == token          →  token is None        [is None]
  67:3   0 == status_code       →  status_code == 0
  99:3   1 < retry_count < 5    ⚠ chained, no fix
```

With `--context 2`:

```
  42:3   None == token  →  token is None  [is None]
         40 │ 
         41 │ def validate(token):
         42 │ if None == token:
               ^
         43 │     raise ValueError
         44 │ 
```

## Fix behavior

`--fix` applies all fixable replacements in one pass per file. Chained comparisons are skipped.

```bash
yodacheck src/ --fix
# fixed src/auth.py  (auth.py.bak.20260504T150000Z)
```

## JSON output

```bash
yodacheck src/ --format json
```

```json
[
  {
    "path": "src/auth.py",
    "lineno": 42,
    "col": 3,
    "expr": "None == token",
    "tag": "is None",
    "replacement": "token is None",
    "chained": false
  }
]
```

`tag` values: `"is None"`, `"is not None"`, `"bool"`, `""` (plain swap), `""` with `chained: true`.

## Test file

`examples/example.py` — runnable collection of every detectable pattern:

```bash
yodacheck examples/example.py --color
yodacheck examples/example.py --color --context 1
```

## Running tests

```bash
python -m unittest discover -s tests -v
```

## Requirements

Python 3.8+. No external dependencies.
