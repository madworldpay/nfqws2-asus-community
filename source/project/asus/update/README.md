# Opkg lock launcher

`opkg-launch.c` uses Linux syscalls and has no libc or runtime dependencies.
It acquires opkg's POSIX file lock, runs the final preflight, then **execs**
opkg in the same PID. A different process or an ordinary `flock` cannot
transfer ownership of this lock. A failed preflight never invokes opkg.

The sole argument is a32-character operation ID. Root-private directories,
fixed paths, ownership and file types are checked. No URL, command or password
is accepted. All checks precede package installation. The worker and hooks
add the journal, process identity and phase checks; an inherited descriptor
is not permission to bypass those checks.

Reproduce the bundled launchers with cross GCC for AArch64 and ARM EABI:

```sh
python3 asus/update/build-launchers.py
```

An extracted compiler tree may instead be supplied with `--toolchain-root`;
no host OS or router package installation is required. Outputs are stripped,
static and deterministic, with a non-executable stack and no build ID.
`bin/launchers.json` binds both ELF hashes to the exact source and compiler
versions. `asus/build.py` checks this record before packaging.

ARMv7 uses the kernel's `fstat64`/`fcntl64` APIs and soft-float instructions,
including the Entware armv7-2.6 case. Tests exercise lock contention, failed
preflight, symlink refusal, same PID across exec and killed-lock-owner recovery
on the host and under both QEMU targets. Router acceptance is recorded
separately; emulation does not confirm a device's kernel or NFQUEUE support.

ABI references: Linux UAPI `arch/arm{,64}/include/uapi/asm/fcntl.h`,
`arch/arm/include/uapi/asm/stat.h`, `include/uapi/asm-generic/stat.h`;
opkg source80503d94, `libopkg/opkg_conf.c`. The ARM/AArch64 open flags differ
from the host x86 test flags. These syscall interface values are not libc
headers or bundled library code.
