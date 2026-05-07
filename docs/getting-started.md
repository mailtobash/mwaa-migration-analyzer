# Getting Started

## Prerequisites

- **Python 3.11+** — required for running the analyzer
- **git** — to clone the repository
- **AWS credentials** — required only when using the `mwaa` source type (configured via the standard AWS credential chain)

## Setup

Clone the repository and run the setup script:

```bash
git clone <repository-url>
cd mwaa-analyzer-agent
./scripts/setup.sh
```

This creates a Python virtual environment at `.venv/` and installs all runtime dependencies.

## First Analysis Run

Run an analysis against the included sample project:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project
```

This produces a Markdown migration report on stdout covering DAGs, dependencies, configuration, and plugins found in the sample project.

## Next Steps

- See [Usage Guide](usage-guide.md) for all CLI options and source types
- See [Architecture](architecture.md) for system design details
- See [Troubleshooting](troubleshooting.md) if you encounter issues
