# Fixed Detector terminal helper

The helper runs only the installed, hash-verified DPI Detector. It exposes a
private Unix socket, bounded PTY input/output, browser heartbeat and a hard
deadline. The standalone lifecycle module uses the same control lock to stop
the broker and its entire child group before package replacement.

Package builders import `terminal_build.py` and call `payload_for(engine)`.
This validates the current C source digest, the checked-in binary digest and
the static ELF architecture. A normal offline package build needs no compiler.
ASUS aliases `armv7-2.6`/`armv7-3.2` use the generic ARMv5 soft-float helper;
`aarch64-3.10` uses ARM64. Native families are arm, arm64, mips, mipsel, mips64,
x86 and x86_64. MIPS builds use software floating point; x86 targets Pentium 4.

Reproduce all seven files with the pinned Zig 0.13.0 Linux x86_64 compiler:

```sh
python3 asus/dpi/terminal_build.py --zig /path/to/zig --output /tmp/dpi-terminals
```

`bin/terminals.json` records compiler SHA256, flags, source SHA256, target, CPU,
ELF identity, size and SHA256 for every output. Compare that manifest and every
output with the checked-in files before replacing them. Compiler caches are
private temporary directories and are removed after the build.

Compiler source: https://ziglang.org/download/0.13.0/zig-0.13.0.tar.xz
Source archive SHA256: 06c73596beeccb71cc073805bdb9c0e05764128f16478fa53bf17dfabc1d4318.
The source kit already records Zig/Rust references in metadata/dpi-tool-sources.json.
Runtime license notices must include the linked musl/LLVM runtime notices and
the xterm frontend notices.

The helper does not add missing Detector releases: upstream alpha.21 offers no
x86-32 or MIPS64 binary. Those native targets keep an explicit unsupported
Detector status until separately reproducible and qualified Detector builds
are available. The main NFQWS2 package remains supported on those targets.
