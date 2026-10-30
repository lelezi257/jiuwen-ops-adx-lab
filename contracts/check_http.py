"""Trusted oracle. Candidate code cannot modify this copy."""
import json,os,sys,time,uuid
import httpx,psycopg

def check(base):
 results=[]
 with httpx.Client(timeout=10,trust_env=False) as c:
  for coupon,want in [(None,20000),('SAVE10',18000),('',20000),(' save10 ',18000)]:
   payload={'quantity':2,'request_key':uuid.uuid4().hex}
   if coupon is not None:payload['coupon']=coupon
   r=c.post(base+'/orders',json=payload);assert r.status_code==200,(coupon,r.status_code,r.text)
   v=r.json();assert v['total_cents']==want,v
   saved=c.get(base+'/orders/'+v['id']);assert saved.status_code==200 and saved.json()['total_cents']==want and saved.json()['quantity']==2
   repeat=c.post(base+'/orders',json=payload);assert repeat.status_code==200 and repeat.json()==v
   conflict=c.post(base+'/orders',json={**payload,'quantity':3});assert conflict.status_code==409
   with psycopg.connect('host=db dbname=orders user=orders password='+os.environ['CONTRACT_DB_PASSWORD']) as database:
    stored=database.execute('SELECT id,quantity,total_cents FROM orders WHERE id=%s',(v['id'],)).fetchone()
    assert stored and stored[1]==2 and stored[2]==want,('Database persistence missing',stored)
   results.append({'coupon':coupon,'total_cents':want,'persisted':True,'idempotent':True})
  for body in [{'quantity':0},{'quantity':2,'coupon':'INVALID'}]:
   r=c.post(base+'/orders',json={**body,'request_key':uuid.uuid4().hex});assert r.status_code==422,r.text
 return {'passed':True,'cases':results,'invalid_inputs':True}
if __name__=='__main__':print(json.dumps(check(sys.argv[1]),ensure_ascii=False))
