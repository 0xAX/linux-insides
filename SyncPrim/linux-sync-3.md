Synchronization primitives in the Linux kernel. Part 3.
================================================================================

Semaphores
--------------------------------------------------------------------------------

This is the third part of the [chapter](https://0xax.gitbook.io/linux-insides/summary/syncprim) which describes synchronization primitives in the Linux kernel and in the previous part we saw special type of [spinlocks](https://en.wikipedia.org/wiki/Spinlock) - `queued spinlocks`. The previous [part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-2) was the last part which describes `spinlocks` related stuff. So we need to go ahead.

The next [synchronization primitive](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) after `spinlock` which we will see in this part is [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29). We will start from theoretical side and will learn what is it `semaphore` and only after this, we will see how it is implemented in the Linux kernel as we did in the previous part.

So, let's start.

Introduction to the semaphores in the Linux kernel
--------------------------------------------------------------------------------

So, what is it `semaphore`? As you may guess - `semaphore` is yet another mechanism for support of thread or process synchronization. The Linux kernel already provides implementation of one synchronization mechanism - `spinlocks`, why do we need in yet another one? To answer on this question we need to know details of both of these mechanisms. We already familiar with the `spinlocks`, so let's start from this mechanism.

`spinlock` creates a lock which will be acquired to protect a shared resource from being modified by more than one process. As a result, other processes that try to acquire the current lock get stopped (aka "spin-in-place" or busy waiting). [Context switch](https://en.wikipedia.org/wiki/Context_switch) is not allowed because [preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29) is disabled to avoid [deadlocks](https://en.wikipedia.org/wiki/Deadlock). As a result, `spinlock` should only be used if the lock will only be acquired for a very short period of time, otherwise amount of busy waiting accumulated by other processes results in extremely inefficient operation. For locks that need to be acquired for a relatively long period of time, we turn to `semaphore`.

[semaphores](https://en.wikipedia.org/wiki/Semaphore_%28programming%29) is a good solution for locks which may be acquired for a long time. In other way this mechanism is not optimal for locks that acquired for a short time. To understand this, we need to know what is `semaphore`.

As usual synchronization primitive, a `semaphore` is based on a variable. This variable may be incremented or decremented and it's state will represent ability to acquire lock. Notice that value of the variable is not limited to `0` and `1`. There are two types of `semaphores`:

* `binary semaphore`;
* `normal semaphore`.

In the first case, value of `semaphore` may be only `1` or `0`. In the second case value of `semaphore` any non-negative number. If the value of `semaphore` is greater than `1` it is called as `counting semaphore` and it allows to acquire a lock to more than `1` process. This allows us to keep records of available resources, when `spinlock` allows to hold a lock only on one task. Besides all of this, one more important thing that `semaphore` allows to sleep. Moreover when processes waits for a lock which is acquired by other process, the [scheduler](https://en.wikipedia.org/wiki/Scheduling_%28computing%29) may switch on another process.

Semaphore API
--------------------------------------------------------------------------------

So, we know a little about `semaphores` from theoretical side, let's look on its implementation in the Linux kernel. All `semaphore` [API](https://en.wikipedia.org/wiki/Application_programming_interface) is located in the [include/linux/semaphore.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/semaphore.h) header file.

We may see that the `semaphore` mechanism is represented by the following structure:

```C
struct semaphore {
	raw_spinlock_t		lock;
	unsigned int		count;
	struct list_head	wait_list;
};
```

in the Linux kernel. The `semaphore` structure consists of three fields:

* `lock` - `spinlock` for a `semaphore` data protection;
* `count` - amount available resources;
* `wait_list` - list of processes which are waiting to acquire a lock.

Before we will consider an [API](https://en.wikipedia.org/wiki/Application_programming_interface) of the `semaphore` mechanism in the Linux kernel, we need to know how to initialize a `semaphore`. Actually the Linux kernel provides two approaches to execute initialization of the given `semaphore` structure. These methods allows to initialize a `semaphore` in a:

* `statically`;
* `dynamically`.

ways. Let's look at the first approach. We are able to initialize a `semaphore` statically with the `DEFINE_SEMAPHORE` macro:

```C
#define DEFINE_SEMAPHORE(name)  \
         struct semaphore name = __SEMAPHORE_INITIALIZER(name, 1)
```

as we may see, the `DEFINE_SEMAPHORE` macro provides ability to initialize only `binary` semaphore. The `DEFINE_SEMAPHORE` macro expands to the definition of the `semaphore` structure which is initialized with the `__SEMAPHORE_INITIALIZER` macro. Let's look at the implementation of this macro:

```C
#define __SEMAPHORE_INITIALIZER(name, n)              \
{                                                                       \
        .lock           = __RAW_SPIN_LOCK_UNLOCKED((name).lock),        \
        .count          = n,                                            \
        .wait_list      = LIST_HEAD_INIT((name).wait_list),             \
}
```

The `__SEMAPHORE_INITIALIZER` macro takes the name of the future `semaphore` structure and does initialization of the fields of this structure. First of all we initialize a `spinlock` of the given `semaphore` with the `__RAW_SPIN_LOCK_UNLOCKED` macro. As you may remember from the [previous](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-1) parts, the `__RAW_SPIN_LOCK_UNLOCKED` is defined in the [include/linux/spinlock_types.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/spinlock_types.h) header file and expands to the `__ARCH_SPIN_LOCK_UNLOCKED` macro which just expands to zero or unlocked state:

```C
#define __ARCH_SPIN_LOCK_UNLOCKED       { { 0 } }
```

The last two fields of the `semaphore` structure `count` and `wait_list` are initialized with the given value which represents count of available resources and empty [list](https://0xax.gitbook.io/linux-insides/summary/datastructures/linux-datastructures-1).

The second way to initialize a `semaphore` structure is to pass the `semaphore` and number of available resources to the `sema_init` function which is defined in the [include/linux/semaphore.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/semaphore.h) header file:

```C
static inline void sema_init(struct semaphore *sem, int val)
{
       static struct lock_class_key __key;
       *sem = (struct semaphore) __SEMAPHORE_INITIALIZER(*sem, val);
       lockdep_init_map(&sem->lock.dep_map, "semaphore->lock", &__key, 0);
}
```

Let's consider implementation of this function. It looks pretty easy and actually it does almost the same. Thus function executes initialization of the given `semaphore` with the `__SEMAPHORE_INITIALIZER` macro which we just saw. As I already wrote in the previous parts of this [chapter](https://0xax.gitbook.io/linux-insides/summary/syncprim), we will skip the stuff which is related to the [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) of the Linux kernel.

So, from now we are able to initialize a `semaphore` let's look at how to lock and unlock. The Linux kernel provides following [API](https://en.wikipedia.org/wiki/Application_programming_interface) to manipulate `semaphores`:

```
void down(struct semaphore *sem);
void up(struct semaphore *sem);
int  down_interruptible(struct semaphore *sem);
int  down_killable(struct semaphore *sem);
int  down_trylock(struct semaphore *sem);
int  down_timeout(struct semaphore *sem, long jiffies);
```

The first two functions: `down` and `up` are for acquiring and releasing of the given `semaphore`. The `down_interruptible` function tries to acquire a `semaphore`. If this try was successful, the `count` field of the given `semaphore` will be decremented and lock will be acquired, in other way the task will be switched to the blocked state or in other words the `TASK_INTERRUPTIBLE` flag will be set. This `TASK_INTERRUPTIBLE` flag means that the process may returned to ruined state by [signal](https://en.wikipedia.org/wiki/Unix_signal).

The `down_killable` function does the same as the `down_interruptible` function, but set the `TASK_KILLABLE` flag for the current process. This means that the waiting process may be interrupted by the kill signal.

The `down_trylock` function is similar on the `spin_trylock` function. This function tries to acquire a lock and exit if this operation was unsuccessful. In this case the process which wants to acquire a lock, will not wait. The last `down_timeout` function tries to acquire a lock. It will be interrupted in a waiting state when the given timeout will be expired. Additionally, you may notice that the timeout is in [jiffies](https://0xax.gitbook.io/linux-insides/summary/timers/linux-timers-1)

We just saw definitions of the `semaphore` [API](https://en.wikipedia.org/wiki/Application_programming_interface). We will start from the `down` function. This function is defined in the [kernel/locking/semaphore.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/semaphore.c) source code file. Let's look on the implementation function:

```C
void down(struct semaphore *sem)
{
        unsigned long flags;

        raw_spin_lock_irqsave(&sem->lock, flags);
        if (likely(sem->count > 0))
                sem->count--;
        else
                __down(sem);
        raw_spin_unlock_irqrestore(&sem->lock, flags);
}
EXPORT_SYMBOL(down);
```

We may see the definition of the `flags` variable at the beginning of the `down` function. This variable will be passed to the `raw_spin_lock_irqsave` and `raw_spin_lock_irqrestore` macros which are defined in the [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/spinlock.h) header file and protect a counter of the given `semaphore` here. Actually both of these macro do the same that `spin_lock` and `spin_unlock` macros, but additionally they save/restore current value of interrupt flags and disables [interrupts](https://en.wikipedia.org/wiki/Interrupt).

As you already may guess, the main work is done between the `raw_spin_lock_irqsave` and `raw_spin_unlock_irqrestore` macros in the `down` function. We compare the value of the `semaphore` counter with zero and if it is bigger than zero, we may decrement this counter. This means that we already acquired the lock. In other way counter is zero. This means that all available resources already finished and we need to wait to acquire this lock. As we may see, the `__down` function will be called in this case.

The `__down` function is defined in the [same](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/semaphore.c) source code file and its implementation looks:

```C
static noinline void __sched __down(struct semaphore *sem)
{
        __down_common(sem, TASK_UNINTERRUPTIBLE, MAX_SCHEDULE_TIMEOUT);
}
```

The `__down` function just calls the `__down_common` function with three parameters:

* `semaphore`;
* `flag` - for the task;
* `timeout` - maximum timeout to wait `semaphore`.

Before we will consider implementation of the `__down_common` function, notice that implementation of the `down_trylock`, `down_timeout` and `down_killable` functions based on the `__down_common` too:

```C
static noinline int __sched __down_interruptible(struct semaphore *sem)
{
        return __down_common(sem, TASK_INTERRUPTIBLE, MAX_SCHEDULE_TIMEOUT);
}
```

The `__down_killable`:

```C
static noinline int __sched __down_killable(struct semaphore *sem)
{
        return __down_common(sem, TASK_KILLABLE, MAX_SCHEDULE_TIMEOUT);
}
```

And the `__down_timeout`:

```C
static noinline int __sched __down_timeout(struct semaphore *sem, long timeout)
{
        return __down_common(sem, TASK_UNINTERRUPTIBLE, timeout);
}
```

Now let's look at the implementation of the `__down_common` function. This function is defined in the [kernel/locking/semaphore.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/semaphore.c) source code file too and starts from the definition of the two following local variables:

```C
struct task_struct *task = current;
struct semaphore_waiter waiter;
```

The first represents current task for the local processor which wants to acquire a lock. The `current` is a macro which is defined in the [arch/x86/include/asm/current.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/current.h) header file:

```C
#define current get_current()
```

Where the `get_current` function returns value of the `current_task` [per-cpu](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1) variable:

```C
DECLARE_PER_CPU(struct task_struct *, current_task);

static __always_inline struct task_struct *get_current(void)
{
        return this_cpu_read_stable(current_task);
}
```

The second variable is `waiter` represents an entry of a `semaphore.wait_list` list:

```C
struct semaphore_waiter {
        struct list_head list;
        struct task_struct *task;
        bool up;
};
```

Next we add current task to the `wait_list` and fill `waiter` fields after definition of these variables:

```C
list_add_tail(&waiter.list, &sem->wait_list);
waiter.task = task;
waiter.up = false;
```

In the next step we join into the following infinite loop:

```C
for (;;) {
        if (signal_pending_state(state, task))
            goto interrupted;

        if (unlikely(timeout <= 0))
            goto timed_out;

        __set_task_state(task, state);

        raw_spin_unlock_irq(&sem->lock);
        timeout = schedule_timeout(timeout);
        raw_spin_lock_irq(&sem->lock);

        if (waiter.up)
            return 0;
}
```

In the previous piece of code we set `waiter.up` to `false`. So, a task will spin in this loop while `up` will not be set to `true`. This loop starts from the check that the current task is in the `pending` state or in other words flags of this task contains `TASK_INTERRUPTIBLE` or `TASK_WAKEKILL` flag. As I already wrote above a task may be interrupted by [signal](https://en.wikipedia.org/wiki/Unix_signal) during wait of ability to acquire a lock. The `signal_pending_state` function is defined in the [include/linux/sched.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/sched.h) source code file and looks:

```C
static inline int signal_pending_state(long state, struct task_struct *p)
{
         if (!(state & (TASK_INTERRUPTIBLE | TASK_WAKEKILL)))
                 return 0;
         if (!signal_pending(p))
                 return 0;

         return (state & TASK_INTERRUPTIBLE) || __fatal_signal_pending(p);
}
```

We check that the `state` [bitmask](https://en.wikipedia.org/wiki/Mask_%28computing%29) contains `TASK_INTERRUPTIBLE` or `TASK_WAKEKILL` bits and if the bitmask does not contain this bit we exit. At the next step we check that the given task has a pending signal and exit if there is not. In the end we just check `TASK_INTERRUPTIBLE` bit in the `state` bitmask again or the [SIGKILL](https://en.wikipedia.org/wiki/Unix_signal#SIGKILL) signal. So, if our task has a pending signal, we will jump at the `interrupted` label:

```C
interrupted:
    list_del(&waiter.list);
    return -EINTR;
```

where we delete task from the list of lock waiters and return the `-EINTR` [error code](https://en.wikipedia.org/wiki/Errno.h). If a task has no pending signal, we check the given timeout and if it is less or equal zero:

```C
if (unlikely(timeout <= 0))
    goto timed_out;
```

we jump at the `timed_out` label:

```C
timed_out:
    list_del(&waiter.list);
    return -ETIME;
```

Where we do almost the same that we did in the `interrupted` label. We delete task from the list of lock waiters, but return the `-ETIME` error code. If a task has no pending signal and the given timeout is not expired yet, the given `state` will be set in the given task:

```C
__set_task_state(task, state);
```

and call the `schedule_timeout` function:

```C
raw_spin_unlock_irq(&sem->lock);
timeout = schedule_timeout(timeout);
raw_spin_lock_irq(&sem->lock);
```

which is defined in the [kernel/time/timer.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/time/timer.c) source code file. The `schedule_timeout` function makes the current task sleep until the given timeout.

That is all about the `__down_common` function. A task which wants to acquire a lock which is already acquired by another task will be spun in the infinite loop while it will not be interrupted by a signal, the given timeout will not be expired or the task which holds a lock will not release it. Now let's look at the implementation of the `up` function.

The `up` function is defined in the [same](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/semaphore.c) source code file as `down` function. As we already know, the main purpose of this function is to release a lock. This function looks:

```C
void up(struct semaphore *sem)
{
        unsigned long flags;

        raw_spin_lock_irqsave(&sem->lock, flags);
        if (likely(list_empty(&sem->wait_list)))
                sem->count++;
        else
                __up(sem);
        raw_spin_unlock_irqrestore(&sem->lock, flags);
}
EXPORT_SYMBOL(up);
```

It looks almost the same as the `down` function. There are only two differences here. First of all we increment a counter of a `semaphore` if the list of waiters is empty. In other way we call the `__up` function from the same source code file. If the list of waiters is not empty we need to allow the first task from the list to acquire a lock:

```C
static noinline void __sched __up(struct semaphore *sem)
{
        struct semaphore_waiter *waiter = list_first_entry(&sem->wait_list,
                                                struct semaphore_waiter, list);
        list_del(&waiter->list);
        waiter->up = true;
        wake_up_process(waiter->task);
}
```

Here we takes the first task from the list of waiters, delete it from the list, set its `waiter-up` to true. From this point the infinite loop from the `__down_common` function will be stopped. The `wake_up_process` function will be called in the end of the `__up` function. As you remember we called the `schedule_timeout` function in the infinite loop from the `__down_common` this function. The `schedule_timeout` function makes the current task sleep until the given timeout will not be expired. So, as our process may sleep right now, we need to wake it up. That's why we call the `wake_up_process` function from the [kernel/sched/core.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/sched/core.c) source code file.

That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the third part of the [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) chapter in the Linux kernel. In the two previous parts we already met the first synchronization primitive `spinlock` provided by the Linux kernel which is implemented as `ticket spinlock` and used for a very short time locks. In this part we saw yet another synchronization primitive - [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29) which is used for long time locks as it leads to [context switch](https://en.wikipedia.org/wiki/Context_switch). In the next part we will continue to dive into synchronization primitives in the Linux kernel and will see next synchronization primitive - [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion).

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](mailto:anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [spinlocks](https://en.wikipedia.org/wiki/Spinlock)
* [synchronization primitive](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29)
* [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29)
* [context switch](https://en.wikipedia.org/wiki/Context_switch)
* [preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29)
* [deadlocks](https://en.wikipedia.org/wiki/Deadlock)
* [scheduler](https://en.wikipedia.org/wiki/Scheduling_%28computing%29)
* [Doubly linked list in the Linux kernel](https://0xax.gitbook.io/linux-insides/summary/datastructures/linux-datastructures-1)
* [jiffies](https://0xax.gitbook.io/linux-insides/summary/timers/linux-timers-1)
* [interrupts](https://en.wikipedia.org/wiki/Interrupt)
* [per-cpu](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1)
* [bitmask](https://en.wikipedia.org/wiki/Mask_%28computing%29)
* [SIGKILL](https://en.wikipedia.org/wiki/Unix_signal#SIGKILL)
* [errno](https://en.wikipedia.org/wiki/Errno.h)
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion)
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-2)
