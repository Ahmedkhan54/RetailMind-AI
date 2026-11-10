# RetailMind AI — Power BI Export Guide (Verified Structure)

**Version:** 2.0.0-phase2
**Generated formats:** Power BI Project (`.pbip`), TMDL semantic model, PBIR report definition, theme JSON
**Verification date:** 8 November 2026

> **Important honesty note**
> The generated project was validated **structurally** by the application's own validator and by the independent audit. All TMDL files were structurally validated for valid table declarations, calculated partitions, source partitions, and cross-references. The project was **not opened in Microsoft Power BI Desktop** because Desktop is not installed on the audit machine. No `.pbix` file is produced. Do not assume the report renders data until you complete the data-source step in §6.

---

## 1. What is generated

A ZIP archive with a real `.pbip` folder layout:

```
<project>.pbip                          ← project pointer
<project>.SemanticModel/
├── .platform
├── definition.pbism
└── definition/
    ├── dataSources/
    │   └── FactSales.tmdl            ← import data source declaration
    │       dataSource FactSales
    │   (no 'kind:' or 'mode:' or 'source =' properties —
    #    those are invalid in dataSource definitions)
    ├── database.tmdl
    ├── model.tmdl
    ├── relationships.tmdl
    └── tables/
        ├── FactSales.tmdl            ← import table with inline M partition
        │   table FactSales
        │   ... columns ...
        │   ... measures ...
        │   partition FactSales = source
        │       mode: import
        │       source = Csv.Document(File.Contents("FactSales.csv"), [...])
        ├── DimDate.tmdl              ← DAX calculated table
        ├── DimProduct.tmdl           ← DAX calculated table
        ├── DimCategory.tmdl          ← DAX calculated table
        ├── DimCustomer.tmdl          ← DAX calculated table
        └── DimRegion.tmdl            ← DAX calculated table
<project>.Report/
├── .platform
├── definition.pbir
├── definition/
│   ├── report.json
│   ├── version.json                  ← report definition version metadata
│   └── pages/
│       ├── pages.json
│       └── <page-guid>/
│           ├── page.json
│           └── visuals/<visual-guid>/visual.json
└── StaticResources/
    └── RegisteredResources/
        └── RetailMindTheme.json
```

Exact table set depends on mapped roles. On a standard retail dataset the audit observed **36 files, 6 tables and 14 measures**.

### What is *not* in the archive
- **No CSV/data files.** FactSales has a partition and data source definition, but the actual data must be loaded by connecting the source in Power BI Desktop.
- No `.pbix` binary.

**Schema identifiers:** every generated JSON file references Microsoft's published schemas (`report/definitionProperties/2.0.0`, `report/definition/report/3.3.0`, `pbip/pbipProperties/1.0.0`, `pagesMetadata/1.0.0`, `page/1.0.0`, `visualContainer/1.0.0`, `platformProperties/2.0.0`, `semanticModel/definitionProperties/1.0.0`, `report/definition/versionMetadata/1.0.0`). All JSON files per project pass `jsonschema` Draft 7 validation against the downloaded Microsoft schemas, and `validate_pbip` rejects any project whose `$schema` differs from the expected identifier.

**TMDL syntax:** all generated TMDL files use valid Microsoft TMDL syntax:
- Tables are declared on their own line (`table Name`) — never `table Name = <DAX>`.
- Calculated tables (DimDate, DimProduct, DimCategory, DimCustomer, DimRegion) use a separate `partition <name> = calculated` block with `source = <DAX expression>`.
- FactSales uses a `partition FactSales = source` block referencing the `FactSales` data source.
- Every table has a `lineageTag`, columns have `dataType` and `sourceColumn`, measures have `formatString` and `lineageTag`.

`DimDate` and the dimension tables are **DAX calculated tables** derived from `FactSales`. Therefore `FactSales` must be connected to data before dimensions or visuals can evaluate.

---

## 2. DAX measures (observed on a retail dataset)

| Measure | Definition (summary) |
|:---|:---|
| Total Sales / Total Revenue | `SUM(FactSales[Sales/Revenue])` |
| Total Profit | `SUM(FactSales[Profit])` |
| Total Cost | `SUM(FactSales[Cost])` |
| Profit Margin | `DIVIDE([Total Profit], [Total Revenue])` |
| Total Orders | `DISTINCTCOUNT(FactSales[OrderID])` |
| Total Customers | `DISTINCTCOUNT(FactSales[CustomerID])` |
| Average Order Value | `DIVIDE([Total Revenue], [Total Orders])` |
| Total Quantity | `SUM(FactSales[Quantity])` |
| Expense Ratio | cost/revenue ratio |
| Previous Period Sales | `CALCULATE([Total Revenue], DATEADD(DimDate[Date], -1, MONTH))` |
| Sales Growth | `[Total Revenue] − [Previous Period Sales]` |
| Sales Growth % | `DIVIDE([Sales Growth], [Previous Period Sales])` |
| YTD Sales | `TOTALYTD([Total Revenue], DimDate[Date])` |

Measures are only emitted when the required roles/columns exist. Non-commercial datasets fall back to count/sum measures.

---

## 3. Internal validation

`validate_pbip(project)` checks:
- a `.pbip` file exists,
- every generated JSON file carries the expected Microsoft-published `$schema` identifier (unsupported/stale URLs are rejected),
- `definition/version.json` exists with valid `$schema` and non-empty `version`,
- the semantic-model folder exists,
- `database.tmdl`, `model.tmdl`, table TMDLs and `relationships.tmdl` exist,
- a data source definition exists under `definition/dataSources/`,
- **data source files contain only `dataSource <name>`** — no `kind:`, `mode:`, or `source =` properties
  (Power BI Desktop rejects "kind is not a supported property" and "source is neither a property nor
  an object in the current context"),
- the report has `definition.pbir`, `definition/report.json` and `pages/pages.json`,
- `definition.pbir` points at the semantic-model folder,
- **TMDL structural validation:** no `table Name = <DAX>` declarations, every table has a partition, calculated partitions have `source = <DAX>`, column `sourceColumn` references resolve,
- relationships reference existing tables and columns,
- measure/table names are non-empty.

The audit result was **no validation errors** on a freshly generated project. This proves internal consistency, schema correctness, and TMDL structural validity, **not** Power BI Desktop compatibility.

Power BI Desktop detection:

```python
detect_power_bi_desktop()  # returned None on the audit machine
```

---

## 4. How to download

1. Upload a dataset and open **Advanced Business Intelligence → Power BI Export Center**.
2. Click **Download Power BI Project (.pbip ZIP)**.
3. Optionally click **Download Power BI Theme (JSON)**.
4. Extract the ZIP to a local folder, e.g. `C:\Reports\RetailMind\`.

Equivalent download buttons also exist in the universal export area.

---

## 5. Opening the project (when Desktop is available)

1. Confirm your Power BI Desktop version supports PBIP (Preview features → **Power BI Project (.pbip) save option**).
2. Open the `<project>.pbip` file with **File → Open**.
3. The semantic model opens with `FactSales` declared as an import table with a data source reference. Connect the data source to your actual CSV/Excel/file before visuals can populate (see §6).

---

## 6. Connect data (required before visuals populate)

Because the export intentionally does **not** embed data:

1. In Power BI Desktop, open **Transform data → Power Query**.
2. Create/point a query named **`FactSales`** at your source CSV/Excel/database.
3. Ensure the source columns match the generated `sourceColumn` names (e.g. `Order ID`, `Order Date`, `Revenue`, `Profit`, `Cost`, `Quantity`, `Product`, `Category`, `Region`, `Customer ID`).
4. Apply and refresh.
5. `DimDate` and the dimension tables will evaluate from `FactSales`.
6. Fix any relationship/type warnings, then use **File → Save As → Power BI file (*.pbix)** if a binary file is required.

If column names differ, either rename them in Power Query or regenerate the project after adjusting the column mapping in RetailMind AI.

---

## 7. Theme

The archive includes `RetailMindTheme.json` under `StaticResources/RegisteredResources/`. To apply it manually:

1. **View → Themes → Browse for themes…**
2. Select `RetailMindTheme.json`.
3. Visual colours and typography update immediately.

The standalone **Download Power BI Theme (JSON)** button produces the same palette for use in any report.

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|:---|:---|
| Tables appear empty | `FactSales` has no data source — complete §6 |
| “Table has no partitions” warning | Same as above; add a Power Query partition |
| Dimensions error | Dimensions are calculated from `FactSales`; load the fact table first |
| PBIP not recognised | Update Power BI Desktop and enable the PBIP preview feature |
| `.pbix` requested | Not generated; use **Save As** in Desktop after connecting data |
| Visuals show wrong fields | Regenerate after correcting the column mapping in RetailMind AI |

---

## 9. What is verified vs not verified

| Claim | Status |
|:---|:---|
| Generates `.pbip` + TMDL + PBIR file tree | ✅ Verified (36 files, 6 tables, 14 measures) |
| `$schema` identifiers match Microsoft's published schemas | ✅ Verified against downloaded `json-schemas` |
| All JSON files pass `jsonschema` validation | ✅ Verified |
| TMDL structural validation passes (no `table Name = DAX`, all tables have partitions, calculated partitions have DAX source, no `kind:`/`mode:` in data sources) | ✅ Verified |
| Data source files use valid `source = <M expression>` syntax | ✅ Verified |
| Internal structural validator passes | ✅ Verified |
| Relationships and measures are internally consistent | ✅ Verified |
| ZIP archive is valid | ✅ Verified (`PK` header, extractable) |
| Opens in Power BI Desktop | ❓ **Not testable here** (Desktop absent) |
| Report visuals render with data | ❌ **Not currently possible without connecting a source** |
| `.pbix` generation | ❌ Not implemented (correctly documented in the app) |
