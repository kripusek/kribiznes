"""Exercise the actual generated install script with fake Git and apt executables."""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class InstallationTests(unittest.TestCase):
 def install(self,url='',token='',existing=False):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
  server=root/'server';fakebin=root/'bin';fakebin.mkdir();server.mkdir()
  if existing:(server/'app.py').write_text('original user code')
  (fakebin/'apt-get').write_text('#!/bin/sh\nexit 0\n')
  (fakebin/'git').write_text('''#!/usr/bin/env python3
import os,sys,subprocess
from pathlib import Path
if os.getenv('GIT_TOKEN'):
 ask=os.environ['GIT_ASKPASS']
 assert subprocess.check_output([ask,'Username for github.com']).decode().strip()=='x-access-token'
 assert subprocess.check_output([ask,'Password for github.com']).decode().strip()==os.environ['GIT_TOKEN']
Path(os.environ['FAKE_ARGS']).write_text(' '.join(sys.argv))
target=Path(sys.argv[-1]);target.mkdir()
(target/'app.py').write_text('fixture app')
(target/'engine.py').write_text('fixture engine')
(target/'static').mkdir();(target/'static/style.css').write_text('fixture CSS')
''')
  for f in fakebin.iterdir():f.chmod(0o755)
  egg=json.loads((ROOT/'deploy/egg-kribusiness.json').read_text())
  script=egg['scripts']['installation']['script'].replace('/mnt/server',str(server))
  env=dict(os.environ,PATH=str(fakebin)+':'+os.environ['PATH'],GIT_REPOSITORY=url,GIT_BRANCH='main',GIT_TOKEN=token,FAKE_ARGS=str(root/'git-args'))
  result=subprocess.run(['bash'],input=script,text=True,capture_output=True,env=env)
  return result,server,root
 def test_manual_install_without_repo(self):
  result,server,_=self.install();self.assertEqual(result.returncode,0);self.assertIn('Manual installation',result.stdout)
 def test_private_repo_download_does_not_put_token_in_arguments(self):
  token='test-only-not-a-real-token'
  result,server,root=self.install('https://github.com/example/private.git',token)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertTrue((server/'app.py').exists());self.assertTrue((server/'static/style.css').exists())
  self.assertNotIn(token,result.stdout+result.stderr+(root/'git-args').read_text())
 def test_token_is_not_sent_to_another_host(self):
  result,server,root=self.install('https://example.com/repository.git','test-only-not-a-real-token')
  self.assertNotEqual(result.returncode,0);self.assertFalse((root/'git-args').exists())
 def test_existing_installation_is_preserved(self):
  result,server,_=self.install('https://github.com/example/repository.git',existing=True)
  self.assertEqual(result.returncode,0);self.assertEqual((server/'app.py').read_text(),'original user code')
