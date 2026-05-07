"""Complex DAG with MWAA compatibility issues.

This DAG intentionally uses patterns that are incompatible with Amazon MWAA
to demonstrate the analyzer's detection capabilities. Issues include:
- SubDagOperator usage (deprecated)
- Local filesystem paths for data exchange
- Direct metadata database access
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.subdag import SubDagOperator
from airflow.settings import Session
from airflow.models import DagRun

default_args = {
    "owner": "data-team",
    "depends_on_past": True,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def create_subdag(parent_dag_id, child_dag_id, args):
    """Create a sub-DAG for parallel processing (deprecated pattern)."""
    subdag = DAG(
        dag_id=f"{parent_dag_id}.{child_dag_id}",
        default_args=args,
        schedule_interval=timedelta(days=1),
        start_date=datetime(2024, 1, 1),
    )

    for i in range(3):
        BashOperator(
            task_id=f"subtask_{i}",
            bash_command=f"echo 'Processing partition {i}'",
            dag=subdag,
        )

    return subdag


def write_to_local_filesystem(**context):
    """Write intermediate results to local filesystem (incompatible with MWAA)."""
    output_path = "/tmp/airflow_intermediate_results.csv"
    with open(output_path, "w") as f:
        f.write("id,value\n")
        f.write("1,100\n")
        f.write("2,200\n")
    print(f"Wrote results to {output_path}")
    return output_path


def read_from_local_path(**context):
    """Read data from a hardcoded local path (incompatible with MWAA)."""
    input_path = "/data/shared/daily_export.csv"
    print(f"Reading from {input_path}")


def query_metadata_db(**context):
    """Query the Airflow metadata database directly (incompatible with MWAA)."""
    session = Session()
    recent_runs = session.query(DagRun).filter(
        DagRun.execution_date >= datetime(2024, 1, 1)
    ).all()
    print(f"Found {len(recent_runs)} recent DAG runs")
    session.close()


with DAG(
    dag_id="complex_problematic_dag",
    default_args=default_args,
    description="A DAG with MWAA compatibility issues for testing",
    schedule_interval=timedelta(days=1),
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example", "problematic"],
) as dag:

    start = BashOperator(
        task_id="start",
        bash_command="echo 'Starting complex pipeline'",
    )

    # SubDagOperator usage - deprecated, should use TaskGroups instead
    parallel_processing = SubDagOperator(
        task_id="parallel_processing",
        subdag=create_subdag("complex_problematic_dag", "parallel_processing", default_args),
    )

    # Writing to local filesystem - not available in MWAA
    write_local = PythonOperator(
        task_id="write_to_local",
        python_callable=write_to_local_filesystem,
    )

    # Reading from hardcoded local path - not available in MWAA
    read_local = PythonOperator(
        task_id="read_from_local",
        python_callable=read_from_local_path,
    )

    # Direct metadata DB access - not allowed in MWAA
    check_metadata = PythonOperator(
        task_id="check_metadata",
        python_callable=query_metadata_db,
    )

    end = BashOperator(
        task_id="end",
        bash_command="echo 'Pipeline complete'",
    )

    start >> parallel_processing >> write_local >> read_local >> check_metadata >> end
