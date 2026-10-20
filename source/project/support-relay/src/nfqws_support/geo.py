"""Optional coarse GeoIP from a local MMDB only; never a remote IP lookup."""
from collections import OrderedDict,deque
from hashlib import sha256
import hmac,ipaddress,os,re,stat,threading,time
from pathlib import Path

def _reader(path):
    import maxminddb
    # mmap avoids loading the ~120 MiB database into each worker's heap.
    return maxminddb.open_database(str(path),mode=maxminddb.MODE_MMAP)

class GeoLookup:
    def __init__(self,path='/var/lib/nfqws-support/geo/dbip-city-lite.mmdb',*,reader_factory=_reader,clock=time.time,owner=0,lookup_limit=60):
        self.path=Path(path);self.factory=reader_factory;self.clock=clock;self.owner=owner;self.limit=lookup_limit
        self._reader=None;self._stamp=None;self._epoch=0;self._cache=OrderedDict();self._recent=deque();self._key=os.urandom(32);self._lock=threading.Lock()
    def _load(self,now):
        try:
            if not self.path.is_absolute() or any(p.is_symlink() for p in [self.path,*self.path.parents]):return False
            st=self.path.stat()
            if not stat.S_ISREG(st.st_mode) or st.st_uid!=self.owner or st.st_nlink!=1 or st.st_mode&0o022 or not 0<st.st_size<=192*1024*1024:return False
            stamp=(st.st_dev,st.st_ino,st.st_mtime_ns,st.st_size)
            if stamp!=self._stamp:
                if self._reader is not None:self._reader.close();self._reader=None
                self._cache.clear();self._stamp=None;reader=self.factory(self.path)
                try:
                    epoch=reader.metadata().build_epoch;end=self.path.stat()
                    if not isinstance(epoch,int) or isinstance(epoch,bool) or epoch<0 or (end.st_dev,end.st_ino,end.st_mtime_ns,end.st_size)!=stamp:raise ValueError()
                except Exception:
                    reader.close();return False
                self._reader=reader;self._epoch=epoch;self._stamp=stamp
            return self._epoch<=now+86400 and now-self._epoch<=62*86400
        except Exception:return False
    @staticmethod
    def _name(value):
        if not isinstance(value,dict) or not isinstance(value.get('names'),dict):return ''
        name=value['names'].get('ru') or value['names'].get('en') or ''
        if not isinstance(name,str) or len(name)>120 or any(ord(c)<32 or 127<=ord(c)<=159 for c in name):raise ValueError()
        return name.strip()
    @classmethod
    def _project(cls,record,age):
        if not isinstance(record,dict):raise ValueError()
        country=record.get('country',{}).get('iso_code')
        if not isinstance(country,str) or not re.fullmatch('[A-Z]{2}',country):raise ValueError()
        subdivisions=record.get('subdivisions',[])
        if not isinstance(subdivisions,list) or len(subdivisions)>16:raise ValueError()
        region=cls._name(subdivisions[0]) if subdivisions else '';city=cls._name(record.get('city',{}))
        return {'available':True,'country':country,'region':region,'city':city,'database_age_days':age}
    def lookup(self,source):
        unavailable={'available':False}
        try:
            ip=ipaddress.ip_address(source)
            if not ip.is_global:return unavailable
            canonical=str(ip);key=hmac.new(self._key,canonical.encode('ascii'),sha256).digest()
        except (ValueError,TypeError):return unavailable
        with self._lock:
            now=self.clock()
            if not self._load(now):return unavailable
            cached=self._cache.get(key)
            if cached and cached[0]>now:
                self._cache.move_to_end(key);return cached[1].copy()
            while self._recent and self._recent[0]<=now-60:self._recent.popleft()
            if len(self._recent)>=self.limit:return unavailable
            self._recent.append(now)
            try:result=self._project(self._reader.get(canonical),max(0,int((now-self._epoch)//86400)))
            except Exception:result=unavailable
            self._cache[key]=(now+(600 if result['available'] else 60),result.copy());self._cache.move_to_end(key)
            while len(self._cache)>2048:self._cache.popitem(last=False)
            return result
