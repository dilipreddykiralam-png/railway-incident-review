"""Read-only aggregate endpoint. Run behind the deployment HTTPS proxy."""
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .usage import totals, badge


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/usage.json', '/badge.json'):
            self.send_error(404)
            return
        try:
            counts = totals(os.environ['RAILREVIEW_USAGE_DB'])
            payload = badge(counts) if self.path == '/badge.json' else counts
            status = 200
        except (KeyError, OSError, sqlite3.Error):
            payload, status = {'error': 'Usage count unavailable'}, 503
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'public, max-age=300' if status == 200 else 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # Do not collect visitor IPs in this service.


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8502), Handler).serve_forever()
