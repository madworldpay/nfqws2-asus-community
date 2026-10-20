/* SPDX-License-Identifier: MIT
 * Short-lived DNS/TLS subprocess guard. No libc, daemon or network settings.
 * Both supervisor and child die with their parent; the supervisor also owns
 * an independent monotonic budget if the PHP request itself gets stuck.
 */
#ifndef LOCATION_MILLISECONDS
#define LOCATION_MILLISECONDS 5000
#endif
#if defined(__aarch64__)
#define FORK 220
#define WAIT 260
#define EXEC 221
#define EXIT 93
#define PARENT 173
#define PID 172
#define PRCTL 167
#define CLOCK 113
#define SLEEP 101
#define KILL 129
#define CLOSE 57
__asm__(".global _start\n_start:\nmov x0, sp\nbl entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long x8 __asm__("x8")=n,x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c,x3 __asm__("x3")=d,x4 __asm__("x4")=0;
    __asm__ volatile("svc 0":"+r"(x0):"r"(x8),"r"(x1),"r"(x2),"r"(x3),"r"(x4):"memory","cc");return x0;
}
#elif defined(__arm__)
#define FORK 2
#define WAIT 114
#define EXEC 11
#define EXIT 1
#define PARENT 64
#define PID 20
#define PRCTL 172
#define CLOCK 263
#define SLEEP 162
#define KILL 37
#define CLOSE 6
__asm__(".global _start\n_start:\nmov r0, sp\nb entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long r7 __asm__("r7")=n,r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d;
    __asm__ volatile("svc 0":"+r"(r0):"r"(r7),"r"(r1),"r"(r2),"r"(r3):"memory","cc");return r0;
}
#elif defined(__x86_64__)
#define FORK 57
#define WAIT 61
#define EXEC 59
#define EXIT 60
#define PARENT 110
#define PID 39
#define PRCTL 157
#define CLOCK 228
#define SLEEP 35
#define KILL 62
#define CLOSE 3
__asm__(".global _start\n_start:\nxor %ebp,%ebp\nmov %rsp,%rdi\nand $-16,%rsp\ncall entry\n");
static long call(long n,long a,long b,long c,long d) {
    register long r10 __asm__("r10")=d;
    __asm__ volatile("syscall":"+a"(n):"D"(a),"S"(b),"d"(c),"r"(r10):"rcx","r11","memory","cc");return n;
}
#else
#error Unsupported ABI
#endif
struct stamp {long sec,nsec;};
__attribute__((noreturn)) static void done(int code) {call(EXIT,code,0,0,0);for(;;){} }
static int bind_parent(long parent) {
    return parent>1&&call(PRCTL,1,9,0,0)==0&&call(PARENT,0,0,0,0)==parent;
}
void entry(long *stack) {
    long argc=stack[0];char **argv=(char **)(stack+1),**env=argv+argc+1;
    if(argc<2||!bind_parent(call(PARENT,0,0,0,0)))done(64);
    struct stamp start,now,pause={0,20000000};
    if(call(CLOCK,1,(long)&start,0,0)<0)done(70);
    for(long fd=3;fd<256;fd++)call(CLOSE,fd,0,0,0);
    long supervisor=call(PID,0,0,0,0);
#if defined(__aarch64__)
    long child=call(FORK,17,0,0,0);
#else
    long child=call(FORK,0,0,0,0);
#endif
    if(child<0)done(70);
    if(child==0) {
        if(!bind_parent(supervisor))done(70);
        call(EXEC,(long)argv[1],(long)(argv+1),(long)env,0);done(127);
    }
    int status=0,expired=0;
    for(;;) {
        long r=call(WAIT,child,(long)&status,1,0);
        if(r==child)done(expired?124:((status&127)?128+(status&127):((status>>8)&255)));
        if(r<0&&r!=-4)done(70);
        if(!expired) {
            if(call(CLOCK,1,(long)&now,0,0)<0||
               (now.sec-start.sec)*1000+(now.nsec-start.nsec)/1000000>=LOCATION_MILLISECONDS) {
                call(KILL,child,9,0,0);expired=1;
            }
        }
        call(SLEEP,(long)&pause,0,0,0);
    }
}
