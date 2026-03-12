# CSV Validation CLI Tool -- Implementation Plan

## 1. Overview

A command-line tool that reads a CSV file, validates each row against a user-supplied JSON schema, and produces a structured report of all validation errors. The tool supports custom validators loaded at runtime from a plugin directory.

---

## 2. Requirements

### Functional

| ID | Requirement |
|----|-------------|
| F1 | Accept a CSV file path, a JSON schema file path, and an optional plugin directory path as CLI arguments. |
| F2 | Parse the CSV file, handling headers, quoted fields, and common edge cases (empty lines, BOM, different delimiters). |
| F3 | Validate every row/cell against the JSON schema (types, required fields, constraints such as min/max, pattern, enum). |
| F4 | Discover and load custom validator plugins from a specified directory at startup. |
| F5 | Apply matching custom validators during the validation pass, alongside the built-in schema checks. |
| F6 | Produce a human-readable report to stdout summarizing all errors, grouped by row, with an exit code reflecting pass/fail. |
| F7 | Optionally output the report as JSON for machine consumption (`--format json`). |

### Non-Functional

- Single-binary or single-entry-point invocation (no server, no GUI).
- Process files of at least several hundred thousand rows without excessive memory use (stream where possible).
- Clear, actionable error messages that include row number, column name, and the violated constraint.

---

## 3. Recommended Technology

**Language:** Python 3.10+

**Rationale:** Rich ecosystem for CSV handling (`csv` stdlib), JSON Schema validation (`jsonschema` library), and dynamic plugin loading (`importlib`). Fast enough for the target file sizes; easy to distribute via `pip` or `pipx`.

**Key dependencies:**

| Package | Purpose |
|---------|---------|
| `jsonschema` (>=4.x) | JSON Schema Draft 2020-12 validation |
| `click` | CLI argument parsing, help text, exit codes |
| `rich` (optional) | Coloured terminal output for the human-readable report |

---

## 4. Architecture

```
csv-validator/
  pyproject.toml
  src/
    csv_validator/
      __init__.py
      cli.py              # Click entrypoint
      reader.py            # CSV reading & normalisation
      schema.py            # JSON schema loading & row-level validation
      plugin_loader.py     # Plugin discovery & registration
      reporter.py          # Error formatting (text + JSON)
      models.py            # Data classes for ValidationError, RowResult, Report
  plugins/                 # Example / default plugin directory
    example_plugin.py
  tests/
    conftest.py
    test_reader.py
    test_schema.py
    test_plugin_loader.py
    test_reporter.py
    test_cli_integration.py
```

### Component Interaction

```
CLI (cli.py)
  |
  +--> Reader (reader.py)          -- streams rows from CSV
  |
  +--> SchemaValidator (schema.py) -- validates each row dict against JSON Schema
  |
  +--> PluginLoader (plugin_loader.py)
  |        |
  |        +--> discovers .py files in plugin dir
  |        +--> imports modules, collects validator callables
  |
  +--> Reporter (reporter.py)      -- collects errors, formats output
```

---

## 5. Detailed Design

### 5.1 CLI Interface (`cli.py`)

```
csv-validator <csv_file> <schema_file> [OPTIONS]

Positional arguments:
  csv_file          Path to the input CSV file.
  schema_file       Path to the JSON schema file.

Options:
  --plugins DIR     Path to the custom validators plugin directory.
  --delimiter CHAR  CSV delimiter (default: auto-detect, fallback comma).
  --format TEXT     Report format: "text" (default) or "json".
  --strict          Treat warnings as errors (exit code 1).
  --max-errors N    Stop after N errors (default: unlimited).
  --help            Show help and exit.
```

Exit codes:
- `0` -- all rows valid.
- `1` -- one or more validation errors found.
- `2` -- input/configuration error (file not found, bad schema, bad plugin).

### 5.2 CSV Reader (`reader.py`)

- Uses `csv.DictReader` for row-by-row streaming.
- Auto-detects delimiter via `csv.Sniffer` on the first 8 KB; falls back to comma.
- Strips BOM from the first header if present.
- Yields `(row_number: int, row: dict[str, str])` tuples.
- Raises a clear error if the file is empty or has no header row.

### 5.3 Schema Validator (`schema.py`)

Responsibilities:

1. **Load & validate the schema itself** -- parse the JSON file, confirm it is a valid JSON Schema document (meta-validate against the JSON Schema meta-schema).
2. **Coerce cell values** -- CSV cells are always strings. Before validation, coerce values to the types declared in the schema (`integer`, `number`, `boolean`, `null`). Leave `string` as-is. If coercion fails, emit a type-error immediately.
3. **Validate each row** -- build a row dict with coerced values, run `jsonschema.validate()`. Collect all errors (use `jsonschema.Draft202012Validator` with `iter_errors()` to avoid stopping at the first).
4. Return a list of `ValidationError` dataclass instances per row.

Schema expectations (documented for users):

```jsonc
{
  "type": "object",
  "properties": {
    "age":   { "type": "integer", "minimum": 0 },
    "email": { "type": "string",  "format": "email" },
    "role":  { "type": "string",  "enum": ["admin", "user", "guest"] }
  },
  "required": ["age", "email"]
}
```

Each top-level property key corresponds to a CSV column header.

### 5.4 Plugin Loader (`plugin_loader.py`)

**Plugin contract:**

Each plugin is a Python file placed in the plugin directory. It must expose a top-level `validators` list (or a `register()` function returning that list). Each validator is a dict:

```python
validators = [
    {
        "column": "phone",            # which column this applies to (or "*" for all)
        "name": "us_phone_format",    # human-readable name for error messages
        "validate": lambda value, row: None if re.match(r'^\+1\d{10}$', value) else "Must be a US phone number (+1XXXXXXXXXX)",
    },
]
```

The `validate` callable receives `(cell_value: str, full_row: dict[str, str])` and returns `None` on success or an error message string on failure.

**Discovery flow:**

1. Glob `plugin_dir/*.py`.
2. For each file, `importlib.util.spec_from_file_location` / `module_from_spec` / `loader.exec_module`.
3. Look for a `validators` attribute (list) or call `register()`.
4. Merge all collected validators into a lookup: `dict[column_name, list[ValidatorCallable]]`.
5. On import failure, log a warning and continue (do not abort the entire run).

**Execution:**

After JSON Schema validation for a row, run all matching plugin validators for each cell. Append any returned error strings to the row's error list.

### 5.5 Data Models (`models.py`)

```python
@dataclass
class ValidationError:
    row: int
    column: str
    value: Any
    constraint: str      # e.g. "minimum", "required", "plugin:us_phone_format"
    message: str

@dataclass
class Report:
    total_rows: int
    valid_rows: int
    invalid_rows: int
    errors: list[ValidationError]
    truncated: bool      # True if --max-errors caused early stop
```

### 5.6 Reporter (`reporter.py`)

**Text mode (default):**

```
CSV Validation Report
=====================
File:   data.csv
Schema: schema.json
Rows:   1,204 checked | 1,187 valid | 17 invalid

Errors:
  Row 14, Column "age": value "-3" violates minimum (0)
  Row 14, Column "email": missing required field
  Row 57, Column "phone": Must be a US phone number (+1XXXXXXXXXX)  [plugin: us_phone_format]
  ...

Result: FAIL (17 errors)
```

**JSON mode (`--format json`):**

Serialise the `Report` dataclass to JSON with an `errors` array of objects.

---

## 6. Implementation Steps

Each step is a single, reviewable pull request.

### Step 1 -- Project scaffolding

- Initialise `pyproject.toml` with project metadata, dependencies, and a `[project.scripts]` entry point.
- Create the package skeleton (`src/csv_validator/`).
- Add a minimal Click CLI that prints `--help`.
- Set up `pytest` and a basic smoke test.

### Step 2 -- CSV reader

- Implement `reader.py` with streaming, delimiter detection, BOM handling.
- Unit tests: normal file, tab-delimited, BOM, empty file, missing headers.

### Step 3 -- JSON Schema validation

- Implement `schema.py`: schema loading, type coercion, `iter_errors` collection.
- Implement `models.py` data classes.
- Unit tests: type mismatches, missing required fields, pattern violations, enum violations, nested constraints.

### Step 4 -- Reporter

- Implement `reporter.py` for both text and JSON output.
- Unit tests: verify formatting, edge cases (zero errors, truncated report).

### Step 5 -- Plugin system

- Implement `plugin_loader.py`.
- Create an example plugin in `plugins/`.
- Unit tests: valid plugin, plugin with syntax error (should warn, not crash), plugin with wrong interface, multiple plugins.

### Step 6 -- CLI integration

- Wire all components together in `cli.py`.
- Integration tests: end-to-end runs with fixture CSV and schema files, asserting exit codes and output content.
- Edge-case tests: missing files, invalid schema JSON, very large CSV (performance sanity check).

### Step 7 -- Polish

- Add `--max-errors` early-stop logic.
- Add `--strict` flag.
- Improve error messages and help text.
- Add a README with usage examples.

---

## 7. Testing Strategy

| Layer | What | Tool |
|-------|------|------|
| Unit | Individual functions in `reader`, `schema`, `plugin_loader`, `reporter` | `pytest` |
| Integration | Full CLI invocation via `click.testing.CliRunner` | `pytest` + Click test utilities |
| Fixture data | Small CSV + schema files in `tests/fixtures/` | Committed to repo |
| Edge cases | Malformed CSV, invalid schema, broken plugins, huge files | Parametrised pytest cases |
| CI | Run all tests on every push | GitHub Actions |

Target coverage: 90%+ line coverage on `src/csv_validator/`.

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CSV cells are always strings; schema type coercion may be lossy or ambiguous (e.g., `""` vs `null`). | False positives in validation. | Document coercion rules clearly. Treat empty string as `null` only when the schema type is not `string`. Provide a `--no-coerce` escape hatch if needed. |
| Malicious or buggy plugins could crash the process or cause security issues. | Denial of service, data leak. | Run plugins in a try/except with timeouts. Document that plugins run with full process privileges -- only load trusted code. |
| Very large CSV files may be slow. | User frustration. | Stream rows; never load the full file into memory. Consider optional parallel validation in a future iteration. |
| JSON Schema `format` keyword (e.g., `email`, `uri`) is not enforced by default in `jsonschema`. | Silent non-validation. | Enable format checking via `jsonschema.FormatChecker` and document which formats are supported. |

---

## 9. Future Enhancements (Out of Scope for v1)

- **Fix mode:** auto-correct common issues (trim whitespace, normalise dates) and write a cleaned CSV.
- **Streaming JSON output:** emit errors as NDJSON for piping into other tools.
- **Parallel validation:** use `multiprocessing` for files with millions of rows.
- **Schema inference:** generate a draft schema from a sample CSV.
- **Remote files:** accept S3 / HTTP URLs as input.
