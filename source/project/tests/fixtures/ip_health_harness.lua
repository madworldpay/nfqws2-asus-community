-- The actual 1.0.7 engine supplies parsing, address conversion, reconstruction
-- and checksums.  Only kernel sends and time scheduling are replaced here.
now=1800000000
sent={}
send_ok=true
local timers={}
clock_gettime=function() local sec=math.floor(now); return sec,math.floor((now-sec)*1000000000+.5) end
timer_set=function(name, callback, milliseconds, oneshot, data)
 timers[name]={callback=callback,period=milliseconds/1000,oneshot=oneshot,data=data,next=now+milliseconds/1000}
 return true
end
raw_packet=function(ctx) return ctx.raw end
rawsend_dissect=function(dis,opts,reconstruction)
 local raw=reconstruct_dissect(dis,reconstruction)
 assert(raw,"invalid emitted packet")
 sent[#sent+1]={dis=deepcopy(dis),opts=opts,raw=raw}
 return send_ok
end
function advance(seconds)
 local target=now+seconds
 while true do
  local nexttime=nil
  for _,t in pairs(timers) do if t.next<=target+.000001 and (not nexttime or t.next<nexttime) then nexttime=t.next end end
  if not nexttime then break end
  now=nexttime
  for name,t in pairs(timers) do
   if t.next<=now+.000001 then
    if t.oneshot then timers[name]=nil else t.next=t.next+t.period end
    local f=type(t.callback)=="string" and _G[t.callback] or t.callback; f(name,t.data)
   end
  end
 end
 now=target
end
function write_manifest(data) local f=assert(io.open(IPHEALTH_MANIFEST,"wb")); f:write(data); f:close() end
function manifest(ips,enabled)
 local s="IPHEALTH1\nexpires "..(math.floor(now)+15).."\nenabled "..(enabled==false and 0 or 1).."\n"
 for _,ip in ipairs(ips or {}) do s=s.."ban "..ip.." "..(math.floor(now)+86400).."\n" end
 write_manifest(s)
end
function events() local f=io.open(WRITABLE.."/events.log","rb"); if not f then return "" end; local s=f:read("*a"); f:close(); return s end
function write_events(s) local f=assert(io.open(WRITABLE.."/events.log","wb")); f:write(s); f:close() end
function lines(s) local _,n=s:gsub("\n",""); return n end
function load_health() dofile(IPHEALTH_SOURCE.."/dns.lua"); dofile(IPHEALTH_SOURCE.."/monitor.lua") end
function tcp(outgoing,ip,port)
 ip=ip or "8.8.8.8"; port=port or 45000
 local server=assert(pton(ip)); local client=assert(pton(#server==4 and "192.168.50.2" or "fd00::2"))
 local dis={payload="",tcp={th_sport=port,th_dport=443,th_seq=100,th_ack=200,th_flags=TH_ACK,th_win=65535,th_urp=0,options={}}}
 if #server==4 then dis.ip={ip_v=4,ip_hl=5,ip_tos=0,ip_len=40,ip_id=123,ip_off=0,ip_ttl=64,ip_p=6,ip_sum=0,ip_src=client,ip_dst=server}
 else dis.ip6={ip6_flow=0x60000000,ip6_plen=20,ip6_nxt=6,ip6_hlim=64,ip6_src=client,ip6_dst=server} end
 if not outgoing then dis_reverse(dis) end
 return {outgoing=outgoing,dis=dis,fwmark=0x123,arg={},track={hostname="www.example.com",hostname_is_ip=false,t_start=1800000000,lua_state={}}}
end
function udp(outgoing,ip)
 local d=tcp(outgoing,ip); local sport,dport=d.dis.tcp.th_sport,d.dis.tcp.th_dport
 d.dis.tcp=nil; d.dis.udp={uh_sport=sport,uh_dport=dport,uh_ulen=12,uh_sum=0}; d.dis.payload="quic"
 if d.dis.ip then d.dis.ip.ip_p=17 else d.dis.ip6.ip6_nxt=17 end
 return d
end
-- Structurally complete ClientHello with a real SNI extension.
local hname="www.example.com"
local sni=bu16(#hname+3).."\0"..bu16(#hname)..hname
local ext=bu16(0)..bu16(#sni)..sni
local hs="\3\3"..string.rep("x",32).."\0"..bu16(2).."\19\1".."\1\0"..bu16(#ext)..ext
hello="\22\3\1"..bu16(#hs+4).."\1"..bu24(#hs)..hs
function dns_answer(ips,cname,family)
 family=family or 1
 local q="\3www\7example\3com\0"..bu16(family)..bu16(1)
 local answers=""
 if cname then answers="\192\12"..bu16(5)..bu16(1)..bu32(60)..bu16(8).."\5alias\192\16" end
 for _,ip in ipairs(ips) do
  local addr=assert(pton(ip)); local name=cname and "\5alias\192\16" or "\192\12"
  answers=answers..name..bu16(#addr==4 and 1 or 28)..bu16(1)..bu32(60)..bu16(#addr)..addr
 end
 return bu16(123)..bu16(0x8180)..bu16(1)..bu16(#ips+(cname and 1 or 0))..bu16(0)..bu16(0)..q..answers
end
function dns_packet(payload)
 local d=udp(false); d.dis.ip.ip_src=pton("192.168.50.1"); d.dis.udp.uh_sport=53; d.dis.payload=payload
 return d
end
function checksum(s)
 if #s%2~=0 then s=s.."\0" end
 local sum=0; for p=1,#s,2 do sum=sum+u16(s,p) end
 while sum>65535 do sum=sum%65536+math.floor(sum/65536) end
 return (65535-sum)%65536
end
function l4_checksum(raw)
 local version=math.floor(raw:byte(1)/16)
 if version==4 then
  local len=(raw:byte(1)%16)*4; local proto=raw:byte(10); local l4=raw:sub(len+1)
  if proto==1 then return checksum(l4) end
  return checksum(raw:sub(13,20).."\0"..string.char(proto)..bu16(#l4)..l4)
 end
 local l4=raw:sub(41)
 return checksum(raw:sub(9,40)..bu32(#l4).."\0\0\0"..raw:sub(7,7)..l4)
end
