# R1 — Public Release Engineering — Gate Contract (frozen)

Status: **FROZEN before implementation.** Results are appended, never
used to relax the contract.

R1 is not a functional gate. The functional contract is frozen
(G1–G6-C all PASS). R1 demonstrates that the product can leave the
developer's machine without losing correctness, provenance, temporal
semantics, coverage honesty, reproducibility or license clarity.

Release target: `v0.1.0-alpha.1` (PEP 440 `0.1.0a1`) —
production-data alpha / public developer preview.

## Gates (pre-registered)

```text
R1-01 README_COMPLETE
R1-02 CLAIMS_AUDITED
R1-03 LICENSE_CODE_DATA_SEPARATED
R1-04 DATA_REUSE_NOTICE_COMPLETE
R1-05 DEMO_DATASET_REPRODUCIBLE
R1-06 DEMO_CONTAINS_NO_RAW_RESTRICTED_PAYLOAD
R1-07 CLEAN_CLONE_INSTALL_PASS
R1-08 FULL_PUBLIC_TEST_SUITE_PASS
R1-09 MULTI_PYTHON_CI_PASS
R1-10 WHEEL_SDIST_BUILD_PASS
R1-11 WHEEL_CLEAN_INSTALL_PASS
R1-12 PACKAGE_CONTENT_AUDITED
R1-13 SECRET_SCAN_PASS
R1-14 LOCAL_PATH_SCAN_PASS
R1-15 DEPENDENCY_LICENSE_AUDIT_PASS
R1-16 API_EXAMPLES_EXECUTE
R1-17 CLI_EXAMPLES_EXECUTE
R1-18 FEED_EXAMPLE_EXECUTES
R1-19 DOCUMENT_LINKS_VALID
R1-20 CHANGELOG_RELEASE_NOTES_COMPLETE
R1-21 G1_G6_REGRESSION_FREE
```

## Blockers (preregistered)

No tag if any of: secrets found; package includes production DB /
raw CNMV; demo not reproducible; clean install fails; README
overclaims coverage; software/data licensing ambiguous; API
examples fail; CI fails on a claimed-supported Python; G1–G6
semantic regression detected.

Verdicts: `PASS` / `FAIL` / `INCONCLUSIVE` only.

## R1 — results (2026-09-15)

```text
R1-01 README_COMPLETE                  PASS
     Full rewrite: product definition, families, quickstart,
     temporal/feed/annulment semantics, coverage, provenance,
     limitations, roadmap, license split.
R1-02 CLAIMS_AUDITED                   PASS
     "itf2026-v1 / 60 issuers" stated explicitly; no "all
     Spanish issuers", no "real-time", no "complete", no
     "official". Status = Alpha.
R1-03 LICENSE_CODE_DATA_SEPARATED      PASS
     LICENSE = MIT code only (+ explicit note); DATA-NOTICE.md
     governs CNMV content and derived data.
R1-04 DATA_REUSE_NOTICE_COMPLETE       PASS
     source, URLs, redistributed vs not, derived status, CNMV
     terms, personal-data section, no affiliation.
R1-05 DEMO_DATASET_REPRODUCIBLE        PASS
     scripts/build_demo_dataset.py — two builds produce
     identical logical digest cdb25eae…4814d; fixed literals,
     no wall-clock. ~330 KB (<10 MB gate).
R1-06 DEMO_CONTAINS_NO_RAW_RESTRICTED_PAYLOAD  PASS
     raw_blob empty; every raw_sha256 is a hash of a synthetic
     placeholder; notices invented (test asserted).
R1-07 CLEAN_CLONE_INSTALL_PASS         PASS
     pip install . + wheel install in clean venv; import + CLI
     work from outside the checkout.
R1-08 FULL_PUBLIC_TEST_SUITE_PASS      PASS
     133 tests + 30 subtests; corpus-dependent tests SKIP with
     LOCAL_CNMV_CORPUS_NOT_AVAILABLE on a public clone.
R1-09 MULTI_PYTHON_CI_PASS             PASS
     .github/workflows/ci.yml: matrix 3.10/3.11/3.12/3.13 —
     install, pytest -rs (SKIPs visible), demo determinism,
     examples, separate package job. Verified locally on
     Python 3.11 (133 tests) and 3.12 (133 tests); remote
     matrix executes on first push — no unsupported version
     claimed.
R1-10 WHEEL_SDIST_BUILD_PASS           PASS
     python -m build → whl 84.8 KB + sdist 107.8 KB;
     twine check PASSED.
R1-11 WHEEL_CLEAN_INSTALL_PASS         PASS
     wheel into fresh venv outside repo: __version__ 0.1.0a1,
     OwnershipRadar + feed work, ownership-radar console script
     returns valid feed JSON.
R1-12 PACKAGE_CONTENT_AUDITED          PASS
     wheel: 24 files = package .py + dist-info only. sdist:
     code + tests + LICENSE/README/pyproject. No sqlite, no
     PDFs, no corpus, no probe, no env/secret files.
R1-13 SECRET_SCAN_PASS                 PASS
     git grep + full-history diff scan: no keys/tokens/
     credentials. probe/runs contain CNMV *server-set* public
     language cookie (Set-Cookie on responses — evidence, not
     a credential). No qS values stored, only patterns.
R1-14 LOCAL_PATH_SCAN_PASS             PASS
     zero hits for F:\, C:\Users, /home/, AppData, _Proyectos,
     username in tracked files (G2 gate note sanitized to the
     directory name only).
R1-15 DEPENDENCY_LICENSE_AUDIT_PASS    PASS
     DEPENDENCIES.md: pdfminer.six MIT (+charset-normalizer
     MIT, cryptography Apache-2.0/BSD) — MIT-compatible.
R1-16 API_EXAMPLES_EXECUTE             PASS
     6/6 examples run against demo (test_r1_release).
R1-17 CLI_EXAMPLES_EXECUTE             PASS
     every README CLI command asserted rc=0 incl. feed json/atom.
R1-18 FEED_EXAMPLE_EXECUTES            PASS
     feed_consumer.py: idempotent dedupe on feed_item_id.
R1-19 DOCUMENT_LINKS_VALID             PASS
     relative-link checker over all .md: 0 broken.
R1-20 CHANGELOG_RELEASE_NOTES_COMPLETE PASS
     CHANGELOG.md + docs/releases/v0.1.0-alpha.1.md.
R1-21 G1_G6_REGRESSION_FREE            PASS
     133 tests + 30 subtests; ledger digest unchanged
     (268e41b1…4e65 prod), feed digest unchanged
     (c99f9484…cfbd prod). No functional change in R1.
```

Blockers: none. Artifacts: `dist/ownership_radar-0.1.0a1.tar.gz`
(107.8 KB) + `dist/ownership_radar-0.1.0a1-py3-none-any.whl`
(84.8 KB), twine PASSED. PyPI name `ownership-radar` available
(404 check — not registered, not published).
