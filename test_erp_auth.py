#!/usr/bin/env python3
"""Assertions /verify-fix — login unifié avec Cactus ERP.

Hermétique : importe server.py avec un DATA_DIR temporaire et un client HTTP
stubbé (aucun appel réseau, aucun vrai ERP). L'ERP est simulé par un faux
`http_requests` dont on contrôle le scénario : ok / refus / down.

Fail-before / pass-after :
    python3 test_erp_auth.py                # code courant (doit passer)
    python3 test_erp_auth.py /chemin/vieux  # server.py+config.py de master HEAD
                                            # (doit échouer : pas de délégation ERP)
"""
import json
import os
import sys
import tempfile

TARGET_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(__file__))

DATA_DIR = tempfile.mkdtemp(prefix='launcher-erp-auth-test-')
os.environ['DATA_DIR'] = DATA_DIR
os.environ['HOST_IP'] = '192.168.1.200'
os.environ['ERP_AUTH_URL'] = 'http://erp.test'
os.environ['ERP_AUTH_KEY'] = 'svc-key-test'

sys.path.insert(0, TARGET_DIR)
import server  # noqa: E402

LAN = {'X-Forwarded-For': '192.168.1.55'}

passed = 0
def check(label, cond, detail=''):
    global passed
    status = 'PASS' if cond else 'FAIL'
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ''))
    if not cond:
        sys.exit(1)
    passed += 1


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload


class FakeERP:
    """Stub de http_requests. mode: 'ok' | 'reject' | 'down'."""
    ERP_USER = {'id': 1, 'username': None, 'email': 'pierre@cactusrad.ca',
                'nom': 'Pierre', 'est_admin': True}
    USERS = [ERP_USER,
             {'id': 8, 'username': 'sharon', 'email': 'sharon@cactusrad.ca',
              'nom': 'Sharon Larouche', 'est_admin': True}]

    def __init__(self):
        self.mode = 'ok'
        self.verify_calls = 0

    def post(self, url, json=None, headers=None, timeout=None):
        assert url.endswith('/api/v1/auth/verify'), url
        assert headers.get('X-Service-Key') == 'svc-key-test'
        self.verify_calls += 1
        if self.mode == 'down':
            raise ConnectionError('ERP down (simulé)')
        if self.mode == 'ok' and json.get('mot_de_passe') == 'erp-pass' and \
                json.get('identifiant') in ('pierre', 'pierre@cactusrad.ca'):
            return FakeResponse(200, {'ok': True, 'user': dict(self.ERP_USER)})
        return FakeResponse(200, {'ok': False})

    def get(self, url, headers=None, timeout=None):
        assert url.endswith('/api/v1/auth/users'), url
        if self.mode == 'down':
            raise ConnectionError('ERP down (simulé)')
        return FakeResponse(200, {'users': [dict(u) for u in self.USERS]})


def users_json():
    with open(os.path.join(DATA_DIR, 'users.json')) as f:
        return json.load(f)['users']


def main():
    fake = FakeERP()
    server.http_requests = fake
    client = server.app.test_client()

    # --- 1. Login avec les identifiants ERP (Pierre n'a PAS de username ERP :
    #        la clé launcher est dérivée du local-part de son email) ---
    r = client.post('/api/auth/login', json={'username': 'pierre', 'password': 'erp-pass'})
    check('login pierre/erp-pass validé par l\'ERP -> 200', r.status_code == 200,
          f'code={r.status_code} body={r.get_data(as_text=True)[:120]}')
    check('l\'ERP a bien été consulté (délégation active)', fake.verify_calls == 1,
          f'verify_calls={fake.verify_calls}')
    u = users_json().get('pierre', {})
    check('users.json: pierre upserté source=erp + role admin (est_admin ERP)',
          u.get('source') == 'erp' and u.get('role') == 'admin', str(u)[:120])
    check('users.json: hash bcrypt du mdp validé mis en cache (fallback offline)',
          bool(u.get('password_hash')), '')
    r = client.get('/api/auth/me')
    check('session ouverte: /api/auth/me -> 200 pierre admin',
          r.status_code == 200 and r.get_json().get('is_admin') is True, '')
    client.post('/api/auth/logout')

    # --- 2. Login par EMAIL ERP -> même compte launcher ---
    r = client.post('/api/auth/login', json={'username': 'pierre@cactusrad.ca',
                                             'password': 'erp-pass'})
    check('login par email ERP -> 200, même user launcher "pierre"',
          r.status_code == 200 and r.get_json()['user']['username'] == 'pierre', '')
    client.post('/api/auth/logout')

    # --- 3. ERP joignable mais refuse -> 401 MÊME si le hash local (cache)
    #        correspond : l'ERP fait autorité quand il répond ---
    fake.mode = 'reject'
    r = client.post('/api/auth/login', json={'username': 'pierre', 'password': 'erp-pass'})
    check('ERP refuse -> 401 malgré le hash local en cache (ERP = autorité)',
          r.status_code == 401, f'code={r.status_code}')

    # --- 4. Compte purement local (mohamed) : reste utilisable même si l'ERP
    #        le refuse (il n'y existe pas) ---
    r = client.post('/api/auth/login', json={'username': 'mohamed', 'password': '12345'})
    check('compte local mohamed -> 200 malgré le refus ERP (source != erp)',
          r.status_code == 200, f'code={r.status_code}')
    client.post('/api/auth/logout')

    # --- 5. ERP down -> fallback offline sur le dernier mdp validé ---
    fake.mode = 'down'
    r = client.post('/api/auth/login', json={'username': 'pierre', 'password': 'erp-pass'})
    check('ERP down -> 200 via le hash bcrypt en cache (launcher survit sans ERP)',
          r.status_code == 200, f'code={r.status_code}')
    client.post('/api/auth/logout')
    r = client.post('/api/auth/login', json={'username': 'pierre@cactusrad.ca',
                                             'password': 'erp-pass'})
    check('ERP down + email tapé -> 200 (dérivation local-part du cache)',
          r.status_code == 200, f'code={r.status_code}')
    client.post('/api/auth/logout')
    r = client.post('/api/auth/login', json={'username': 'pierre', 'password': 'mauvais'})
    check('ERP down + mauvais mdp -> 401', r.status_code == 401, f'code={r.status_code}')

    # --- 6. Sélecteur LAN : la liste fusionne users ERP et comptes locaux ---
    fake.mode = 'ok'
    server._erp_users_cache.update(ts=0, users=None)  # force un refetch
    r = client.get('/api/auth/me', headers=LAN)
    names = {x['username'] for x in (r.get_json() or {}).get('users', [])}
    check('401 LAN: sélecteur = users ERP (sharon) ∪ locaux (mohamed)',
          r.status_code == 401 and {'pierre', 'sharon', 'mohamed'} <= names, str(names))

    # --- 7. select-user LAN d'un user ERP jamais loggé ici -> entrée créée ---
    r = client.post('/api/auth/select-user', json={'username': 'sharon'}, headers=LAN)
    check('select-user sharon (ERP, inconnu localement) -> 200', r.status_code == 200,
          f'code={r.status_code} body={r.get_data(as_text=True)[:120]}')
    s = users_json().get('sharon', {})
    check('users.json: sharon créée source=erp sans hash (pas de login offline)',
          s.get('source') == 'erp' and not s.get('password_hash'), str(s)[:120])

    # --- 8. Changement de mdp d'un compte ERP -> refusé (géré par l'ERP) ---
    client.post('/api/auth/logout')
    client.post('/api/auth/login', json={'username': 'pierre', 'password': 'erp-pass'})
    r = client.post('/api/auth/password', json={'current_password': 'erp-pass',
                                                'new_password': 'nouveau'})
    check('changement de mdp d\'un compte ERP -> 400 « géré par l\'ERP »',
          r.status_code == 400 and 'ERP' in r.get_json().get('message', ''),
          f'code={r.status_code}')

    print(f"\n✅ {passed}/{passed} assertions passées (login unifié ERP)")


if __name__ == '__main__':
    main()
