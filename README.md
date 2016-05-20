# csvcmp
A small tool for comparing Lantern CSVs

# How to run

The overall format is

    ./csvcmp.py first_csv_to_compare second_csv_to_compare --original-file file_both_csvs_were_derived_from

The two CSVs to compare are Lantern analysis result files. The "original file" is the file originally uploaded to the Lantern instances.

The output is a CSV with one or more sections, focussing on the differences within one column at a time:

    column in first.csv, same column in second.csv, PMCID from original file, PMID from original, DOI from original, Title from original
    # ... some differences

    another column in first.csv, the same column in second.csv, (... the 4 identifying columns from the original CSV ...)

    # and so on.

As you can see, the original file is used to supply information on the identifiers of the articles which were found to have different values. Columns 3-6 can essentially be copy-pasted as they are into a new CSV, for easy re-running in the two Lantern instances being compared.

There is an additional output: suspicious records. Those rows which had no identifier in common (PMCID, PMID, DOI) are regarded as suspicious - i.e. perhaps the same row describes a totally different article in the two result files. If there are less than 50 suspicious records, these will be output to the screen. For more than 50 another CSV will be written.

# Example

The command

    ./csvcmp.py apc_2012_2013_results.csv processed_apc_2012_2013.csv --original-file apc_2012_2013.csv

was used on the files in the example/ directory in order to produce the results

    example/apc_2012_2013_results.csv_comparison_processed_apc_2012_2013.csv.csv
    example/apc_2012_2013_results.csv_suspicious_processed_apc_2012_2013.csv.csv

# Configuration

The script supports two config options at the moment, WHITELIST_COLUMNS and EXPECTED_HEADER_DIFFERENCES_RAW.

If WHITELIST_COLUMNS is set, then all column names which are not in that list will be deleted from the 2 CSVs to be compared prior to comparison.

If EXPECTED_HEADER_DIFFERENCES_RAW is set, then it describes alternative names for columns which are in the same position in both CSV files being compared. E.g. "AAM?" and "Author Manuscript?" have the same meaning, but must also be in the same position in both files.

You can set settings for all files in settings.json in the directory of the script.

You can set per-csv settings by saving them as [original_filename].json . So if comparing `1.csv` to `2.csv` with `--original-file apc_2012_2013.csv`, you could write a specific whitelist in `apc_2012_2013.csv.json` in the script's directory.