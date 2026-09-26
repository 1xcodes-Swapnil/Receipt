# Escalate Demo Repository

A Python module with no test files. Used to trigger ESCALATE verdict.

## Installation

No installation required for demo purposes.

## Usage

```python
from data_processing import process, summarise
```

This repository intentionally has NO test files. The TestRunner agent
will find nothing to execute and returns INSUFFICIENT_EVIDENCE, causing
the overall verdict to be ESCALATE.
