from concurrent.futures import ThreadPoolExecutor
import pytest
from railreview.usage import record_usage, totals, badge, configured_path


def result(identity='a'):
    return {'id': identity, 'prediction': {'incident': 'uncertain'}, 'error': None}


def test_counter_is_idempotent_and_counts_sessions(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    assert record_usage(path, 'session1', result(), 'vlm')
    assert not record_usage(path, 'session1', result(), 'vlm')
    assert record_usage(path, 'session1', result('b'), 'vlm')
    assert record_usage(path, 'session2', result('c'), 'vlm')
    assert totals(path) == {'completed_analyses': 3, 'testing_sessions': 2}


@pytest.mark.parametrize('record,backend', [
    (result(), 'demo'), ({'id': 'a', 'prediction': None, 'error': 'failed'}, 'vlm'),
    ({**result(), 'media_type': 'video', 'frames': [result(), {'error': 'failed'}]}, 'vlm'),
    ({**result(), 'media_type': 'video', 'frames': []}, 'vlm'),
])
def test_failed_partial_and_demo_do_not_count(tmp_path, record, backend):
    path = tmp_path / 'usage.sqlite3'
    assert not record_usage(path, 'session', record, backend)
    assert totals(path)['completed_analyses'] == 0


def test_video_counts_once_not_per_frame(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    assert record_usage(path, 's', {**result(), 'media_type': 'video', 'frames': [result(), result('b')]}, 'vlm')
    assert totals(path)['completed_analyses'] == 1


def test_concurrent_duplicate_events_count_once(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: record_usage(path, 's', result(), 'vlm'), range(20)))
    assert totals(path) == {'completed_analyses': 1, 'testing_sessions': 1}


def test_local_tracking_disabled_even_with_database(monkeypatch):
    monkeypatch.delenv('RAILREVIEW_PUBLIC', raising=False)
    monkeypatch.setenv('RAILREVIEW_USAGE_DB', '/tmp/example.sqlite3')
    assert configured_path() is None
    monkeypatch.setenv('RAILREVIEW_PUBLIC', '1')
    assert configured_path() == '/tmp/example.sqlite3'


def test_badge_reads_do_not_increment(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    record_usage(path, 's', result(), 'vlm')
    for _ in range(3):
        assert badge(totals(path))['message'] == '1'
    assert totals(path)['completed_analyses'] == 1


def test_public_endpoint_is_read_only(tmp_path, monkeypatch):
    import json
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
    from railreview.usage_server import Handler
    path = tmp_path / 'usage.sqlite3'
    monkeypatch.setenv('RAILREVIEW_USAGE_DB', str(path))
    record_usage(path, 's', result(), 'vlm')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f'http://127.0.0.1:{server.server_port}'
        with urlopen(base + '/badge.json') as response:
            assert json.load(response)['message'] == '1'
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/usage.json', data=b'{}', method='POST'))
        assert error.value.code == 501
        assert totals(path)['completed_analyses'] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
