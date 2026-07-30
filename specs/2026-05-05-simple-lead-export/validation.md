# Validation — Simple Lead Export

## Automated Validation
- [ ] Run `python export_leads.py [sample_file].json` and check for 0 exit code.
- [ ] Verify both `.csv` and `.xlsx` files exist in the target directory.
- [ ] Verify column names are flattened (e.g., no dictionary/list strings in cells).
- [ ] Verify that a column known to be empty in the source (e.g., `contact_email` if none exist) is NOT present in the output.

## Manual Validation
- [ ] Open the `.xlsx` file in Excel/LibreOffice to ensure formatting is correct.
- [ ] Open the `.csv` file in a text editor to verify the delimiter and encoding (UTF-8).
- [ ] Test with the `--output-dir` argument to ensure files land in the correct location.
- [ ] Test with a file that has different levels of nesting.

## Definition of Done
- Script `export_leads.py` is fully functional.
- Documentation/Help text is clear.
- All requested features (flattening, pruning, naming, formats) are implemented and verified.
