#!/usr/bin/env python3
"""Create a disposable demonstration. Never modifies an existing database."""
import json, os
from pathlib import Path
os.environ.setdefault('DATA_DIR',str(Path(__file__).parent/'demo-data'))
os.environ.setdefault('ADMIN_PASSWORD','DemoAdmin2026!')
import app
from engine import SCENARIOS,default_decision,simulate
if app.DB.exists():raise SystemExit('Demo database already exists. Choose a new DATA_DIR; existing files are preserved.')
app.init()
with app.connect() as db:
 admin=db.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
 gid=db.execute("INSERT INTO games(teacher,name,code,scenario,total,status) VALUES(?, '2TI — Rynek agencji IT', 'DEMO2026', 'it', 12, 'active')",(admin,)).lastrowid
 names=['KripusTech','Byte Factory','Pixel Studio','Cloud Crew']
 cs=[];ids=[];ds=[]
 for i,name in enumerate(names):
  state=app.initial_state();cs.append(state)
  cid=db.execute('INSERT INTO companies(game_id,name,code,state) VALUES(?,?,?,?)',(gid,name,app.code(),json.dumps(state))).lastrowid;ids.append(cid)
  uid=db.execute("INSERT INTO users(username,password,role) VALUES(?,?,'student')",('team'+str(i+1),app.hash_password('DemoStudent2026!'))).lastrowid
  db.execute('INSERT INTO members VALUES(?,?)',(uid,cid))
  d=default_decision(SCENARIOS['it']);d.update(equipment=2,quantities=[6+i,14+2*i,6],marketing=800+500*i,quality=55+10*i)
  ds.append(d)
 rs=simulate(SCENARIOS['it'],cs,ds,1)
 for cid,d,r in zip(ids,ds,rs):
  db.execute('INSERT INTO decisions(company_id,round,payload,submitted) VALUES(?,1,?,1)',(cid,json.dumps(d)))
  db.execute('INSERT INTO results VALUES(?,1,?)',(cid,json.dumps(r)))
  db.execute('UPDATE companies SET state=? WHERE id=?',(json.dumps({k:r[k] for k in app.initial_state()}),cid))
 db.execute('UPDATE games SET round=2 WHERE id=?',(gid,))
 for cid in ids:
  d=default_decision(SCENARIOS['it']);d.update(quantities=[7,18,6],quality=65)
  db.execute('INSERT INTO decisions(company_id,round,payload,submitted) VALUES(?,2,?,0)',(cid,json.dumps(d)))
print('Demo: admin / DemoAdmin2026! ; team1–team4 / DemoStudent2026!')
print('Start: DATA_DIR='+str(app.DB.parent)+' python3 app.py')
