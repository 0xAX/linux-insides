Timers and time management in the Linux kernel. Part 7.
================================================================================

Time related system calls in the Linux kernel
--------------------------------------------------------------------------------

This is the seventh and last part [chapter](https://0xax.gitbook.io/linux-insides/summary/timers/), which describes timers and time management related stuff in the Linux kernel. In the previous [part](https://0xax.gitbook.io/linux-insides/summary/timers/linux-timers-6), we discussed timers in the context of [x86_64](https://en.wikipedia.org/wiki/X86-64): [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer) and [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter). Internal time management is an interesting part of the Linux kernel, but of course not only the kernel needs the `time` concept. Our programs also need to know time. In this part, we will consider implementation of some time management related [system calls](https://en.wikipedia.org/wiki/System_call). These system calls are:

* `clock_gettime`;
* `gettimeofday`;
* `nanosleep`.

We will start from a simple userspace [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) program and see all way from the call of the [standard library](https://en.wikipedia.org/wiki/Standard_library) function to the implementation of certain system calls. As each [architecture](https://github.com/torvalds/linux/tree/master/arch) provides its own implementation of certain system calls, we will consider only [x86_64](https://en.wikipedia.org/wiki/X86-64) specific implementations of system calls, as this book is related to this architecture.

Additionally, we will not consider the concept of system calls in this part, but only implementations of these three system calls in the Linux kernel. If you are interested in what is a `system call`, there is a special [chapter](https://0xax.gitbook.io/linux-insides/summary/syscall) about this.

So, let's start from the `gettimeofday` system call.

Implementation of the `gettimeofday` system call
--------------------------------------------------------------------------------

As we can understand from the name `gettimeofday`, this function returns the current time. First of all, let's look at the following simple example:

```C
#include <time.h>
#include <sys/time.h>
#include <stdio.h>

int main(int argc, char **argv)
{
    char buffer[40];
    struct timeval time;
        
    gettimeofday(&time, NULL);

    strftime(buffer, 40, "Current date/time: %m-%d-%Y/%T", localtime(&time.tv_sec));
    printf("%s\n",buffer);

    return 0;
}
```

As you can see, here we call the `gettimeofday` function, which takes two parameters. The first parameter is a pointer to the `timeval` structure, which represents an elapsed time:

```C
struct timeval {
    time_t      tv_sec;     /* seconds */
    suseconds_t tv_usec;    /* microseconds */
};
```

The second parameter of the `gettimeofday` function is a pointer to the `timezone` structure which represents a timezone. In our example, we pass address of the `timeval time` to the `gettimeofday` function, the Linux kernel fills the given `timeval` structure and returns it back to us. Additionally, we format the time with the `strftime` function to get something more human readable than elapsed microseconds. Let's see the result:

```C
~$ gcc date.c -o date
~$ ./date
Current date/time: 03-26-2016/16:42:02
```

As you may already know, a userspace application does not call a system call directly from the kernel space. Before the actual system call entry will be called, we call a function from the standard library. In my case it is [glibc](https://en.wikipedia.org/wiki/GNU_C_Library), so I will consider this case. The implementation of the `gettimeofday` function is located in the [sysdeps/unix/sysv/linux/x86/gettimeofday.c](https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/unix/sysv/linux/x86/gettimeofday.c;h=36f7c26ffb0e818709d032c605fec8c4bd22a14e;hb=HEAD) source code file. As you already may know, the `gettimeofday` is not a usual system call. It is located in the special area which is called `vDSO` (you can read more about it in the [part](https://0xax.gitbook.io/linux-insides/summary/syscall/linux-syscall-3), which describes this concept).

The `glibc` implementation of `gettimeofday` tries to resolve the given symbol; in our case this symbol is `__vdso_gettimeofday` by the call of the `_dl_vdso_vsym` internal function. If the symbol cannot be resolved, it returns `NULL` and we fallback to the call of the usual system call:

```C
return (_dl_vdso_vsym ("__vdso_gettimeofday", &linux26)
  ?: (void*) (&__gettimeofday_syscall));
```

The `gettimeofday` entry is located in the [arch/x86/entry/vdso/vclock_gettime.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vdso/vclock_gettime.c) source code file. As we can see the `gettimeofday` is a weak alias of the `__vdso_gettimeofday`:

```C
int gettimeofday(struct timeval *, struct timezone *)
	__attribute__((weak, alias("__vdso_gettimeofday")));
```

The `__vdso_gettimeofday` is defined in the same source code file and calls the `do_realtime` function if the given `timeval` is not null:

```C
notrace int __vdso_gettimeofday(struct timeval *tv, struct timezone *tz)
{
	if (likely(tv != NULL)) {
		if (unlikely(do_realtime((struct timespec *)tv) == VCLOCK_NONE))
			return vdso_fallback_gtod(tv, tz);
		tv->tv_usec /= 1000;
	}
	if (unlikely(tz != NULL)) {
		tz->tz_minuteswest = gtod->tz_minuteswest;
		tz->tz_dsttime = gtod->tz_dsttime;
	}

	return 0;
}
```

If the `do_realtime` will fail, we fallback to the real system call via call the `syscall` instruction and passing the `__NR_gettimeofday` system call number and the given `timeval` and `timezone`:

```C
notrace static long vdso_fallback_gtod(struct timeval *tv, struct timezone *tz)
{
	long ret;

	asm("syscall" : "=a" (ret) :
	    "0" (__NR_gettimeofday), "D" (tv), "S" (tz) : "memory");
	return ret;
}
```

The `do_realtime` function gets the time data from the `vsyscall_gtod_data` structure which is defined in the [arch/x86/include/asm/vgtod.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/vgtod.h#L16) header file and contains mapping of the `timespec` structure and a couple of fields which are related to the current clock source in the system. This function fills the given `timeval` structure with values from the `vsyscall_gtod_data` which contains a time related data which is updated via timer interrupt.

First of all we try to access the `gtod` or `global time of day` the `vsyscall_gtod_data` structure via the call of the `gtod_read_begin` and will continue to do it until it will be successful:

```C
do {
	seq = gtod_read_begin(gtod);
	mode = gtod->vclock_mode;
	ts->tv_sec = gtod->wall_time_sec;
	ns = gtod->wall_time_snsec;
	ns += vgetsns(&mode);
	ns >>= gtod->shift;
} while (unlikely(gtod_read_retry(gtod, seq)));

ts->tv_sec += __iter_div_u64_rem(ns, NSEC_PER_SEC, &ns);
ts->tv_nsec = ns;
```

As we got access to the `gtod`, we fill the `ts->tv_sec` with the `gtod->wall_time_sec` which stores current time in seconds gotten from the [real time clock](https://en.wikipedia.org/wiki/Real-time_clock) during initialization of the timekeeping subsystem in the Linux kernel and the same value but in nanoseconds. In the end of this code we just fill the given `timespec` structure with the resulted values.

That's all about the `gettimeofday` system call. The next system call in our list is the `clock_gettime`.

Implementation of the clock_gettime system call
--------------------------------------------------------------------------------

The `clock_gettime` function gets the time which is specified by the second parameter. Generally the `clock_gettime` function takes two parameters:

* `clk_id` - clock identifier;
* `timespec` - address of the `timespec` structure which represent elapsed time.

Let's look on the following simple example:

```C
#include <time.h>
#include <sys/time.h>
#include <stdio.h>

int main(int argc, char **argv)
{
    struct timespec elapsed_from_boot;

    clock_gettime(CLOCK_BOOTTIME, &elapsed_from_boot);

    printf("%d - seconds elapsed from boot\n", elapsed_from_boot.tv_sec);
    
    return 0;
}
```

which prints `uptime` information:

```C
~$ gcc uptime.c -o uptime
~$ ./uptime
14180 - seconds elapsed from boot
```

We can easily check the result with the help of the [uptime](https://en.wikipedia.org/wiki/Uptime#Using_uptime) util:

```
~$ uptime
up  3:56
```

The `elapsed_from_boot.tv_sec` represents elapsed time in seconds, so:

```python
>>> 14180 / 60
236
>>> 14180 / 60 / 60
3
>>> 14180 / 60 % 60
56
```

The `clock_id` maybe one of the following:

* `CLOCK_REALTIME` - system wide clock which measures real or wall-clock time;
* `CLOCK_REALTIME_COARSE` - faster version of the `CLOCK_REALTIME`;
* `CLOCK_MONOTONIC` - represents monotonic time since some unspecified starting point; 
* `CLOCK_MONOTONIC_COARSE` - faster version of the `CLOCK_MONOTONIC`;
* `CLOCK_MONOTONIC_RAW` - the same as the `CLOCK_MONOTONIC` but provides non [NTP](https://en.wikipedia.org/wiki/Network_Time_Protocol) adjusted time. 
* `CLOCK_BOOTTIME` - the same as the `CLOCK_MONOTONIC` but plus time that the system was suspended;
* `CLOCK_PROCESS_CPUTIME_ID` - per-process time consumed by all threads in the process;
* `CLOCK_THREAD_CPUTIME_ID` - thread-specific clock.

The `clock_gettime` is not usual syscall too, but as the `gettimeofday`, this system call is placed in the `vDSO` area. Entry of this system call is located in the same source code file - [arch/x86/entry/vdso/vclock_gettime.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vdso/vclock_gettime.c)) as for `gettimeofday`.

The Implementation of the `clock_gettime` depends on the clock id. If we have passed the `CLOCK_REALTIME` clock id, the `do_realtime` function will be called:

```C
notrace int __vdso_clock_gettime(clockid_t clock, struct timespec *ts)
{
	switch (clock) {
	case CLOCK_REALTIME:
		if (do_realtime(ts) == VCLOCK_NONE)
			goto fallback;
		break;
    ...
    ...
    ...
fallback:
	return vdso_fallback_gettime(clock, ts);
}
```

In other cases, the `do_{name_of_clock_id}` function is called. Implementations of some of them is similar. For example if we will pass the `CLOCK_MONOTONIC` clock id:

```C
...
...
...
case CLOCK_MONOTONIC:
	if (do_monotonic(ts) == VCLOCK_NONE)
		goto fallback;
	break;
...
...
...
```

the `do_monotonic` function will be called which is very similar on the implementation of the `do_realtime`:

```C
notrace static int __always_inline do_monotonic(struct timespec *ts)
{
	do {
		seq = gtod_read_begin(gtod);
		mode = gtod->vclock_mode;
		ts->tv_sec = gtod->monotonic_time_sec;
		ns = gtod->monotonic_time_snsec;
		ns += vgetsns(&mode);
		ns >>= gtod->shift;
	} while (unlikely(gtod_read_retry(gtod, seq)));

	ts->tv_sec += __iter_div_u64_rem(ns, NSEC_PER_SEC, &ns);
	ts->tv_nsec = ns;

	return mode;
}
```

We already saw a little about the implementation of this function in the previous paragraph about the `gettimeofday`. There is only one difference here, that the `sec` and `nsec` of our `timespec` value will be based on the `gtod->monotonic_time_sec` instead of `gtod->wall_time_sec` which maps the value of the `tk->tkr_mono.xtime_nsec` or number of [nanoseconds](https://en.wikipedia.org/wiki/Nanosecond) elapsed.

That's all.

Implementation of the `nanosleep` system call
--------------------------------------------------------------------------------

The last system call in our list is the `nanosleep`. As you can understand from its name, this function provides `sleeping` ability. Let's look on the following simple example:

```C
#include <time.h>
#include <stdlib.h>
#include <stdio.h>

int main (void)
{    
   struct timespec ts = {5,0};

   printf("sleep five seconds\n");
   nanosleep(&ts, NULL);
   printf("end of sleep\n");

   return 0;
}
```

If we will compile and run it, we will see the first line

```
~$ gcc sleep_test.c -o sleep
~$ ./sleep
sleep five seconds
end of sleep
```

and the second line after five seconds.

The `nanosleep` is not located in the `vDSO` area like the `gettimeofday` and the `clock_gettime` functions. So, let's look how the `real` system call which is located in the kernel space will be called by the standard library. The implementation of the `nanosleep` system call will be called with the help of the [syscall](http://www.felixcloutier.com/x86/SYSCALL.html) instruction. Before the execution of the `syscall` instruction, parameters of the system call must be put in processor [registers](https://en.wikipedia.org/wiki/Processor_register) according to order which is described in the [System V Application Binary Interface](http://www.x86-64.org/documentation/abi.pdf) or in other words:

* `rdi` - first parameter;
* `rsi` - second parameter;
* `rdx` - third parameter;
* `r10` - fourth parameter;
* `r8` - fifth parameter;
* `r9` - sixth parameter.

The `nanosleep` system call has two parameters - two pointers to the `timespec` structures. The system call suspends the calling thread until the given timeout has elapsed. Additionally it will finish if a signal interrupts its execution. It takes two parameters, the first is `timespec` which represents timeout for the sleep. The second parameter is the pointer to the `timespec` structure too and it contains remainder of time if the call of the `nanosleep` was interrupted.

As `nanosleep` has two parameters:

```C
int nanosleep(const struct timespec *req, struct timespec *rem);
```

To call system call, we need put the `req` to the `rdi` register, and the `rem` parameter to the `rsi` register. The [glibc](https://en.wikipedia.org/wiki/GNU_C_Library) does these job in the `INTERNAL_SYSCALL` macro which is located in the [sysdeps/unix/sysv/linux/x86_64/sysdep.h](https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/unix/sysv/linux/x86_64/sysdep.h;h=d023d68174d3dfb4e698160b31ae31ad291802e1;hb=HEAD) header file.

```C
# define INTERNAL_SYSCALL(name, err, nr, args...) \
  INTERNAL_SYSCALL_NCS (__NR_##name, err, nr, ##args)
```

which takes the name of the system call, storage for possible error during execution of system call, number of the system call (all `x86_64` system calls you can find in the [system calls table](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/syscalls/syscall_64.tbl)) and arguments of certain system call. The `INTERNAL_SYSCALL` macro just expands to the call of the `INTERNAL_SYSCALL_NCS` macro, which prepares arguments of system call (puts them into the processor registers in correct order), executes `syscall` instruction and returns the result:

```C
# define INTERNAL_SYSCALL_NCS(name, err, nr, args...)      \
  ({									                                      \
    unsigned long int resultvar;					                          \
    LOAD_ARGS_##nr (args)						                              \
    LOAD_REGS_##nr							                                  \
    asm volatile (							                                  \
    "syscall\n\t"							                                  \
    : "=a" (resultvar)							                              \
    : "0" (name) ASM_ARGS_##nr : "memory", REGISTERS_CLOBBERED_BY_SYSCALL);   \
    (long int) resultvar; })
```

The `LOAD_ARGS_##nr` macro calls the `LOAD_ARGS_N` macro where the `N` is number of arguments of the system call. In our case, it will be the `LOAD_ARGS_2` macro. Ultimately all of these macros will be expanded to the following:

```C
# define LOAD_REGS_TYPES_1(t1, a1)					   \
  register t1 _a1 asm ("rdi") = __arg1;					   \
  LOAD_REGS_0

# define LOAD_REGS_TYPES_2(t1, a1, t2, a2)				   \
  register t2 _a2 asm ("rsi") = __arg2;					   \
  LOAD_REGS_TYPES_1(t1, a1)
...
...
...
```

After the `syscall` instruction will be executed, the [context switch](https://en.wikipedia.org/wiki/Context_switch) will occur and the kernel will transfer execution to the system call handler. The system call handler for the `nanosleep` system call is located in the [kernel/time/hrtimer.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/time/hrtimer.c) source code file and defined with the `SYSCALL_DEFINE2` macro helper:

```C
SYSCALL_DEFINE2(nanosleep, struct timespec __user *, rqtp,
		struct timespec __user *, rmtp)
{
	struct timespec tu;

	if (copy_from_user(&tu, rqtp, sizeof(tu)))
		return -EFAULT;

	if (!timespec_valid(&tu))
		return -EINVAL;

	return hrtimer_nanosleep(&tu, rmtp, HRTIMER_MODE_REL, CLOCK_MONOTONIC);
}
```

More about the `SYSCALL_DEFINE2` macro you may read in the [chapter](https://0xax.gitbook.io/linux-insides/summary/syscall) about system calls. If we look at the implementation of the `nanosleep` system call, first of all we will see that it starts from the call of the `copy_from_user` function. This function copies the given data from the userspace to kernelspace. In our case we copy timeout value to sleep to the kernelspace `timespec` structure and check that the given `timespec` is valid by the call of the `timesc_valid` function:

```C
static inline bool timespec_valid(const struct timespec *ts)
{
	if (ts->tv_sec < 0)
		return false;
	if ((unsigned long)ts->tv_nsec >= NSEC_PER_SEC)
		return false;
	return true;
}
```

which just checks that the given `timespec` does not represent date before `1970` and nanoseconds does not overflow `1` second. The `nanosleep` function ends with the call of the `hrtimer_nanosleep` function from the same source code file. The `hrtimer_nanosleep` function creates a [timer](https://0xax.gitbook.io/linux-insides/summary/timers/linux-timers-4) and calls the `do_nanosleep` function. The `do_nanosleep` does main job for us. This function provides loop:

```C
do {
	set_current_state(TASK_INTERRUPTIBLE);
	hrtimer_start_expires(&t->timer, mode);

	if (likely(t->task))
		freezable_schedule();
    
} while (t->task && !signal_pending(current));

__set_current_state(TASK_RUNNING);
return t->task == NULL;
```

Which freezes current task during sleep. After we set `TASK_INTERRUPTIBLE` flag for the current task, the `hrtimer_start_expires` function starts the give high-resolution timer on the current processor. As the given high resolution timer will expire, the task will be again running.

That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the seventh part of the [chapter](https://0xax.gitbook.io/linux-insides/summary/timers/) that describes timers and timer management related stuff in the Linux kernel. In the previous part we saw [x86_64](https://en.wikipedia.org/wiki/X86-64) specific clock sources. As I wrote in the beginning, this part is the last part of this chapter. We saw important time management related concepts like `clocksource` and `clockevents` frameworks, `jiffies` counter and etc., in this chpater. Of course this does not cover all of the time management in the Linux kernel. Many parts of this mostly related to the scheduling which we will see in other chapter. 

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](mailto:anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**


Links
--------------------------------------------------------------------------------

* [system call](https://en.wikipedia.org/wiki/System_call)
* [C programming language](https://en.wikipedia.org/wiki/C_%28programming_language%29)
* [standard library](https://en.wikipedia.org/wiki/Standard_library)
* [glibc](https://en.wikipedia.org/wiki/GNU_C_Library)
* [real time clock](https://en.wikipedia.org/wiki/Real-time_clock)
* [NTP](https://en.wikipedia.org/wiki/Network_Time_Protocol)
* [nanoseconds](https://en.wikipedia.org/wiki/Nanosecond)
* [register](https://en.wikipedia.org/wiki/Processor_register)
* [System V Application Binary Interface](http://www.x86-64.org/documentation/abi.pdf)
* [context switch](https://en.wikipedia.org/wiki/Context_switch)
* [Introduction to timers in the Linux kernel](https://0xax.gitbook.io/linux-insides/summary/timers/linux-timers-4)
* [uptime](https://en.wikipedia.org/wiki/Uptime#Using_uptime)
* [system calls table for x86_64](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/syscalls/syscall_64.tbl)
* [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer)
* [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [previous part](https://0xax.gitbook.io/linux-insides/summary/timers/linux-timers-6)
