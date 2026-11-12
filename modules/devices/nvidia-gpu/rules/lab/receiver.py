"""Local-only test webhook; records bounded request bodies, never auth headers."""
import json
from batch1_notifications import interpret
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Store:
    def __init__(self, path, max_bytes=5 * 1024 * 1024):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.lock = threading.Lock()

    def append(self, payload):
        record = {'received_at': datetime.now(timezone.utc).isoformat(), 'payload': payload,
                  'interpretations': interpret(payload)}
        line = json.dumps(record, ensure_ascii=False) + '\n'
        with self.lock:
            if self.path.exists() and self.path.stat().st_size + len(line.encode()) > self.max_bytes:
                self.path.replace(self.path.with_suffix('.previous.jsonl'))
            with self.path.open('a') as stream:
                stream.write(line)
        return record

    def recent(self):
        with self.lock:
            if not self.path.exists():
                return []
            lines = self.path.read_text().splitlines()
            return [json.loads(line) for line in lines[-100:]]


class Handler(BaseHTTPRequestHandler):
    store = None

    def reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health':
            self.reply(200, {'ok': True})
        elif self.path == '/batch1/events':
            self.reply(200, {'events': [{'received_at':r['received_at'],
                'notifications':r['interpretations']} for r in self.store.recent() if r.get('interpretations')]})
        elif self.path == '/events':
            self.reply(200, {'events': self.store.recent()})
        else:
            self.reply(404, {'error': 'not found'})

    def do_POST(self):
        if self.path != '/webhook':
            self.reply(404, {'error': 'not found'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 65536:
                self.reply(413, {'error': 'body must be 1..65536 bytes'})
                return
            raw = self.rfile.read(length).decode('utf-8')
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = {'text': raw}
            self.store.append(payload)
            self.reply(200, {'ok': True})
        except (ValueError, UnicodeError):
            self.reply(400, {'error': 'invalid body'})
        except OSError:
            self.reply(500, {'error': 'event persistence failed'})

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    Handler.store = Store(os.environ.get('EVENTS_PATH', '/data/events.jsonl'))
    ThreadingHTTPServer(('0.0.0.0', 9080), Handler).serve_forever()
