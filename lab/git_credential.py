"""git credential helper: credentials go only to git's private pipe."""
import sys
from pathlib import Path
def secret(name):
 p=Path('/run/secrets')/name
 return p.read_text().strip() if p.exists() else ''
if len(sys.argv)>1 and sys.argv[1]=='get':
 fields=dict(line.rstrip('\n').split('=',1) for line in sys.stdin if '=' in line)
 if fields.get('host')=='github.com':print('username=x-access-token\npassword='+secret('github_token')+'\n')
