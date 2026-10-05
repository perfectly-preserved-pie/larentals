"""Exercise emitted container logs in isolated processes with real handlers."""

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_logging(code: str, **environment: str | None) -> list[dict]:
    """Capture the actual stream without changing pytest's logging handlers.

    A fresh process also exercises package initialization and environment
    thresholds in the order used by standalone commands.

    Args:
        code: Python snippet executed from the repository root.
        environment: Environment overrides; None removes a setting.

    Returns:
        Parsed events from the subprocess's stderr stream.
    """
    env = {**os.environ, "LOG_LEVEL": "DEBUG", **environment}
    env = {key: value for key, value in env.items() if value is not None}
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], cwd=ROOT,
        env=env, text=True, capture_output=True, check=True,
    )
    assert completed.stdout == ""
    return [json.loads(line) for line in completed.stderr.splitlines()]


def test_debug_is_enabled_without_environment_setting() -> None:
    """Verify the default threshold keeps diagnostics from both logging APIs.

    Removing LOG_LEVEL exercises the same default used by a new container.

    Returns:
        None.
    """
    events = run_logging('''
        import functions
        import logging
        from loguru import logger
        logger.debug('application diagnostic')
        logging.debug('library diagnostic')
    ''', LOG_LEVEL=None)
    assert [event['level'] for event in events] == ['debug', 'debug']


def test_invalid_threshold_does_not_remove_working_sinks() -> None:
    """Keep logging usable after rejecting an invalid threshold.

    Validation must happen before replacing existing sinks.

    Returns:
        None.
    """
    events = run_logging('''
        import os
        from functions.logging_config import configure_logging
        from loguru import logger
        os.environ['LOG_LEVEL'] = 'invalid'
        try:
            configure_logging()
        except ValueError:
            logger.error('configuration rejected')
        else:
            raise AssertionError('invalid threshold accepted')
    ''')
    assert [event['message'] for event in events] == ['configuration rejected']


def test_all_standard_levels_are_single_json_events() -> None:
    """Verify severity names, caller fields, and multiline event boundaries.

    Both logging APIs must preserve exceptions inside a single Docker line.

    Returns:
        None.
    """
    events = run_logging('''
        import functions
        import logging
        from loguru import logger
        for name in ('debug', 'info', 'success', 'warning', 'error', 'critical'):
            getattr(logger, name)('loguru ' + name)
        for name in ('debug', 'info', 'warning', 'error', 'critical'):
            getattr(logging.getLogger('library'), name)('standard %s', name)
        logger.bind(mls='123').info('first line\\nsecond line')
        try:
            raise ValueError('exception detail')
        except ValueError:
            logger.exception('loguru failure')
            logging.exception('standard failure')
    ''')
    assert [event['level'] for event in events] == [
        'debug', 'info', 'info', 'warn', 'error', 'fatal',
        'debug', 'info', 'warn', 'error', 'fatal', 'info', 'error', 'error',
    ]
    assert events[6]['message'] == 'standard debug'
    assert events[6]['logger'] == 'library'
    assert events[6]['function'] == '<module>'
    assert events[11]['message'] == 'first line\nsecond line'
    assert events[11]['extra'] == {'mls': '123'}
    for event in events[-2:]:
        assert 'Traceback' in event['message']
        assert 'ValueError: exception detail' in event['message']
    assert all(event['time'].endswith('+00:00') for event in events)


@pytest.mark.parametrize('level,expected', [
    ('debug', ['debug', 'info', 'warn', 'error', 'fatal']),
    ('INFO', ['info', 'warn', 'error', 'fatal']),
    ('WARN', ['warn', 'error', 'fatal']),
    ('ERROR', ['error', 'fatal']),
    ('FATAL', ['fatal']),
])
def test_threshold_applies_to_both_logging_apis(level: str, expected: list[str]) -> None:
    """Check that aliases and thresholds behave consistently across APIs.

    A library event should never bypass the application's configured threshold.

    Args:
        level: Environment threshold or accepted alias to exercise.
        expected: Ordered severities remaining above that threshold.

    Returns:
        None.
    """
    events = run_logging('''
        import functions
        import logging
        from loguru import logger
        for name in ('debug', 'info', 'warning', 'error', 'critical'):
            getattr(logger, name)('application event')
        for name in ('debug', 'info', 'warning', 'error', 'critical'):
            getattr(logging, name)('library event')
    ''', LOG_LEVEL=level)
    assert [event['level'] for event in events] == expected * 2


@pytest.mark.parametrize('pipeline', ['buy', 'lease'])
def test_reconfiguration_keeps_one_console_sink_and_shared_file(
    tmp_path: Path, pipeline: str,
) -> None:
    """Keep repeated setup from duplicating or losing labeled pipeline events.

    Shared library calls must inherit the job label in console and file logs.

    Args:
        tmp_path: Isolated home directory containing the rotating log file.
        pipeline: Buy or lease job label to apply to shared helper events.

    Returns:
        None.
    """
    events = run_logging('''
        from functions.logging_config import configure_logging
        from loguru import logger
        import logging
        import os
        configure_logging(logfile='~/pipeline.log', pipeline=os.environ['TEST_PIPELINE'])
        configure_logging(logfile='~/pipeline.log', pipeline=os.environ['TEST_PIPELINE'])
        logger.debug('pipeline debug')
        logging.debug('library debug')
    ''', HOME=str(tmp_path), TEST_PIPELINE=pipeline)
    assert [event['message'] for event in events] == [
        f'[{pipeline}] pipeline debug', f'[{pipeline}] library debug',
    ]
    assert all(event['pipeline'] == pipeline for event in events)
    file_logs = (tmp_path / 'pipeline.log').read_text()
    assert file_logs.count('pipeline debug') == 1
    assert file_logs.count('library debug') == 1
    assert file_logs.count(f'[{pipeline}]') == 2


def test_flask_filter_survives_shared_handler() -> None:
    """Keep expected source-map noise suppressed without losing Flask errors.

    The bridge must respect filters attached to the originating Flask logger.

    Returns:
        None.
    """
    events = run_logging('''
        from flask import Flask
        from functions.source_map_logging import register_source_map_error_filter
        app = Flask('logging-test')
        register_source_map_error_filter(app)
        app.logger.error('Exception on /_dash-component-suites/pkg/file.js.map [GET]')
        app.logger.error('Exception on /api/listings [GET]')
    ''')
    assert len(events) == 1
    assert events[0]['level'] == 'error'
    assert events[0]['message'] == 'Exception on /api/listings [GET]'


@pytest.mark.parametrize('level', ['DEBUG', 'INFO', 'ERROR'])
def test_gunicorn_keeps_only_warnings_and_errors(level: str) -> None:
    """Keep server noise suppressed independently of application thresholds.

    Real Gunicorn initialization must disable access logging and still emit
    warnings and errors once, even when application logging is more restrictive.
    """
    events = run_logging('''
        import runpy
        import logging
        from gunicorn.config import Config
        from gunicorn.glogging import Logger
        settings = runpy.run_path('gunicorn.conf.py')
        config = Config()
        for key in ('loglevel', 'accesslog', 'errorlog', 'logconfig_dict'):
            config.set(key, settings[key])
        server_logger = Logger(config)
        assert config.accesslog is None
        server_logger.debug('worker diagnostic')
        server_logger.info('worker started')
        logging.getLogger('gunicorn.access').info('GET /health 200')
        server_logger.warning('worker warning')
        server_logger.error('worker failure')
        server_logger.critical('worker fatal')
        logging.debug('application diagnostic')
        logging.error('application failure')
    ''', LOG_LEVEL=level)
    expected = ['warn', 'error', 'fatal']
    if level == 'DEBUG':
        expected.append('debug')
    expected.append('error')
    assert [event['level'] for event in events] == expected
    assert [event['message'] for event in events[:3]] == [
        'worker warning', 'worker failure', 'worker fatal',
    ]
    assert all(event['logger'] == 'gunicorn.error' for event in events[:3])
