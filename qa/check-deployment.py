"""Static deployment wiring checks. Requires PyYAML; does not run Docker."""
from pathlib import Path
import re
import yaml
root=Path(__file__).resolve().parents[1]
config=yaml.safe_load((root/'deploy/compose.yml').read_text())
services=config['services']
for name in ['database','cache','backend','frontend']:
    assert not services[name].get('ports'),f'{name} must remain private'
assert services['proxy']['ports']==['80:80','443:443']
backend=services['backend']['environment']
assert backend['DJANGO_SETTINGS_MODULE']=='config.production' and backend['DJANGO_DEBUG']=='0'
assert 'env_file' not in services['backend'] and 'POSTGRES_PASSWORD' not in backend
assert '${APP_DATABASE_PASSWORD:' in backend['DATABASE_URL']
assert services['backend']['depends_on']['migrate']['condition']=='service_completed_successfully'
assert '/api/ready/' in services['backend']['healthcheck']['test'][-1]
template=dict(line.split('=',1) for line in (root/'deploy/.env.production.example').read_text().splitlines() if line and not line.startswith('#'))
variables=set(re.findall(r'(?<!\$)\$\{([A-Z_]+)',(root/'deploy/compose.yml').read_text()))
assert variables <= template.keys(),f'Missing variables: {variables-template.keys()}'
for script in (root/'deploy').glob('*.sh'):
    assert b'\r' not in script.read_bytes(),f'{script.name} must use LF'
ignore=(root/'.dockerignore').read_text()
assert '**/.env*' in ignore and '**/*.sqlite3*' in ignore
print('Deployment wiring, private services, variable coverage and build-context exclusions passed.')
print('Docker image builds, PostgreSQL/Redis runtime and backup restoration require a Docker host.')
