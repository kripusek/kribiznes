#!/usr/bin/env python3
import csv, hashlib, hmac, html, io, json, os, secrets, signal, sqlite3, time, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse
from engine import (SCENARIOS, EVENTS, BANKS, ACCOUNTANTS, SUPPLIERS, default_decision,
                    continuing_decision, normalize, validate, simulate, costs, required_cash, warnings)
ROOT=Path(__file__).parent
DB=Path(os.getenv('DATA_DIR',str(ROOT/'data')))/'business.sqlite3'
COOKIE_SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true'
LOGIN_ATTEMPTS={}; ATTEMPT_LOCK=threading.Lock()

@contextmanager
def connect():
 db=sqlite3.connect(DB,timeout=30);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
 try:
  with db:yield db
 finally:db.close()

def hash_password(p,salt=None):
 salt=salt or secrets.token_hex(16)
 return salt+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(salt),260000).hex()

def check_password(p,hashed):return hmac.compare_digest(hash_password(p,hashed.split(':')[0]),hashed)

def init():
 DB.parent.mkdir(parents=True,exist_ok=True)
 with connect() as db:
  db.executescript('''
  PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','teacher','student')));
  CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),csrf TEXT NOT NULL,expires INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS games(id INTEGER PRIMARY KEY,teacher INTEGER NOT NULL REFERENCES users(id),name TEXT NOT NULL,code TEXT UNIQUE NOT NULL,scenario TEXT NOT NULL,round INTEGER NOT NULL DEFAULT 1,total INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'lobby',event TEXT NOT NULL DEFAULT 'normal');
  CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY,game_id INTEGER NOT NULL REFERENCES games(id),name TEXT NOT NULL,code TEXT UNIQUE NOT NULL,state TEXT NOT NULL,UNIQUE(game_id,name));
  CREATE TABLE IF NOT EXISTS members(user_id INTEGER PRIMARY KEY REFERENCES users(id),company_id INTEGER NOT NULL REFERENCES companies(id));
  CREATE TABLE IF NOT EXISTS decisions(company_id INTEGER NOT NULL REFERENCES companies(id),round INTEGER NOT NULL,payload TEXT NOT NULL,submitted INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(company_id,round));
  CREATE TABLE IF NOT EXISTS results(company_id INTEGER NOT NULL REFERENCES companies(id),round INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(company_id,round));
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,created INTEGER NOT NULL,user_id INTEGER REFERENCES users(id),game_id INTEGER REFERENCES games(id),action TEXT NOT NULL);
  ''')
  columns={r[1] for r in db.execute('PRAGMA table_info(decisions)')}
  if 'revision' not in columns:db.execute('ALTER TABLE decisions ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
  db.execute('PRAGMA user_version=2')
  if not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
   password=os.getenv('ADMIN_PASSWORD','')
   if len(password)<12:raise RuntimeError('Ustaw ADMIN_PASSWORD (minimum 12 znaków) przed pierwszym startem.')
   db.execute('INSERT INTO users(username,password,role) VALUES(?,?,?)',(os.getenv('ADMIN_USERNAME','admin'),hash_password(password),'admin'))

def esc(x):return html.escape(str(x),quote=True)
def cash(x):return f'{x:,.2f}'.replace(',',' ').replace('.',',')+' zł'
def field(label,name,value='',kind='text',attrs=''):
 return f'<label>{esc(label)}<input type="{kind}" name="{esc(name)}" value="{esc(value)}" {attrs} required></label>'
def note(t):return f'<div class="notice">{esc(t)}</div>'
def tag(t):return f'<span class="tag">{esc(t)}</span>'
def audit(db,user,game,action):db.execute('INSERT INTO audit(created,user_id,game_id,action) VALUES(?,?,?,?)',(int(time.time()),user['id'],game,action))
def initial_state():return dict(cash=100000,debt=0,assets=0,equipment=0,employees=0,skill=40,reputation=50,bankrupt=False,wage=0)
def code():return secrets.token_hex(4).upper()

class Error(Exception):
 def __init__(self,message,status=400):self.message=message;self.status=status

class Handler(BaseHTTPRequestHandler):
 server_version='KriBusiness/1.1'
 def setup(self):
  super().setup();self.connection.settimeout(15)
 def log_message(self,fmt,*args):
  # No passwords, cookies, join codes or submitted bodies in logs.
  print(f'{self.client_address[0]} {self.command} {urlparse(self.path).path}',flush=True)
 def send(self,body,status=200,typ='text/html; charset=utf-8',extra=None):
  data=body.encode() if isinstance(body,str) else body
  self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(data)))
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
  self.send_header('Referrer-Policy','no-referrer');self.send_header('Cache-Control','no-store')
  self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
  for k,v in (extra or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(data)
 def redirect(self,path,extra=None):self.send('',303,extra={'Location':path,**(extra or {})})
 def session(self,db):
  cookies={}
  for item in self.headers.get('Cookie','').split(';'):
   if '=' in item:k,v=item.strip().split('=',1);cookies[k]=v
  token=cookies.get('kb_session','')
  return db.execute('SELECT users.*,sessions.csrf,sessions.token FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?',(token,int(time.time()))).fetchone()
 def form(self,action,body,csrf):
  return f'<form action="{action}" method="post"><input type="hidden" name="csrf" value="{esc(csrf)}">{body}</form>'
 def page(self,title,body,user=None):
  nav='<a href="/">Pulpit</a>'
  if user:
   nav+=f'<span class="identity">{esc(user["username"])} · {dict(admin="administrator",teacher="nauczyciel",student="uczeń")[user["role"]]}</span>'
   nav+=self.form('/logout','<button class="ghost">Wyloguj</button>',user['csrf'])
  else:nav+='<a href="/join">Dołącz do klasy</a>'
  return f'''<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · KriBusiness</title><link rel="stylesheet" href="/static/style.css"><script src="/static/app.js" defer></script></head><body><header><a class="brand" href="/"><b>K</b> KriBusiness<span>LABORATORIUM BIZNESU</span></a><nav>{nav}</nav></header><main><div class="heading"><div class="eyebrow">TWOJA FIRMA. TWOJE DECYZJE.</div><h1>{esc(title)}</h1></div>{body}</main><footer>KriBusiness 1.1 · autorska szkolna symulacja biznesowa · kwoty i stawki są parametrami gry</footer></body></html>'''
 def public_csrf(self):
  cookies={}
  for part in self.headers.get('Cookie','').split(';'):
   if '=' in part:k,v=part.strip().split('=',1);cookies[k]=v
  token=cookies.get('kb_form','')
  if len(token)!=64:token=secrets.token_hex(32)
  return token
 def cookie(self,name,value,maxage):
  return f'{name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={maxage}'+('; Secure' if COOKIE_SECURE else '')
 def auth(self,u,role=None):
  if not u:raise Error('Zaloguj się, aby otworzyć tę stronę.',401)
  if role and u['role'] not in role:raise Error('Brak uprawnień.',403)
 def owned_game(self,db,u,gid):
  self.auth(u,('admin','teacher'))
  g=db.execute('SELECT * FROM games WHERE id=?',(gid,)).fetchone()
  if not g:raise Error('Nie znaleziono rozgrywki.',404)
  if u['role']!='admin' and g['teacher']!=u['id']:raise Error('To rozgrywka innego nauczyciela.',403)
  return g
 def company(self,db,u):
  self.auth(u,('student',))
  c=db.execute('SELECT companies.* FROM companies JOIN members ON members.company_id=companies.id WHERE members.user_id=?',(u['id'],)).fetchone()
  if not c:raise Error('Konto nie ma firmy.',404)
  return c,db.execute('SELECT * FROM games WHERE id=?',(c['game_id'],)).fetchone()
 def do_GET(self):
  path=urlparse(self.path).path
  try:
   if path=='/health':return self.send('{"status":"ok"}',typ='application/json')
   if path in ('/static/style.css','/static/app.js'):
    return self.send((ROOT/path.lstrip('/')).read_bytes(),typ='text/css; charset=utf-8' if path.endswith('css') else 'text/javascript; charset=utf-8')
   with connect() as db:
    u=self.session(db)
    if path in ('/login','/join') or (path=='/' and not u):
     csrf=self.public_csrf()
     if path=='/join':
      body='<p class="lead">Dołącz kodem klasy. Utwórz firmę albo wpisz kod zespołu otrzymany od współpracownika.</p>'
      fields=field('Kod klasy','class_code')+field('Twój login','username',attrs='minlength="3" maxlength="40" autocomplete="username"')+field('Twoje hasło (min. 12 znaków)','password',kind='password',attrs='minlength="12" autocomplete="new-password"')
      fields+='<label>Nazwa nowej firmy<input name="company_name" maxlength="60" placeholder="np. KripusTech"></label><label>Kod istniejącego zespołu (opcjonalnie)<input name="team_code" placeholder="Wpisz zamiast nazwy nowej firmy"></label><button>Dołącz do symulacji →</button>'
      body+='<section class="card narrow">'+self.form('/join',fields,csrf)+'</section>'
      title='Wejdź do gry'
     else:
      title='Zarządzanie zaczyna się tutaj'
      body='<p class="lead">Zbuduj ofertę, zatrudnij zespół i sprawdź, jak Twoja firma radzi sobie na rynku.</p><section class="card narrow">'+self.form('/login',field('Login','username',attrs='autocomplete="username" maxlength="40"')+field('Hasło','password',kind='password',attrs='autocomplete="current-password"')+'<button>Zaloguj się →</button>',csrf)+'<p>Uczeń? <a href="/join">Dołącz do klasy kodem</a>.</p></section>'
     return self.send(self.page(title,body,u),extra={'Set-Cookie':self.cookie('kb_form',csrf,3600)})
    self.auth(u)
    if path=='/':
     if u['role']=='student':return self.redirect('/company')
     return self.send(self.dashboard(db,u))
    if path=='/company':
     c,g=self.company(db,u);return self.send(self.company_page(db,u,c,g))
    if path.startswith('/game/'):
     try:gid=int(path.split('/')[2])
     except ValueError:raise Error('Błędny identyfikator.',404)
     g=self.owned_game(db,u,gid)
     if path.endswith('/export'):return self.export(db,g)
     return self.send(self.game_page(db,u,g))
    if path=='/ranking':
     c,g=self.company(db,u);return self.send(self.page('Ranking klasy',self.ranking(db,g),u))
    if path=='/report':
     c,g=self.company(db,u);return self.send(self.page('Raporty Twojej firmy',self.reports(db,c,g),u))
    raise Error('Nie znaleziono strony.',404)
  except Error as e:self.send(self.page('Nie można otworzyć strony',note(e.message)),e.status)
  except Exception:
   import traceback;traceback.print_exc();self.send(self.page('Błąd',note('Wystąpił błąd serwera.')),500)
 def dashboard(self,db,u):
  games=db.execute('SELECT * FROM games '+('' if u['role']=='admin' else 'WHERE teacher=? ')+'ORDER BY id DESC',() if u['role']=='admin' else (u['id'],)).fetchall()
  tiles=''
  for g in games:
   n=db.execute('SELECT COUNT(*) FROM companies WHERE game_id=?',(g['id'],)).fetchone()[0]
   tiles+=f'<a class="card game-tile" href="/game/{g["id"]}">{tag(self.status(g))}<h2>{esc(g["name"])}</h2><p>{esc(SCENARIOS[g["scenario"]]["name"])}</p><div class="tile-bottom">{n} firm <span>Runda {min(g["round"],g["total"])}/{g["total"]} →</span></div></a>'
  opts=''.join(f'<option value="{k}">{esc(v["name"])}</option>' for k,v in SCENARIOS.items())
  form=field('Nazwa klasy / rozgrywki','name',attrs='maxlength="80"')+f'<label>Scenariusz<select name="scenario">{opts}</select></label>'+field('Liczba rund','total',12,'number','min="1" max="24"')+'<button>Utwórz rozgrywkę</button>'
  body='<p class="lead">Przygotuj klasę, zaproś zespoły i zarządzaj kolejnymi miesiącami ich firm.</p><div class="grid games">'+tiles+'</div><section class="card"><h2>Nowa rozgrywka</h2>'+self.form('/games',form,u['csrf'])+'</section>'
  if u['role']=='admin':
   body+='<section class="card"><h2>Konto nauczyciela</h2>'+self.form('/teachers',field('Login nauczyciela','username',attrs='minlength="3" maxlength="40"')+field('Hasło (min. 12 znaków)','password',kind='password',attrs='minlength="12"')+'<button>Dodaj nauczyciela</button>',u['csrf'])+'</section>'
  return self.page('Panel prowadzącego',body,u)
 def status(self,g):return {'lobby':'Zapisy zespołów','active':'Decyzje otwarte','finished':'Zakończona'}[g['status']]
 def ranking(self,db,g):
  rows=[]
  for c in db.execute('SELECT * FROM companies WHERE game_id=?',(g['id'],)):
   s=json.loads(c['state']);last=db.execute('SELECT payload FROM results WHERE company_id=? ORDER BY round DESC LIMIT 1',(c['id'],)).fetchone();r=json.loads(last[0]) if last else {}
   rows.append((s['cash']+s['assets']-s['debt'],c,s,r))
  rows.sort(key=lambda x:(-x[0],x[1]['id']))
  table='<div class="table-wrap"><table><thead><tr><th>#</th><th>Firma</th><th>Kapitał własny</th><th>Gotówka</th><th>Dług</th><th>Zysk rundy</th><th>Reputacja</th></tr></thead><tbody>'
  for i,(score,c,s,r) in enumerate(rows,1):table+=f'<tr><td>{i}</td><td><strong>{esc(c["name"])}</strong></td><td>{cash(score)}</td><td>{cash(s["cash"])}</td><td>{cash(s["debt"])}</td><td class="{ "positive" if r.get("profit",0)>=0 else "negative"}">{cash(r.get("profit",0))}</td><td>{s["reputation"]:.0f}/100</td></tr>'
  return '<section class="card"><h2>Rynek Twojej klasy</h2><p>Ranking według kapitału własnego: gotówka + wartość księgowa wyposażenia − zadłużenie.</p>'+table+'</tbody></table></div></section>'
 def game_page(self,db,u,g):
  companies=db.execute('SELECT * FROM companies WHERE game_id=? ORDER BY id',(g['id'],)).fetchall()
  body=f'<p class="lead">{esc(SCENARIOS[g["scenario"]]["name"])} · runda {min(g["round"],g["total"])}/{g["total"]} · {esc(self.status(g))}</p>'
  if g['status']=='lobby':
   body+=f'<section class="card"><h2>Zaproś klasę</h2><p>Uczniowie otwierają <strong>/join</strong> na tym serwerze i wpisują kod:</p><div class="join-code">{esc(g["code"])}</div><p>Zapisy zamykają się po rozpoczęciu gry. Minimum dwie firmy.</p>'+self.form('/start',f'<input type="hidden" name="game" value="{g["id"]}"><button>Rozpocznij rundę 1</button>',u['csrf'])+'</section>'
  if g['status']=='active':
   body+='<section class="card"><h2>Gotowość zespołów</h2><div class="table-wrap"><table><tr><th>Firma</th><th>Zespół</th><th>Decyzje</th></tr>'
   for c in companies:
    d=db.execute('SELECT submitted FROM decisions WHERE company_id=? AND round=?',(c['id'],g['round'])).fetchone()
    members=db.execute('SELECT username FROM users JOIN members ON users.id=members.user_id WHERE company_id=?',(c['id'],)).fetchall()
    body+=f'<tr><td>{esc(c["name"])}</td><td>{esc(", ".join(m[0] for m in members))}</td><td>{tag("Upadłość" if json.loads(c['state']).get('bankrupt') else ("Zatwierdzone" if d and d[0] else "W trakcie"))}</td></tr>'
   opts=''.join(f'<option value="{k}" {"selected" if k==g["event"] else ""}>{esc(v[0])}</option>' for k,v in EVENTS.items())
   body+='</table></div><h3>Sytuacja gospodarcza</h3><p>Zdarzenie jest widoczne dla uczniów przed podjęciem decyzji. Zmiana zdarzenia cofa zatwierdzenia wszystkich zespołów.</p>'+self.form('/event',f'<input type="hidden" name="game" value="{g["id"]}"><select name="event">{opts}</select><button class="secondary">Ustaw zdarzenie</button>',u['csrf'])
   body+='<hr><p>Rozliczenie wymaga zatwierdzenia planu przez wszystkie firmy. Następna runda otworzy się automatycznie.</p>'+self.form('/advance',f'<input type="hidden" name="game" value="{g["id"]}"><input type="hidden" name="round" value="{g["round"]}"><label class="check"><input type="checkbox" required name="confirm" value="yes"> Potwierdzam rozliczenie tej rundy</label><button>Rozlicz rundę {g["round"]} →</button>',u['csrf'])+'</section>'
  body+=self.ranking(db,g)+f'<p><a class="button secondary" href="/game/{g["id"]}/export">Pobierz wszystkie wyniki CSV</a></p>'
  for c in companies:body+=f'<details class="card"><summary>Raporty: {esc(c["name"])}</summary>'+self.reports(db,c,g)+'</details>'
  logs=db.execute('SELECT action,created FROM audit WHERE game_id=? ORDER BY id DESC LIMIT 20',(g['id'],)).fetchall()
  body+='<details class="card"><summary>Dziennik rozgrywki</summary><ul>'+''.join(f'<li>{time.strftime("%Y-%m-%d %H:%M UTC",time.gmtime(a[1]))} — {esc(a[0])}</li>' for a in logs)+'</ul></details>'
  return self.page(g['name'],body,u)
 def company_page(self,db,u,c,g):
  s=SCENARIOS[g['scenario']];state=json.loads(c['state'])
  body=f'<p class="lead">{esc(g["name"])} · {esc(s["name"])} · runda {min(g["round"],g["total"])}/{g["total"]}</p><div class="tabs"><a href="/company" class="active">Decyzje</a><a href="/report">Raporty</a><a href="/ranking">Ranking</a></div>'
  body+='<div class="grid stats">'+''.join(f'<div class="card stat"><span>{label}</span><strong>{value}</strong></div>' for label,value in [('Gotówka',cash(state['cash'])),('Zadłużenie',cash(state['debt'])),('Reputacja',f'{state["reputation"]:.0f}/100'),('Stanowiska',str(state['equipment']))])+'</div>'
  if g['status']=='lobby':return self.page(c['name'],body+note('Nauczyciel jeszcze nie rozpoczął rozgrywki.')+f'<section class="card"><h2>Kod zespołu</h2><div class="join-code">{esc(c["code"])}</div><p>Podaj ten kod członkom swojej firmy razem z kodem klasy. Każdy otrzyma własny login. Maksymalnie 5 osób w firmie.</p></section>',u)
  if state.get('bankrupt'):return self.page(c['name'],body+note('Firma ogłosiła upadłość: nie wystarcza gotówki ani dostępnego kredytu na koszty kolejnego miesiąca. Jej udział w rynku zostaje wyłączony. Sprawdź raporty.'),u)
  if g['status']=='finished':return self.page(c['name'],body+note('Rozgrywka zakończona. Sprawdź raporty i ranking.')+self.ranking(db,g),u)
  row=db.execute('SELECT * FROM decisions WHERE company_id=? AND round=?',(c['id'],g['round'])).fetchone()
  previous=db.execute('SELECT payload FROM decisions WHERE company_id=? AND round<? ORDER BY round DESC LIMIT 1',(c['id'],g['round'])).fetchone()
  d=normalize(json.loads(row['payload'])) if row else continuing_decision(s,state,json.loads(previous[0]) if previous else None)
  revision=row['revision'] if row else 0
  submitted=row and row['submitted']
  body+=note('Plan zatwierdzony. Możesz cofnąć zatwierdzenie do czasu rozliczenia rundy.' if submitted else 'Zapisz plan, sprawdź prognozę kosztów, a następnie zatwierdź decyzje.')
  event=EVENTS[g['event']]
  body+=f'<section class="market-strip"><b>{esc(event[0])}</b><span>Popyt ×{event[1]} · koszt materiałów ×{event[2]}</span></section>'
  disabled='disabled' if submitted else ''
  offer='<section class="card"><h2>01 / Oferta i plan realizacji</h2><p>Planowana ilość to maksymalna liczba usług, które chcesz przygotować. Część może nie znaleźć klientów. Materiały kosztują także przy niesprzedanej usłudze.</p><div class="table-wrap"><table><tr><th>Usługa</th><th>Cena (zł)</th><th>Plan (szt.)</th><th>Dostawca zasobów</th><th>Koszt bazowy / czas</th></tr>'
  for i,x in enumerate(s['services']):
   supplier_options=''.join(f'<option value="{k}" {"selected" if k==d["suppliers"][i] else ""}>{esc(v["name"])} · koszt ×{v["cost"]} · jakość do {v["quality"]}%</option>' for k,v in SUPPLIERS.items())
   offer+=f'<tr><td><strong>{esc(x["name"])}</strong></td><td><input aria-label="Cena {esc(x["name"])}" type="number" name="price{i}" value="{d["prices"][i]}" min="{x["price"]*.25}" max="{x["price"]*4}" step="0.01" required></td><td><input aria-label="Ilość {esc(x["name"])}" type="number" name="quantity{i}" value="{d["quantities"][i]}" min="0" max="10000" step="1" required></td><td><select name="supplier{i}" aria-label="Dostawca {esc(x['name'])}">{supplier_options}</select></td><td>{cash(x["cost"])} / {x["hours"]} h<br><small>Popyt bazowy: {x["demand"]} na firmę</small></td></tr>'
  offer+='</table></div>'+field('Jakość usług (%)','quality',d['quality'],'number','min="20" max="100"')+'</section>'
  hr='<section class="card"><h2>02 / Ludzie i stanowiska</h2><p>Pracownik potrzebuje stanowiska. Jedno stanowisko kosztuje '+cash(s['equipment'])+'. Zakup pozostaje na kolejne rundy.</p><div class="grid inputs">'
  hr+=field('Docelowa liczba pracowników','employees',d['employees'],'number','min="0" max="30"')+field('Pensja za osobę (zł)','wage',d['wage'],'number',f'min="{s["wage"]*.8}" max="20000" step="0.01"')+field('Zakup nowych stanowisk','equipment',d['equipment'],'number','min="0" max="30"')+field('Budżet szkoleń (zł)','training',d['training'],'number','min="0" max="30000" step="0.01"')
  hr+='</div><p>160 h/osobę × wpływ pensji i kompetencji. Koszt pracodawcy: pensja × 1,20. Zwolnienie: 0,5 poprzedniej pensji odprawy. Kompetencje: '+str(round(state['skill']))+'/100.</p></section>'
  finance='<section class="card"><h2>03 / Marketing i finansowanie</h2><div class="grid inputs">'+field('Marketing (zł)','marketing',d['marketing'],'number','min="0" max="50000" step="0.01"')+field('Nowy kredyt (zł)','loan',d['loan'],'number','min="0" max="100000" step="0.01"')+field('Spłata kredytu (zł)','repay',d['repay'],'number','min="0" max="150000" step="0.01"')+'</div><p>Czynsz: '+cash(s['rent'])+'/rundę. Odsetki: 1%/rundę. Maksymalny dług: 150 000 zł. Podatek od dodatniego wyniku: 19%. Stawki są uproszczeniami dydaktycznymi.</p></section>'
  choices=''.join(f'<option value="{k}" {"selected" if k==d["bank"] else ""}>{esc(v["name"])} · {cash(v["fee"])} + {v["interest"]*100:g}% długu / rundę</option>' for k,v in BANKS.items())
  accounting_choices=''.join(f'<option value="{k}" {"selected" if k==d["accountant"] else ""}>{esc(v["name"])} · {cash(v["fee"])} + {cash(v["document"])} / dokument</option>' for k,v in ACCOUNTANTS.items())
  finance=finance.replace('</section>',f'<div class="grid inputs"><label>Bank<select name="bank">{choices}</select></label><label>Księgowość<select name="accountant">{accounting_choices}</select></label></div></section>')
  finance=finance.replace('Odsetki: 1%/rundę.','Odsetki według wybranego banku.')
  required=required_cash(d,s,state,g['event'])
  detail=costs(d,s,state,g['event'])
  preview=f'<section class="card"><h2>04 / Kontrola budżetu</h2><p>Gotówka z kredytem: <strong>{cash(state["cash"]+d["loan"])}</strong></p><p>Maksymalny wydatek przed sprzedażą: <strong>{cash(required)}</strong></p><p>Przeliczany po zapisaniu. Nie uwzględnia przyszłych przychodów ani podatku. Wynik sprzedaży zależy od decyzji innych firm.</p></section>'
  issues=warnings(d,s,state,g['event'])
  preview+='<section class="card"><h2>Lista ostrzeżeń</h2>'+('<ul>'+''.join('<li>'+esc(issue)+'</li>' for issue in issues)+'</ul>' if issues else '<p>Plan nie ma wykrytych ostrzeżeń. Wynik zależy od konkurencji.</p>')+f'<p>Księgowość: {cash(detail["accounting"])} ({detail["documents"]} dokumentów), opłata bankowa: {cash(detail["bank_fee"])}.</p></section>'
  controls=f'<input type="hidden" name="revision" value="{revision}">'+'<input type="hidden" name="round" value="'+str(g['round'])+'"><div class="actions"><button name="mode" value="draft" class="secondary">Zapisz i przelicz budżet</button><button name="mode" value="submit">Zatwierdź decyzje →</button></div>'
  if not state['equipment']:
   body+=note('Startujesz bez stanowisk. Kup je w sekcji Ludzie i stanowiska, aby pracownicy mogli realizować usługi; potem wpisz plan ilości w ofercie.')
  body+=self.form('/decision',f'<fieldset {disabled}>'+offer+hr+finance+preview+controls+'</fieldset>',u['csrf'])
  if submitted:body+=self.form('/unsubmit',f'<input type="hidden" name="revision" value="{revision}"><input type="hidden" name="round" value="{g["round"]}"><button class="secondary">Cofnij zatwierdzenie</button>',u['csrf'])
  return self.page(c['name'],body,u)
 def reports(self,db,c,g):
  reports=db.execute('SELECT * FROM results WHERE company_id=? ORDER BY round DESC',(c['id'],)).fetchall()
  if not reports:return note('Raporty pojawią się po rozliczeniu pierwszej rundy.')
  body=''
  for row in reports:
   r=json.loads(row['payload']);d=json.loads(db.execute('SELECT payload FROM decisions WHERE company_id=? AND round=?',(c['id'],row['round'])).fetchone()[0]);s=SCENARIOS[g['scenario']]
   body+=f'<section class="card"><h2>Miesiąc {row["round"]} · {esc(EVENTS[r["event"]][0])}</h2><div class="grid stats">'+''.join(f'<div class="stat"><span>{label}</span><strong>{value}</strong></div>' for label,value in [('Przychód',cash(r['revenue'])),('Zysk netto',cash(r['profit'])),('Gotówka',cash(r['cash'])),('Udział w popycie',str(r['share'])+'%')])+'</div><div class="table-wrap"><table><tr><th>Usługa</th><th>Plan</th><th>Możliwości</th><th>Sprzedaż</th><th>Cena</th><th>Popyt rynku</th></tr>'
   for i,x in enumerate(s['services']):body+=f'<tr><td>{esc(x["name"])}</td><td>{d["quantities"][i]}</td><td>{r["capacity"][i]}</td><td>{r["sales"][i]}</td><td>{cash(d["prices"][i])}</td><td>{r["demand"][i]}</td></tr>'
   body+='</table></div><h3>Rachunek wyników</h3><div class="table-wrap"><table>'
   labels=[('revenue','Przychody'),('wages','Wynagrodzenia i narzuty'),('materials','Materiały'),('rent','Czynsz'),('marketing','Marketing'),('training','Szkolenia'),('severance','Odprawy'),('interest','Odsetki'),('bank_fee','Opłata bankowa'),('accounting','Księgowość'),('depreciation','Amortyzacja'),('tax','Podatek'),('profit','Zysk netto'),('assets','Wartość księgowa wyposażenia'),('debt','Dług'),('equity','Kapitał własny')]
   body+=''.join(f'<tr><td>{label}</td><td>{cash(r.get(key,0))}</td></tr>' for key,label in labels)+'</table></div>'
   if 'cash_flow' in r:
    body+=f'<h3>Przepływy pieniężne</h3><p>Przepływ z działalności: {cash(r["revenue"]-r["costs"]-r["tax"])} · inwestycje: −{cash(r["investment"])} · kredyt: +{cash(d["loan"])} · spłata: −{cash(d["repay"])} · zmiana gotówki: <strong>{cash(r["cash_flow"])}</strong>.</p>'
    body+='<h3>Marża na usługach (przed kosztami stałymi)</h3><div class="table-wrap"><table><tr><th>Usługa</th><th>Przychód</th><th>Materiały</th><th>Marża kwotowa</th><th>Jakość</th></tr>'+''.join(f'<tr><td>{esc(x["name"])}</td><td>{cash(r["service_revenues"][i])}</td><td>{cash(r["material_costs"][i])}</td><td>{cash(r["service_revenues"][i]-r["material_costs"][i])}</td><td>{r["quality_realized"][i]}%</td></tr>' for i,x in enumerate(s['services']))+'</table></div>'
   body+='<h3>Co wpłynęło na wynik?</h3><ul>'
   if sum(r['capacity'])<sum(d['quantities']):body+='<li>Brak roboczogodzin lub stanowisk ograniczył realizację planu. Zwiększ zatrudnienie, kup stanowiska lub zmniejsz plan.</li>'
   if sum(r['sales'])<sum(r['capacity']):body+='<li>Część przygotowanych usług nie znalazła klientów. Sprawdź cenę, jakość, marketing i skalę planu.</li>'
   if r['profit']<0:body+='<li>Przychody nie pokryły kosztów. Porównaj marże usług i koszty stałe.</li>'
   body+=f'<li>Dostępne roboczogodziny: {r["hours"]}. Reputacja: {r["reputation"]:.1f}/100. Kompetencje: {r["skill"]:.1f}/100.</li><li>Gotówka i zysk różnią się: zakup stanowisk, kredyt i jego spłata zmieniają gotówkę, a amortyzacja zmienia wynik.</li></ul></section>'
  return body
 def export(self,db,g):
  buff=io.StringIO();buff.write('\ufeff');writer=csv.writer(buff,delimiter=';');writer.writerow(['firma','runda','przychod','koszty','amortyzacja','podatek','zysk','gotowka','dlug','kapital_wlasny','udzial_popytu','reputacja','zdarzenie'])
  for row in db.execute('SELECT companies.name,results.round,results.payload FROM results JOIN companies ON companies.id=results.company_id WHERE companies.game_id=? ORDER BY results.round,companies.id',(g['id'],)):
   r=json.loads(row[2]);name=row[0];name="'"+name if name.lstrip().startswith(('=','+','-','@')) or name.startswith(('\t','\r')) else name
   writer.writerow([name,row[1]]+[r[k] for k in ['revenue','costs','depreciation','tax','profit','cash','debt','equity','share','reputation','event']])
  return self.send(buff.getvalue(),typ='text/csv; charset=utf-8',extra={'Content-Disposition':f'attachment; filename="wyniki-{g["id"]}.csv"'})
 def do_POST(self):
  u=None
  try:
   path=urlparse(self.path).path
   try:length=int(self.headers.get('Content-Length','0'))
   except ValueError:raise Error('Nieprawidłowe żądanie.')
   if not 0<length<=32768:raise Error('Za duże lub puste żądanie.',413)
   if not self.headers.get('Content-Type','').startswith('application/x-www-form-urlencoded'):raise Error('Nieprawidłowy format.',415)
   data=parse_qs(self.rfile.read(length).decode(),keep_blank_values=True,max_num_fields=50)
   def f(k,default=''):return data.get(k,[default])[0]
   with connect() as db:
    db.execute('BEGIN IMMEDIATE')
    u=self.session(db)
    expected=self.public_csrf() if path in ('/login','/join') else (u['csrf'] if u else '')
    if not expected or not hmac.compare_digest(expected,f('csrf')):raise Error('Formularz wygasł. Odśwież stronę.',403)
    if path=='/login':
     key=(self.client_address[0],f('username').lower())
     with ATTEMPT_LOCK:
      now=time.time();attempts=[x for x in LOGIN_ATTEMPTS.get(key,[]) if now-x<900]
      if len(attempts)>=10:raise Error('Zbyt wiele prób. Spróbuj za 15 minut.',429)
      attempts.append(now);LOGIN_ATTEMPTS[key]=attempts
      if len(LOGIN_ATTEMPTS)>10000:
       for k in list(LOGIN_ATTEMPTS):
        if all(now-x>=900 for x in LOGIN_ATTEMPTS[k]):LOGIN_ATTEMPTS.pop(k,None)
     user=db.execute('SELECT * FROM users WHERE username=?',(f('username'),)).fetchone()
     if not user or not check_password(f('password'),user['password']):raise Error('Nieprawidłowy login lub hasło.',401)
     token=secrets.token_hex(32);db.execute('DELETE FROM sessions WHERE expires<?',(int(time.time()),))
     db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token,user['id'],secrets.token_hex(32),int(time.time())+43200))
     db.commit();return self.redirect('/',{'Set-Cookie':self.cookie('kb_session',token,43200)})
    if path=='/join':
     username=f('username').strip();password=f('password')
     if not 3<=len(username)<=40 or not all(x.isalnum() or x in '_-.' for x in username):raise Error('Login: 3–40 liter, cyfr lub znaków _-.')
     if not 12<=len(password)<=256:raise Error('Hasło musi mieć 12–256 znaków.')
     g=db.execute("SELECT * FROM games WHERE code=? AND status='lobby'",(f('class_code').strip().upper(),)).fetchone()
     if not g:raise Error('Błędny kod klasy albo zapisy są już zamknięte.')
     if f('team_code').strip():
      c=db.execute('SELECT * FROM companies WHERE game_id=? AND code=?',(g['id'],f('team_code').strip().upper())).fetchone()
      if not c:raise Error('Nieprawidłowy kod zespołu.')
      if db.execute('SELECT COUNT(*) FROM members WHERE company_id=?',(c['id'],)).fetchone()[0]>=5:raise Error('Zespół ma już pięć osób.')
      cid=c['id']
     else:
      name=f('company_name').strip()
      if not 1<=len(name)<=60:raise Error('Wpisz nazwę firmy (maks. 60 znaków).')
      if db.execute('SELECT COUNT(*) FROM companies WHERE game_id=?',(g['id'],)).fetchone()[0]>=40:raise Error('Limit 40 firm w klasie.')
      cid=db.execute('INSERT INTO companies(game_id,name,code,state) VALUES(?,?,?,?)',(g['id'],name,code(),json.dumps(initial_state()))).lastrowid
     uid=db.execute('INSERT INTO users(username,password,role) VALUES(?,?,?)',(username,hash_password(password),'student')).lastrowid
     db.execute('INSERT INTO members VALUES(?,?)',(uid,cid));db.commit();return self.redirect('/login')
    self.auth(u)
    if path=='/logout':
     db.execute('DELETE FROM sessions WHERE token=?',(u['token'],));db.commit();return self.redirect('/login',{'Set-Cookie':self.cookie('kb_session','',0)})
    if path=='/teachers':
     self.auth(u,('admin',));username=f('username').strip()
     if not 3<=len(username)<=40 or not all(x.isalnum() or x in '_-.' for x in username) or not 12<=len(f('password'))<=256:raise Error('Login: 3–40 znaków. Hasło: 12–256 znaków.')
     db.execute('INSERT INTO users(username,password,role) VALUES(?,?,?)',(username,hash_password(f('password')),'teacher'));db.commit();return self.redirect('/')
    if path=='/games':
     self.auth(u,('admin','teacher'))
     if not 1<=len(f('name').strip())<=80 or f('scenario') not in SCENARIOS:raise Error('Nieprawidłowa nazwa lub scenariusz.')
     try:total=int(f('total'))
     except ValueError:raise Error('Nieprawidłowa liczba rund.')
     if not 1<=total<=24:raise Error('Wybierz od 1 do 24 rund.')
     gid=db.execute('INSERT INTO games(teacher,name,code,scenario,total) VALUES(?,?,?,?,?)',(u['id'],f('name').strip(),code(),f('scenario'),total)).lastrowid
     audit(db,u,gid,'Utworzono rozgrywkę');db.commit();return self.redirect('/game/'+str(gid))
    if path in ('/start','/event','/advance'):
     try:gid=int(f('game'))
     except ValueError:raise Error('Błędna rozgrywka.')
     g=self.owned_game(db,u,gid);companies=db.execute('SELECT * FROM companies WHERE game_id=? ORDER BY id',(gid,)).fetchall()
     if path=='/start':
      if g['status']!='lobby' or len(companies)<2:raise Error('Potrzebne minimum dwie firmy, a gra musi być w fazie zapisów.')
      db.execute("UPDATE games SET status='active' WHERE id=?",(gid,));audit(db,u,gid,'Rozpoczęto rozgrywkę')
     elif path=='/event':
      if g['status']!='active' or f('event') not in EVENTS:raise Error('Nie można ustawić zdarzenia.')
      if f('event')!=g['event']:
       db.execute('UPDATE games SET event=? WHERE id=?',(f('event'),gid));db.execute('UPDATE decisions SET submitted=0,revision=revision+1 WHERE round=? AND company_id IN (SELECT id FROM companies WHERE game_id=?)',(g['round'],gid));audit(db,u,gid,'Zmieniono zdarzenie: '+EVENTS[f('event')][0])
     else:
      if g['status']!='active' or str(g['round'])!=f('round') or f('confirm')!='yes':raise Error('Runda została już rozliczona lub brak potwierdzenia.',409)
      decisions=[]
      for c in companies:
       if json.loads(c['state']).get('bankrupt'):
        inactive=default_decision(SCENARIOS[g['scenario']]);decisions.append(inactive)
        db.execute('INSERT OR IGNORE INTO decisions(company_id,round,payload,submitted) VALUES(?,?,?,1)',(c['id'],g['round'],json.dumps(inactive)));continue
       row=db.execute('SELECT * FROM decisions WHERE company_id=? AND round=?',(c['id'],g['round'])).fetchone()
       if not row or not row['submitted']:raise Error('Wszystkie firmy muszą zatwierdzić decyzje: '+c['name'],409)
       decisions.append(json.loads(row['payload']))
      results=simulate(SCENARIOS[g['scenario']],[json.loads(c['state']) for c in companies],decisions,g['round'],g['event'])
      for c,r in zip(companies,results):
       db.execute('INSERT INTO results VALUES(?,?,?)',(c['id'],g['round'],json.dumps(r)))
       state={k:r[k] for k in initial_state()};db.execute('UPDATE companies SET state=? WHERE id=?',(json.dumps(state),c['id']))
      db.execute("UPDATE games SET round=round+1,status=?,event='normal' WHERE id=?",('finished' if g['round']==g['total'] else 'active',gid))
      audit(db,u,gid,f'Rozliczono rundę {g["round"]}')
     db.commit();return self.redirect('/game/'+str(gid))
    if path in ('/decision','/unsubmit'):
     c,g=self.company(db,u)
     if json.loads(c['state']).get('bankrupt'):raise Error('Firma ogłosiła upadłość.',409)
     if g['status']!='active' or f('round')!=str(g['round']):raise Error('Runda została już zamknięta. Odśwież stronę.',409)
     existing=db.execute('SELECT submitted,revision FROM decisions WHERE company_id=? AND round=?',(c['id'],g['round'])).fetchone()
     if f('revision')!=str(existing['revision'] if existing else 0):raise Error('Plan zmienił się w innej karcie lub u członka zespołu. Odśwież stronę i ponownie sprawdź decyzje.',409)
     if path=='/unsubmit':
      db.execute('UPDATE decisions SET submitted=0,revision=revision+1 WHERE company_id=? AND round=?',(c['id'],g['round']))
     else:
      if existing and existing[0]:raise Error('Najpierw cofnij zatwierdzenie.',409)
      try:
       d={k:float(f(k)) for k in ['employees','wage','marketing','training','equipment','loan','repay','quality']}
       d['prices']=[float(f('price'+str(i))) for i in range(3)];d['quantities']=[float(f('quantity'+str(i))) for i in range(3)]
      except ValueError:raise Error('Wpisz liczby we wszystkich polach.')
      d.update(bank=f('bank','standard'),accountant=f('accountant','basic'),suppliers=[f('supplier'+str(i),'standard') for i in range(3)])
      try:d=validate(d,SCENARIOS[g['scenario']],json.loads(c['state']),g['event'],check_budget=f('mode')=='submit')
      except ValueError as e:raise Error(str(e))
      if f('mode') not in ('draft','submit'):raise Error('Błędny tryb zapisu.')
      db.execute('INSERT INTO decisions(company_id,round,payload,submitted,revision) VALUES(?,?,?,?,1) ON CONFLICT(company_id,round) DO UPDATE SET payload=excluded.payload,submitted=excluded.submitted,revision=decisions.revision+1',(c['id'],g['round'],json.dumps(d),int(f('mode')=='submit')))
      audit(db,u,g['id'],c['name']+(': zatwierdzono decyzje' if f('mode')=='submit' else ': zapisano szkic'))
     db.commit();return self.redirect('/company')
    raise Error('Nie znaleziono operacji.',404)
  except sqlite3.IntegrityError:self.send(self.page('Nie zapisano',note('Taki login lub nazwa firmy już istnieje. Wróć do formularza i wybierz inny.'),u),409)
  except Error as e:self.send(self.page('Nie zapisano',note(e.message)+'<p><a href="/">Wróć do pulpitu</a></p>',u),e.status)
  except (UnicodeDecodeError,ValueError):self.send(self.page('Nie zapisano',note('Nieprawidłowe dane formularza.'),u),400)
  except Exception:
   import traceback;traceback.print_exc();self.send(self.page('Błąd',note('Wystąpił błąd serwera. Dane nie zostały zapisane.'),u),500)

def run():
 init();port=int(os.getenv('SERVER_PORT',os.getenv('PORT','8080')))
 server=ThreadingHTTPServer(('0.0.0.0',port),Handler)
 def stop(sig,frame):threading.Thread(target=server.shutdown,daemon=True).start()
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 print(f'KriBusiness ready on 0.0.0.0:{port}',flush=True)
 try:server.serve_forever()
 finally:server.server_close()
if __name__=='__main__':run()
