# etelemetry

Lightweight version-check telemetry service and client library.

## Client Installation

```bash
pip install etelemetry
```

## Usage

```python
import etelemetry

# Check for updates
etelemetry.check_available_version("org/project", "1.0.0")

# Direct version query
result = etelemetry.get_project("org/project")
```

See [docs/external-setup-guide.md](docs/external-setup-guide.md) for server deployment.
