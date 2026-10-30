"""One immutable official storage root per read-only reader subprocess."""
import os


def initialize(root):
    # Set once, before importing Jiuwen's global path configuration. Never rebind
    # a running process to a different case, and never use Session symlinks.
    os.environ['JIUWENSWARM_DATA_DIR'] = root
    os.environ['JIUWENSWARM_CONFIG_DIR'] = root + '/config'


def read(operation, session_id, params):
    if operation == 'metadata':
        from jiuwenswarm.server.runtime.session.session_metadata import get_session_metadata
        return get_session_metadata(session_id, cache_bust=True, enable_writeback=False)
    if operation == 'history':
        from jiuwenswarm.server.control.history_service import load_history_query
        return load_history_query(params)
    raise ValueError('Read-only recording operation is not supported')
