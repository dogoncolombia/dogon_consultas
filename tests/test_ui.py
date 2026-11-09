"""Offline checks: python -m unittest discover -s tests -p test_ui.py -v"""
from html.parser import HTMLParser
from pathlib import Path
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from jinja2 import DictLoader
from ui_support import Database, make_app, report


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('style', 'script'):
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.extend(data.split())


def visible_text(response):
    parser = VisibleText()
    parser.feed(response.get_data(as_text=True))
    return ' '.join(parser.parts)


class DesignAndReportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database()
        cls.app = make_app(cls.db)
        with ZipFile(Path(__file__).parent / 'fixtures' / 'ui_original_templates.zip') as archive:
            cls.original_templates = {name: archive.read(name).decode('utf-8-sig') for name in archive.namelist()}

    def setUp(self):
        self.db.tables = Database().tables
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(user_id='test-user', rol='admin')
        self.guest = self.app.test_client()

    def test_original_module_texts_are_preserved(self):
        paths = ['/', '/login', '/register', '/dashboard', '/perfil', '/wallet', '/consultas',
                 '/negative-reports', '/admin/recargas/pendientes',
                 '/registro/pendiente/test-token', '/wallet/recarga/1/pendiente']
        for path in paths:
            with self.subTest(path=path):
                # The requested bottom navigation adds labels outside the modules.
                current = visible_text(self.client.get(path)).removesuffix(' Inicio Consultar Reportar Saldo')
                if path == '/':
                    current = current.replace('Consultar reportados gratis', '').strip()
                    current = ' '.join(current.split())
                current_env = self.app.jinja_env
                self.app.jinja_env = current_env.overlay(loader=DictLoader(self.original_templates))
                try:
                    original = visible_text(self.client.get(path))
                finally:
                    self.app.jinja_env = current_env
                self.assertEqual(current, original)

    def test_public_home_texts_are_preserved(self):
        current = visible_text(self.guest.get('/')).replace('Consultar reportados gratis', '')
        current_env = self.app.jinja_env
        self.app.jinja_env = current_env.overlay(loader=DictLoader(self.original_templates))
        try:
            original = visible_text(self.guest.get('/'))
        finally:
            self.app.jinja_env = current_env
        self.assertEqual(' '.join(current.split()), original)

    def test_free_link_is_below_existing_home_content(self):
        html = self.guest.get('/').get_data(as_text=True)
        self.assertGreater(html.index('class="free-consultation-access"'), html.index('id="rankingList"'))
        self.assertEqual(html.count('Consultar reportados gratis'), 1)
        self.assertIn('/reportados/gratis', html)

    def test_free_lookup_works_without_registration_or_charge(self):
        for count, color in [(0, 'green'), (1, 'yellow'), (2, 'yellow'), (3, 'red'), (4, 'red')]:
            with self.subTest(count=count):
                self.db.tables['negative_reports'] = [report(i) for i in range(count)]
                response = self.guest.post('/reportados/gratis', data={'lookup_type': 'phone', 'lookup_value': '3001234567'})
                self.assertEqual(response.status_code, 200)
                self.assertIn(f'traffic-light--{color}'.encode(), response.data)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertNotIn(b'Cliente de prueba', response.data)
                self.assertNotIn(b'Entrega no recibida', response.data)
                self.assertNotIn(b'Direcci', response.data)
                self.assertIn(f'{count} '.encode() + ('reporte' if count == 1 else 'reportes').encode() + b'</span>', response.data)
        self.assertEqual(self.db.tables['users'][0]['saldo'], 8000)
        self.assertEqual(len(self.db.tables['balance_transactions']), 1)
        self.assertEqual(self.db.tables['query_history'], [])

    def test_free_lookup_does_not_show_signal_before_search(self):
        response = self.guest.get('/reportados/gratis')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'role="img"', response.data)

    def test_free_lookup_requires_exact_numbers_and_active_reports(self):
        partial = self.guest.post('/reportados/gratis', data={'lookup_type': 'phone', 'lookup_value': '300123'})
        self.assertIn(b'traffic-light--green', partial.data)
        self.db.tables['negative_reports'][0]['status'] = 'resuelto'
        full = self.guest.post('/reportados/gratis', data={'lookup_type': 'document', 'lookup_value': '123456'})
        self.assertIn(b'traffic-light--yellow', full.data)

    def test_invalid_free_search_has_no_false_green(self):
        for value in ['', '%', '<script>', '123', '123456789012345678901']:
            response = self.guest.post('/reportados/gratis', data={'lookup_type': 'phone', 'lookup_value': value})
            self.assertNotIn(b'role="img"', response.data)
        response = self.guest.post('/reportados/gratis', data={'lookup_type': 'other', 'lookup_value': '123456'})
        self.assertNotIn(b'role="img"', response.data)

    def test_free_failure_has_no_false_green(self):
        with patch.object(self.db, 'table', side_effect=RuntimeError('offline error')):
            response = self.guest.post('/reportados/gratis', data={'lookup_type': 'phone', 'lookup_value': '3001234567'})
        self.assertNotIn(b'role="img"', response.data)
        self.assertIn(b'No fue posible realizar la consulta', response.data)

    def test_free_count_does_not_depend_on_returned_row_limit(self):
        self.db.tables['negative_reports'] = [report(i) for i in range(1003)]
        response = self.guest.post('/reportados/gratis', data={'lookup_type': 'phone', 'lookup_value': '3001234567'})
        self.assertIn(b'traffic-light--red', response.data)
        self.assertIn(b'1003 reportes', response.data)

    def test_paid_consultation_keeps_original_text_and_cost(self):
        for count, color in [(0, 'green'), (1, 'yellow'), (2, 'yellow'), (3, 'red')]:
            with self.subTest(count=count):
                self.db.tables['negative_reports'] = [report(i) for i in range(count)]
                self.db.tables['users'][0].update(balance=8000, saldo=8000)
                before = len(self.db.tables['balance_transactions'])
                response = self.client.post('/consultas', data={'document': '123456'})
                self.assertIn(f'traffic-light--{color}'.encode(), response.data)
                self.assertIn('M\u00f3dulo de consultas'.encode(), response.data)
                self.assertEqual(self.db.tables['users'][0]['saldo'], 7600)
                self.assertEqual(len(self.db.tables['balance_transactions']), before + 1)

    def test_paid_consultation_still_requires_login_and_balance(self):
        response = self.guest.post('/consultas', data={'document': '123456'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/login'))
        self.db.tables['users'][0].update(balance=100, saldo=100)
        response = self.client.post('/consultas', data={'document': '123456'})
        self.assertTrue(response.location.endswith('/wallet'))
        self.assertEqual(self.db.tables['users'][0]['saldo'], 100)

    def test_no_traffic_light_legend_in_existing_pages(self):
        for path in ['/', '/consultas']:
            response = self.client.get(path)
            for phrase in ['1–2 reportes', '3 o más reportes', 'Cómo leer el semáforo', 'Un semáforo.']:
                self.assertNotIn(phrase.encode(), response.data)


if __name__ == '__main__':
    unittest.main()
