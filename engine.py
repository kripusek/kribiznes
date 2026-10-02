"""Original, deterministic classroom market model. All money is in PLN."""
import math
from decimal import Decimal, ROUND_HALF_UP
SCENARIOS = {
 'it': {'name':'Agencja IT', 'rent':2500, 'equipment':6000, 'wage':5200, 'services':[
  {'name':'Strony internetowe','price':2500,'cost':250,'hours':24,'demand':22},
  {'name':'Opieka techniczna','price':500,'cost':60,'hours':5,'demand':90},
  {'name':'Kampanie internetowe','price':1200,'cost':160,'hours':12,'demand':42}]},
 'restaurant': {'name':'Restauracja', 'rent':4000, 'equipment':8000, 'wage':4800, 'services':[
  {'name':'Obiady','price':45,'cost':15,'hours':0.3,'demand':1500},
  {'name':'Catering','price':900,'cost':300,'hours':8,'demand':35},
  {'name':'Desery','price':22,'cost':6,'hours':0.12,'demand':1300}]},
 'workshop': {'name':'Warsztat samochodowy', 'rent':3000, 'equipment':10000, 'wage':5500, 'services':[
  {'name':'Przeglądy','price':250,'cost':30,'hours':2,'demand':150},
  {'name':'Naprawy','price':900,'cost':250,'hours':6,'demand':60},
  {'name':'Wymiana opon','price':160,'cost':15,'hours':1,'demand':180}]}
}
EVENTS = {'normal':('Stabilny rynek',1,1), 'boom':('Wzrost gospodarczy',1.25,1),
 'crisis':('Spadek popytu',0.75,1), 'energy':('Droższe materiały i energia',1,1.2)}

# Parameters belong to this original educational model, not to real banking/tax rules.
BANKS = {
    'standard': {'name': 'Prosty rachunek', 'fee': 0, 'interest': .01},
    'growth': {'name': 'Rozwój', 'fee': 150, 'interest': .008},
    'credit': {'name': 'Kredyt Plus', 'fee': 350, 'interest': .005},
}
ACCOUNTANTS = {
    'basic': {'name': 'Biuro podstawowe', 'fee': 100, 'document': 20},
    'plus': {'name': 'Biuro Plus', 'fee': 300, 'document': 8},
}
SUPPLIERS = {
    'budget': {'name': 'Ekonomiczny', 'cost': .8, 'quality': 55},
    'standard': {'name': 'Standard', 'cost': 1, 'quality': 80},
    'premium': {'name': 'Premium', 'cost': 1.25, 'quality': 100},
}

def money(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

def normalize(d):
    """Backward-compatible defaults; never mutate saved decisions."""
    return dict(d, bank=d.get('bank', 'standard'), accountant=d.get('accountant', 'basic'),
                suppliers=list(d.get('suppliers', ['standard'] * 3)))

def default_decision(s):
    return dict(employees=2, wage=s['wage'], marketing=1000, training=0, equipment=0,
                loan=0, repay=0, quality=60, bank='standard', accountant='basic',
                suppliers=['standard']*3, prices=[x['price'] for x in s['services']],
                quantities=[0, 0, 0])

def continuing_decision(s, old, previous=None):
    d = normalize(previous or default_decision(s))
    if previous:
        d.update(employees=int(old['employees']), wage=old.get('wage') or s['wage'],
                 equipment=0, loan=0, repay=0, training=0)
    return d

def costs(d, s, old, event='normal', quantities=None):
    d = normalize(d)
    q = d['quantities'] if quantities is None else quantities
    supplier_costs = [money(n*x['cost']*(.7+d['quality']/100*.6)*EVENTS[event][2]*
                           SUPPLIERS[v]['cost']) for n,x,v in zip(q,s['services'],d['suppliers'])]
    # Payroll and service sales are aggregated into documents; customers are not individual invoices here.
    documents = int(d['employees']) + sum(n>0 for n in q) + int(d['equipment']>0) + int(d['loan']>0) + int(d['repay']>0)
    accountant = ACCOUNTANTS[d['accountant']]
    debt = money(old['debt']+d['loan']-d['repay'])
    items = dict(wages=money(d['employees']*d['wage']*1.2), rent=money(s['rent']),
                 marketing=money(d['marketing']), training=money(d['training']),
                 severance=money(max(0,old['employees']-d['employees'])*(old.get('wage') or s['wage'])*.5),
                 materials=money(sum(supplier_costs)), interest=money(debt*BANKS[d['bank']]['interest']),
                 bank_fee=money(BANKS[d['bank']]['fee']),
                 accounting=money(accountant['fee']+documents*accountant['document']))
    return dict(items, documents=documents, material_costs=supplier_costs, debt=debt,
                operating=money(sum(items.values())), investment=money(d['equipment']*s['equipment']))

def outlay(d, s, old):
    c = costs(d,s,old)
    return money(c['operating']-c['materials']-c['interest']+c['investment']+d['repay'])

def required_cash(d,s,old,event='normal'):
    c=costs(d,s,old,event)
    return money(c['operating']+c['investment']+d['repay'])

def validate(d,s,old,event='normal',check_budget=True):
    d=normalize(d)
    if event not in EVENTS: raise ValueError('Nieprawidłowe zdarzenie.')
    limits={'employees':(0,30),'wage':(s['wage']*.8,20000),'marketing':(0,50000),'training':(0,30000),
            'equipment':(0,30),'loan':(0,100000),'repay':(0,150000),'quality':(20,100)}
    for k,(lo,hi) in limits.items():
        v=d.get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:
            raise ValueError('Nieprawidłowe pole: '+k)
        if k not in ('employees','equipment','quality') and abs(v-money(v))>1e-7:
            raise ValueError('Kwoty podawaj z dokładnością do grosza: '+k)
    for k in ('employees','equipment'):
        if int(d[k])!=d[k]: raise ValueError('Liczba osób i stanowisk musi być całkowita.')
    for key in ('prices','quantities','suppliers'):
        if not isinstance(d.get(key),list) or len(d[key])!=3: raise ValueError('Wymagane trzy usługi.')
    if d['bank'] not in BANKS or d['accountant'] not in ACCOUNTANTS or any(v not in SUPPLIERS for v in d['suppliers']):
        raise ValueError('Nieprawidłowy bank, dostawca lub biuro rachunkowe.')
    for i,x in enumerate(s['services']):
        p,q=d['prices'][i],d['quantities'][i]
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (p,q)):
            raise ValueError('Błędna oferta.')
        if not x['price']*.25<=p<=x['price']*4 or not 0<=q<=10000 or int(q)!=q or abs(p-money(p))>1e-7:
            raise ValueError('Cena lub ilość poza zakresem; ceny podawaj w groszach.')
    if money(old['debt']+d['loan'])>150000 or d['repay']>money(old['debt']+d['loan']):
        raise ValueError('Limit zadłużenia: 150 000 zł. Spłata nie może przekroczyć długu.')
    if check_budget and required_cash(d,s,old,event)>money(old['cash']+d['loan']):
        raise ValueError('Za mało gotówki na ten plan. Zmniejsz koszty lub weź kredyt.')
    return d

def capacity(d,s,old):
    skill=min(100,old['skill']+(d['training']/d['employees']/150 if d['employees'] else 0))
    morale=max(.65,min(1.15,d['wage']/s['wage']))
    hours=min(d['employees'],old['equipment']+d['equipment'])*160*morale*(.7+skill/200)
    need=sum(q*x['hours'] for q,x in zip(d['quantities'],s['services']))
    factor=min(1,hours/need) if need else 1
    return dict(skill=skill, morale=money(morale*100), hours=hours,
                caps=[math.floor(q*factor+1e-9) for q in d['quantities']])

def warnings(d,s,old,event='normal'):
    d=normalize(d);p=capacity(d,s,old);issues=[]
    if required_cash(d,s,old,event)>money(old['cash']+d['loan']):issues.append('Budżet przekroczony: szkic można zapisać, ale nie zatwierdzić.')
    if sum(d['quantities'])==0:issues.append('Nie zaplanowano żadnej usługi: nie będzie przychodów ze sprzedaży.')
    if d['employees']>old['equipment']+d['equipment']:issues.append('Część pracowników nie ma stanowiska pracy.')
    if sum(p['caps'])<sum(d['quantities']):issues.append('Za mało roboczogodzin: nie zrealizujesz całego planu.')
    if d['training'] and not d['employees']:issues.append('Brak pracowników: szkolenie będzie kosztem bez wzrostu kompetencji.')
    for i,v in enumerate(d['suppliers']):
        if d['quantities'][i] and d['quality']>SUPPLIERS[v]['quality']:
            issues.append(s['services'][i]['name']+': dostawca ograniczy jakość do '+str(SUPPLIERS[v]['quality'])+'%.')
    return issues

def can_continue(s,state):
    """Check a genuinely affordable next plan, including layoffs and interest on new credit."""
    loan=money(min(100000,max(0,150000-state['debt'])))
    available=money(state['cash']+loan)
    for n in range(int(state['employees'])+1):
        for bank in BANKS:
            for accountant in ACCOUNTANTS:
                d=default_decision(s)
                d.update(employees=n,wage=s['wage']*.8,marketing=0,loan=loan,bank=bank,accountant=accountant)
                if required_cash(d,s,state)<=available:return True
    return False

def distribute(total,weights,caps):
    awards=[0]*len(weights)
    while total>0:
        active=[i for i in range(len(weights)) if awards[i]<caps[i] and weights[i]>0]
        if not active:break
        denom=sum(weights[i] for i in active)
        desired={i:total*weights[i]/denom for i in active}
        moved=0
        for i in active:
            n=min(caps[i]-awards[i],int(desired[i]));awards[i]+=n;moved+=n
        total-=moved
        if total<=0:break
        for i in sorted(active,key=lambda i:(-(desired[i]%1),i)):
            if total and awards[i]<caps[i]:awards[i]+=1;total-=1
    return awards

def simulate(s,companies,decisions,round_no,event='normal'):
    if len(companies)!=len(decisions):raise ValueError('Brak decyzji.')
    decisions=[normalize(d) for d in decisions]
    plans=[];dm=EVENTS[event][1]
    for c,d in zip(companies,decisions):
        if c.get('bankrupt',False):
            plans.append({'skill':c['skill'],'hours':0,'morale':0,'caps':[0,0,0],'sales':[0,0,0],'qualities':[0,0,0]});continue
        validate(d,s,c,event)
        plans.append(dict(capacity(d,s,c),sales=[0,0,0],
                          qualities=[min(d['quality'],SUPPLIERS[v]['quality']) for v in d['suppliers']]))
    demands=[]
    for j,x in enumerate(s['services']):
        demand=round(x['demand']*len(companies)*dm*(1+.08*math.sin(round_no*1.7+j)))
        demands.append(demand);weights=[]
        for c,d,p in zip(companies,decisions,plans):
            if c.get('bankrupt',False) or p['caps'][j]==0:weights.append(0);continue
            weights.append((x['price']/d['prices'][j])**1.5*(.4+p['qualities'][j]/100)*(.5+c['reputation']/100)*
                           (1+math.log1p(d['marketing']/500)*.25)*(.7+p['skill']/200))
        total_weight=sum(weights)
        acceptance=sum(w*min(1,(x['price']/d['prices'][j])**1.8*(.7+p['qualities'][j]/200))
                       for w,d,p in zip(weights,decisions,plans))/total_weight if total_weight else 0
        sales=distribute(round(demand*acceptance),weights,[p['caps'][j] for p in plans])
        for p,n in zip(plans,sales):p['sales'][j]=n
    results=[]
    for c,d,p in zip(companies,decisions,plans):
        if c.get('bankrupt',False):
            r=dict(c)
            r.update({k:0 for k in ['revenue','costs','wages','materials','rent','marketing','training','interest','severance','depreciation','tax','profit','bank_fee','accounting','documents','investment','cash_flow']})
            r.update(equity=money(c['cash']+c['assets']-c['debt']),sales=[0]*3,capacity=[0]*3,hours=0,
                     demand=demands,event=event,share=0,quality_realized=[0]*3,material_costs=[0]*3,
                     service_revenues=[0]*3,bank=d['bank'],accountant=d['accountant'],wage=c.get('wage',0))
            results.append(r);continue
        cost=costs(d,s,c,event,p['caps'])
        service_revenues=[money(n*price) for n,price in zip(p['sales'],d['prices'])]
        revenue=money(sum(service_revenues))
        depreciation=money(min(c['assets']+cost['investment'],(c['equipment']+d['equipment'])*s['equipment']*.02))
        before_tax=money(revenue-cost['operating']-depreciation)
        tax=money(max(0,before_tax)*.19);profit=money(before_tax-tax)
        cash=money(c['cash']+revenue-cost['operating']-tax-cost['investment']+d['loan']-d['repay'])
        book=money(c['assets']+cost['investment']-depreciation)
        delivered_quality=sum(n*q for n,q in zip(p['sales'],p['qualities']))/max(1,sum(p['sales']))
        reputation=c['reputation'] if sum(p['sales'])==0 else max(10,min(100,c['reputation']*.8+(delivered_quality*.7+p['skill']*.3)*.2))
        r=dict(cost,revenue=revenue,costs=cost['operating'],depreciation=depreciation,tax=tax,profit=profit,
               cash=cash,assets=book,equity=money(cash+book-cost['debt']),cash_flow=money(cash-c['cash']),
               employees=int(d['employees']),wage=d['wage'],equipment=int(c['equipment']+d['equipment']),
               skill=p['skill'],reputation=reputation,morale=p['morale'],quality_realized=p['qualities'],
               sales=p['sales'],capacity=p['caps'],hours=round(p['hours'],1),demand=demands,event=event,
               share=money(sum(p['sales'])/max(1,sum(demands))*100),service_revenues=service_revenues,
               bank=d['bank'],accountant=d['accountant'])
        r['bankrupt']=not can_continue(s,r)
        results.append(r)
    return results
