#!/usr/bin/env python3
"""Assertions /verify-fix — multi-user, sélecteur LAN, page partagée, owner de worktree.

État AVANT (capturé avant rebuild, ancien code) :
  - GET /api/auth/me sans cookie  -> 200 auto-login 'pierre' (LE BUG)
  - GET /api/shared/page          -> 404
  - POST /api/auth/select-user    -> 404
Ce script vérifie l'état APRÈS : chaque assertion ci-dessous échouerait sur l'ancien code.
"""
import requests
import subprocess
import sys
import os

BASE = 'https://192.168.1.200'
PROJECTS = '/home/cactus/claude'
TEST_REPO = 'wt-owner-test'

requests.packages.urllib3.disable_warnings()

passed = 0
def check(label, cond, detail=''):
    global passed
    status = 'PASS' if cond else 'FAIL'
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ''))
    if not cond:
        sys.exit(1)
    passed += 1

def main():
    # --- 1. Plus d'auto-login : 401 + liste des users pour le sélecteur LAN ---
    r = requests.get(f'{BASE}/api/auth/me', verify=False)
    check('auth/me sans cookie -> 401 (plus d\'auto-login pierre)', r.status_code == 401, f'code={r.status_code}')
    data = r.json()
    check('401 contient lan=true + users[] pour le sélecteur', data.get('lan') is True and
          {u['username'] for u in data.get('users', [])} >= {'pierre', 'mohamed'}, str(data)[:120])

    # --- 2. Sélection de user sans mot de passe (LAN) ---
    s_mo = requests.Session(); s_mo.verify = False
    r = s_mo.post(f'{BASE}/api/auth/select-user', json={'username': 'mohamed'})
    check('select-user mohamed -> 200', r.status_code == 200, f'code={r.status_code}')
    r = s_mo.get(f'{BASE}/api/auth/me')
    check('session = mohamed (pas pierre)', r.status_code == 200 and r.json().get('username') == 'mohamed')

    r = s_mo.post(f'{BASE}/api/auth/select-user', json={'username': 'inconnu'})
    check('select-user inconnu -> 404', r.status_code == 404, f'code={r.status_code}')

    # --- 3. select-user hors LAN -> 403 (XFF non-LAN, nginx préfixe l'IP cliente) ---
    r = requests.post(f'{BASE}/api/auth/select-user', json={'username': 'pierre'},
                      headers={'X-Forwarded-For': '8.8.8.8'}, verify=False)
    check('select-user hors LAN -> 403', r.status_code == 403, f'code={r.status_code}')

    # --- 4. Anciennes sessions auto-login (sans version) invalidées ---
    mint = ("from server import app; from flask.sessions import SecureCookieSessionInterface; "
            "si = SecureCookieSessionInterface(); s = si.get_signing_serializer(app); "
            "print(s.dumps({'username': 'pierre'})); print(s.dumps({'username': 'pierre', 'v': 2}))")
    out = subprocess.run(['docker', 'exec', 'terminal-launcher', 'python', '-c', mint],
                         capture_output=True, text=True)
    cookies = [l for l in out.stdout.strip().split('\n') if l.startswith('ey') or '.' in l][-2:]
    legacy, versioned = cookies[0], cookies[1]
    r = requests.get(f'{BASE}/api/auth/me', cookies={'cactus_session': legacy}, verify=False)
    check('ancienne session (sans v) -> 401 (invalidée, repasse par le sélecteur)',
          r.status_code == 401, f'code={r.status_code}')
    r = requests.get(f'{BASE}/api/auth/me', cookies={'cactus_session': versioned}, verify=False)
    check('session versionnée (v=2) -> 200', r.status_code == 200 and r.json().get('username') == 'pierre')

    # --- 5. Page partagée : lecture pour tous, écriture admin only ---
    s_pi = requests.Session(); s_pi.verify = False
    s_pi.post(f'{BASE}/api/auth/select-user', json={'username': 'pierre'})

    r = s_mo.get(f'{BASE}/api/shared/page')
    check('GET shared/page (mohamed) -> 200', r.status_code == 200, f'code={r.status_code}')
    r = s_mo.post(f'{BASE}/api/shared/page', json={'apps': []})
    check('POST shared/page (mohamed, non-admin) -> 403', r.status_code == 403, f'code={r.status_code}')

    shared_before = s_pi.get(f'{BASE}/api/shared/page').json()
    test_app = {'id': 'shared_test_1', 'name': 'Test Partagé', 'url': 'http://192.168.1.200:9999',
                'desc': 'test', 'icon': 'globe', 'gradient': ''}
    r = s_pi.post(f'{BASE}/api/shared/page', json={'apps': shared_before.get('apps', []) + [test_app]})
    check('POST shared/page (pierre, admin) -> 200', r.status_code == 200, f'code={r.status_code}')
    r = s_mo.get(f'{BASE}/api/shared/page')
    check('mohamed voit le raccourci ajouté par l\'admin',
          any(a.get('id') == 'shared_test_1' for a in r.json().get('apps', [])))
    # rollback
    s_pi.post(f'{BASE}/api/shared/page', json={'apps': shared_before.get('apps', [])})

    # --- 6. Worktree taggé au nom du créateur ---
    repo = os.path.join(PROJECTS, TEST_REPO)
    subprocess.run(['rm', '-rf', repo, repo + '--feat-owner'], check=True)
    subprocess.run(f'git init -q {repo} && cd {repo} && git commit -q --allow-empty -m init',
                   shell=True, check=True)
    try:
        r = s_mo.post(f'{BASE}/api/projects/{TEST_REPO}/git/worktrees', json={'branch': 'feat/owner'})
        check('création worktree par mohamed -> 200', r.status_code == 200, r.text[:120])
        check('réponse contient owner=mohamed', r.json().get('owner') == 'mohamed')

        git = s_mo.get(f'{BASE}/api/projects/folders?git=1').json().get('git', {})
        wts = git.get(TEST_REPO, {}).get('worktrees', [])
        wt = next((w for w in wts if w['dirname'] == f'{TEST_REPO}--feat-owner'), None)
        check('get_git_info expose origin=user owner=mohamed owner_display=Mohamed',
              wt is not None and wt['origin'] == 'user' and wt['owner'] == 'mohamed'
              and wt['owner_display'] == 'Mohamed', str(wt))

        # Reclassement claude -> plus d'owner ; puis pierre le revendique
        r = s_pi.post(f'{BASE}/api/projects/{TEST_REPO}/git/worktrees/{TEST_REPO}--feat-owner/origin',
                      json={'origin': 'claude'})
        check('reclasser origin=claude -> 200, owner null', r.status_code == 200 and r.json().get('owner') is None)
        r = s_pi.post(f'{BASE}/api/projects/{TEST_REPO}/git/worktrees/{TEST_REPO}--feat-owner/origin',
                      json={'origin': 'user'})
        check('pierre revendique -> owner=pierre', r.status_code == 200 and r.json().get('owner') == 'pierre')

        git = s_pi.get(f'{BASE}/api/projects/folders?git=1').json().get('git', {})
        wt = next((w for w in git.get(TEST_REPO, {}).get('worktrees', [])
                   if w['dirname'] == f'{TEST_REPO}--feat-owner'), None)
        check('owner=pierre visible dans get_git_info (base du badge P + avertissement)',
              wt is not None and wt['owner'] == 'pierre' and wt['owner_display'] == 'Pierre', str(wt))
    finally:
        s_pi.delete(f'{BASE}/api/projects/{TEST_REPO}/git/worktrees/{TEST_REPO}--feat-owner?force=1')
        subprocess.run(['rm', '-rf', repo, repo + '--feat-owner'])

    print(f"\n{passed} assertions OK")

if __name__ == '__main__':
    main()
