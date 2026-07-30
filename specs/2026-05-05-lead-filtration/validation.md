# Validation: Lead Filtration & Format Conversion

## Automated Validation
- [ ] **Type Check:** `mypy filter_leads.py` passes without errors.
- [ ] **Linting:** `ruff check .` passes.
- [ ] **Unit Tests:**
    - [ ] `test_contact_filter`: verify leads without phones are dropped when required.
    - [ ] `test_rating_filter`: verify threshold logic.
    - [ ] `test_category_filter`: verify both primary and secondary category matching.
    - [ ] `test_deduplication`: verify multiple records with same `place_id` result in one output.
- [ ] **Export Integrity:** Verify that `df.to_excel` produces a valid file that can be read back via `pd.read_excel`.

## Manual Validation
- [ ] **Interactive Flow:** Run `python filter_leads.py --interactive` and verify all prompts are intuitive.
- [ ] **CLI Flow:** Run `python filter_leads.py --min-rating 4.5 --require-email` and verify it skips prompts and applies filters.
- [ ] **Excel Review:** Open the generated `.xlsx` in Excel/LibreOffice.
    - [ ] Columns are correctly named.
    - [ ] No nested JSON strings are visible in cells (should be flattened or joined strings).
    - [ ] Special characters (UTF-8) are preserved.
- [ ] **Empty State:** Verify the script handles a case where 0 leads match the criteria without crashing.

## Definition of Done
1.  `filter_leads.py` is functional and supports all requested filters.
2.  Pandas and openpyxl are added to `requirements.txt`.
3.  Successful export to JSONL, CSV, and XLSX confirmed.
4.  Documentation (this spec) is complete and committed to the branch.
