import tempfile
import unittest
from pathlib import Path

from pyopenlayersqt.apps.csv_plotter import CsvLoaderThread


class BlankRecordTests(unittest.TestCase):
    def test_invalid_chunk_sizes_are_rejected(self):
        for size in (0, -1):
            with self.assertRaises(ValueError):
                CsvLoaderThread([], ['lat', 'lon'], size)

    def test_blank_chunks_do_not_end_import(self):
        for chunk_size in (1, 2, 3):
            with self.subTest(chunk_size=chunk_size), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'data.csv'
                path.write_text('lat,lon\n\n\n\n40,-105\n\n\n\n41,-106\n\n\n\n')
                loader = CsvLoaderThread([str(path)], ['lat', 'lon'], chunk_size)
                chunks, completed, errors = [], [], []
                loader.chunk_ready.connect(chunks.append)
                loader.finished_success.connect(completed.append)
                loader.finished_error.connect(errors.append)
                loader.run()
                self.assertEqual(errors, [])
                self.assertEqual(completed, [[]])
                self.assertEqual([str(value) for chunk in chunks for value in chunk['lat']], ['40', '41'])
                self.assertEqual([chunk._read_source_row(i) for chunk in chunks for i in range(len(chunk))], [['40', '-105'], ['41', '-106']])
