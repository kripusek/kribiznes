"""Regression tests for accounting, teamwork, drafts, suppliers and legacy databases."""
import json, os, random, sqlite3, tempfile, threading, unittest
from pathlib import Path
import app
from engine import (SCENARIOS, BANKS, ACCOUNTANTS, default_decision, costs, validate,
                    simulate, can_continue, required_cash, money, continuing_decision)
from test_business import Client

class RegressionTests(unittest.TestCase):
 def plan(self):
  d=default_decision(SCENARIOS['it']);d.update(equipment=2,quantities=[8,20,8]);return d
 def test_severance_uses_previous_salary(self):
  c=app.initial_state();c.update(employees=3,wage=8000)
  d=self.plan();d.update(employees=1,wage=4160)
  self.assertEqual(costs(d,SCENARIOS['it'],c)['severance'],8000)
 def test_saving_draft_can_exceed_budget_but_submission_cannot(self):
  d=self.plan();d.update(employees=30,equipment=30)
  validate(d,SCENARIOS['it'],app.initial_state(),check_budget=False)
  with self.assertRaises(ValueError):validate(d,SCENARIOS['it'],app.initial_state())
 def test_no_sales_cannot_farm_reputation_or_empty_training(self):
  d=self.plan();d.update(employees=0,equipment=0,training=1000,quality=100,quantities=[0]*3)
  c=app.initial_state();r=simulate(SCENARIOS['it'],[c],[d],1)[0]
  self.assertEqual(r['reputation'],c['reputation']);self.assertEqual(r['skill'],c['skill'])
  self.assertEqual(r['training'],1000)
 def test_suppliers_affect_realized_quality_and_cost(self):
  s=SCENARIOS['it'];c=app.initial_state();d=self.plan();d.update(quality=100,suppliers=['budget']*3)
  cheap=simulate(s,[c],[d],1)[0]
  d['suppliers']=['premium']*3
  premium=simulate(s,[c],[d],1)[0]
  self.assertEqual(cheap['quality_realized'],[55]*3)
  self.assertEqual(premium['quality_realized'],[100]*3)
  self.assertLess(cheap['materials'],premium['materials'])
 def test_banks_and_accounting_are_charged(self):
  d=self.plan();c=app.initial_state();c['debt']=100000;d.update(bank='credit',accountant='plus')
  bill=costs(d,SCENARIOS['it'],c)
  self.assertEqual(bill['interest'],500);self.assertEqual(bill['bank_fee'],350)
  self.assertEqual(bill['accounting'],300+bill['documents']*8)
 def test_insolvency_includes_layoffs_and_new_credit_interest(self):
  c=app.initial_state();c.update(debt=150000,cash=5000,employees=3,wage=5200)
  self.assertFalse(can_continue(SCENARIOS['it'],c))
  c.update(cash=20000)
  self.assertTrue(can_continue(SCENARIOS['it'],c))
 def test_maximum_debt_can_be_repaid_in_one_round(self):
  d=default_decision(SCENARIOS['it']);d.update(repay=150000)
  c=app.initial_state();c.update(cash=200000,debt=150000)
  validate(d,SCENARIOS['it'],c)
 def test_one_off_orders_do_not_repeat_next_round(self):
  d=self.plan();d.update(loan=1000,repay=100,training=500,bank='growth')
  c=app.initial_state();c.update(employees=4,wage=6500)
  nxt=continuing_decision(SCENARIOS['it'],c,d)
  for field in ('loan','repay','equipment','training'):self.assertEqual(nxt[field],0)
  self.assertEqual(nxt['employees'],4);self.assertEqual(nxt['bank'],'growth')
  self.assertEqual(d['equipment'],2)
 def test_long_games_keep_cent_exact_accounting(self):
  rng=random.Random(453)
  for s in SCENARIOS.values():
   cs=[app.initial_state() for _ in range(8)]
   for rnd in range(1,25):
    ds=[]
    for c in cs:
     d=default_decision(s)
     d.update(equipment=2 if rnd==1 else 0,employees=2,wage=s['wage']+rng.randint(0,99)/100,
              quantities=[rng.randint(2,8) for _ in range(3)],marketing=0,bank=rng.choice(list(BANKS)))
     if not c.get('bankrupt'):
      gap=max(0,required_cash(d,s,c)-c['cash'])
      d['loan']=min(100000,max(0,150000-c['debt']),money(gap/0.98+500) if gap else 0)
      try:validate(d,s,c)
      except ValueError:
       d=default_decision(s);d.update(employees=0,marketing=0,loan=min(100000,max(0,150000-c['debt'])))
       try:validate(d,s,c)
       except ValueError:
        # Find the feasible rescue plan promised by can_continue.
        found=False
        for n in range(c['employees']+1):
         for bank in BANKS:
          for accountant in ACCOUNTANTS:
           d.update(employees=n,wage=s['wage']*.8,bank=bank,accountant=accountant)
           try:validate(d,s,c);found=True;break
           except ValueError:pass
          if found:break
         if found:break
        self.assertTrue(found,'Active company must have an affordable plan')
     ds.append(d)
    rs=simulate(s,cs,ds,rnd)
    for old,r in zip(cs,rs):
     self.assertEqual(r['equity'],money(r['cash']+r['assets']-r['debt']))
     self.assertEqual(r['profit'],money(r['revenue']-r['costs']-r['depreciation']-r['tax']))
     self.assertEqual(r['cash_flow'],money(r['cash']-old['cash']))
     self.assertGreaterEqual(r['cash'],-.001);self.assertGreaterEqual(r['assets'],0)
     self.assertEqual(money(r['equity']-(old['cash']+old['assets']-old['debt'])),r['profit'])
    cs=[{k:r[k] for k in app.initial_state()} for r in rs]

class RevisionHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.previous_db=app.DB;app.DB=Path(self.tmp.name)/'business.sqlite3'
  os.environ['ADMIN_PASSWORD']='RegressionAdmin2026!';app.init()
  with app.connect() as db:
   teacher=db.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
   gid=db.execute("INSERT INTO games(teacher,name,code,scenario,total,status) VALUES(?,'Klasa','CODE','it',12,'active')",(teacher,)).lastrowid
   cid=db.execute("INSERT INTO companies(game_id,name,code,state) VALUES(?,'Firma','TEAM',?)",(gid,json.dumps(app.initial_state()))).lastrowid
   uid=db.execute("INSERT INTO users(username,password,role) VALUES('student',?,'student')",(app.hash_password('StudentPassword!'),)).lastrowid
   db.execute('INSERT INTO members VALUES(?,?)',(uid,cid))
  self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
  self.a=Client(f'http://127.0.0.1:{self.server.server_port}');self.b=Client(self.a.base)
  for client in (self.a,self.b):client.login('student','StudentPassword!')
 def tearDown(self):
  self.server.shutdown();self.server.server_close();app.DB=self.previous_db;self.tmp.cleanup()
 def decision(self):
  return dict(round=1,mode='draft',employees=2,wage=5200,marketing=1000,training=0,equipment=2,
              loan=0,repay=0,quality=60,price0=2500,price1=500,price2=1200,quantity0=5,quantity1=10,quantity2=5)
 def test_stale_teammate_cannot_overwrite_or_unsubmit(self):
  d=self.decision();self.assertEqual(self.a.post('/decision',d)[0],200)
  self.assertEqual(self.b.post('/decision',d)[0],409)
  self.b.request('/company');self.assertEqual(self.b.post('/decision',dict(d,mode='submit'))[0],200)
  self.assertEqual(self.a.post('/unsubmit',dict(round=1))[0],409)
  self.a.request('/company');self.assertEqual(self.a.post('/unsubmit',dict(round=1))[0],200)
 def test_overspend_draft_is_retained_with_warnings(self):
  d=self.decision();d.update(employees=30,equipment=30)
  status,body=self.a.post('/decision',d)
  self.assertEqual(status,200);self.assertIn('Budżet przekroczony',body)
  self.assertEqual(self.a.post('/decision',dict(d,mode='submit'))[0],400)
  with app.connect() as db:self.assertEqual(db.execute('SELECT submitted FROM decisions').fetchone()[0],0)

class MigrationTests(unittest.TestCase):
 def test_legacy_database_gains_revision_without_losing_data(self):
  previous=app.DB
  with tempfile.TemporaryDirectory() as temp:
   app.DB=Path(temp)/'business.sqlite3'
   try:
    with sqlite3.connect(app.DB) as db:
     db.execute('CREATE TABLE decisions(company_id INTEGER,round INTEGER,payload TEXT,submitted INTEGER,PRIMARY KEY(company_id,round))')
     db.execute("INSERT INTO decisions VALUES(1,1,'{}',1)")
    os.environ['ADMIN_PASSWORD']='MigrationPassword!';app.init();app.init()
    with app.connect() as db:
     row=db.execute('SELECT * FROM decisions').fetchone()
     self.assertEqual(row['payload'],'{}');self.assertEqual(row['submitted'],1);self.assertEqual(row['revision'],0)
   finally:app.DB=previous
