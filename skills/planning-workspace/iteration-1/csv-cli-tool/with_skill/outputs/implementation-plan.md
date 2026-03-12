# CSV Schema Validator CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Build a CLI tool that reads a CSV file, validates each row against a JSON schema, supports custom validator plugins, and outputs a structured validation error report.

**Architecture:** Python CLI using `argparse` for argument parsing, `csv` (stdlib) for CSV reading, `jsonschema` for JSON Schema validation, and a plugin system that dynamically loads custom validators from a user-specified directory via `importlib`. The tool reads a CSV, converts each row to a dict, validates against a JSON Schema, runs any loaded plugins, then outputs a JSON or human-readable error report. Designed as an installable package with a `csv-validator` entry point.

**Tech Stack:** Python 3.10+, jsonschema, pytest, argparse, importlib, csv (stdlib)

---

## Dependency Graph

```
Task 1 (CSV reader) ─────────────────────────────────┐
Task 2 (schema validator) ── depends on 1 ────────────┤
Task 3 (plugin system) ── no deps ────────────────────┤
Task 4 (report formatter) ── depends on 2, 3 ─────────┤
Task 5 (CLI entry point) ── depends on 1, 2, 3, 4 ────┤
Task 6 (integration tests) ── depends on 5 ───────────┘
```

---

### Task 1: CSV Reader Module

Parse a CSV file into a list of row dictionaries with line-number tracking.

**Files:**
- Create: `src/csv_validator/__init__.py`
- Create: `src/csv_validator/reader.py`
- Test: `tests/test_reader.py`
- Create: `tests/__init__.py`
- Create: `tests/fixtures/valid.csv`
- Create: `tests/fixtures/empty.csv`
- Create: `tests/fixtures/headers_only.csv`

**Step 1: Create project skeleton**

Create the package directories and empty `__init__.py` files:

```bash
mkdir -p src/csv_validator tests/fixtures
touch src/__init__.py src/csv_validator/__init__.py tests/__init__.py
```

**Step 2: Create test fixtures**

`tests/fixtures/valid.csv`:
```csv
name,age,email
Alice,30,alice@example.com
Bob,25,bob@example.com
```

`tests/fixtures/empty.csv`:
```csv
```

`tests/fixtures/headers_only.csv`:
```csv
name,age,email
```

**Step 3: Write the failing tests**

`tests/test_reader.py`:
```python
import os
import pytest
from csv_validator.reader import read_csv

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_read_csv_returns_list_of_row_dicts():
    rows = read_csv(os.path.join(FIXTURES, "valid.csv"))
    assert len(rows) == 2
    assert rows[0]["data"] == {"name": "Alice", "age": "30", "email": "alice@example.com"}
    assert rows[0]["line"] == 2
    assert rows[1]["data"] == {"name": "Bob", "age": "25", "email": "bob@example.com"}
    assert rows[1]["line"] == 3


def test_read_csv_empty_file_returns_empty_list():
    rows = read_csv(os.path.join(FIXTURES, "empty.csv"))
    assert rows == []


def test_read_csv_headers_only_returns_empty_list():
    rows = read_csv(os.path.join(FIXTURES, "headers_only.csv"))
    assert rows == []


def test_read_csv_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        read_csv("/nonexistent/path.csv")
```

**Step 4: Run tests to verify they fail**

Run: `pytest tests/test_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csv_validator'`

**Step 5: Write minimal implementation**

`src/csv_validator/reader.py`:
```python
import csv
from typing import TypedDict


class Row(TypedDict):
    line: int
    data: dict[str, str]


def read_csv(file_path: str) -> list[Row]:
    """Read a CSV file and return a list of row dicts with line numbers.

    Each returned item has:
      - 'line': the 1-based line number in the original file
      - 'data': a dict mapping column headers to string values

    Raises FileNotFoundError if the file does not exist.
    """
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows: list[Row] = []
        for i, row in enumerate(reader, start=2):  # header is line 1
            rows.append({"line": i, "data": dict(row)})
        return rows
```

**Step 6: Create `pyproject.toml` so the package is importable**

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "csv-validator"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "jsonschema>=4.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[project.scripts]
csv-validator = "csv_validator.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

Install in dev mode:
```bash
pip install -e ".[dev]"
```

**Step 7: Run tests to verify they pass**

Run: `pytest tests/test_reader.py -v`
Expected: All 4 tests PASS

**Step 8: Commit**

```bash
git add src/ tests/ pyproject.toml
git commit -m "feat: add CSV reader module with line-number tracking"
```

---

### Task 2: Schema Validator Module

Validate row dicts against a JSON Schema and collect per-row errors.

**Files:**
- Create: `src/csv_validator/validator.py`
- Test: `tests/test_validator.py`
- Create: `tests/fixtures/schema_basic.json`

**Step 1: Create test fixture**

`tests/fixtures/schema_basic.json`:
```json
{
  "type": "object",
  "properties": {
    "name": { "type": "string", "minLength": 1 },
    "age": { "type": "integer", "minimum": 0 },
    "email": { "type": "string", "format": "email" }
  },
  "required": ["name", "age", "email"]
}
```

**Step 2: Write the failing tests**

`tests/test_validator.py`:
```python
import json
import os
import pytest
from csv_validator.validator import validate_rows, load_schema, ValidationError

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_schema():
    return load_schema(os.path.join(FIXTURES, "schema_basic.json"))


def test_load_schema_returns_dict():
    schema = _load_schema()
    assert schema["type"] == "object"
    assert "name" in schema["properties"]


def test_load_schema_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_schema("/nonexistent/schema.json")


def test_load_schema_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json{{{")
    with pytest.raises(json.JSONDecodeError):
        load_schema(str(bad))


def test_validate_rows_all_valid():
    schema = _load_schema()
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "30", "email": "alice@example.com"}},
    ]
    errors = validate_rows(rows, schema)
    assert errors == []


def test_validate_rows_type_coercion_integer():
    """CSV values are strings. The validator should coerce 'age' to int per schema."""
    schema = _load_schema()
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "30", "email": "alice@example.com"}},
    ]
    errors = validate_rows(rows, schema)
    assert errors == []


def test_validate_rows_missing_required_field():
    schema = _load_schema()
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "30"}},
    ]
    errors = validate_rows(rows, schema)
    assert len(errors) == 1
    assert errors[0]["line"] == 2
    assert "email" in errors[0]["message"]


def test_validate_rows_invalid_value():
    schema = _load_schema()
    rows = [
        {"line": 2, "data": {"name": "", "age": "30", "email": "alice@example.com"}},
    ]
    errors = validate_rows(rows, schema)
    assert len(errors) == 1
    assert errors[0]["line"] == 2
    assert "name" in errors[0]["message"] or "minLength" in errors[0]["message"]


def test_validate_rows_non_numeric_age():
    schema = _load_schema()
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "notanumber", "email": "alice@example.com"}},
    ]
    errors = validate_rows(rows, schema)
    assert len(errors) == 1
    assert errors[0]["line"] == 2


def test_validate_rows_multiple_rows_multiple_errors():
    schema = _load_schema()
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "30", "email": "alice@example.com"}},
        {"line": 3, "data": {"name": "", "age": "notanumber", "email": "bob@example.com"}},
        {"line": 4, "data": {"name": "Charlie", "age": "40"}},
    ]
    errors = validate_rows(rows, schema)
    # Row 2: valid -> 0 errors
    # Row 3: name too short + age not coercible -> 2 errors
    # Row 4: missing email -> 1 error
    assert len(errors) == 3
    line_numbers = [e["line"] for e in errors]
    assert 3 in line_numbers
    assert 4 in line_numbers


def test_validate_rows_empty_list():
    schema = _load_schema()
    errors = validate_rows([], schema)
    assert errors == []
```

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_validator.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

**Step 4: Write minimal implementation**

`src/csv_validator/validator.py`:
```python
import json
from typing import Any

import jsonschema


class ValidationError:
    """Represents a single validation error on a specific CSV line."""

    def __init__(self, line: int, field: str, message: str):
        self.line = line
        self.field = field
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, "field": self.field, "message": self.message}


def load_schema(file_path: str) -> dict:
    """Load and return a JSON Schema from a file path.

    Raises FileNotFoundError if the file does not exist.
    Raises json.JSONDecodeError if the file is not valid JSON.
    """
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


def _coerce_row(data: dict[str, str], schema: dict) -> dict[str, Any]:
    """Attempt to coerce CSV string values to the types declared in the schema.

    CSV readers return all values as strings. This function converts values
    to integer or number types when the schema declares them, so that
    jsonschema validation works correctly.
    """
    properties = schema.get("properties", {})
    coerced: dict[str, Any] = {}
    for key, value in data.items():
        prop_schema = properties.get(key, {})
        declared_type = prop_schema.get("type")
        if declared_type == "integer":
            try:
                coerced[key] = int(value)
            except (ValueError, TypeError):
                coerced[key] = value  # leave as string; validation will catch it
        elif declared_type == "number":
            try:
                coerced[key] = float(value)
            except (ValueError, TypeError):
                coerced[key] = value
        elif declared_type == "boolean":
            lower = value.lower()
            if lower in ("true", "1", "yes"):
                coerced[key] = True
            elif lower in ("false", "0", "no"):
                coerced[key] = False
            else:
                coerced[key] = value
        else:
            coerced[key] = value
    return coerced


def validate_rows(rows: list[dict], schema: dict) -> list[dict[str, Any]]:
    """Validate a list of row dicts against a JSON Schema.

    Args:
        rows: List of dicts with 'line' (int) and 'data' (dict) keys,
              as produced by reader.read_csv().
        schema: A JSON Schema dict.

    Returns:
        A list of error dicts, each with 'line', 'field', and 'message' keys.
        Returns an empty list if all rows are valid.
    """
    errors: list[dict[str, Any]] = []
    json_validator = jsonschema.Draft7Validator(schema)

    for row in rows:
        line = row["line"]
        coerced = _coerce_row(row["data"], schema)
        for error in json_validator.iter_errors(coerced):
            # Determine the field name from the error path or the validator type
            if error.path:
                field = str(error.path[0])
            elif error.validator == "required":
                # Extract field name from "'fieldname' is a required property"
                field = error.message.split("'")[1] if "'" in error.message else "unknown"
            else:
                field = "unknown"

            errors.append({
                "line": line,
                "field": field,
                "message": error.message,
            })

    return errors
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_validator.py -v`
Expected: All 10 tests PASS

**Step 6: Commit**

```bash
git add src/csv_validator/validator.py tests/test_validator.py tests/fixtures/schema_basic.json
git commit -m "feat: add schema validator with CSV type coercion"
```

---

### Task 3: Plugin System

Load custom validator functions from a user-specified plugin directory.

**Files:**
- Create: `src/csv_validator/plugins.py`
- Test: `tests/test_plugins.py`
- Create: `tests/fixtures/plugins/check_email_domain.py`
- Create: `tests/fixtures/plugins/check_age_range.py`
- Create: `tests/fixtures/plugins/not_a_plugin.txt`

**Step 1: Create test plugin fixtures**

`tests/fixtures/plugins/check_email_domain.py`:
```python
"""Plugin: reject email addresses not from example.com."""


def validate(row_data: dict, line: int) -> list[dict]:
    """Return a list of error dicts for this row, or empty list if valid."""
    errors = []
    email = row_data.get("email", "")
    if email and not email.endswith("@example.com"):
        errors.append({
            "line": line,
            "field": "email",
            "message": f"Email domain must be example.com, got: {email}",
        })
    return errors
```

`tests/fixtures/plugins/check_age_range.py`:
```python
"""Plugin: reject ages outside 18-65."""


def validate(row_data: dict, line: int) -> list[dict]:
    """Return a list of error dicts for this row, or empty list if valid."""
    errors = []
    age_str = row_data.get("age", "")
    try:
        age = int(age_str)
    except (ValueError, TypeError):
        return errors  # type validation is handled by schema validator
    if age < 18 or age > 65:
        errors.append({
            "line": line,
            "field": "age",
            "message": f"Age must be between 18 and 65, got: {age}",
        })
    return errors
```

`tests/fixtures/plugins/not_a_plugin.txt`:
```
This file should be ignored by the plugin loader.
```

**Step 2: Write the failing tests**

`tests/test_plugins.py`:
```python
import os
import pytest
from csv_validator.plugins import load_plugins, run_plugins

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "plugins")


def test_load_plugins_finds_python_files():
    plugins = load_plugins(PLUGIN_DIR)
    names = [p["name"] for p in plugins]
    assert "check_email_domain" in names
    assert "check_age_range" in names


def test_load_plugins_ignores_non_python_files():
    plugins = load_plugins(PLUGIN_DIR)
    names = [p["name"] for p in plugins]
    assert "not_a_plugin" not in names


def test_load_plugins_each_has_validate_callable():
    plugins = load_plugins(PLUGIN_DIR)
    for plugin in plugins:
        assert callable(plugin["validate"])


def test_load_plugins_nonexistent_dir_raises():
    with pytest.raises(FileNotFoundError):
        load_plugins("/nonexistent/plugin/dir")


def test_load_plugins_empty_dir(tmp_path):
    plugins = load_plugins(str(tmp_path))
    assert plugins == []


def test_run_plugins_returns_errors():
    plugins = load_plugins(PLUGIN_DIR)
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "30", "email": "alice@other.com"}},
    ]
    errors = run_plugins(rows, plugins)
    assert len(errors) >= 1
    assert any("example.com" in e["message"] for e in errors)


def test_run_plugins_valid_row_no_errors():
    plugins = load_plugins(PLUGIN_DIR)
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "30", "email": "alice@example.com"}},
    ]
    errors = run_plugins(rows, plugins)
    assert errors == []


def test_run_plugins_age_range_violation():
    plugins = load_plugins(PLUGIN_DIR)
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "10", "email": "alice@example.com"}},
    ]
    errors = run_plugins(rows, plugins)
    assert len(errors) >= 1
    assert any("age" in e["field"].lower() for e in errors)


def test_run_plugins_no_plugins_no_errors():
    rows = [
        {"line": 2, "data": {"name": "Alice", "age": "30", "email": "alice@example.com"}},
    ]
    errors = run_plugins(rows, [])
    assert errors == []
```

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_plugins.py -v`
Expected: FAIL with `ImportError`

**Step 4: Write minimal implementation**

`src/csv_validator/plugins.py`:
```python
import importlib.util
import os
from typing import Any


def load_plugins(plugin_dir: str) -> list[dict[str, Any]]:
    """Load all Python files from a directory as validator plugins.

    Each plugin must define a `validate(row_data: dict, line: int) -> list[dict]`
    function. Files without a `validate` function are skipped with a warning.

    Args:
        plugin_dir: Path to directory containing plugin .py files.

    Returns:
        List of dicts with 'name' (str) and 'validate' (callable) keys.

    Raises:
        FileNotFoundError: If plugin_dir does not exist.
    """
    if not os.path.isdir(plugin_dir):
        raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

    plugins: list[dict[str, Any]] = []
    for filename in sorted(os.listdir(plugin_dir)):
        if not filename.endswith(".py"):
            continue
        name = filename[:-3]  # strip .py
        filepath = os.path.join(plugin_dir, filename)

        spec = importlib.util.spec_from_file_location(f"csv_validator_plugin_{name}", filepath)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "validate") or not callable(module.validate):
            continue

        plugins.append({"name": name, "validate": module.validate})

    return plugins


def run_plugins(rows: list[dict], plugins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run all loaded plugins against each row and collect errors.

    Args:
        rows: List of dicts with 'line' (int) and 'data' (dict) keys.
        plugins: List of plugin dicts as returned by load_plugins().

    Returns:
        A list of error dicts, each with 'line', 'field', and 'message' keys.
    """
    errors: list[dict[str, Any]] = []
    for row in rows:
        for plugin in plugins:
            try:
                plugin_errors = plugin["validate"](row["data"], row["line"])
                errors.extend(plugin_errors)
            except Exception as exc:
                errors.append({
                    "line": row["line"],
                    "field": "plugin_error",
                    "message": f"Plugin '{plugin['name']}' raised: {exc}",
                })
    return errors
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_plugins.py -v`
Expected: All 9 tests PASS

**Step 6: Commit**

```bash
git add src/csv_validator/plugins.py tests/test_plugins.py tests/fixtures/plugins/
git commit -m "feat: add plugin system for custom validators"
```

---

### Task 4: Report Formatter

Format validation errors into human-readable text or JSON output.

**Files:**
- Create: `src/csv_validator/report.py`
- Test: `tests/test_report.py`

**Step 1: Write the failing tests**

`tests/test_report.py`:
```python
import json
import pytest
from csv_validator.report import format_report


def _sample_errors():
    return [
        {"line": 2, "field": "name", "message": "'' is too short"},
        {"line": 3, "field": "email", "message": "'email' is a required property"},
        {"line": 3, "field": "age", "message": "Age must be between 18 and 65, got: 10"},
    ]


def test_format_report_json_output():
    errors = _sample_errors()
    result = format_report(errors, output_format="json")
    parsed = json.loads(result)
    assert parsed["total_errors"] == 3
    assert parsed["rows_with_errors"] == 2
    assert len(parsed["errors"]) == 3


def test_format_report_json_structure():
    errors = _sample_errors()
    result = format_report(errors, output_format="json")
    parsed = json.loads(result)
    first = parsed["errors"][0]
    assert "line" in first
    assert "field" in first
    assert "message" in first


def test_format_report_text_output():
    errors = _sample_errors()
    result = format_report(errors, output_format="text")
    assert "Line 2" in result
    assert "Line 3" in result
    assert "name" in result
    assert "email" in result


def test_format_report_text_groups_by_line():
    errors = _sample_errors()
    result = format_report(errors, output_format="text")
    # Line 3 has 2 errors; they should appear together
    lines = result.split("\n")
    line3_indices = [i for i, l in enumerate(lines) if "Line 3" in l]
    assert len(line3_indices) == 1  # one header for line 3, errors listed below


def test_format_report_no_errors_json():
    result = format_report([], output_format="json")
    parsed = json.loads(result)
    assert parsed["total_errors"] == 0
    assert parsed["errors"] == []


def test_format_report_no_errors_text():
    result = format_report([], output_format="text")
    assert "no validation errors" in result.lower()


def test_format_report_invalid_format_raises():
    with pytest.raises(ValueError, match="format"):
        format_report([], output_format="xml")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

`src/csv_validator/report.py`:
```python
import json
from typing import Any


def format_report(errors: list[dict[str, Any]], output_format: str = "text") -> str:
    """Format validation errors into a report string.

    Args:
        errors: List of error dicts with 'line', 'field', and 'message' keys.
        output_format: Either 'json' or 'text'.

    Returns:
        Formatted report string.

    Raises:
        ValueError: If output_format is not 'json' or 'text'.
    """
    if output_format not in ("json", "text"):
        raise ValueError(f"Unsupported output format: '{output_format}'. Use 'json' or 'text'.")

    if output_format == "json":
        return _format_json(errors)
    return _format_text(errors)


def _format_json(errors: list[dict[str, Any]]) -> str:
    unique_lines = set(e["line"] for e in errors)
    report = {
        "total_errors": len(errors),
        "rows_with_errors": len(unique_lines),
        "errors": errors,
    }
    return json.dumps(report, indent=2)


def _format_text(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return "Validation complete: no validation errors found."

    # Group errors by line number
    by_line: dict[int, list[dict[str, Any]]] = {}
    for error in errors:
        by_line.setdefault(error["line"], []).append(error)

    unique_lines = len(by_line)
    lines = [
        f"Validation Report: {len(errors)} error(s) found across {unique_lines} row(s).",
        "",
    ]

    for line_num in sorted(by_line.keys()):
        line_errors = by_line[line_num]
        lines.append(f"  Line {line_num}:")
        for err in line_errors:
            lines.append(f"    - [{err['field']}] {err['message']}")
        lines.append("")

    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add src/csv_validator/report.py tests/test_report.py
git commit -m "feat: add report formatter with JSON and text output"
```

---

### Task 5: CLI Entry Point

Wire all modules together into an `argparse`-based CLI.

**Files:**
- Create: `src/csv_validator/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import json
import os
import subprocess
import sys
import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
CSV_FILE = os.path.join(FIXTURES, "valid.csv")
SCHEMA_FILE = os.path.join(FIXTURES, "schema_basic.json")
PLUGIN_DIR = os.path.join(FIXTURES, "plugins")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the CLI as a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "csv_validator.cli", *args],
        capture_output=True,
        text=True,
    )


def test_cli_no_args_prints_usage():
    result = run_cli()
    assert result.returncode != 0
    assert "usage" in result.stderr.lower() or "error" in result.stderr.lower()


def test_cli_valid_csv_no_errors():
    result = run_cli(CSV_FILE, "--schema", SCHEMA_FILE)
    assert result.returncode == 0
    assert "no validation errors" in result.stdout.lower()


def test_cli_json_output():
    result = run_cli(CSV_FILE, "--schema", SCHEMA_FILE, "--format", "json")
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["total_errors"] == 0


def test_cli_with_plugins():
    result = run_cli(
        CSV_FILE,
        "--schema", SCHEMA_FILE,
        "--plugins", PLUGIN_DIR,
        "--format", "json",
    )
    assert result.returncode == 1  # errors found -> exit code 1
    parsed = json.loads(result.stdout)
    assert parsed["total_errors"] == 0  # valid.csv uses example.com and ages 25, 30


def test_cli_missing_csv_file():
    result = run_cli("/nonexistent/file.csv", "--schema", SCHEMA_FILE)
    assert result.returncode != 0
    assert "error" in result.stderr.lower() or "not found" in result.stderr.lower()


def test_cli_missing_schema_file():
    result = run_cli(CSV_FILE, "--schema", "/nonexistent/schema.json")
    assert result.returncode != 0


def test_cli_exit_code_0_when_no_errors():
    result = run_cli(CSV_FILE, "--schema", SCHEMA_FILE)
    assert result.returncode == 0


def test_cli_exit_code_1_when_errors_found():
    """Use a CSV that will produce schema validation errors."""
    # Create a temporary CSV with bad data
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("name,age,email\n")
        f.write(",notanumber,bademail\n")
        tmp_csv = f.name
    try:
        result = run_cli(tmp_csv, "--schema", SCHEMA_FILE)
        assert result.returncode == 1
    finally:
        os.unlink(tmp_csv)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError` or process error

**Step 3: Write minimal implementation**

`src/csv_validator/cli.py`:
```python
"""CSV Schema Validator CLI.

Reads a CSV file, validates each row against a JSON Schema,
optionally runs custom validator plugins, and outputs a report.
"""
import argparse
import sys

from csv_validator.reader import read_csv
from csv_validator.validator import load_schema, validate_rows
from csv_validator.plugins import load_plugins, run_plugins
from csv_validator.report import format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv-validator",
        description="Validate CSV data against a JSON Schema and output an error report.",
    )
    parser.add_argument(
        "csv_file",
        help="Path to the CSV file to validate.",
    )
    parser.add_argument(
        "--schema",
        required=True,
        help="Path to the JSON Schema file.",
    )
    parser.add_argument(
        "--plugins",
        default=None,
        help="Path to a directory containing custom validator plugins.",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="Output format: 'text' (default) or 'json'.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Read CSV
    try:
        rows = read_csv(args.csv_file)
    except FileNotFoundError:
        print(f"Error: CSV file not found: {args.csv_file}", file=sys.stderr)
        return 2

    # Load schema
    try:
        schema = load_schema(args.schema)
    except FileNotFoundError:
        print(f"Error: Schema file not found: {args.schema}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: Failed to load schema: {exc}", file=sys.stderr)
        return 2

    # Validate against schema
    errors = validate_rows(rows, schema)

    # Load and run plugins if specified
    if args.plugins:
        try:
            plugins = load_plugins(args.plugins)
        except FileNotFoundError:
            print(f"Error: Plugin directory not found: {args.plugins}", file=sys.stderr)
            return 2
        plugin_errors = run_plugins(rows, plugins)
        errors.extend(plugin_errors)

    # Output report
    report = format_report(errors, output_format=args.output_format)
    print(report)

    # Exit code: 0 if no errors, 1 if validation errors found
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Fix test expectation for plugins with valid data**

The test `test_cli_with_plugins` uses `valid.csv` which has `alice@example.com` and `bob@example.com` (valid domains) and ages 30, 25 (valid range). So plugins should find zero errors and exit code should be 0. Update the test:

In `tests/test_cli.py`, change `test_cli_with_plugins`:
```python
def test_cli_with_plugins():
    result = run_cli(
        CSV_FILE,
        "--schema", SCHEMA_FILE,
        "--plugins", PLUGIN_DIR,
        "--format", "json",
    )
    assert result.returncode == 0  # valid.csv uses example.com and ages 25, 30
    parsed = json.loads(result.stdout)
    assert parsed["total_errors"] == 0
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: All 8 tests PASS

**Step 6: Commit**

```bash
git add src/csv_validator/cli.py tests/test_cli.py
git commit -m "feat: add CLI entry point wiring reader, validator, plugins, and report"
```

---

### Task 6: Integration Tests

End-to-end tests covering the full pipeline with various edge cases.

**Files:**
- Test: `tests/test_integration.py`
- Create: `tests/fixtures/bad_data.csv`
- Create: `tests/fixtures/mixed_data.csv`
- Create: `tests/fixtures/plugins_broken/broken_plugin.py`

**Step 1: Create test fixtures**

`tests/fixtures/bad_data.csv`:
```csv
name,age,email
,notanumber,
Alice,-5,not-an-email
```

`tests/fixtures/mixed_data.csv`:
```csv
name,age,email
Alice,30,alice@example.com
,25,bob@example.com
Charlie,notanumber,charlie@example.com
Diana,40,diana@other.com
```

`tests/fixtures/plugins_broken/broken_plugin.py`:
```python
"""Plugin that raises an exception."""


def validate(row_data: dict, line: int) -> list[dict]:
    raise RuntimeError("Plugin intentionally broken for testing")
```

**Step 2: Write the failing tests**

`tests/test_integration.py`:
```python
import json
import os
import subprocess
import sys
import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SCHEMA = os.path.join(FIXTURES, "schema_basic.json")
PLUGIN_DIR = os.path.join(FIXTURES, "plugins")
BROKEN_PLUGIN_DIR = os.path.join(FIXTURES, "plugins_broken")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "csv_validator.cli", *args],
        capture_output=True,
        text=True,
    )


def test_integration_bad_data_reports_all_errors():
    result = run_cli(
        os.path.join(FIXTURES, "bad_data.csv"),
        "--schema", SCHEMA,
        "--format", "json",
    )
    assert result.returncode == 1
    parsed = json.loads(result.stdout)
    assert parsed["total_errors"] >= 3  # multiple errors across 2 rows
    assert parsed["rows_with_errors"] == 2


def test_integration_mixed_data_correct_error_count():
    result = run_cli(
        os.path.join(FIXTURES, "mixed_data.csv"),
        "--schema", SCHEMA,
        "--format", "json",
    )
    assert result.returncode == 1
    parsed = json.loads(result.stdout)
    # Row 2 (Alice): valid -> 0 errors
    # Row 3 (empty name): minLength violation -> 1 error
    # Row 4 (Charlie, notanumber): age coercion fail -> 1 error
    # Row 5 (Diana): valid (schema doesn't check email domain) -> 0 errors
    assert parsed["total_errors"] >= 2
    error_lines = [e["line"] for e in parsed["errors"]]
    assert 3 in error_lines
    assert 4 in error_lines


def test_integration_mixed_data_with_plugins():
    result = run_cli(
        os.path.join(FIXTURES, "mixed_data.csv"),
        "--schema", SCHEMA,
        "--plugins", PLUGIN_DIR,
        "--format", "json",
    )
    assert result.returncode == 1
    parsed = json.loads(result.stdout)
    # Schema errors + plugin errors (diana@other.com fails domain check)
    messages = [e["message"] for e in parsed["errors"]]
    assert any("example.com" in m for m in messages)


def test_integration_text_output_is_readable():
    result = run_cli(
        os.path.join(FIXTURES, "bad_data.csv"),
        "--schema", SCHEMA,
        "--format", "text",
    )
    assert result.returncode == 1
    assert "Validation Report" in result.stdout
    assert "Line 2" in result.stdout
    assert "Line 3" in result.stdout


def test_integration_broken_plugin_reports_plugin_error():
    result = run_cli(
        os.path.join(FIXTURES, "mixed_data.csv"),
        "--schema", SCHEMA,
        "--plugins", BROKEN_PLUGIN_DIR,
        "--format", "json",
    )
    assert result.returncode == 1
    parsed = json.loads(result.stdout)
    messages = [e["message"] for e in parsed["errors"]]
    assert any("Plugin" in m and "raised" in m for m in messages)


def test_integration_valid_csv_exit_code_zero():
    result = run_cli(
        os.path.join(FIXTURES, "valid.csv"),
        "--schema", SCHEMA,
        "--format", "json",
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["total_errors"] == 0
```

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL (fixtures not yet created or some tests may pass if prior tasks are done)

**Step 4: Create the fixture files (code shown in Step 1)**

No new implementation code needed. Just create the fixture files listed above.

**Step 5: Run all tests to verify everything passes**

Run: `pytest tests/ -v`
Expected: All tests PASS across all test files

**Step 6: Commit**

```bash
git add tests/test_integration.py tests/fixtures/bad_data.csv tests/fixtures/mixed_data.csv tests/fixtures/plugins_broken/
git commit -m "test: add integration tests for full CLI pipeline"
```

---

## Execution Order Summary

**Wave 1 (no dependencies, parallel-safe):**
- Task 1: CSV reader module (foundational I/O)
- Task 3: Plugin system (independent module)

**Wave 2 (depends on Wave 1):**
- Task 2: Schema validator (depends on Task 1 for Row type convention)

**Wave 3 (depends on Waves 1 and 2):**
- Task 4: Report formatter (depends on Task 2 and 3 for error dict shape)

**Wave 4 (depends on all prior):**
- Task 5: CLI entry point (wires all modules together)

**Wave 5 (depends on Wave 4):**
- Task 6: Integration tests (end-to-end validation)

---

## Verification Checklist

After all tasks complete, run these checks:

1. **Full test suite passes:**
   - Run: `pytest tests/ -v`
   - Expected: All tests PASS, zero failures

2. **CLI runs end-to-end:**
   - Run: `csv-validator tests/fixtures/valid.csv --schema tests/fixtures/schema_basic.json`
   - Expected: Exit code 0, "no validation errors" message
   - Run: `csv-validator tests/fixtures/bad_data.csv --schema tests/fixtures/schema_basic.json --format json`
   - Expected: Exit code 1, JSON with `total_errors >= 3`

3. **Plugin system works:**
   - Run: `csv-validator tests/fixtures/mixed_data.csv --schema tests/fixtures/schema_basic.json --plugins tests/fixtures/plugins --format json`
   - Expected: Exit code 1, errors include both schema and plugin errors

4. **Package installs cleanly:**
   - Run: `pip install -e ".[dev]"` completes without errors
   - Run: `csv-validator --help` prints usage

5. **File structure is correct:**
   ```
   src/csv_validator/
   ├── __init__.py
   ├── cli.py
   ├── plugins.py
   ├── reader.py
   ├── report.py
   └── validator.py
   tests/
   ├── __init__.py
   ├── fixtures/
   │   ├── bad_data.csv
   │   ├── empty.csv
   │   ├── headers_only.csv
   │   ├── mixed_data.csv
   │   ├── plugins/
   │   │   ├── check_age_range.py
   │   │   ├── check_email_domain.py
   │   │   └── not_a_plugin.txt
   │   ├── plugins_broken/
   │   │   └── broken_plugin.py
   │   ├── schema_basic.json
   │   └── valid.csv
   ├── test_cli.py
   ├── test_integration.py
   ├── test_plugins.py
   ├── test_reader.py
   └── test_validator.py
   pyproject.toml
   ```
