"""Supervise the original static Web server and our read-only transport."""
import subprocess,sys,time,signal
children=[]
def stop(*_):
 for child in children:
  if child.poll() is None:child.terminate()
 for child in children:
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:child.kill()
signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
try:
 children.append(subprocess.Popen([sys.executable,'-m','uvicorn','lab.native_observer:app','--host','127.0.0.1','--port','8081','--no-access-log']))
 children.append(subprocess.Popen([sys.executable,'-m','jiuwenswarm.channels.web.app_web','--host','0.0.0.0','--port','8080','--dist','/opt/jiuwen-native-web','--api-target','http://127.0.0.1:8081','--ws-target','ws://127.0.0.1:8081']))
 while all(child.poll() is None for child in children):time.sleep(.5)
 raise SystemExit('Native observer child exited')
finally:stop()
