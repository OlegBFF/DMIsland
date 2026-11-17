"""Тесты ИИ-клиента на локальном HTTP-сервере: история, SSE-стриминг, ошибки, отмена."""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from modules.ai_client import AIClient, AIError, build_payload, iter_sse, trim_history


class H(BaseHTTPRequestHandler):
    log = []
    mode = 'sse'

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        H.log.append((body, self.headers.get('Authorization')))
        if H.mode == 'err':
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': {'message': 'Incorrect API key'}}).encode())
        elif H.mode == 'json':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'choices': [{'message': {'content': 'целиком'}}]}).encode())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            self.wfile.write(b': keepalive\n\n')
            for i, piece in enumerate(['При', 'вет', ', ', 'мир']):
                ch = {'choices': [{'delta': {'content': piece}}]}
                self.wfile.write(b'data: ' + json.dumps(ch, ensure_ascii=False).encode() + b'\n\n')
                self.wfile.flush()
                time.sleep(0.15 if H.mode == 'slow' else 0)
            self.wfile.write(b'data: {"choices":[{"delta":{}}]}\n\ndata: [DONE]\n\n')


class Pure(unittest.TestCase):
    def test_trim_keeps_latest_and_starts_with_user(self):
        hist = [{'role': 'user', 'content': 'a' * 100}, {'role': 'assistant', 'content': 'b' * 100},
                {'role': 'user', 'content': 'c' * 100}, {'role': 'assistant', 'content': 'd' * 100},
                {'role': 'user', 'content': 'last'}]
        out = trim_history(hist, 260)
        self.assertEqual(out[-1]['content'], 'last')
        self.assertEqual(out[0]['role'], 'user')
        self.assertEqual(len(trim_history(hist, 10)), 1)                # последний вопрос — всегда

    def test_payload_has_system_and_stream(self):
        p = build_payload('m', 'sys', [{'role': 'user', 'content': 'q'}], 1000, True)
        self.assertEqual(p['messages'][0], {'role': 'system', 'content': 'sys'})
        self.assertTrue(p['stream'])

    def test_sse_parser(self):
        lines = [b': ping', b'', b'data: {"choices":[{"delta":{"content":"A"}}]}', b'data: not json',
                 b'data: {"choices":[{"delta":{"content":null}}]}', b'data: {"choices":[{"delta":{"content":"B"}}]}',
                 b'data: [DONE]', b'data: {"choices":[{"delta":{"content":"after-done"}}]}']
        self.assertEqual(list(iter_sse(lines)), ['A', 'B'])
        with self.assertRaises(AIError):
            list(iter_sse([b'data: {"error":{"message":"quota"}}']))


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.srv.server_port}/v1/chat/completions'

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        H.log.clear()
        H.mode = 'sse'

    def test_stream_and_full_history_is_sent(self):
        hist = [{'role': 'user', 'content': 'Меня зовут Аня'}, {'role': 'assistant', 'content': 'Привет, Аня'},
                {'role': 'user', 'content': 'Как меня зовут?'}]
        c = AIClient(self.url, 'k123', 'm')
        self.assertEqual(list(c.stream(hist)), ['При', 'вет', ', ', 'мир'])
        body, auth = H.log[0]
        self.assertEqual([m['role'] for m in body['messages']], ['system', 'user', 'assistant', 'user'])   # раньше уходил один запрос
        self.assertTrue(body['stream'])
        self.assertEqual(auth, 'Bearer k123')

    def test_json_fallback_when_server_ignores_stream(self):
        H.mode = 'json'
        self.assertEqual(AIClient(self.url).complete([{'role': 'user', 'content': 'q'}]), 'целиком')

    def test_http_error_is_readable(self):
        H.mode = 'err'
        with self.assertRaises(AIError) as cm:
            AIClient(self.url).complete([{'role': 'user', 'content': 'q'}])
        self.assertIn('401', str(cm.exception))
        self.assertIn('Incorrect API key', str(cm.exception))

    def test_cancel_stops_stream_midway(self):
        H.mode = 'slow'
        cancel, got = threading.Event(), []
        for piece in AIClient(self.url).stream([{'role': 'user', 'content': 'q'}], cancel=cancel):
            got.append(piece)
            cancel.set()
        self.assertEqual(got, ['При'])

    def test_blocks_plain_http_to_remote_hosts(self):
        with self.assertRaises(AIError):
            AIClient('http://example.com/v1/chat/completions').complete([{'role': 'user', 'content': 'q'}])


if __name__ == '__main__':
    unittest.main()


class NormalizeUrlTests(unittest.TestCase):
    def test_gemini_base_and_variants(self):
        from modules.ai_client import normalize_url
        full = 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
        for u in ('https://generativelanguage.googleapis.com/v1beta/', 'https://generativelanguage.googleapis.com/v1beta',
                  'https://generativelanguage.googleapis.com/v1beta/openai/', full, 'https://generativelanguage.googleapis.com'):
            self.assertEqual(normalize_url(u), full, u)

    def test_openai_style(self):
        from modules.ai_client import normalize_url
        self.assertEqual(normalize_url('https://api.openai.com/v1'), 'https://api.openai.com/v1/chat/completions')
        self.assertEqual(normalize_url('http://localhost:11434/v1/'), 'http://localhost:11434/v1/chat/completions')
        self.assertEqual(normalize_url('https://api.openai.com/v1/chat/completions'), 'https://api.openai.com/v1/chat/completions')

    def test_gemini_list_error(self):
        from modules.ai_client import _err_text
        self.assertEqual(_err_text([{'error': {'message': 'bad key'}}]), 'bad key')
