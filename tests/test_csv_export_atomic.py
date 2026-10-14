import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from pyopenlayersqt.apps.csv_plotter import CsvTable


class AtomicCsvExportTests(unittest.TestCase):
    def test_export_can_replace_its_source_with_selected_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.csv'
            header = b'lat,lon,label\n'
            first = b'40,-105,a\n'
            path.write_bytes(header + first + b'41,-106,b\n')
            table = CsvTable.from_source_rows(
                ['lat', 'lon', 'label'], str(path),
                np.array([len(header), len(header) + len(first)], dtype=np.uint64),
            ).filtered(np.array([False, True]))
            table.write_csv(str(path))
            with path.open(newline='') as source:
                self.assertEqual(list(csv.reader(source)), [['lat', 'lon', 'label'], ['41', '-106', 'b']])
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_failed_export_preserves_destination_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'output.csv'
            path.write_bytes(b'keep existing data\n')
            table = CsvTable.from_source_rows(['lat'], 'unused.csv', np.array([0]))
            with patch.object(table, '_read_source_row', side_effect=OSError('read failed')):
                with self.assertRaises(OSError):
                    table.write_csv(str(path))
            self.assertEqual(path.read_bytes(), b'keep existing data\n')
            self.assertEqual(list(Path(directory).iterdir()), [path])
