# PLC version-control

Version control for Rockwell PLC programs. Parses Studio 5000 L5X
exports into structured data so changes can be tracked and compared.

## What it does

- Reads an L5X export and pulls out controller settings, I/O modules, data types, AOIs, tags,
  programs, routines, and tasks
- Parses ladder logic rungs and Structured Text into syntax trees
- Returns plain Python objects (Pydantic models) that can be dumped
  to JSON with a single call

## Getting started

Needs Python 3.10+.

```
pip install -r requirements.txt
```

```python
from parsers.l5x import L5XParser

doc = L5XParser().parse_file("MyProject.L5X")
print(doc.controller.name)
```

To run the tests: `pip install -r requirements-dev.txt`, then `pytest`.

## Roadmap

- [ ] Diff engine
- [ ] Change history
- [ ] FBD and SFC routines
