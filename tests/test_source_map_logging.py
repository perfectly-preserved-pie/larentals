import logging
import unittest

from functions.source_map_logging import DashComponentSourceMapErrorFilter


class DashComponentSourceMapErrorFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        """Handle setUp.

        Each test installs the filter on a fresh logger so state does not leak across cases.

        Returns:
            None.
        """
        self.filter = DashComponentSourceMapErrorFilter()

    def test_suppresses_component_source_map_exception(self) -> None:
        """Verify that suppresses component source map exception.

        The known browser source-map exception is expected noise from packaged assets.

        Returns:
            None.
        """
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
        """Verify that keeps other application errors.

        The narrow filter must leave unrelated application failures visible.

        Returns:
            None.
        """
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
