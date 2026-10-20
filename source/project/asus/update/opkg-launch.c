/* SPDX-License-Identifier: MIT
 * One POSIX lock owner from the final preflight through exec(opkg).
 * Freestanding Linux syscalls: no router libc or new package dependency.
 */
#ifndef UPDATE_ROOT
#define UPDATE_ROOT "/opt/var/lib/nfqws2-asus/updates"
#endif
#ifndef OPKG_LOCK
#define OPKG_LOCK "/opt/tmp/opkg.lock"
#endif
#ifndef OPKG_BIN
#define OPKG_BIN "/opt/bin/opkg"
#endif
#ifndef UPDATE_OWNER
#define UPDATE_OWNER 0
#endif

#if defined(__aarch64__)
#define NR_OPENAT 56
#define NR_CLOSE 57
#define NR_STAT 80
#define NR_FCNTL 25
#define NR_FORK 220
#define NR_WAIT 260
#define NR_EXEC 221
#define NR_EXIT 93
#define SET_LOCK 6
#define OPEN_DIRECTORY 040000
#define OPEN_NOFOLLOW 0100000
__asm__(".global _start\n_start:\nmov x0, sp\nbl entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long x8 __asm__("x8")=n,x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c,x3 __asm__("x3")=d,x4 __asm__("x4")=0;
    __asm__ volatile("svc 0":"+r"(x0):"r"(x8),"r"(x1),"r"(x2),"r"(x3),"r"(x4):"memory","cc");return x0;
}
#elif defined(__arm__)
#define NR_OPENAT 322
#define NR_CLOSE 6
#define NR_STAT 197 /* fstat64, available before the supported 2.6.36 kernel. */
#define NR_FCNTL 221
#define NR_FORK 2
#define NR_WAIT 114
#define NR_EXEC 11
#define NR_EXIT 1
#define SET_LOCK 13 /* F_SETLK64, 64-bit offsets on ARM EABI. */
#define OPEN_DIRECTORY 040000
#define OPEN_NOFOLLOW 0100000
__asm__(".global _start\n_start:\nmov r0, sp\nb entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long r7 __asm__("r7")=n,r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d;
    __asm__ volatile("svc 0":"+r"(r0):"r"(r7),"r"(r1),"r"(r2),"r"(r3):"memory","cc");return r0;
}
#elif defined(__x86_64__)
/* Host executable-boundary tests; never bundled in router IPKs. */
#define NR_OPENAT 257
#define NR_CLOSE 3
#define NR_STAT 5
#define NR_FCNTL 72
#define NR_FORK 57
#define NR_WAIT 61
#define NR_EXEC 59
#define NR_EXIT 60
#define SET_LOCK 6
#define OPEN_DIRECTORY 00200000
#define OPEN_NOFOLLOW 00400000
__asm__(".global _start\n_start:\nxor %ebp,%ebp\nmov %rsp,%rdi\nand $-16,%rsp\ncall entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long r10 __asm__("r10")=d;
    __asm__ volatile("syscall":"+a"(n):"D"(a),"S"(b),"d"(c),"r"(r10):"rcx","r11","memory","cc");return n;
}
#else
#error Unsupported syscall ABI
#endif

typedef unsigned int u32;
_Alignas(8) static unsigned char st[256];
static char runtime[2048],package[2048];
static struct {short type,whence;long long start,len;int pid;} lock={1,0,0,0,0};
_Static_assert(__builtin_offsetof(__typeof__(lock),start)==8,"flock ABI");

__attribute__((noreturn)) static void done(int code) {call(NR_EXIT,code,0,0,0);for(;;){} }
static int object(long fd,int directory,int private) {
    if(fd<0||call(NR_STAT,fd,(long)st,0,0)<0)return 0;
#if defined(__x86_64__)
    u32 mode=*(u32*)(st+24),uid=*(u32*)(st+28);unsigned long links=*(unsigned long*)(st+16);
#else
    /* ARM fstat64 and asm-generic AArch64 stat share these three offsets. */
    u32 mode=*(u32*)(st+16),uid=*(u32*)(st+24),links=*(u32*)(st+20);
#endif
    if(uid!=UPDATE_OWNER||(mode&0170000)!=(directory?0040000:0100000)||(mode&0022))return 0;
    if(private&&(mode&0777)!=0700)return 0;
    return directory||links==1;
}
static long directory(long parent,const char *name) {
    long fd=call(NR_OPENAT,parent,(long)name,OPEN_DIRECTORY|OPEN_NOFOLLOW|04000,0);
    if(!object(fd,1,1))done(75);
    /* Directory descriptors do not authorize hooks and do not survive exec. */
    if(call(NR_FCNTL,fd,2,1,0)<0)done(75);return fd;
}
static void path(char *out,const char *id,const char *suffix) {
    const char *parts[]={UPDATE_ROOT,"/operations/",id,suffix};int n=0;
    for(int i=0;i<4;i++)for(const char *p=parts[i];*p;p++){if(n>=2047)done(75);out[n++]=*p;}out[n]=0;
}
__attribute__((used,noreturn)) void entry(long *stack) {
    long argc=stack[0];char **argv=(char**)&stack[1];if(argc!=2)done(75);
    const char *id=argv[1];int n=0;for(;id[n];n++)if(n>=32||!((id[n]>='0'&&id[n]<='9')||(id[n]>='a'&&id[n]<='f')))done(75);if(n!=32)done(75);
    long root=directory(-100,UPDATE_ROOT),ops=directory(root,"operations"),op=directory(ops,id);directory(op,"runtime");
    path(runtime,id,"/runtime/check.sh");path(package,id,"/package.ipk");
    long script=call(NR_OPENAT,-100,(long)runtime,OPEN_NOFOLLOW|04000,0);if(!object(script,0,0))done(75);call(NR_CLOSE,script,0,0,0);
    long fd=call(NR_OPENAT,-100,(long)OPKG_LOCK,OPEN_NOFOLLOW|04000|0100|2,0600);if(!object(fd,0,0))done(75);
    if(call(NR_FCNTL,fd,SET_LOCK,(long)&lock,0)<0)done(73);
    /* ASUS maintainer scripts need system administration tools such as cru.
     * Keep a fixed trusted PATH, including the stock sbin directories. */
    char *env[]={"PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin","LANG=C","LC_ALL=C",0};
#if defined(__aarch64__)
    long child=call(NR_FORK,17,0,0,0); /* clone(SIGCHLD, NULL, ...). */
#else
    long child=call(NR_FORK,0,0,0,0);
#endif
    if(child<0)done(76);
    if(child==0){call(NR_CLOSE,fd,0,0,0);char *args[]={"sh",runtime,(char*)id,0};call(NR_EXEC,(long)"/bin/sh",(long)args,(long)env,0);done(74);}
    int status=0;long waited;do{waited=call(NR_WAIT,child,(long)&status,0,0);}while(waited==-4);
    if(waited!=child||status!=0)done(74);
    /* No fork here: POSIX locks belong to this PID, which opkg keeps. */
    char *args[]={OPKG_BIN,"--nodeps","install",package,0};call(NR_EXEC,(long)OPKG_BIN,(long)args,(long)env,0);done(76);
}
