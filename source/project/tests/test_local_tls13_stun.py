"""The packaged predicate runs in every pinned official 1.0.7 engine."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
ENGINES=os.environ.get('NFQWS_TEST_ENGINE_DIR')
QEMU=os.environ.get('NFQWS_TEST_QEMU_DIR')
FAMILIES={'arm':('armv7','arm'),'arm64':('aarch64','aarch64'),'mips':('mips','mips'),
          'mipsel':('mipsel','mipsel'),'mips64':('mips64','mips64'),'x86':('x86','i386'),'x86_64':('x86_64',None)}

LUA_CASES=r'''
local function b16(n) return string.char(math.floor(n/256),n%256) end
local function b24(n) return string.char(math.floor(n/65536),math.floor(n/256)%256,n%256) end
local function record(body) return string.char(22,3,1)..b16(#body)..body end
local function message(extensions)
 local body=string.char(3,3)..string.rep("R",32)..string.char(0)..b16(2)..b16(0x1301)..string.char(1,0)..b16(#extensions)..extensions
 return string.char(1)..b24(#body)..body
end
local function versions(raw) return b16(43)..b16(#raw)..raw end
local v13=message(versions(string.char(4)..b16(0x0304)..b16(0x0303)))
local v12=message(versions(string.char(2)..b16(0x0303)))
local function ds(raw) return {dis={payload=raw},reasm_data=raw,track={lua_state={}}} end
local function check(value,wanted,name)
 local ok,result=pcall(nfqws_local_offers_tls13,value)
 assert(ok,name.." raised an exception: "..tostring(result))
 assert(result==wanted,name.." returned "..tostring(result))
end
check(ds(record(v13)),true,"TLS1.3 offer")
check(ds(record(v12)),false,"TLS1.2 offer")
check(ds(record(message(""))),false,"no versions extension")
check(ds(v13),true,"pure ClientHello handshake")
check(ds(record(message(versions(string.char(4)..b16(0x0a0a)..b16(0x0304))))),true,"GREASE version")
check(ds("garbage\0\43\0\3\2\3\4"),false,"not a magic byte scan")
for n=0,#record(v13)-1 do check(ds(record(v13):sub(1,n)),false,"truncated hello "..n) end
local partial=ds(record(v13):sub(1,18))
check(partial,false,"partial flow")
assert(partial.track.lua_state.nfqws_local_tls13==nil,"partial input poisoned flow cache")
partial.reasm_data=record(v13);check(partial,true,"completed flow")
partial.reasm_data="later packet";check(partial,true,"boolean cache")
check(nil,false,"nil context");check("bad",false,"string context")
check({track=true,reasm_data=record(v13)},false,"non-table track")
check({track={lua_state=true},reasm_data=record(v13)},false,"non-table state")
check({track={lua_state={nfqws_local_tls13="yes"}},reasm_data=record(v13)},false,"non-boolean cache")
check({dis=true},false,"non-table dissect")
check(ds(string.rep("X",70000)),false,"bounded input")
check(ds(record(message(versions(string.char(3)..b16(0x0304).."X")))),false,"odd version vector")
check(ds(record(message(versions(string.char(2)..b16(0x0304).."X")))),false,"version extension trailing byte")
check(ds(record(message(versions(string.char(2)..b16(0x0304)).."X"))),false,"truncated next extension")
check(ds(record(message(versions(string.char(2)..b16(0x0304))..versions(string.char(2)..b16(0x0304))))),false,"duplicate versions extension")
local flow=ds(record(v12));check(flow,false,"TLS1.2 cached result");assert(flow.track.lua_state.nfqws_local_tls13==false)
assert(flow.reasm_data==record(v12) and flow.dis.payload==record(v12),"predicate mutated packet bytes")
print("LOCAL_TLS13_STUN_OK")
'''


@unittest.skipUnless(ENGINES and QEMU,'Requires the verified 1.0.7 engines and qemu-user')
class LocalTls13PredicateTests(unittest.TestCase):
    def test_valid_and_malformed_client_hello_in_all_official_engine_families(self):
        records=json.loads((ROOT/'openwrt/assets.json').read_text())['engines']
        with tempfile.TemporaryDirectory(prefix='local-tls13-lua-') as folder:
            script=Path(folder)/'case.lua';script.write_text(LUA_CASES)
            for family,(name,emulator) in FAMILIES.items():
                with self.subTest(family=family):
                    engine=Path(ENGINES)/('nfqws2-'+name)
                    self.assertEqual(hashlib.sha256(engine.read_bytes()).hexdigest(),records[family]['unpacked_sha256'])
                    command=([str(Path(QEMU)/('qemu-'+emulator))] if emulator else [])+[str(engine)]
                    version=subprocess.check_output(command+['--version'],text=True,timeout=20)
                    self.assertIn('v1.0.7 (038c97e5819df10f8e8c22a2f1fffe57f2f7379b)',version)
                    if os.geteuid()!=0:command=['sudo','-n']+command
                    args=['--intercept=0',f'--uid={os.getuid()}:{os.getgid()}',
                          '--lua-init=@'+str(Path(ENGINES)/'lua/zapret-lib.lua'),
                          '--lua-init=@'+str(ROOT/'asus/lua/local-tls13-stun.lua')]
                    # Matched old/new official MIPS64 engines also SIGBUS with
                    # unrelated LuaJIT packet tests under this qemu-user build.
                    # This interpreter-only diagnostic never enters packages.
                    if family=='mips64':args+=['--lua-init=jit.off()']
                    result=subprocess.run(command+args+['--lua-init=@'+str(script)],capture_output=True,text=True,timeout=20)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertIn('LOCAL_TLS13_STUN_OK',result.stdout)
