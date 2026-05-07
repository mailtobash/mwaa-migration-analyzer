# Examples

This directory contains a sample Airflow project that you can use to test the MWAA Analyzer without connecting to a real Airflow environment.

## Sample Project

The `sample-project/` directory simulates a typical Airflow project structure with:

- **`dags/`** — Example DAG files
  - `example_dag.py` — A simple, MWAA-compatible DAG using standard operators (BashOperator, PythonOperator)
  - `complex_dag.py` — A DAG with several MWAA compatibility issues (SubDagOperator usage, local filesystem paths, direct metadata DB access) to demonstrate the analyzer's detection capabilities
- **`plugins/`** — Custom Airflow plugins
  - `custom_operator.py` — A sample custom operator plugin
- **`requirements.txt`** — Python dependencies (includes both compatible and problematic packages)
- **`airflow.cfg`** — Airflow configuration file (includes both supported and unsupported keys)

## Running the Analyzer Against the Sample Project

After completing setup, run the analyzer against the sample project using the filesystem source type:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project
```

This will produce a compatibility report highlighting issues found in the sample project, including:

- Deprecated SubDagOperator usage in `complex_dag.py`
- Local filesystem path references in DAGs
- Direct metadata database access patterns
- Unsupported configuration keys in `airflow.cfg`
- Dependency version conflicts and incompatible packages in `requirements.txt`

## Using Examples as a Reference

These examples are useful for:

1. **Verifying your setup** — Confirm the analyzer runs correctly before pointing it at your own project
2. **Understanding findings** — See what types of issues the analyzer detects and how they are reported
3. **Learning patterns** — Compare `example_dag.py` (compatible) with `complex_dag.py` (problematic) to understand MWAA best practices
