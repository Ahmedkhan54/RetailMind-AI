"""Unit tests for RetailMind AI Power BI PBIP/TMDL/PBIR project generation."""
from __future__ import annotations

from io import BytesIO
import json
import re
import zipfile

import pandas as pd
import pytest

from retailmind.powerbi import (
    PAGE_SCHEMA,
    PAGES_SCHEMA,
    PBIP_SCHEMA,
    PBIPProject,
    PLATFORM_SCHEMA,
    REPORT_PROPERTIES_SCHEMA,
    REPORT_SCHEMA,
    SEMANTIC_PROPERTIES_SCHEMA,
    VERSION_METADATA_SCHEMA,
    VISUAL_SCHEMA,
    build_pbip,
    detect_power_bi_desktop,
    validate_pbip,
)
from retailmind.schema import infer_schema


@pytest.fixture
def sample_retail_df() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["ORD_1", "ORD_2", "ORD_3"],
        "order_date": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "sales": [100.0, 200.0, 300.0],
        "profit": [20.0, 50.0, 60.0],
        "quantity": [2, 4, 6],
        "product_name": ["Widget A", "Widget B", "Widget A"],
        "category": ["Gadgets", "Tools", "Gadgets"],
        "region": ["North", "South", "East"],
        "customer_name": ["Alice", "Bob", "Charlie"],
    })


def test_build_pbip_valid_project(sample_retail_df: pd.DataFrame):
    schema = infer_schema(sample_retail_df)
    project = build_pbip(
        sample_retail_df,
        schema,
        project_name="Sales Intelligence",
        insights=["Sales increased by 10%"],
        forecast_available=True,
        inventory_available=True,
    )
    
    assert isinstance(project, PBIPProject)
    assert project.valid, f"Validation errors: {project.validation}"
    assert len(project.validation) == 0
    assert len(project.tables) >= 1
    assert "FactSales" in project.tables
    assert any("DimDate" in t for t in project.tables)
    assert any("DimProduct" in t for t in project.tables)
    assert len(project.measures) >= 3
    assert "Total Sales" in project.measures
    assert "Total Profit" in project.measures
    
    # Check that pbip file exists
    pbip_file = next(f for f in project.files if f.endswith(".pbip"))
    pbip_json = json.loads(project.files[pbip_file])
    assert "artifacts" in pbip_json
    
    # Check report pages
    assert "Executive Overview" in project.pages
    assert "Sales Analysis" in project.pages


def test_build_pbip_zip_archive(sample_retail_df: pd.DataFrame):
    schema = infer_schema(sample_retail_df)
    project = build_pbip(sample_retail_df, schema, project_name="ExportTest")
    zip_bytes = project.to_zip_bytes()
    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 0
    
    # Verify zip archive contents
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
        names = archive.namelist()
        assert any(n.endswith(".pbip") for n in names)
        assert any("model.tmdl" in n for n in names)
        assert any("report.json" in n for n in names)
        assert any("pages.json" in n for n in names)


def test_validate_pbip_detects_missing_files():
    # Empty files dictionary
    errors = validate_pbip({})
    assert len(errors) > 0
    assert "No .pbip project file was generated." in errors[0]
    
    # Missing required report files
    incomplete = {
        "Test.pbip": json.dumps({"artifacts": [{"report": {"path": "Test.Report"}}]}),
    }
    errors2 = validate_pbip(incomplete)
    assert any("Missing required file" in e for e in errors2)


def test_build_pbip_generic_dataset():
    # Dataset without sales/profit (HR / operations)
    df = pd.DataFrame({
        "employee_id": ["E1", "E2"],
        "employee_name": ["Alice", "Bob"],
        "salary": [70000, 80000],
        "department": ["Engineering", "Product"],
    })
    schema = infer_schema(df)
    project = build_pbip(df, schema, project_name="HR Analytics")
    assert project.valid, f"Validation errors: {project.validation}"
    assert "FactData" in project.tables
    assert "Total Records" in project.measures


def test_detect_power_bi_desktop():
    # Calling detect_power_bi_desktop returns string path or None without raising
    result = detect_power_bi_desktop()
    assert result is None or isinstance(result, str)


def test_generated_project_uses_published_microsoft_schemas(sample_retail_df: pd.DataFrame):
    """Every generated JSON uses the schema identifier Microsoft publishes.

    Power BI Desktop rejects a project whose ``definition.pbir`` (or the
    ``.pbip`` shortcut) points at a non-existent schema URL, so the exact
    identifiers are asserted here rather than assumed.
    """
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="Schema Test")
    files = project.files

    pbip_path = next(path for path in files if path.endswith(".pbip"))
    assert json.loads(files[pbip_path])["$schema"] == PBIP_SCHEMA
    assert PBIP_SCHEMA == "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"

    report_pbir = next(path for path in files if path.endswith("definition.pbir"))
    assert json.loads(files[report_pbir])["$schema"] == REPORT_PROPERTIES_SCHEMA
    assert "definitionProperties/2.0.0" in REPORT_PROPERTIES_SCHEMA

    report_json_path = next(path for path in files if path.endswith("definition/report.json"))
    report_json = json.loads(files[report_json_path])
    assert report_json["$schema"] == REPORT_SCHEMA
    for slot in ("baseTheme", "customTheme"):
        assert set(report_json["themeCollection"][slot]["reportVersionAtImport"]) == {"page", "report", "visual"}

    pages_json = json.loads(next(files[path] for path in files if path.endswith("definition/pages/pages.json")))
    assert pages_json["$schema"] == PAGES_SCHEMA

    pbism = json.loads(next(files[path] for path in files if path.endswith("definition.pbism")))
    assert pbism["$schema"] == SEMANTIC_PROPERTIES_SCHEMA

    for path, content in files.items():
        if path.endswith(("page.json", "visual.json", "/.platform")):
            payload = json.loads(content)
            if path.endswith("page.json"):
                assert payload["$schema"] == PAGE_SCHEMA
            elif path.endswith("visual.json"):
                assert payload["$schema"] == VISUAL_SCHEMA
            else:
                assert payload["$schema"] == PLATFORM_SCHEMA

    # ``validate_pbip`` must reject a stale/unsupported schema instead of
    # silently accepting it.
    report_folder = json.loads(files[pbip_path])["artifacts"][0]["report"]["path"]
    stale = dict(files)
    stale[pbip_path] = json.dumps(
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/pbip/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": report_folder}}],
        }
    )
    assert any("$schema" in error for error in validate_pbip(stale))


def test_build_pbip_includes_version_metadata(sample_retail_df: pd.DataFrame):
    """definition/version.json is mandatory for Power BI Desktop to open the PBIP."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="Version Metadata Test")
    files = project.files

    version_paths = [path for path in files if path.endswith("definition/version.json")]
    assert version_paths, "definition/version.json was not generated"
    version_path = version_paths[0]
    version_meta = json.loads(files[version_path])
    assert version_meta["$schema"] == VERSION_METADATA_SCHEMA
    assert VERSION_METADATA_SCHEMA == (
        "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
        "versionMetadata/1.0.0/schema.json"
    )
    assert isinstance(version_meta.get("version"), str) and version_meta["version"], (
        "version.json 'version' must be a non-empty string"
    )


def test_validate_pbip_rejects_missing_version_json(sample_retail_df: pd.DataFrame):
    """validate_pbip must flag a missing definition/version.json as an error."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="Missing Version Test")
    files = dict(project.files)
    version_path = next(path for path in files if path.endswith("definition/version.json"))
    del files[version_path]
    errors = validate_pbip(files)
    assert any("version.json" in error and "Missing required file" in error for error in errors), errors


def test_validate_pbip_rejects_invalid_version_metadata(sample_retail_df: pd.DataFrame):
    """validate_pbip must flag version.json with an empty/non-string version."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="Invalid Version Test")
    files = dict(project.files)
    version_path = next(path for path in files if path.endswith("definition/version.json"))
    files[version_path] = json.dumps({"$schema": VERSION_METADATA_SCHEMA, "version": ""})
    errors = validate_pbip(files)
    assert any("version.json" in error for error in errors), errors


def test_generated_tmdl_has_no_invalid_table_assignments(sample_retail_df: pd.DataFrame):
    """No generated TMDL table may use 'table Name = DAX' syntax.

    Power BI Desktop rejects 'table Name = <expression>' because an object
    of type Table does not support a default property assignment.
    """
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="TMDL Syntax Test")
    for path, content in project.files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue
        for line_num, line in enumerate(content.splitlines(), start=1):
            assert not re.match(r"^table\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*.+$", line), (
                f"{path}:{line_num}: invalid 'table Name = DAX' declaration: {line.strip()}"
            )


def test_generated_tmdl_tables_have_partitions(sample_retail_df: pd.DataFrame):
    """Every generated TMDL table must have a partition block."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="TMDL Partition Test")
    files = project.files
    table_names = set()
    table_files = {}
    for path, content in files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue
        for line in content.splitlines():
            match = re.match(r"^table\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", line)
            if match:
                table_names.add(match.group(1))
                table_files[match.group(1)] = content
    for table_name in table_names:
        content = table_files[table_name]
        found_partition = False
        for line in content.splitlines():
            if re.match(rf"^\tpartition\s+{table_name}\s*=\s*(m|calculated)\s*$", line):
                found_partition = True
                break
        assert found_partition, f"Table '{table_name}' has no partition definition."


def test_generated_tmdl_calculated_partitions_have_source(sample_retail_df: pd.DataFrame):
    """Every calculated partition must have a 'source = <DAX>' expression."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="TMDL Calc Partition Test")
    files = project.files
    for path, content in files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue
        lines = content.splitlines()
        in_calculated = False
        calc_name = ""
        for line_num, line in enumerate(lines, start=1):
            part_match = re.match(
                r"^\tpartition\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*calculated\s*$", line
            )
            if part_match:
                in_calculated = True
                calc_name = part_match.group(1)
                continue
            if in_calculated:
                if re.match(r"^\t\tsource\s*=\s*.+$", line):
                    in_calculated = False
                    calc_name = ""
                    continue
                if re.match(r"^\t\t", line) is None and line.strip() != "":
                    # Left the partition block without finding source =
                    errors = [f"{path}:{line_num}: calculated partition '{calc_name}' "
                              f"is missing a 'source = <DAX expression>' line."]
                    assert False, errors[0]


def test_generated_tmdl_has_fact_table_m_partition(sample_retail_df: pd.DataFrame):
    """FactSales/FactData import partitions must use the TMDL M source type."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="TMDL FactSource Test")
    files = project.files
    fact_tmdl = None
    for path, content in files.items():
        if path.endswith("/tables/FactSales.tmdl") or path.endswith("/tables/FactData.tmdl"):
            fact_tmdl = content
            break
    assert fact_tmdl is not None, "Fact table TMDL was not generated"
    assert re.search(r"^\tpartition\s+(FactSales|FactData)\s*=\s*m\s*$", fact_tmdl, re.MULTILINE), (
        "Fact table must use a TMDL M partition"
    )
    assert "Table.PromoteHeaders(Csv.Document(File.Contents(" in fact_tmdl
    assert "QuoteStyle=QuoteStyle.Csv" in fact_tmdl


def test_fact_csv_is_in_pbip_zip_and_matches_tmdl_columns():
    """Packaged CSV headers and quoting must match the fact table definition."""
    frame = pd.DataFrame({
        "order_id": ["ORD-1"],
        "product, name": ['Widget, "A"\nsecond line'],
        "sales": [12.5],
    })
    project = build_pbip(frame, infer_schema(frame), project_name="Fact CSV Package Test")
    fact_path = next(path for path in project.files if path.endswith("/tables/FactSales.tmdl"))
    model_folder = fact_path.split("/definition/tables/")[0]
    csv_path = f"{model_folder}/FactSales.csv"

    assert csv_path in project.files
    csv_text = project.files[csv_path]
    assert csv_text.startswith("\ufeff")
    parsed = pd.read_csv(BytesIO(csv_text.encode("utf-8")), encoding="utf-8-sig")
    assert list(parsed.columns) == list(frame.columns)
    assert parsed.loc[0, "product, name"] == frame.loc[0, "product, name"]

    fact_tmdl = project.files[fact_path]
    for column in frame.columns:
        expected_source = f"sourceColumn: '{column}'" if "," in column else f"sourceColumn: {column}"
        assert expected_source in fact_tmdl

    with zipfile.ZipFile(BytesIO(project.to_zip_bytes()), "r") as archive:
        assert csv_path in archive.namelist()
        assert archive.read(csv_path).decode("utf-8").startswith("\ufeff")


def test_validate_pbip_rejects_missing_fact_csv(sample_retail_df: pd.DataFrame):
    """A file-based M partition must not validate without its packaged CSV."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="Missing Fact CSV Test")
    files = dict(project.files)
    csv_path = next(path for path in files if path.endswith(".SemanticModel/FactSales.csv"))
    del files[csv_path]

    errors = validate_pbip(files)
    assert any("not included in the PBIP project" in error for error in errors), errors


def test_validate_pbip_rejects_source_partition_type(sample_retail_df: pd.DataFrame):
    """The legacy `= source` partition declaration is not a valid M partition."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="Invalid Partition Type Test")
    files = dict(project.files)
    fact_path = next(path for path in files if path.endswith("/tables/FactSales.tmdl"))
    files[fact_path] = files[fact_path].replace(
        "partition FactSales = m",
        "partition FactSales = source",
        1,
    )

    errors = validate_pbip(files)
    assert any("no partition definition" in error for error in errors), errors


def test_generated_tmdl_has_data_source_definition(sample_retail_df: pd.DataFrame):
    """A data source definition must exist under definition/dataSources/."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="TMDL DataSource Test")
    files = project.files
    ds_paths = [path for path in files if "/definition/dataSources/" in path and path.endswith(".tmdl")]
    assert ds_paths, "No data source definition files were generated"
    ds_content = files[ds_paths[0]]
    assert re.match(r"^dataSource\s+[A-Za-z_][A-Za-z0-9_]*\s*$", ds_content.splitlines()[0]), (
        f"Invalid data source declaration in {ds_paths[0]}: {ds_lines[0]!r}"
    )


def test_validate_pbip_rejects_invalid_table_assignment(sample_retail_df: pd.DataFrame):
    """validate_pbip must flag 'table Name = DAX' as an error."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="TMDL Invalid Assign Test")
    files = dict(project.files)
    # Find a table file and corrupt it with invalid syntax
    for path, content in files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue
        lines = content.splitlines()
        # Find the table declaration line and corrupt it
        for i, line in enumerate(lines):
            if re.match(r"^table\s+[A-Za-z_][A-Za-z0-9_]*\s*$", line):
                table_name = line.split()[1]
                lines[i] = f"table {table_name} = INVALID_DAX_EXPRESSION()"
                break
        files[path] = "\n".join(lines)
        break
    errors = validate_pbip(files)
    assert any("invalid TMDL" in error and "table Name = DAX" not in error for error in errors), errors


def test_validate_pbip_rejects_missing_partition(sample_retail_df: pd.DataFrame):
    """validate_pbip must flag a table with no partition."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="TMDL No Partition Test")
    files = dict(project.files)
    # Remove all partition lines from DimCategory
    for path, content in files.items():
        if "DimCategory.tmdl" not in path:
            continue
        lines = [l for l in content.splitlines() if not l.startswith("\tpartition")]
        files[path] = "\n".join(lines)
        break
    errors = validate_pbip(files)
    assert any("no partition definition" in error for error in errors), errors


def test_validate_pbip_rejects_calculated_partition_without_source(sample_retail_df: pd.DataFrame):
    """validate_pbip must flag a calculated partition without 'source = DAX'."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="TMDL No Source Test")
    files = dict(project.files)
    for path, content in files.items():
        if "DimCategory.tmdl" not in path:
            continue
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            # Remove the 'source = SELECTCOLUMNS(...)' line from the
            # calculated partition but keep the partition declaration
            # and 'mode: import'.
            if re.match(r"^\t\tsource\s*=\s*SELECTCOLUMNS", line):
                continue
            new_lines.append(line)
        files[path] = "\n".join(new_lines)
        break
    errors = validate_pbip(files)
    assert any("calculated partition" in error and "source" in error for error in errors), errors


def test_generated_tmdl_data_source_has_no_kind_property(sample_retail_df: pd.DataFrame):
    """Generated data source TMDL files must not contain 'kind: ...'.

    Power BI Desktop rejects 'kind' as an unsupported property in dataSource
    definitions: "Unsupported property - kind is not a supported property in
    the current context!"
    """
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="DS Kind Test")
    for path, content in project.files.items():
        if "/definition/dataSources/" not in path or not path.endswith(".tmdl"):
            continue
        for line_num, line in enumerate(content.splitlines(), start=1):
            assert not re.match(r"^\tkind\s*:", line), (
                f"{path}:{line_num}: invalid 'kind:' in data source: {line.strip()}"
            )


def test_generated_tmdl_data_source_has_no_source_property(sample_retail_df: pd.DataFrame):
    """Generated data source TMDL files must NOT have 'source = <M>'.

    Power BI Desktop rejects 'source' as an unsupported property in
    dataSource definitions: "The keyword 'source' is neither a property nor
    an object in the current context!"
    """
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="DS No Source Test")
    for path, content in project.files.items():
        if "/definition/dataSources/" not in path or not path.endswith(".tmdl"):
            continue
        has_source = any(re.match(r"^\t+\tsource\s*=\s*", line) for line in content.splitlines())
        assert not has_source, f"{path}: data source must not contain 'source = <M expression>'"


def test_generated_tmdl_data_source_has_no_mode_property(sample_retail_df: pd.DataFrame):
    """Generated data source TMDL files must not contain 'mode: ...'.

    'mode: import' belongs in the partition, not the data source.
    """
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="DS Mode Test")
    for path, content in project.files.items():
        if "/definition/dataSources/" not in path or not path.endswith(".tmdl"):
            continue
        for line_num, line in enumerate(content.splitlines(), start=1):
            assert not re.match(r"^\tmode\s*:", line), (
                f"{path}:{line_num}: invalid 'mode:' in data source: {line.strip()}"
            )


def test_generated_tmdl_fact_table_has_inline_m_expression(sample_retail_df: pd.DataFrame):
    """Fact table source partition must have an inline M expression."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="DS Inline M Test")
    files = project.files
    fact_tmdl = None
    for path, content in files.items():
        if path.endswith("/tables/FactSales.tmdl") or path.endswith("/tables/FactData.tmdl"):
            fact_tmdl = content
            break
    assert fact_tmdl is not None, "Fact table TMDL was not generated"
    assert re.search(r"^\tpartition\s+(FactSales|FactData)\s*=\s*m\s*$", fact_tmdl, re.MULTILINE), (
        "Fact table must use a TMDL M partition"
    )
    assert re.search(r"^\t+\tsource\s*=\s*Table\.PromoteHeaders\(Csv\.Document", fact_tmdl, re.MULTILINE), (
        "Fact table M partition must promote the serialized CSV headers"
    )
    ds_paths = [path for path in files if "/definition/dataSources/" in path and path.endswith(".tmdl")]
    assert ds_paths, "No data source definition files were generated"


def test_validate_pbip_rejects_kind_in_data_source(sample_retail_df: pd.DataFrame):
    """validate_pbip must flag 'kind: ...' in a data source definition."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="DS Invalid Kind Test")
    files = dict(project.files)
    for path, content in files.items():
        if "/definition/dataSources/" not in path or not path.endswith(".tmdl"):
            continue
        lines = content.splitlines()
        # Insert 'kind: File' after the dataSource declaration line
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if re.match(r"^dataSource\s+", line):
                new_lines.append("\tkind: File")
        files[path] = "\n".join(new_lines)
        break
    errors = validate_pbip(files)
    assert any("kind" in error and "not a supported property" in error for error in errors), errors


def test_validate_pbip_rejects_mode_in_data_source(sample_retail_df: pd.DataFrame):
    """validate_pbip must flag 'mode: ...' in a data source definition."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="DS Invalid Mode Test")
    files = dict(project.files)
    for path, content in files.items():
        if "/definition/dataSources/" not in path or not path.endswith(".tmdl"):
            continue
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if re.match(r"^dataSource\s+", line):
                new_lines.append("\tmode: import")
        files[path] = "\n".join(new_lines)
        break
    errors = validate_pbip(files)
    assert any("mode" in error and "not a supported property" in error for error in errors), errors


def test_validate_pbip_rejects_missing_data_source(sample_retail_df: pd.DataFrame):
    """validate_pbip must flag missing definition/dataSources/ directory."""
    project = build_pbip(sample_retail_df, infer_schema(sample_retail_df), project_name="DS Missing Test")
    files = dict(project.files)
    files = {path: content for path, content in files.items() if "/definition/dataSources/" not in path}
    errors = validate_pbip(files)
    assert any("data source" in error.lower() for error in errors), errors
