#include "cambc.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static void try_open(cambc_ctx *c, const char *path) {
  int fd = open(path, O_RDONLY);
  char buf[256];
  if (fd >= 0) {
    snprintf(buf, sizeof(buf), "ATTACK SUCCEEDED: open(%s) = %d\n", path, fd);
    cambc_print(c, buf);
    close(fd);
  } else {
    snprintf(buf, sizeof(buf), "blocked: open(%s) errno=%d\n", path, errno);
    cambc_print(c, buf);
  }
}

static void try_socket(cambc_ctx *c) {
  int fd = socket(AF_INET, SOCK_STREAM, 0);
  char buf[256];
  if (fd >= 0) {
    snprintf(buf, sizeof(buf), "ATTACK SUCCEEDED: socket() = %d\n", fd);
    cambc_print(c, buf);
    close(fd);
  } else {
    snprintf(buf, sizeof(buf), "blocked: socket errno=%d\n", errno);
    cambc_print(c, buf);
  }
}

static void try_shm(cambc_ctx *c) {
  long r = syscall(SYS_shmget, 1234, 4096, 0666);
  char buf[256];
  if (r >= 0) {
    snprintf(buf, sizeof(buf), "ATTACK SUCCEEDED: shmget = %ld\n", r);
    cambc_print(c, buf);
  } else {
    snprintf(buf, sizeof(buf), "blocked: shmget errno=%d\n", errno);
    cambc_print(c, buf);
  }
}

static void try_kill(cambc_ctx *c) {
  int r = kill(2, SIGTERM);
  char buf[256];
  if (r == 0) {
    cambc_print(c, "ATTACK SUCCEEDED: kill\n");
  } else {
    snprintf(buf, sizeof(buf), "blocked: kill errno=%d\n", errno);
    cambc_print(c, buf);
  }
}

static void try_fork(cambc_ctx *c) {
  pid_t pid = fork();
  char buf[256];
  if (pid > 0) {
    cambc_print(c, "ATTACK SUCCEEDED: fork (parent saw child)\n");
    waitpid(pid, NULL, 0);
  } else if (pid == 0) {
    _exit(0);
  } else {
    snprintf(buf, sizeof(buf), "blocked: fork errno=%d\n", errno);
    cambc_print(c, buf);
  }
}

static void try_memfd(cambc_ctx *c) {
  long fd = syscall(SYS_memfd_create, "x", 0);
  char buf[256];
  if (fd >= 0) {
    snprintf(buf, sizeof(buf), "ATTACK SUCCEEDED: memfd_create = %ld\n", fd);
    cambc_print(c, buf);
  } else {
    snprintf(buf, sizeof(buf), "blocked: memfd_create errno=%d\n", errno);
    cambc_print(c, buf);
  }
}

static void try_umask(cambc_ctx *c) {
  long r = syscall(SYS_umask, 0);
  char buf[256];
  if (r >= 0) {
    snprintf(buf, sizeof(buf), "ATTACK SUCCEEDED: umask = %ld (returned old)\n",
             r);
    cambc_print(c, buf);
  } else {
    snprintf(buf, sizeof(buf), "blocked: umask errno=%d\n", errno);
    cambc_print(c, buf);
  }
}

int main(void) {
  cambc_ctx *c = cambc_init();
  if (!c)
    return 1;
  if (cambc_round(c) == 0) {
    try_open(c, "/etc/passwd");
    try_open(c, "/proc/self/maps");
    try_open(c, "/dev/shm/something");
    try_socket(c);
    try_shm(c);
    try_kill(c);
    try_fork(c);
    try_memfd(c);
    try_umask(c);
  }
  if (cambc_round(c) == 5) {
    cambc_resign(c, "attacker done");
  }
  while (1) {
    if (cambc_end_turn(c) < 0)
      break;
    if (cambc_round(c) == 5) {
      cambc_resign(c, "attacker done");
      cambc_end_turn(c);
      break;
    }
  }
  cambc_free(c);
  return 0;
}
