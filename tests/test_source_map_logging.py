import logging
import unittest

from functions.source_map_logging import DashComponentSourceMapErrorFilter


class DashComponentSourceMapErrorFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = DashComponentSourceMapErrorFilter()

    def test_suppresses_component_source_map_exception(self) -> None:
        record = logging.LogRecord(
            name="app",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Exception on /_dash-component-suites/dash/dash_renderer.js.map [GET]",
            args=(),
            exc_info=None,
        )

        self.assertFalse(self.filter.filter(record))

    def test_keeps_other_application_errors(self) -> None:
        record = logging.LogRecord(
            name="app",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Exception on /api/listings [GET]",
            args=(),
            exc_info=None,
        )

        self.assertTrue(self.filter.filter(record))


if __name__ == "__main__":
    unittest.main()
