/* Private fixed-program PTY broker. No TCP, shell, or browser-selected argv.
 * Build: cc -std=c99 -O2 -Wall -Wextra -Werror terminal.c -o dpi-terminal
 * argv: PRIVATE_DIR VERIFIED_BINARY REPORT_CWD COLS ROWS en|ru
 * Unix stream requests: P offset\n; I length\n<bytes>; R cols rows\n; S\n.
 * Reply: DPT1 state end_offset exit_code byte_length\n<bytes>; -1 = no exit.
 * Only P renews the running-session heartbeat. Output is capped at 2 MiB.
 */
#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <sys/wait.h>
#include <sys/prctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <poll.h>
#include <termios.h>
#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#ifndef DPI_IDLE_SECONDS
#define DPI_IDLE_SECONDS 90
#endif
#ifndef DPI_HARD_SECONDS
#define DPI_HARD_SECONDS 1800
#endif
#define OUTPUT_CAP 2097152U
#define CHUNK_CAP 32768U

static volatile sig_atomic_t stopping;
static int shutdown_requested;
static const char *state = "running";
static int exit_code = -1;
static size_t output_size;
static int output_fd = -1, status_fd = -1, master_fd = -1;
static pid_t child_pid;
static double last_poll, started, finished;

static void on_signal(int sig) { (void)sig; stopping = 1; }
static double monotime(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) _exit(1);
    return t.tv_sec + t.tv_nsec / 1000000000.0;
}
static int allwrite(int fd, const void *buf, size_t len) {
    const char *p = buf;
    while (len) {
        ssize_t n = write(fd, p, len);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n; len -= (size_t)n;
    }
    return 0;
}
static int number(const char *p, unsigned long max, unsigned long *out) {
    char *end; unsigned long v;
    if (!p[0] || (p[0] == '0' && p[1])) return 0;
    for (const char *c = p; *c; c++) if (*c < '0' || *c > '9') return 0;
    errno = 0; v = strtoul(p, &end, 10);
    if (errno || *end || v > max) return 0;
    *out = v; return 1;
}
static int no_links(const char *p) {
    char copy[PATH_MAX]; struct stat s;
    if (p[0] != '/' || strlen(p) >= sizeof(copy)) return 0;
    strcpy(copy, p);
    for (char *c = copy + 1; ; c++) {
        if (*c != '/' && *c) continue;
        char saved = *c; *c = 0;
        if (lstat(copy, &s) || S_ISLNK(s.st_mode)) return 0;
        *c = saved; if (!saved) break;
    }
    char real[PATH_MAX]; return realpath(p, real) && !strcmp(p, real);
}
static int regular_fd(int fd) {
    struct stat s;
    return fd >= 0 && !fstat(fd, &s) && S_ISREG(s.st_mode) &&
        s.st_uid == geteuid() && (s.st_mode & 0777) == 0600 && s.st_nlink == 1 && !s.st_size;
}
static void save_status(void) {
    char b[96]; int n = snprintf(b, sizeof(b), "%s %d %zu\n", state, exit_code, output_size);
    if (lseek(status_fd, 0, SEEK_SET) < 0 || ftruncate(status_fd, 0) || allwrite(status_fd, b, (size_t)n)) stopping = 1;
}
static void cleanup_group(void) {
    if (child_pid <= 1) return;
    /* Keep our direct child unreaped until every group signal is complete.
     * Its reserved PID also reserves the group's identity. A child that has
     * not reached setsid() yet must be signalled directly as well. */
    kill(-child_pid, SIGTERM);
    kill(child_pid, SIGTERM);
    struct timespec t = {0, 100000000}; nanosleep(&t, NULL);
    kill(-child_pid, SIGKILL);
    kill(child_pid, SIGKILL);
    int result;
    while (waitpid(child_pid, &result, 0) < 0 && errno == EINTR) {}
    /* Reap descendants adopted through PR_SET_CHILD_SUBREAPER. */
    while (waitpid(-1, NULL, WNOHANG) > 0) {}
    child_pid = 0;
}
static int child_ready(int fd) {
    double deadline = monotime() + 3;
    while (!stopping && monotime() < deadline) {
        struct pollfd p = {fd, POLLIN, 0};
        int result = poll(&p, 1, 100);
        if (result < 0 && errno == EINTR) continue;
        if (result < 0) return 0;
        if (result > 0) {
            char answer;
            return read(fd, &answer, 1) == 1 && answer == 'Y';
        }
    }
    return 0;
}
static void end_session(const char *reason) {
    if (strcmp(state, "running")) return;
    state = reason; finished = monotime(); cleanup_group(); save_status();
}
static void drain_output(void) {
    char b[8192]; ssize_t n;
    while ((n = read(master_fd, b, sizeof(b))) > 0) {
        size_t count = (size_t)n;
        if (count > OUTPUT_CAP - output_size) count = OUTPUT_CAP - output_size;
        if (count && allwrite(output_fd, b, count)) { end_session("failed"); return; }
        output_size += count;
        if (output_size == OUTPUT_CAP) { end_session("output_limit"); return; }
    }
}
static int read_exact(int fd, void *buf, size_t len) {
    char *p = buf;
    while (len) {
        ssize_t n = read(fd, p, len);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return 0;
        p += n; len -= (size_t)n;
    }
    return 1;
}
static void reply(int fd, size_t offset, int with_output) {
    char header[128], b[CHUNK_CAP]; size_t len = 0;
    if (with_output) {
        len = output_size - offset; if (len > sizeof(b)) len = sizeof(b);
        if (len && pread(output_fd, b, len, (off_t)offset) != (ssize_t)len) return;
    } else offset = 0;
    int n = snprintf(header, sizeof(header), "DPT1 %s %zu %d %zu\n", state, offset + len, exit_code, len);
    if (!allwrite(fd, header, (size_t)n) && len) (void)allwrite(fd, b, len);
}
static void client(int fd) {
    char line[96], payload[1024]; size_t n = 0;
    struct timeval timeout = {1, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    while (n + 1 < sizeof(line)) {
        if (!read_exact(fd, line + n, 1)) goto invalid;
        if (line[n++] == '\n') break;
    }
    if (!n || line[n - 1] != '\n') goto invalid;
    line[n - 1] = 0;
    unsigned long a, b;
    if (!strncmp(line, "P ", 2) && number(line + 2, output_size, &a)) {
        if (!strcmp(state, "running")) last_poll = monotime();
        reply(fd, (size_t)a, 1); return;
    }
    if (!strncmp(line, "I ", 2) && number(line + 2, sizeof(payload), &a) && a > 0) {
        if (!read_exact(fd, payload, a)) goto invalid;
        if (!strcmp(state, "running")) {
            ssize_t wrote = write(master_fd, payload, a);
            if (wrote != (ssize_t)a) goto invalid;
        }
        reply(fd, 0, 0); return;
    }
    if (!strncmp(line, "R ", 2)) {
        char *space = strchr(line + 2, ' ');
        if (!space) goto invalid;
        *space++ = 0;
        if (!number(line + 2, 500, &a) || a < 20 || !number(space, 200, &b) || b < 5) goto invalid;
        struct winsize w = {(unsigned short)b, (unsigned short)a, 0, 0};
        if (!strcmp(state, "running") && ioctl(master_fd, TIOCSWINSZ, &w)) goto invalid;
        reply(fd, 0, 0); return;
    }
    if (!strcmp(line, "S")) { end_session("stopped"); reply(fd, 0, 0); shutdown_requested = 1; return; }
invalid:
    (void)allwrite(fd, "ERR\n", 4);
}
static void daemon_run(int ready, const char *dir, const char *binary, const char *cwd, unsigned long cols, unsigned long rows, const char *lang) {
    int listener = -1, lock = -1, slave = -1, dirfd = -1;
    if (setsid() < 0) goto fail;
    /* The parent is a short-lived launcher. Never inherit PHP session/update locks. */
    long limit = sysconf(_SC_OPEN_MAX); if (limit < 0 || limit > 65536) limit = 65536;
    for (int fd = 0; fd < limit; fd++) if (fd != ready) close(fd);
    int nullfd = open("/dev/null", O_RDWR);
    if (nullfd != 0 || dup2(0, 1) < 0 || dup2(0, 2) < 0) goto fail;
    umask(0077);
    dirfd = open(dir, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0 || fchdir(dirfd)) goto fail;
    lock = openat(dirfd, "broker.lock", O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (!regular_fd(lock) || flock(lock, LOCK_EX | LOCK_NB)) goto fail;
    output_fd = openat(dirfd, "output", O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    status_fd = openat(dirfd, "status", O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (!regular_fd(output_fd) || !regular_fd(status_fd)) goto fail;
    listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    struct sockaddr_un address; memset(&address, 0, sizeof(address)); address.sun_family = AF_UNIX;
    if (snprintf(address.sun_path, sizeof(address.sun_path), "%s/control.sock", dir) >= (int)sizeof(address.sun_path)) goto fail;
    if (listener < 0 || bind(listener, (struct sockaddr *)&address, sizeof(address)) || chmod(address.sun_path, 0600) || listen(listener, 8)) goto fail;
    master_fd = posix_openpt(O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (master_fd < 0 || grantpt(master_fd) || unlockpt(master_fd)) goto fail;
    char *slave_name = ptsname(master_fd); if (!slave_name) goto fail;
    slave = open(slave_name, O_RDWR | O_NOCTTY | O_CLOEXEC); if (slave < 0) goto fail;
    struct winsize w = {(unsigned short)rows, (unsigned short)cols, 0, 0};
    if (ioctl(slave, TIOCSWINSZ, &w)) goto fail;
    (void)prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0);
    signal(SIGPIPE, SIG_IGN); signal(SIGTERM, on_signal); signal(SIGINT, on_signal); signal(SIGHUP, on_signal);
    int child_ack[2]; if (pipe2(child_ack, O_CLOEXEC)) goto fail;
    child_pid = fork(); if (child_pid < 0) goto fail;
    if (!child_pid) {
        signal(SIGPIPE, SIG_DFL); signal(SIGTERM, SIG_DFL); signal(SIGINT, SIG_DFL); signal(SIGHUP, SIG_DFL);
        close(ready); close(child_ack[0]);
        if (setsid() < 0 || ioctl(slave, TIOCSCTTY, 0) || chdir(cwd) || dup2(slave, 0) < 0 || dup2(slave, 1) < 0 || dup2(slave, 2) < 0) _exit(126);
        if (clearenv() || setenv("TERM", "xterm-256color", 1) || setenv("LANG", "C.UTF-8", 1) || setenv("HOME", cwd, 1) || setenv("PATH", "/opt/bin:/opt/sbin:/usr/bin:/usr/sbin:/bin:/sbin", 1)) _exit(126);
        if (allwrite(child_ack[1], "Y", 1)) _exit(126);
        close(child_ack[1]);
        char *const argv[] = {(char *)binary, "--lang", (char *)lang, NULL};
        execv(binary, argv); _exit(127);
    }
    close(child_ack[1]);
    int established = child_ready(child_ack[0]); close(child_ack[0]);
    if (!established) goto fail;
    close(slave); slave = -1;
    started = last_poll = monotime(); save_status();
    if (allwrite(ready, "Y", 1)) end_session("failed");
    close(ready); ready = -1;
    for (;;) {
        double now = monotime();
        if (stopping) { end_session("stopped"); shutdown_requested = 1; }
        if (!strcmp(state, "running") && (now - last_poll >= DPI_IDLE_SECONDS || now - started >= DPI_HARD_SECONDS)) end_session("expired");
        if (shutdown_requested || (strcmp(state, "running") && now - finished >= 90)) break;
        struct pollfd fds[2] = {{listener, POLLIN, 0}, {master_fd, POLLIN, 0}};
        int count = !strcmp(state, "running") ? 2 : 1;
        int result = poll(fds, (nfds_t)count, 100);
        if (result < 0 && errno != EINTR) { end_session("failed"); break; }
        if (count == 2) {
            drain_output();
            siginfo_t status; memset(&status, 0, sizeof(status));
            int observed = child_pid > 0 ? waitid(P_PID, (id_t)child_pid, &status, WEXITED | WNOHANG | WNOWAIT) : -1;
            if (!observed && status.si_pid == child_pid && child_pid > 0) {
                drain_output();
                exit_code = status.si_code == CLD_EXITED ? status.si_status : 128 + status.si_status;
                end_session("exited");
            }
        }
        if (fds[0].revents & POLLIN) {
            int fd = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
            if (fd >= 0) { client(fd); close(fd); }
        }
    }
    cleanup_group(); save_status(); unlinkat(dirfd, "control.sock", 0); _exit(0);
fail:
    if (child_pid > 1) cleanup_group();
    if (status_fd >= 0) { state = "failed"; save_status(); }
    if (ready >= 0) { (void)allwrite(ready, "N", 1); close(ready); }
    _exit(1);
}
int main(int argc, char **argv) {
    struct stat s; unsigned long cols, rows;
    if (argc != 7 || !number(argv[4], 500, &cols) || cols < 20 || !number(argv[5], 200, &rows) || rows < 5 ||
        (strcmp(argv[6], "en") && strcmp(argv[6], "ru"))) return 2;
    if (!no_links(argv[1]) || stat(argv[1], &s) || !S_ISDIR(s.st_mode) || s.st_uid != geteuid() || (s.st_mode & 0777) != 0700) return 2;
    if (!no_links(argv[2]) || stat(argv[2], &s) || !S_ISREG(s.st_mode) || s.st_uid != geteuid() || s.st_nlink != 1 || (s.st_mode & 0777) != 0755) return 2;
    if (!no_links(argv[3]) || stat(argv[3], &s) || !S_ISDIR(s.st_mode) || s.st_uid != geteuid() || (s.st_mode & 0022)) return 2;
    char parent[PATH_MAX]; if (strlen(argv[2]) >= sizeof(parent)) return 2;
    strcpy(parent, argv[2]); char *slash = strrchr(parent, '/'); if (!slash || slash == parent) return 2; *slash = 0;
    if (strcmp(parent, argv[3])) return 2;
    int ready[2]; if (pipe2(ready, O_CLOEXEC)) return 1;
    pid_t daemon = fork(); if (daemon < 0) return 1;
    if (!daemon) { close(ready[0]); daemon_run(ready[1], argv[1], argv[2], argv[3], cols, rows, argv[6]); }
    close(ready[1]); struct pollfd p = {ready[0], POLLIN, 0}; char answer = 0;
    if (poll(&p, 1, 4000) > 0 && read(ready[0], &answer, 1) != 1) answer = 0;
    close(ready[0]); if (answer != 'Y') { kill(daemon, SIGTERM); (void)waitpid(daemon, NULL, 0); return 1; }
    return 0;
}
