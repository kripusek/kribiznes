#!/usr/bin/env python3
"""Offline operator actions: consistent backup and interactive password reset."""
import argparse, getpass, sqlite3
from pathlib import Path
import app
p=argparse.ArgumentParser(description='KriBusiness: administracja bazą danych')
s=p.add_subparsers(dest='action',required=True)
b=s.add_parser('backup');b.add_argument('destination')
r=s.add_parser('password');r.add_argument('username')
a=p.parse_args()
if not app.DB.exists():p.error('Brak bazy. Najpierw uruchom aplikację lub ustaw DATA_DIR.')
if a.action=='backup':
 dest=Path(a.destination).resolve()
 if dest==app.DB.resolve() or dest.exists():p.error('Wybierz nowy plik kopii; istniejący plik nie zostanie nadpisany.')
 dest.parent.mkdir(parents=True,exist_ok=True)
 with app.connect() as source, sqlite3.connect(dest) as target:source.backup(target)
 print('Kopia zapisana:',dest)
else:
 password=getpass.getpass('Nowe hasło (min. 12 znaków): ')
 if not 12<=len(password)<=256:p.error('Hasło musi mieć 12–256 znaków.')
 if password!=getpass.getpass('Powtórz hasło: '):p.error('Hasła różnią się.')
 with app.connect() as db:
  user=db.execute('SELECT id FROM users WHERE username=?',(a.username,)).fetchone()
  if not user:p.error('Nie znaleziono użytkownika.')
  db.execute('UPDATE users SET password=? WHERE id=?',(app.hash_password(password),user['id']))
  db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
 print('Hasło zmienione; sesje użytkownika wylogowane.')
