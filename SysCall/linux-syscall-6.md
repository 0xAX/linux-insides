Limits on resources in Linux
================================================================================

Each process in the system uses certain amount of different resources like files, CPU time, memory and so on.

Such resources are not infinite and each process and we should have an instrument to manage it. Sometimes it is useful to know current limits for a certain resource or to change it's value. In this post we will consider such instruments that allow us to get information about limits for a process and increase or decrease such limits.

We will start from userspace view and then we will look how it is implemented in the Linux kernel.

There are three main fundamental [system calls](https://en.wikipedia.org/wiki/System_call) to manage resource limit for a process:

  * `getrlimit`
  * `setrlimit`
  * `prlimit`

The first two allows a process to read and set limits on a system resource. The last one is extension for previous functions. The `prlimit` allows to set and read the resource limits of a process specified by [PID](https://en.wikipedia.org/wiki/Process_identifier). Definitions of these functions looks:

The `getrlimit` is:

```C
int getrlimit(int resource, struct rlimit *rlim);
```

The `setrlimit` is:

```C
int setrlimit(int resource, const struct rlimit *rlim);
```

And the definition of the `prlimit` is:

```C
int prlimit(pid_t pid, int resource, const struct rlimit *new_limit,
            struct rlimit *old_limit);
```

In the first two cases, functions takes two parameters:

  * `resource` - represents resource type (we will see available types later);
  * `rlim` - combination of `soft` and `hard` limits.

There are two types of limits:

  * `soft`
  * `hard`

The first provides actual limit for a resource of a process. The second is a ceiling value of a `soft` limit and can be set only by superuser. So, `soft` limit can never exceed related `hard` limit.

Both these values are combined in the `rlimit` structure:

```C
struct rlimit {
    rlim_t rlim_cur;
    rlim_t rlim_max;
};
```

The last one function looks a little bit complex and takes `4` arguments. Besides `resource` argument, it takes:

  * `pid` - specifies an ID of a process on which the `prlimit` should be executed;
  * `new_limit` - provides new limits values if it is not `NULL`;
  * `old_limit` - current `soft` and `hard` limits will be placed here if it is not `NULL`.

Exactly `prlimit` function is used by [ulimit](https://www.gnu.org/software/bash/manual/html_node/Bash-Builtins.html#index-ulimit) util. We can verify this with the help of [strace](https://linux.die.net/man/1/strace) util.

For example:

```
~$ strace ulimit -s 2>&1 | grep rl

prlimit64(0, RLIMIT_NPROC, NULL, {rlim_cur=63727, rlim_max=63727}) = 0
prlimit64(0, RLIMIT_NOFILE, NULL, {rlim_cur=1024, rlim_max=4*1024}) = 0
prlimit64(0, RLIMIT_STACK, NULL, {rlim_cur=8192*1024, rlim_max=RLIM64_INFINITY}) = 0
```

Here we can see `prlimit64`, but not the `prlimit`. The fact is that we see underlying system call here instead of library call.

Now let's look at list of available resources:

| Resource          | Description
|-------------------|------------------------------------------------------------------------------------------|
| RLIMIT_CPU        | CPU time limit given in seconds                                                          |
| RLIMIT_FSIZE      | the maximum size of files that a process may create                                      |
| RLIMIT_DATA       | the maximum  size  of  the process's data segment                                        |
| RLIMIT_STACK      | the maximum size of the process stack in bytes                                           |
| RLIMIT_CORE       | the maximum size of a [core](http://man7.org/linux/man-pages/man5/core.5.html) file.     |
| RLIMIT_RSS        | the number of bytes that can be allocated for a process in RAM                           |
| RLIMIT_NPROC      | the maximum number of processes that can be created by a user                            |
| RLIMIT_NOFILE     | the maximum number of a file descriptor that can be opened by a process                  |
| RLIMIT_MEMLOCK    | the maximum number of bytes of memory that may be locked into RAM by [mlock](http://man7.org/linux/man-pages/man2/mlock.2.html).|
| RLIMIT_AS         | the maximum size of virtual memory in bytes.                                             |
| RLIMIT_LOCKS      | the maximum number [flock](https://linux.die.net/man/1/flock) and locking related [fcntl](http://man7.org/linux/man-pages/man2/fcntl.2.html) calls|
| RLIMIT_SIGPENDING | maximum number of [signals](http://man7.org/linux/man-pages/man7/signal.7.html) that may be queued for a user of the calling process|
| RLIMIT_MSGQUEUE   | the number of bytes that can be allocated for [POSIX message queues](http://man7.org/linux/man-pages/man7/mq_overview.7.html) |
| RLIMIT_NICE       | the maximum [nice](https://linux.die.net/man/1/nice) value that can be set by a process  |
| RLIMIT_RTPRIO     | maximum real-time priority value                                                         |
| RLIMIT_RTTIME     | maximum number of microseconds that a process may be scheduled under real-time scheduling policy without making blocking system call|

If you're looking into source code of open source projects, you will note that reading or updating of a resource limit is quite widely used operation.

For example: [systemd](https://github.com/systemd/systemd/blob/01a45898fce8def67d51332bccc410eb1e8710e7/src/core/main.c)

```C
/* Don't limit the coredump size */
(void) setrlimit(RLIMIT_CORE, &RLIMIT_MAKE_CONST(RLIM_INFINITY));
```

Or [haproxy](https://github.com/haproxy/haproxy/blob/25f067ccec52f53b0248a05caceb7841a3cb99df/src/haproxy.c):

```C
getrlimit(RLIMIT_NOFILE, &limit);
if (limit.rlim_cur < global.maxsock) {
	Warning("[%s.main()] FD limit (%d) too low for maxconn=%d/maxsock=%d. Please raise 'ulimit-n' to %d or more to avoid any trouble.\n",
		argv[0], (int)limit.rlim_cur, global.maxconn, global.maxsock, global.maxsock);
}
```

We've just saw a little bit about resources limits related stuff in the userspace, now let's look at the same system calls in the Linux kernel.

Limits on resource in the Linux kernel
--------------------------------------------------------------------------------

Both implementation of `getrlimit` system call and `setrlimit` looks similar. Both they execute `do_prlimit` function that is core implementation of the `prlimit` system call and copy from/to given `rlimit` from/to userspace:

The `getrlimit`:

```C
SYSCALL_DEFINE2(getrlimit, unsigned int, resource, struct rlimit __user *, rlim)
{
	struct rlimit value;
	int ret;

	ret = do_prlimit(current, resource, NULL, &value);
	if (!ret)
		ret = copy_to_user(rlim, &value, sizeof(*rlim)) ? -EFAULT : 0;

	return ret;
}
```

and `setrlimit`:

```C
SYSCALL_DEFINE2(setrlimit, unsigned int, resource, struct rlimit __user *, rlim)
{
	struct rlimit new_rlim;

	if (copy_from_user(&new_rlim, rlim, sizeof(*rlim)))
		return -EFAULT;
	return do_prlimit(current, resource, &new_rlim, NULL);
}
```

Implementations of these system calls are defined in the [kernel/sys.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/sys.c) kernel source code file.

First of all the `do_prlimit` function executes a check that the given resource is valid:

```C
if (resource >= RLIM_NLIMITS)
	return -EINVAL;
```

and in a failure case returns `-EINVAL` error. After this check will pass successfully and new limits was passed as non `NULL` value, two following checks:

```C
if (new_rlim) {
	if (new_rlim->rlim_cur > new_rlim->rlim_max)
		return -EINVAL;
	if (resource == RLIMIT_NOFILE &&
			new_rlim->rlim_max > sysctl_nr_open)
		return -EPERM;
}
```

check that the given `soft` limit does not exceed `hard` limit and in a case when the given resource is the maximum number of a file descriptors that hard limit is not greater than `sysctl_nr_open` value. The value of the `sysctl_nr_open` can be found via [procfs](https://en.wikipedia.org/wiki/Procfs):

```
~$ cat /proc/sys/fs/nr_open 
1048576
```

After all of these checks we lock `tasklist` to be sure that [signal]() handlers related things will not be destroyed while we updating limits for a given resource:

```C
read_lock(&tasklist_lock);
...
...
...
read_unlock(&tasklist_lock);
```

We need to do this because `prlimit` system call allows us to update limits of another task by the given pid. As task list is locked, we take the `rlimit` instance that is responsible for the given resource limit of the given process:

```C
rlim = tsk->signal->rlim + resource;
```

where the `tsk->signal->rlim` is just array of `struct rlimit` that represents certain resources. And if the `new_rlim` is not `NULL` we just update its value. If `old_rlim` is not `NULL` we fill it:

```C
if (old_rlim)
    *old_rlim = *rlim;
```

That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the second part that describes implementation of the system calls in the Linux kernel. If you have questions or suggestions, ping me on Twitter [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-internals/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

* [system calls](https://en.wikipedia.org/wiki/System_call)
* [PID](https://en.wikipedia.org/wiki/Process_identifier)
* [ulimit](https://www.gnu.org/software/bash/manual/html_node/Bash-Builtins.html#index-ulimit)
* [strace](https://linux.die.net/man/1/strace)
* [POSIX message queues](http://man7.org/linux/man-pages/man7/mq_overview.7.html)
