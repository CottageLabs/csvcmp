#!/usr/bin/env python
import csv
import json
import sys
import os
import argparse
import logging
from collections import OrderedDict
import traceback
import codecs
import cStringIO

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s :: %(message)s')

DEFAULT_RESULTS_FILENAME = '{}_comparison_{}.csv'


def load_unicode(filename):
    with codecs.open(filename, 'rb', encoding='utf-8') as f:
        content = f.read()
    return content


class UTF8Recoder:
    """
    Iterator that reads an encoded stream and reencodes the input to UTF-8
    """
    def __init__(self, f, encoding):
        self.reader = codecs.getreader(encoding)(f)

    def __iter__(self):
        return self

    def next(self):
        return self.reader.next().encode("utf-8")


class UnicodeReader:
    """
    A CSV reader which will iterate over lines in the CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        f = UTF8Recoder(f, encoding)
        self.reader = csv.reader(f, dialect=dialect, **kwds)

    def next(self):
        row = self.reader.next()
        return [unicode(s, "utf-8") for s in row]

    def __iter__(self):
        return self


class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([unicode(s).encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def loadcsv(filename, ignore_blank_rows=True):
    def _is_empty(row):
        return sum([1 if c is not None and c != "" else 0 for c in row]) == 0

    r = []
    for row in UnicodeReader(open(filename, 'rb')):
        if ignore_blank_rows:
            if _is_empty(row):
                continue
        r.append(row)
    return r


def savecsv(filename, list_of_lists):
    with open(filename, 'wb') as o:
        csvwriter = UnicodeWriter(o)
        csvwriter.writerows(list_of_lists)


def normalise(val):
    return val.strip().lower()


def pmcid_cmp(a_val, b_val):
    n_a_val = normalise(a_val)
    n_b_val = normalise(b_val)
    if n_a_val.startswith('pmc'):
        n_a_val = n_a_val[3:]
    if n_b_val.startswith('pmc'):
        n_b_val = n_b_val[3:]
    return n_a_val == n_b_val

CMP_TRANSFORMS = {}


def cmpcell(cell_num, a_val, b_val):

    if cell_num in CMP_TRANSFORMS:
        return CMP_TRANSFORMS[cell_num](a_val, b_val)
    else:
        return normalise(a_val) == normalise(b_val)


def delete_column(csv_contents, col):
    """
    Delete a column from a CSV.

    :param csv_contents: list of lists, as returned by `csv` core lib.
    :param col: string with column name or integer showing which cell to delete from each csv row
    """
    if isinstance(col, int):
        colindex = col
    elif isinstance(col, basestring):
        header_row = csv_contents[0]
        try:
            colindex = header_row.index(col)
        except ValueError as e:
            raise ValueError("Cannot delete column {} from CSV, it's not in the CSV header. Original error: \n\n {} \n {}".format(col, e.message, traceback.format_exc()))

    for row in csv_contents:
        if colindex > len(row):
            raise ValueError("Cannot delete cell {} from CSV, found a row which is not long enough. Either the CSV is not rectangular (rows have an inconsistent length) or you requested deleting a column which does not exist. Call stack: \n\n {}".format(colindex, traceback.format_exc()))
        row.pop(colindex)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("a", help="Path to first CSV file to compare. Results of analysis on the file passed as --original-file.")
    parser.add_argument("b", help="Path to second CSV file to compare. Results of analysis on the file passed as --original-file.")
    parser.add_argument(
            '-o', '--output-path',
            help="Path to comparison results CSV file that this script can write to. It will be overwritten. Default {}"
                .format(DEFAULT_RESULTS_FILENAME.format('FirstSheetFilename.csv', 'SecondSheetFilename.csv'))
    )
    parser.add_argument(
            '--original-file', required=True,
            help="Path to the original CSV file that the two positional arguments are derived from."
    )
    parser.add_argument(
            '--print-headers', action="store_true",
            help="Dump csv headers of the two CSVs to compare and the original. Headers are printed after processing whitelisted columns (if a whitelist exists, all columns that are NOT whitelisted are deleted)."
    )

    args = parser.parse_args(argv[1:])

    a = loadcsv(args.a)
    b = loadcsv(args.b)
    o = loadcsv(args.original_file)
    
    a_filename = args.a.split(os.path.sep)[-1]
    b_filename = args.b.split(os.path.sep)[-1]
    o_filename = args.original_file.split(os.path.sep)[-1]

    config = {}
    if os.path.isfile('settings.json'):
        try:
            config.update(json.load(open('settings.json')))
        except ValueError:
            raise ValueError(
                "settings.json exists, but contains invalid JSON. "
                "Remove the file or fix it before running again.")
    if os.path.isfile(o_filename + '.json'):
        try:
            config.update(json.load(open(o_filename + '.json')))
        except ValueError:
            raise ValueError(
                "settings.json exists, but contains invalid JSON. "
                "Remove the file or fix it before running again.")

    if 'EXPECTED_HEADER_DIFFERENCES_RAW' in config:
        expected_header_differences_raw = config['EXPECTED_HEADER_DIFFERENCES_RAW']
    else:
        expected_header_differences_raw = []

    expected_header_differences = {}
    for column_variations in expected_header_differences_raw:
        for variant in column_variations:
            other_variants = column_variations[:]
            other_variants.remove(variant)
            expected_header_differences[variant] = tuple(other_variants)

    results = []

    suspicious = [['Row #', a_filename + ' PMCID', b_filename + ' PMCID', a_filename + ' PMID', b_filename + ' PMID', a_filename + ' DOI', b_filename + ' DOI', a_filename + ' Article title', b_filename + ' Article title']]
    
    if len(a) < len(b):
        logging.warn('Sheets have a different number of rows. Comparison will only go as far as the end of sheet {}, the rest of the rows in sheet {} will be ignored.'.format(args.a, args.b))
    if len(a) > len(b):
        raise ValueError('Sheet {} has more rows than sheet {}, comparison can\'t continue. Switch the order of the arguments if you want a partial comparison.'.format(a_filename, b_filename))

    a_header_row = a[0]
    b_header_row = b[0]
    o_header_row = o[0]
    if 'WHITELIST_COLUMNS' in config:
        logging.info("Whitelist found, deleting all columns not in whitelist. "
                     "Whitelist: \n {}".format(config['WHITELIST_COLUMNS']))

        def whitelist_csv(csv_contents, header_row, filename):
            remove_columns = sorted(list(set(header_row) - set(config['WHITELIST_COLUMNS'])))
            for col in remove_columns:
                delete_column(csv_contents, col)
                logging.info("Deleted column '{}' from {}, not in whitelist.".format(col, filename))

        whitelist_csv(a, a_header_row, a_filename)
        logging.info("\n\n")
        whitelist_csv(b, b_header_row, b_filename)
    else:
        logging.info('No column whitelist found.')

    if args.print_headers:
        def print_header(header_row, filename):
            logging.info("{} header:\n".format(filename))
            logging.info('"' + '","'.join(header_row) + '"')
            logging.info("\n")
        print_header(a_header_row, a_filename)
        print_header(b_header_row, b_filename)
        print_header(o_header_row, o_filename)

    try:
        DOI = a_header_row.index('DOI')
        PMID = a_header_row.index('PMID')
        PMCID = a_header_row.index('PMCID')
        TITLE = a_header_row.index('Article title')
        O_DOI = o_header_row.index('DOI')
        O_PMID = o_header_row.index('PMID')
        O_PMCID = o_header_row.index('PMCID')
        O_TITLE = o_header_row.index('Article title')
    except ValueError as e:
        raise ValueError("We expect all sheets to have DOI, PMID, PMCID and Article title column headers. Original error: \n\n {} \n {}".format(e.message, traceback.format_exc()))

    CMP_TRANSFORMS[PMCID] = pmcid_cmp

    if len(a_header_row) != len(b_header_row):
        logging.debug('{} header (length {}): {}'.format(a_filename, len(a_header_row), a_header_row))
        logging.debug('{} header (length {}): {}'.format(b_filename, len(b_header_row), b_header_row))
        logging.debug('Difference (a - b): {}'.format(set(a_header_row) - set(b_header_row)))
        logging.debug('Difference (b - a): {}'.format(set(b_header_row) - set(a_header_row)))
        raise ValueError('CSV files have different number of columns, stopping.')

    if a_header_row != b_header_row:
        def check_header_expected_differences(header_row_1, header_row_2, filename_1, filename_2):
            for col in header_row_1:
                colindex = header_row_1.index(col)
    
                if col in expected_header_differences:
                    corresponding_col_check = header_row_2[colindex]
                    if corresponding_col_check in expected_header_differences[col]:
                        logging.debug("Column '{}' at position {} in {} within expected parameters, moving on."
                                      .format(col, colindex + 1, filename_1))
                        continue
                    else:
                        logging.debug("Column '{}' at position {} in {} is unexpectedly different from column '{}' at the same position in {}."
                                      .format(col, colindex + 1, filename_1, corresponding_col_check, filename_2))
                        logging.debug('{} header: {}'.format(filename_1, header_row_1))
                        logging.debug('{} header: {}'.format(filename_2, header_row_2))
                        raise ValueError('CSV files have different headers, stopping.')

        check_header_expected_differences(a_header_row, b_header_row, a_filename, b_filename)
        check_header_expected_differences(b_header_row, a_header_row, b_filename, a_filename)

        a_remaining_cols = a_header_row[:]
        b_remaining_cols = b_header_row[:]
        for col in expected_header_differences.keys():
            if col in a_remaining_cols: a_remaining_cols.remove(col)
            if col in b_remaining_cols: b_remaining_cols.remove(col)

        if len(a_remaining_cols) != len(b_remaining_cols):
            logging.debug('{} header: {}'.format(a_filename, a_header_row))
            logging.debug('{} header: {}'.format(b_filename, b_header_row))
            logging.debug('{} remaining columns to check: {}'.format(a_filename, a_remaining_cols))
            logging.debug('{} remaining columns to check: {}'.format(b_filename, b_remaining_cols))
            raise ValueError('Different number of remaining columns to check. Double check the list of alternative column names in expected_header_differences, or check your CSV headers.')

        for i in range(0, len(a_remaining_cols)):
            a_header = a_remaining_cols[i]
            b_header = b_remaining_cols[i]
            if a_header != b_header:
                logging.debug("Unexpectedly different headers for column number {}, aborting.".format(i+1))
                logging.debug('{} problem header: {}.'.format(a_filename, a_header))
                logging.debug('{} problem header: {}.'.format(b_filename, b_header))
                logging.debug('{} expected headers without variations: {}'.format(a_filename, a_remaining_cols))
                logging.debug('{} expected headers without variations: {}'.format(b_filename, b_remaining_cols))
                raise ValueError('CSV files have different headers, stopping.')

    # The differences dict records only the differences between cells.
    # If the values are the same that's not recorded anywhere.
    # Its overall shape is
    # {"col #": {"row # 1": ["value in a", "value in b"], "row # 2": ["value in a", "value in b"], ...}, "col # 2": { row info again... } }
    differences = OrderedDict()
    for h_index in range(len(a_header_row)):
        differences[h_index] = OrderedDict()  # evtl will be filled as "row #": [a_value, b_value]

    processed_rows = 0
    for row_num in range(1, len(a)):
        a_row = a[row_num]
        b_row = b[row_num]

        # do all the identifiers differ? one is ok, maybe one tool got
        # it, the other one didn't. But all of them is suspicious.
        if not cmpcell(PMCID, a_row[PMCID], b_row[PMCID]) and not cmpcell(PMID, a_row[PMID], b_row[PMID]) and not cmpcell(DOI, a_row[DOI], b_row[DOI]):
            suspicious.append([row_num, a_row[PMCID], b_row[PMCID], a_row[PMID], b_row[PMID], a_row[DOI], b_row[DOI], a_row[TITLE], b_row[TITLE]])
            continue

        # The identifiers are ok, we are talking about the same
        # artifact. Let's compare all the data then.

        for cell_num in range(len(a_row)):
            if not cmpcell(cell_num, a_row[cell_num], b_row[cell_num]):
                differences[cell_num][row_num] = [a_row[cell_num], b_row[cell_num]]

        processed_rows += 1

    for column_header_index, coldiffs in differences.iteritems():
        if len(coldiffs) == 0:
            continue
        else:
            results.append( [ 'Row #', '{} {}'.format(a_filename, a_header_row[column_header_index]), '{} {}'.format(b_filename, b_header_row[column_header_index]), '{} PMCID'.format(o_filename), '{} PMID'.format(o_filename), '{} DOI'.format(o_filename), '{} Article title'.format(o_filename)] )
            for row_num, rowdiffs in coldiffs.iteritems():
                results.append( [ row_num+1, rowdiffs[0], rowdiffs[1], o[row_num][O_PMCID], o[row_num][O_PMID], o[row_num][O_DOI], o[row_num][O_TITLE] ] )
            results.append([])

    if args.output_path:
        results_path = args.output_path
    else:
        results_path = DEFAULT_RESULTS_FILENAME.format(a_filename, b_filename)
    savecsv(results_path, results)
    logging.info("Saved results to {}".format(results_path))

    suspicious_fn = '{}_suspicious_{}.csv'.format(a_filename, b_filename)
    if len(suspicious) > 1:  # there's a header row already
        if len(suspicious) < 50:
            logger.info('These records are suspicious: all identifiers on the same row did not match across the two sheets. So a (potentially) different article was on the same row in the two sheets.')
            logger.info(json.dumps(suspicious, indent=2))
        savecsv(suspicious_fn, suspicious)
        logging.info('Saved suspicious records to {}'.format(suspicious_fn))

    logging.info('Original file {} number of rows {}'.format(o_filename, len(o)))
    logging.info('{} number of rows {}'.format(a_filename, len(a)))
    logging.info('{} number of rows {}'.format(b_filename, len(b)))
    logging.info('{} suspicious rows which were not processed for differences (all the IDs on those rows did not match across the two CSVs being compared).'.format(len(suspicious)))
    logging.info('{} rows were processed for differences'.format(processed_rows))
if __name__ == '__main__':
    main(sys.argv)
