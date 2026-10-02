import copy, json, math, os, re, sys, tempfile, threading, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from engine import SCENARIOS, validate, simulate, distribute, default_decision
class EngineTests(unittest.TestCase):
 def plan(self,scenario='it'):
  d=default_decision(SCENARIOS[scenario]);d.update(equipment=2,quantities=[12,40,18]);return d
 def test_allocation_conserves_demand_and_capacity(self):
  self.assertEqual(distribute(100,[1,1],[10,200]),[10,90])
  self.assertEqual(sum(distribute(101,[1,1,1],[200]*3)),101)
  self.assertEqual(distribute(10,[0,0],[10,10]),[0,0])
  for total in range(100):
   awards=distribute(total,[.3,1.7,5],[3,12,20])
   self.assertEqual(sum(awards),min(total,35))
   self.assertTrue(all(n<=c for n,c in zip(awards,[3,12,20])))
 def test_financial_identity_capacity_and_determinism(self):
  s=SCENARIOS['it'];cs=[app.initial_state() for _ in range(2)];ds=[self.plan(),self.plan()]
  r=simulate(s,cs,ds,1)
  self.assertEqual(r,simulate(s,cs,ds,1))
  for x in r:
   self.assertAlmostEqual(x['equity'],x['cash']+x['assets']-x['debt'],places=2)
   self.assertAlmostEqual(x['profit'],x['revenue']-x['costs']-x['depreciation']-x['tax'],places=2)
   self.assertTrue(all(a<=b for a,b in zip(x['sales'],x['capacity'])))
   self.assertLessEqual(sum(q*y['hours'] for q,y in zip(x['capacity'],s['services'])),x['hours']+.1)
  for i in range(3):self.assertLessEqual(sum(x['sales'][i] for x in r),r[0]['demand'][i])
 def test_price_changes_competitive_sales(self):
  s=SCENARIOS['restaurant'];cs=[app.initial_state() for _ in range(2)]
  for c in cs:c.update(equipment=10,cash=1000000)
  ds=[default_decision(s),default_decision(s)]
  for d in ds:d.update(employees=10,quantities=[4000,100,3000])
  ds[0]['prices']=[x['price']*.5 for x in s['services']]
  rs=simulate(s,cs,ds,1)
  self.assertGreater(sum(rs[0]['sales']),sum(rs[1]['sales']))
 def test_all_teams_overpricing_reduces_market_sales(self):
  s=SCENARIOS['restaurant'];cs=[app.initial_state() for _ in range(2)]
  for c in cs:c.update(equipment=30,cash=10000000)
  plans=[default_decision(s),default_decision(s)]
  for d in plans:d.update(employees=30,quantities=[6000,200,6000])
  regular=simulate(s,cs,plans,1)
  for d in plans:d['prices']=[x['price']*4 for x in s['services']]
  overpriced=simulate(s,cs,plans,1)
  self.assertLess(sum(sum(r['sales']) for r in overpriced),sum(sum(r['sales']) for r in regular))
 def test_invalid_and_overbudget_decisions(self):
  for key,value in [('loan',float('nan')),('quality',float('inf')),('equipment',1.5),('repay',1),('marketing',50001)]:
   d=self.plan();d[key]=value
   with self.assertRaises(ValueError):validate(d,SCENARIOS['it'],app.initial_state())
  d=self.plan();d.update(employees=30,equipment=30)
  with self.assertRaises(ValueError):validate(d,SCENARIOS['it'],app.initial_state())
 def test_all_scenarios_and_events(self):
  for scenario,s in SCENARIOS.items():
   for event in app.EVENTS:
    d=default_decision(s);d.update(equipment=2,quantities=[2,2,2])
    result=simulate(s,[app.initial_state()]*2,[d,d],1,event)
    self.assertEqual(len(result),2)
    self.assertTrue(all(math.isfinite(x['cash']) for x in result))
 def test_bankrupt_team_does_not_block_market(self):
  c=app.initial_state();c['bankrupt']=True
  r=simulate(SCENARIOS['it'],[c,app.initial_state()],[default_decision(SCENARIOS['it']),self.plan()],1)
  self.assertEqual(r[0]['sales'],[0,0,0]);self.assertEqual(r[0]['cash'],100000)
  self.assertFalse(r[1]['bankrupt'])
class Client:
 def __init__(self,base):self.base=base;self.opener=build_opener(HTTPCookieProcessor(CookieJar()));self.csrf='';self.revision='0'
 def request(self,path,params=None):
  req=Request(self.base+path,data=urlencode(params).encode() if params is not None else None)
  try:
   response=self.opener.open(req);status=response.status;body=response.read().decode()
  except HTTPError as e:status=e.code;body=e.read().decode()
  match=re.search(r'name="csrf" value="([a-f0-9]+)"',body)
  if match:self.csrf=match[1]
  rev=re.search(r'name="revision" value="(\d+)"',body)
  if rev:self.revision=rev[1]
  return status,body
 def post(self,path,params={}):
  if path in ('/decision','/unsubmit'):params=dict(revision=self.revision,**params)
  return self.request(path,dict(csrf=self.csrf,**params))
 def login(self,name,password):
  self.request('/login');return self.post('/login',dict(username=name,password=password))
class IntegrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();app.DB=Path(cls.tmp.name)/'business.sqlite3'
  os.environ['ADMIN_PASSWORD']='test-admin-password';app.init()
  cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
  cls.base=f'http://127.0.0.1:{cls.server.server_port}'
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
 def test_full_classroom_and_security(self):
  admin=Client(self.base);self.assertEqual(admin.login('admin','test-admin-password')[0],200)
  self.assertEqual(admin.post('/teachers',dict(username='teacher',password='teacher-password'))[0],200)
  self.assertEqual(admin.post('/teachers',dict(username='other',password='another-password'))[0],200)
  teacher=Client(self.base);teacher.login('teacher','teacher-password')
  status,body=teacher.post('/games',dict(name='Test <script>alert(1)</script>',scenario='it',total=2));self.assertEqual(status,200)
  self.assertIn('&lt;script&gt;',body);self.assertNotIn('<script>alert(1)</script>',body)
  with app.connect() as db:g=dict(db.execute('SELECT * FROM games').fetchone())
  gid=g['id'];students=[]
  for i in range(2):
   student=Client(self.base);student.request('/join')
   self.assertEqual(student.post('/join',dict(class_code=g['code'],username='student'+str(i),password='student-password',company_name='Firma '+str(i)))[0],200)
   student.login('student'+str(i),'student-password');students.append(student)
  member=Client(self.base);member.request('/join')
  with app.connect() as db:team=dict(db.execute('SELECT * FROM companies ORDER BY id LIMIT 1').fetchone())
  self.assertEqual(member.post('/join',dict(class_code=g['code'],team_code=team['code'],username='member',password='member-password'))[0],200)
  member.login('member','member-password')
  self.assertEqual(students[0].request('/game/'+str(gid))[0],403)
  other=Client(self.base);other.login('other','another-password')
  self.assertEqual(other.request('/game/'+str(gid))[0],403)
  self.assertEqual(other.request('/game/'+str(gid)+'/export')[0],403)
  self.assertEqual(teacher.request('/game/'+str(gid))[0],200)
  self.assertEqual(teacher.request('/start',dict(game=gid,csrf='bad'))[0],403)
  self.assertEqual(teacher.post('/start',dict(game=gid))[0],200)
  self.assertEqual(teacher.post('/advance',dict(game=gid,round=1,confirm='yes'))[0],409)
  def plan(round_no,equipment):
   return dict(round=round_no,mode='submit',employees=2,wage=5200,marketing=1000,training=0,equipment=equipment,loan=0,repay=0,quality=60,
    price0=2500,price1=500,price2=1200,quantity0=10,quantity1=20,quantity2=10)
  self.assertEqual(students[0].post('/decision',{**plan(1,2),'loan':'nan'})[0],400)
  for student in students:self.assertEqual(student.post('/decision',plan(1,2))[0],200)
  self.assertEqual(member.request('/company')[0],200)
  self.assertIn('Plan zatwierdzony',member.request('/company')[1])
  self.assertEqual(teacher.post('/event',dict(game=gid,event='crisis'))[0],200)
  with app.connect() as db:self.assertEqual(db.execute('SELECT SUM(submitted) FROM decisions').fetchone()[0],0)
  for student in students:
   student.request('/company');self.assertEqual(student.post('/decision',plan(1,2))[0],200)
  self.assertEqual(teacher.post('/advance',dict(game=gid,round=1,confirm='yes'))[0],200)
  self.assertEqual(teacher.post('/advance',dict(game=gid,round=1,confirm='yes'))[0],409)
  self.assertEqual(students[0].post('/decision',plan(1,0))[0],409)
  for student in students:
   student.request('/company');self.assertEqual(student.post('/decision',plan(2,0))[0],200)
  duplicate=Client(self.base);duplicate.login('teacher','teacher-password')
  with ThreadPoolExecutor(max_workers=2) as workers:
   responses=list(workers.map(lambda client:client.post('/advance',dict(game=gid,round=2,confirm='yes'))[0],[teacher,duplicate]))
  self.assertEqual(sorted(responses),[200,409])
  self.assertIn('Rozgrywka zakończona',students[0].request('/company')[1])
  self.assertIn('Rachunek wyników',students[0].request('/report')[1])
  self.assertIn('Firma 1',students[0].request('/ranking')[1])
  status,export=teacher.request('/game/'+str(gid)+'/export');self.assertEqual(status,200);self.assertEqual(len(export.splitlines()),5)
  with app.connect() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM results').fetchone()[0],4)
   before=db.execute('SELECT state FROM companies ORDER BY id').fetchall()
  app.init() # reinitialize after a restart without overwriting results, accounts or state
  with app.connect() as db:self.assertEqual([r[0] for r in before],[r[0] for r in db.execute('SELECT state FROM companies ORDER BY id')])
  self.assertEqual(teacher.post('/advance',dict(game=gid,round=3,confirm='yes'))[0],409)
  self.assertEqual(students[0].post('/logout')[0],200)
  self.assertEqual(students[0].request('/report')[0],401)
if __name__=='__main__':unittest.main()
