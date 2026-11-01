"""Address discovery reads fixed firmware keys behind the usual HTTP boundary."""
import json, subprocess, unittest
from test_dpi_normalize import PHP, PUBLIC
from test_share_router_http import ShareRouterTests

class MtprotoAddressTests(unittest.TestCase):
 def collect(self, values):
  code="require $argv[1].'/mtproto-addresses.php';$v=json_decode(stream_get_contents(STDIN),true);$keys=[];$r=AsusMtprotoAddresses::collect(function($key)use($v,&$keys){$keys[]=$key;return $v[$key]??null;});echo json_encode(['result'=>$r,'keys'=>$keys]);"
  p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(values),text=True,capture_output=True)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);return json.loads(p.stdout)
 def test_distinct_router_and_ai_board_addresses_and_only_fixed_keys(self):
  v=self.collect({'lan_ipaddr':'192.168.50.1\n','ai_sys_ip_address':'192.168.50.232'})
  self.assertEqual(v['result'],{'router':'192.168.50.1','docker':'192.168.50.232'});self.assertEqual(v['keys'],['lan_ipaddr','ai_sys_ip_address'])
 def test_missing_invalid_and_interconnect_addresses_are_not_guessed(self):
  for value in [None,'','0.0.0.0','127.0.0.1','169.254.0.2','224.0.0.1','host;id','192.168.0.999']:
   self.assertEqual(self.collect({'lan_ipaddr':value,'ai_sys_ip_address':value})['result'],{'router':None,'docker':None})

class MtprotoAddressHttpTests(ShareRouterTests):
 def test_discovery_auth_csrf_origin_and_closed_fields(self):
  params={'cmd':'mtprotoaddresses','csrf_token':'bad'}
  self.assertEqual(self.request(params)[0],401);token=self.login()
  self.assertEqual(self.request(params)[0],403);params['csrf_token']=token
  self.origin='https://evil.invalid';self.assertEqual(self.request(params)[0],403);self.origin='http://localhost'
  self.assertEqual(self.request(params|{'host':'192.168.1.1'})[0],400)
  code,value=self.request(params);self.assertEqual(code,200);self.assertEqual(set(value),{'router','docker'})
