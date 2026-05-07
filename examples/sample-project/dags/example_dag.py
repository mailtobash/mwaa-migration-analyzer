"""Example DAG demonstrating MWAA-compatible patterns.

This DAG uses standard operators and follows best practices for
Amazon MWAA compatibility. It should produce no compatibility findings
when analyzed.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def process_data(**context):
    """Process data using XCom for inter-task communication."""
    execution_date = context["execution_date"]
    print(f"Processing data for {execution_date}")
    # Use XCom to pass data between tasks (MWAA-compatible pattern)
    context["ti"].xcom_push(key="record_count", value=42)


def report_results(**context):
    """Generate a summary report from upstream task results."""
    ti = context["ti"]
    record_count = ti.xcom_pull(task_ids="process_data", key="record_count")
    print(f"Processed {record_count} records successfully")


with DAG(
    dag_id="example_compatible_dag",
    default_args=default_args,
    description="A simple MWAA-compatible DAG",
    schedule_interval=timedelta(days=1),
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example", "compatible"],
) as dag:

    start = EmptyOperator(task_id="start")

    extract = BashOperator(
        task_id="extract_data",
        bash_command="echo 'Extracting data from source...'",
    )

    process = PythonOperator(
        task_id="process_data",
        python_callable=process_data,
    )

    report = PythonOperator(
        task_id="report_results",
        python_callable=report_results,
    )

    end = EmptyOperator(task_id="end")

    start >> extract >> process >> report >> end
