## What and why

<!-- One paragraph: what changed and the reason. Link the issue. -->

## Semantic impact

<!-- Does this change parsed values, ledger derivations, feed items,
     or the public contract? If yes: which versions were bumped
     (semantic_parser_version / DERIVATION_VERSION / schema)? -->

## Verification

- [ ] `ruff check .` passes
- [ ] `python -m pytest tests/` passes
- [ ] New behaviour is covered by a regression test
- [ ] No raw CNMV documents or personal data added
      (see DATA-NOTICE.md)
- [ ] Docs updated where behaviour changed
