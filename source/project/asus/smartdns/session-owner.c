/* SPDX-License-Identifier: MIT
 * A single fixed exec after setsid. No libc, paths or commands from callers.
 * Kept separate from the DNS parser; old ASUS firmware may lack setsid.
 */
#ifndef CONFIG_WORKER
#define CONFIG_WORKER "/opt/lib/nfqws2-asus/smartdns/config-worker.sh"
#endif
#if defined(__aarch64__)
#define NR_SETSID 157
#define NR_EXECVE 221
#define NR_EXIT 93
__asm__(".global _start\n_start:\nmov x0, sp\nbl entry\n");
static long call(long n,long a,long b,long c) {
    register long x8 __asm__("x8")=n,x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c;
    __asm__ volatile("svc 0":"+r"(x0):"r"(x8),"r"(x1),"r"(x2):"memory","cc");return x0;
}
#elif defined(__arm__)
#define NR_SETSID 66
#define NR_EXECVE 11
#define NR_EXIT 1
__asm__(".global _start\n_start:\nmov r0, sp\nb entry\n");
static long call(long n,long a,long b,long c) {
    register long r7 __asm__("r7")=n,r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c;
    __asm__ volatile("svc 0":"+r"(r0):"r"(r7),"r"(r1),"r"(r2):"memory","cc");return r0;
}
#elif defined(__x86_64__)
#define NR_SETSID 112
#define NR_EXECVE 59
#define NR_EXIT 60
__asm__(".global _start\n_start:\nxor %ebp,%ebp\nmov %rsp,%rdi\nand $-16,%rsp\ncall entry\n");
static long call(long n,long a,long b,long c) {
    __asm__ volatile("syscall":"+a"(n):"D"(a),"S"(b),"d"(c):"rcx","r11","memory","cc");return n;
}
#else
#error Unsupported syscall ABI
#endif
__attribute__((noreturn)) static void fail(void) {call(NR_EXIT,2,0,0);for(;;){} }
static int identifier(const char *s) {
    int i=0;for(;s[i];i++)if(i>=32 || !((s[i]>='a'&&s[i]<='f')||(s[i]>='0'&&s[i]<='9')))return 0;
    return i==32;
}
static int decimal(const char *s,int max) {
    int i=0;if(s[0]<'1'||s[0]>'9')return 0;
    for(;s[i];i++)if(i>=max||s[i]<'0'||s[i]>'9')return 0;
    return i>0;
}
__attribute__((noreturn)) void entry(long *stack) {
    long argc=stack[0];char **argv=(char **)(stack+1);
    if(argc!=4||!identifier(argv[1])||!decimal(argv[2],10)||!decimal(argv[3],20))fail();
    if(call(NR_SETSID,0,0,0)<0)fail();
    char *args[]={"/bin/sh",CONFIG_WORKER,"session",argv[1],argv[2],argv[3],(char *)0};
    call(NR_EXECVE,(long)args[0],(long)args,(long)(argv+argc+1));fail();
}
