# Troubleshooting

## Common Issues

### Import Errors

**Symptom:** `ModuleNotFoundError: No module named 'models'` or similar import errors.

**Cause:** The `PYTHONPATH` is not set to include the `src/` directory.

**Solution:** Always use the provided scripts to run the analyzer:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project
```

If you need to invoke Python directly, set `PYTHONPATH` first:

```bash
export PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"
.venv/bin/python -m cli analyze --source-type filesystem --path ./examples/sample-project
```

### Virtual Environment Not Found

**Symptom:** `Error: Virtual environment not found at .venv`

**Cause:** The setup script has not been run yet.

**Solution:**

```bash
./scripts/setup.sh
```

### Credential Issues

**Symptom:** `Error: --endpoint (or AIRFLOW_API_ENDPOINT env var) is required when --source-type is 'api'`

**Cause:** Required credentials are not provided via CLI flags or environment variables.

**Solution for API source type:**

```bash
export AIRFLOW_API_ENDPOINT=https://your-airflow.example.com/api/v1
export AIRFLOW_API_TOKEN=your-token-here
./scripts/run.sh analyze --source-type api
```

**Solution for MWAA source type:**

```bash
export MWAA_ENVIRONMENT_NAME=your-environment-name
export MWAA_REGION=us-east-1
./scripts/run.sh analyze --source-type mwaa
```

### AWS Credential Chain Issues (MWAA Source Type)

**Symptom:** `botocore.exceptions.NoCredentialsError` or `ExpiredTokenException`

**Cause:** AWS credentials are not configured or have expired.

**Solution:** Ensure valid AWS credentials are available through one of:

- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`)
- AWS credentials file (`~/.aws/credentials`)
- IAM instance role (when running on EC2/ECS)
- AWS SSO session (`aws sso login`)

Verify credentials are working:

```bash
aws sts get-caller-identity
```

### Connectivity Problems

**Symptom:** `TimeoutError` or `ConnectionError` when using `api` or `mwaa` source types.

**Cause:** The target endpoint is unreachable due to network configuration, firewalls, or incorrect URLs.

**Solutions:**

- Verify the endpoint URL is correct and accessible from your network
- Check that any VPN or proxy is properly configured
- For MWAA, ensure your IAM permissions include `airflow:GetEnvironment` and related actions
- Increase timeout by checking network connectivity: `curl -v <endpoint-url>`

## FAQ

**Q: Can I run the analyzer without the scripts?**

Yes, but you must set `PYTHONPATH` to include the `src/` directory. See the "Import Errors" section above.

**Q: What Python version is required?**

Python 3.11 or later.

**Q: How do I disable telemetry?**

Set the environment variable before running:

```bash
export MWAA_ANALYZER_TELEMETRY_OPT_OUT=true
```

**Q: Where are analysis reports saved?**

By default, reports are printed to stdout. Use `--output-file` to save to a file:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project --output-file report.md
```

**Q: What MWAA versions are supported as targets?**

Currently `2.10.3`. Available versions are determined by the JSON files in `data/compatibility/`.

**Q: How do I run the tests?**

```bash
./scripts/test.sh
```

This automatically installs dev dependencies if needed and runs the full test suite.
