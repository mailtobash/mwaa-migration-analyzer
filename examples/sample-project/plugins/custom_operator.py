"""Sample custom operator plugin for Airflow.

This plugin demonstrates a simple custom operator that is compatible
with Amazon MWAA. It extends BaseOperator and follows standard patterns
for custom operator development.
"""

from airflow.models import BaseOperator
from airflow.utils.decorators import apply_defaults


class DataValidationOperator(BaseOperator):
    """Custom operator that validates data quality checks.

    This operator runs a set of validation rules against a dataset
    and reports results via XCom.

    Args:
        dataset_name: Name of the dataset to validate.
        validation_rules: List of validation rule names to apply.
        fail_on_error: Whether to fail the task if validation errors are found.
    """

    template_fields = ("dataset_name",)
    ui_color = "#e8f7e4"

    @apply_defaults
    def __init__(
        self,
        dataset_name: str,
        validation_rules: list[str] | None = None,
        fail_on_error: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.dataset_name = dataset_name
        self.validation_rules = validation_rules or ["not_null", "unique_id"]
        self.fail_on_error = fail_on_error

    def execute(self, context):
        """Execute data validation checks."""
        self.log.info(
            "Validating dataset '%s' with rules: %s",
            self.dataset_name,
            self.validation_rules,
        )

        results = {}
        errors = []

        for rule in self.validation_rules:
            passed = self._run_validation(rule)
            results[rule] = "PASSED" if passed else "FAILED"
            if not passed:
                errors.append(f"Validation rule '{rule}' failed for {self.dataset_name}")

        # Push results to XCom for downstream tasks
        context["ti"].xcom_push(key="validation_results", value=results)

        if errors and self.fail_on_error:
            raise ValueError(
                f"Data validation failed: {'; '.join(errors)}"
            )

        self.log.info("Validation complete: %s", results)
        return results

    def _run_validation(self, rule: str) -> bool:
        """Run a single validation rule. Override in subclasses for real logic."""
        self.log.info("Running validation rule: %s", rule)
        # Placeholder — in a real implementation, this would query the dataset
        return True
