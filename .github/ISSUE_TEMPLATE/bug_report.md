---
name: Bug report
about: Something in the API, CLI, parsers or ingestion is wrong
labels: bug
---

**What happened**

<!-- What you ran and what you got. -->

**What you expected**

<!-- For data issues: what the CNMV notice actually declares
     (registration number + filing date help a lot). -->

**Reproduction**

```python
# minimal code / CLI command
```

**Environment**

- ownership-radar version (`ownership-radar --version`):
- dataset (`radar.dataset_info()` / `ownership-radar dataset-info`):
- Python version:
- OS:

**Notes**

- Never attach raw CNMV documents to the issue (see
  DATA-NOTICE.md) — cite registration numbers instead.
- If the bug is a wrong value rather than a crash, include the
  notice_key and the field.
