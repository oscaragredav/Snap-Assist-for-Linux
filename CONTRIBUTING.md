# Contributing

Use Python 3.11 or newer. Create a virtual environment, then install and check
the project with:

```bash
python -m pip install -e '.[dev]'
python -m compileall -q snapassist tests
ruff check snapassist tests
pytest
```

State and X11 operations belong to the daemon event-loop thread. Tkinter must
communicate through queues and every UI response must preserve its `flow_id`.
Tests that require a real X server should be clearly separated from pure unit
tests and include reproducible manual steps.
