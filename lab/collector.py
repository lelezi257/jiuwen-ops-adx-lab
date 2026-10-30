"""Read application JSONL volume and push actual log lines to Loki."""
import json,time
from pathlib import Path
import httpx
from lab.common import DATA
file=Path('/logs/order.jsonl');cursor=DATA/'cursor.json';offset=0;inode=None
if cursor.exists():
 saved=json.loads(cursor.read_text());offset=saved['offset'];inode=saved['inode']
while True:
 try:
  if file.exists():
   stat=file.stat()
   if inode!=stat.st_ino or stat.st_size<offset:offset=0;inode=stat.st_ino
   with file.open() as f:
    f.seek(offset);lines=[]
    for _ in range(100):
     line=f.readline()
     if not line:break
     event=json.loads(line);lines.append([str(int(float(event['time'])*1e9)),line.strip()])
    end=f.tell()
   if lines:
    r=httpx.post('http://loki:3100/loki/api/v1/push',json={'streams':[{'stream':{'service':'order-api'},'values':lines}]},timeout=10,trust_env=False);r.raise_for_status();offset=end;cursor.write_text(json.dumps({'offset':offset,'inode':inode}))
 except Exception as exc:print('collector retry:',type(exc).__name__,flush=True)
 time.sleep(1)
