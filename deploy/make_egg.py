"""Generate a Pterodactyl PTDL_v2-compatible Pelican egg. No hosted repo required."""
import json
from pathlib import Path
variables=[
 ('Admin login','ADMIN_USERNAME','admin','required|string|min:3|max:40','Login administratora tworzony przy pierwszym starcie.'),
 ('Admin password','ADMIN_PASSWORD','','required|string|min:12|max:256','Ustaw własne hasło. Zmienna nie resetuje istniejącego konta. Minimum 12 znaków.'),
 ('HTTPS cookies','COOKIE_SECURE','false','required|in:true,false','true za reverse proxy z HTTPS; false przy lokalnym HTTP.'),
 ('Git repository (optional)','GIT_REPOSITORY','','nullable|string|max:300','Adres HTTPS repo z app.py w katalogu głównym. Prywatny GitHub wymaga GIT_TOKEN. Puste: prześlij pliki ręcznie.'),
 ('Private repository token (optional)','GIT_TOKEN','','nullable|string|max:512','Opcjonalny token GitHub z dostępem Contents: read do tego prywatnego repo. Wpisz w panelu, nigdy w URL repo.'),
 ('Repository branch','GIT_BRANCH','main','required|string|max:80','Gałąź repozytorium dla instalacji automatycznej.')]
install='''#!/bin/bash
set -euo pipefail
mkdir -p /mnt/server
cd /mnt/server
if [ -z "${GIT_REPOSITORY:-}" ]; then
 echo "Manual installation: upload app.py, engine.py and static/ to the server root before starting."
 exit 0
fi
case "$GIT_REPOSITORY" in https://*) ;; *) echo "Only public HTTPS Git URLs are supported"; exit 1;; esac
if [ -f /mnt/server/app.py ]; then
 echo "Existing application preserved. Upload updates manually; database is never deleted."
 exit 0
fi
apt-get update
apt-get install -y --no-install-recommends git ca-certificates
project_temp=$(mktemp -d)
trap 'rm -rf "$project_temp"' EXIT
if [ -n "${GIT_TOKEN:-}" ]; then
 case "$GIT_REPOSITORY" in https://github.com/*) ;; *) echo "Private token is supported only for github.com"; exit 1;; esac
 cat > "$project_temp/askpass" <<'ASKPASS'
#!/bin/sh
case "$1" in
 *Username*) printf '%s\\n' 'x-access-token' ;;
 *Password*) printf '%s\\n' "$GIT_TOKEN" ;;
 *) exit 1 ;;
esac
ASKPASS
 chmod 700 "$project_temp/askpass"
 export GIT_ASKPASS="$project_temp/askpass"
fi
export GIT_TERMINAL_PROMPT=0
git -c credential.helper= clone --depth 1 --single-branch --branch "${GIT_BRANCH:-main}" -- "$GIT_REPOSITORY" "$project_temp/source"
test -f "$project_temp/source/app.py"
test -f "$project_temp/source/engine.py"
test -d "$project_temp/source/static"
cp "$project_temp/source/app.py" "$project_temp/source/engine.py" /mnt/server/
cp -R "$project_temp/source/static" /mnt/server/
if [ -f "$project_temp/source/manage.py" ]; then cp "$project_temp/source/manage.py" /mnt/server/; fi
echo "KriBusiness installation complete"
'''
egg={
 '_comment':'Generated KriBusiness egg. Import into Pelican. PTDL_v2 compatibility format.',
 'meta':{'version':'PTDL_v2','update_url':None}, 'exported_at':'2026-10-02T12:00:00+00:00',
 'name':'KriBusiness - Classroom Business Simulator','author':'kripusek@users.noreply.github.com',
 'description':'Original classroom simulation. Python + SQLite; no pip dependencies. Upload project files to server root or set a Git URL (private GitHub supported with GIT_TOKEN). Set ADMIN_PASSWORD before first start.',
 'features':None,'docker_images':{'Python 3.12':'ghcr.io/parkervcp/yolks:python_3.12'},'file_denylist':[],
 'startup':'python -u app.py',
 'config':{'files':'{}','startup':json.dumps({'done':'KriBusiness ready on'}),'logs':'{}','stop':'^SIGTERM'},
 'scripts':{'installation':{'script':install,'container':'debian:bookworm-slim','entrypoint':'bash'}},
 'variables':[{'name':n,'description':desc,'env_variable':env,'default_value':v,'user_viewable':env not in ('ADMIN_PASSWORD','GIT_TOKEN'),'user_editable':True,'rules':rules,'field_type':'text'} for n,env,v,rules,desc in variables]
}
Path(__file__).with_name('egg-kribusiness-pterodactyl.json').write_text(json.dumps(egg,ensure_ascii=False,indent=2)+'\n')
egg['meta']['version']='PLCN_v3'
egg['uuid']='5c8c4515-2d10-4754-a976-a9af08d5c31f'
egg['tags']=['education','business','python']
egg['features']=[]
egg['startup_commands']={'Default':egg.pop('startup')}
for i,variable in enumerate(egg['variables'],1):
 variable['rules']=variable['rules'].split('|');variable['sort']=i;variable.pop('field_type')
Path(__file__).with_name('egg-kribusiness.json').write_text(json.dumps(egg,ensure_ascii=False,indent=2)+'\n')
