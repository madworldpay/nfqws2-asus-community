/* SPDX-License-Identifier: MIT
 * Bounded DNS probe for SmartDNS validation and recovery without /opt/libc.
 * Only numeric destinations, one question, A/AAAA and fixed UDP/TCP modes.
 */
#if defined(__aarch64__)
#define NR_READ 63
#define NR_WRITE 64
#define NR_OPENAT 56
#define NR_CLOSE 57
#define NR_SOCKET 198
#define NR_CONNECT 203
#define NR_CLOCK 113
#define NR_POLL 73
#define NR_EXIT 93
__asm__(".global _start\n_start:\nmov x0, sp\nbl entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long x8 __asm__("x8")=n,x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c,x3 __asm__("x3")=d,x4 __asm__("x4")=0;
    __asm__ volatile("svc 0":"+r"(x0):"r"(x8),"r"(x1),"r"(x2),"r"(x3),"r"(x4):"memory","cc");return x0;
}
#elif defined(__arm__)
#define NR_READ 3
#define NR_WRITE 4
#define NR_OPENAT 322
#define NR_CLOSE 6
#define NR_SOCKET 281
#define NR_CONNECT 283
#define NR_CLOCK 263
#define NR_POLL 168
#define NR_EXIT 1
__asm__(".global _start\n_start:\nmov r0, sp\nb entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long r7 __asm__("r7")=n,r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d;
    __asm__ volatile("svc 0":"+r"(r0):"r"(r7),"r"(r1),"r"(r2),"r"(r3):"memory","cc");return r0;
}
#elif defined(__x86_64__)
#define NR_READ 0
#define NR_WRITE 1
#define NR_OPENAT 257
#define NR_CLOSE 3
#define NR_SOCKET 41
#define NR_CONNECT 42
#define NR_CLOCK 228
#define NR_POLL 7
#define NR_EXIT 60
__asm__(".global _start\n_start:\nxor %ebp,%ebp\nmov %rsp,%rdi\nand $-16,%rsp\ncall entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long r10 __asm__("r10")=d;
    __asm__ volatile("syscall":"+a"(n):"D"(a),"S"(b),"d"(c),"r"(r10):"rcx","r11","memory","cc");return n;
}
#else
#error Unsupported syscall ABI
#endif
typedef unsigned char u8;
typedef unsigned short u16;
/* GCC may lower aggregate initialization to memset even with -fno-builtin. */
void *memset(void *destination,int value,unsigned long size) {
    volatile u8 *p=destination;
    while(size--)*p++=(u8)value;
    return destination;
}
struct stamp { long sec,ns; };
struct pollfd { int fd;short events,revents; };
struct address {u16 family,port;unsigned int flow;u8 bytes[16];unsigned int scope;};
struct rr {char owner[254],target[254],ip[40];int type;};
static struct rr records[64];
static struct stamp deadline;
static u8 query[512],packet[4096];
static char question[254],output[4096];
static int outlen,rcode=-1,truncated,answers;
static const char *reason="invalid_response";
static int length(const char *s) {int n=0;while(s[n])++n;return n;}
static int equal(const char *a,const char *b) {int i=0;while(a[i]&&a[i]==b[i])++i;return a[i]==b[i];}
static void copy(char *a,const char *b) {while((*a++=*b++)){} }
static void text(const char *s) {while(*s && outlen<4090)output[outlen++]=*s++;}
static void number(int n) {char b[12];int i=0;if(n<0){text("-1");return;}do{b[i++]=(char)('0'+n%10);n/=10;}while(n);while(i)output[outlen++]=b[--i];}
__attribute__((noreturn)) static void finish(int ok) {
    text(ok?"{\"ok\":true,\"rcode\":" : "{\"ok\":false,\"rcode\":");number(rcode);
    text(",\"truncated\":");text(truncated?"true":"false");text(",\"answers\":[");
    if(ok)for(int i=0;i<answers;i++){if(i)text(",");text("\"");text(records[i].ip);text("\"");}
    text("],\"reason\":\"");text(ok?"ready":reason);text("\"}\n");
    call(NR_WRITE,1,(long)output,outlen,0);call(NR_EXIT,ok?0:2,0,0,0);for(;;){}
}
static int decimal(const char *s,int maximum) {
    if(!*s)return -1;
    int n=0;
    for(;*s;s++){if(*s<'0'||*s>'9'||n>(maximum-(*s-'0'))/10)return -1;n=n*10+*s-'0';}
    return n;
}
static int hex(char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
static int ipv4(const char *s,u8 *out) {
    for(int i=0;i<4;i++){
        int n=0,digits=0;const char *start=s;
        while(*s>='0'&&*s<='9'){n=n*10+*s++-'0';if(++digits>3||n>255)return 0;}
        if(!digits||(digits>1&&*start=='0'))return 0;
        out[i]=(u8)n;
        if(i==3)return !*s;
        if(*s++!='.')return 0;
    }return 0;
}
static int ipv6(const char *s,u8 *out) {
    u16 w[8]={0};int n=0,hole=-1;
    if(s[0]==':'&&s[1]==':'){hole=0;s+=2;}
    while(*s){
        if(n>=8)return 0;
        const char *start=s;int x=0,digits=0;
        while(hex(*s)>=0){x=x*16+hex(*s++);if(++digits>4)return 0;}
        if(*s=='.'){
            u8 a[4];if(n>6||!ipv4(start,a))return 0;
            w[n++]=(u16)(a[0]*256+a[1]);w[n++]=(u16)(a[2]*256+a[3]);while(*s)++s;break;
        }
        if(!digits)return 0;
        w[n++]=(u16)x;
        if(!*s)break;
        if(*s++!=':')return 0;
        if(*s==':'){if(hole>=0)return 0;hole=n;++s;}else if(!*s)return 0;
    }
    if(hole<0){if(n!=8)return 0;}
    else {if(n>=8)return 0;int gap=8-n;for(int i=n-1;i>=hole;i--)w[i+gap]=w[i];for(int i=hole;i<hole+gap;i++)w[i]=0;}
    for(int i=0;i<8;i++){out[i*2]=(u8)(w[i]>>8);out[i*2+1]=(u8)w[i];}return 1;
}
static int clocknow(struct stamp *t){return call(NR_CLOCK,1,(long)t,0,0)>=0;}
static int remaining(void) {
    struct stamp t;if(!clocknow(&t))return 0;
    long s=deadline.sec-t.sec,ns=deadline.ns-t.ns;if(ns<0){--s;ns+=1000000000;}
    if(s<0)return 0;
    if(s>10)return 10000;
    return (int)(s*1000+ns/1000000);
}
static int ready(int fd,int events) {
    for(;;){int ms=remaining();if(ms<=0){reason="timeout";return 0;}
        struct pollfd p={fd,(short)events,0};long r;
#if defined(__aarch64__)
        struct stamp timeout={ms/1000,(ms%1000)*1000000};r=call(NR_POLL,(long)&p,1,(long)&timeout,0);
#else
        r=call(NR_POLL,(long)&p,1,ms,0);
#endif
        if(r==-4)continue;
        if(r>0&&(p.revents&events))return 1;
        reason=r==0?"timeout":"io_failed";return 0;
    }
}
static int transfer(int fd,u8 *buf,int len,int write,int datagram) {
    int pos=0;
    while(pos<len){
        if(!ready(fd,write?4:1))return -1;
        long n=call(write?NR_WRITE:NR_READ,fd,(long)(buf+pos),len-pos,0);
        if(n==-4||n==-11)continue;
        if(n<=0){reason="io_failed";return -1;}
        pos+=(int)n;if(datagram)return pos;
    }return pos;
}
static int word(const u8 *p){return p[0]*256+p[1];}
static void putword(u8 *p,int value){p[0]=(u8)(value>>8);p[1]=(u8)value;}
static int dnsname(const u8 *data,int size,int *offset,char *out) {
    int at=*offset,end=-1,n=0,jumps=0;
    for(int k=0;k<128;k++){
        if(at>=size)return 0;
        int c=data[at++];
        if(!c){if(end<0)end=at;out[n]=0;*offset=end;return 1;}
        if((c&192)==192){
            if(at>=size||++jumps>16)return 0;
            int target=(c&63)*256+data[at++];
            if(target<12||target>=at-2)return 0;
            if(end<0)end=at;
            at=target;continue;
        }
        if(c>63||at+c>size||n+c+(n?1:0)>253)return 0;
        if(n)out[n++]='.';
        for(int i=0;i<c;i++){
            int ch=data[at++];if(ch>='A'&&ch<='Z')ch+='a'-'A';
            if(!((ch>='a'&&ch<='z')||(ch>='0'&&ch<='9')||ch=='-'||ch=='_'))return 0;
            out[n++]=(char)ch;
        }
    }return 0;
}
static void iptext(const u8 *data,int six,char *out) {
    int pos=0;
    for(int i=0;i<(six?8:4);i++){
        if(i)out[pos++]=six?':':'.';
        int n=six?word(data+i*2):data[i];char b[6];int j=0;
        do{
            if(six){b[j++]="0123456789abcdef"[n&15];n>>=4;}
            else{b[j++]=(char)('0'+n%10);n/=10;}
        }while(n);
        while(j)out[pos++]=b[--j];
    }out[pos]=0;
}
static int parse(int len,int qlen,int qtype) {
    if(len<12||word(packet)!=word(query)||!(packet[2]&128)||(packet[2]&120)||word(packet+4)!=1)return 0;
    rcode=packet[3]&15;truncated=!!(packet[2]&2);if(truncated){reason="truncated";return 0;}
    if(rcode){reason="dns_rcode";return 0;}
    int at=12;char name[254];
    if(!dnsname(packet,len,&at,name)||!equal(name,question)||at+4>len||word(packet+at)!=qtype||word(packet+at+2)!=1)return 0;
    at+=4;int count=word(packet+6);if(count>64)return 0;
    for(int i=0;i<count;i++){
        struct rr *r=&records[i];
        if(!dnsname(packet,len,&at,r->owner)||at+10>len)return 0;
        r->type=word(packet+at);int cls=word(packet+at+2),size=word(packet+at+8);at+=10;
        if(at+size>len||cls!=1)return 0;
        if(r->type==5){int next=at;if(!dnsname(packet,len,&next,r->target)||next!=at+size)return 0;}
        else if(r->type==qtype){if(size!=(qtype==28?16:4))return 0;iptext(packet+at,qtype==28,r->ip);}
        at+=size;
    }
    /* Answers must belong to the question or its bounded CNAME chain. */
    copy(name,question);
    for(int hop=0;hop<=count;hop++){
        const char *next=0;
        for(int i=0;i<count;i++)if(records[i].type==5&&equal(records[i].owner,name)){next=records[i].target;break;}
        if(!next)break;
        if(hop==count)return 0;
        copy(name,next);
    }
    answers=0;
    for(int i=0;i<count;i++)if(records[i].type==qtype && (equal(records[i].owner,name)||equal(records[i].owner,question))) {
        if(i!=answers)copy(records[answers].ip,records[i].ip);
        ++answers;
    }
    if(!answers)reason="no_address";
    (void)qlen;return answers>0;
}
__attribute__((used,noreturn)) void entry(long *stack) {
    long argc=stack[0];char **argv=(char**)&stack[1];reason="invalid_arguments";
    if(argc!=7)finish(0);
    int port=decimal(argv[2],65535),timeout=decimal(argv[6],5000),tcp=equal(argv[5],"tcp"),qtype=equal(argv[4],"A")?1:(equal(argv[4],"AAAA")?28:0);
    if(port<1||timeout<1||(!tcp&&!equal(argv[5],"udp"))||!qtype||length(argv[1])>45||length(argv[3])>253)finish(0);
    int qlen=12,label=0,at=12;const char *domain=argv[3];
    if(!*domain)finish(0);
    copy(question,domain);
    for(int i=0;;i++){
        int c=domain[i];if(c>='A'&&c<='Z')c+='a'-'A';question[i]=(char)c;
        if(c=='.'||!c){
            if(label<1||label>63||domain[i-label]=='-'||domain[i-1]=='-')finish(0);
            query[at-label-1]=(u8)label;label=0;if(!c)break;query[at++]=0;
        }else{
            if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-'))finish(0);
            if(!label&&at==12)query[at++]=0;
            query[at++]=(u8)c;++label;
        }
    }
    query[at++]=0;putword(query+at,qtype);at+=2;putword(query+at,1);at+=2;qlen=at;
    struct address addr={0};u8 ip[16];int six=0;
    if(ipv4(argv[1],ip))addr.family=2;else if(ipv6(argv[1],ip)){addr.family=10;six=1;}else finish(0);
    addr.port=(u16)(((unsigned)port>>8)|((unsigned)port<<8));
    if(six){for(int i=0;i<16;i++)addr.bytes[i]=ip[i];}else{u8 *p=(u8*)&addr.flow;for(int i=0;i<4;i++)p[i]=ip[i];}
    long random=call(NR_OPENAT,-100,(long)"/dev/urandom",0,0);reason="random_unavailable";
    if(random<0||call(NR_READ,random,(long)query,2,0)!=2)finish(0);
    call(NR_CLOSE,random,0,0,0);
    query[2]=1;query[5]=1;
    if(!clocknow(&deadline))finish(0);
    deadline.sec+=timeout/1000;deadline.ns+=(timeout%1000)*1000000;
    if(deadline.ns>=1000000000){deadline.ns-=1000000000;++deadline.sec;}
    int fd=(int)call(NR_SOCKET,addr.family,(tcp?1:2)|04000|02000000,0,0);reason="io_failed";
    if(fd<0)finish(0);
    long rc=call(NR_CONNECT,fd,(long)&addr,six?28:16,0);
    if(rc<0&&rc!=-115)finish(0);
    if(tcp){
        u8 size[2];putword(size,qlen);
        if(transfer(fd,size,2,1,0)!=2||transfer(fd,query,qlen,1,0)!=qlen||transfer(fd,size,2,0,0)!=2)finish(0);
        int n=word(size);if(n<12||n>4096||transfer(fd,packet,n,0,0)!=n)finish(0);
        reason="invalid_response";finish(parse(n,qlen,qtype));
    }
    if(transfer(fd,query,qlen,1,1)!=qlen)finish(0);
    int n=transfer(fd,packet,4096,0,1);if(n<0)finish(0);
    reason="invalid_response";finish(parse(n,qlen,qtype));
}
