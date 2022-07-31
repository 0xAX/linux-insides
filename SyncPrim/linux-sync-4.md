Synchronization primitives in the Linux kernel. Part 4.
================================================================================

Introduction
--------------------------------------------------------------------------------

This is the fourth part of the [chapter](https://0xax.gitbook.io/linux-insides/summary/syncprim) which describes synchronization primitives in the Linux kernel and in the previous parts we finished to consider different types [spinlocks](https://en.wikipedia.org/wiki/Spinlock) and [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29) synchronization primitives. We will continue to learn [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) in this part and consider yet another one which is called - [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion) which is stands for `MUTual EXclusion`.

As in all previous parts of this [book](https://github.com/0xAX/linux-insides/blob/master/SUMMARY.md), we will try to consider this synchronization primitive from the theoretical side and only than we will consider [API](https://en.wikipedia.org/wiki/Application_programming_interface) provided by the Linux kernel to manipulate with `mutexes`.

So, let's start.

Concept of `mutex`
--------------------------------------------------------------------------------

We already familiar with the [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29) synchronization primitive from the previous [part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-3). It represented by the:

```C
struct semaphore {
	raw_spinlock_t		lock;
	unsigned int		count;
	struct list_head	wait_list;
};
```

structure which holds information about state of a [lock](https://en.wikipedia.org/wiki/Lock_%28computer_science%29) and list of a lock waiters. Depending on the value of the `count` field, a `semaphore` can provide access to a resource to more than one processes wishing to access this resource. The [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion) concept is very similar to a [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29) concept. But it has some differences. The main difference between `semaphore` and `mutex` synchronization primitive is that `mutex` has more strict semantic. Unlike a `semaphore`, only one [process](https://en.wikipedia.org/wiki/Process_%28computing%29) may hold `mutex` at one time and only the `owner` of a `mutex` may release or unlock it. Additional difference in implementation of `lock` [API](https://en.wikipedia.org/wiki/Application_programming_interface). The `semaphore` synchronization primitive forces rescheduling of processes which are in waiters list. The implementation of `mutex` lock `API` allows to avoid this situation and has expensive [context switches](https://en.wikipedia.org/wiki/Context_switch).

The `mutex` synchronization primitive represented by the following:

```C
struct mutex {
        atomic_t                count;
        spinlock_t              wait_lock;
        struct list_head        wait_list;
#if defined(CONFIG_DEBUG_MUTEXES) || defined(CONFIG_MUTEX_SPIN_ON_OWNER)
        struct task_struct      *owner;
#endif
#ifdef CONFIG_MUTEX_SPIN_ON_OWNER
        struct optimistic_spin_queue osq;
#endif
#ifdef CONFIG_DEBUG_MUTEXES
        void                    *magic;
#endif
#ifdef CONFIG_DEBUG_LOCK_ALLOC
        struct lockdep_map      dep_map;
#endif
};
```

structure in the Linux kernel. This structure is defined in the [include/linux/mutex.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/mutex.h) header file and contains a set of fields similar to the `semaphore` structure. The first field of the `mutex` structure is - `count`. Value of this field represents state of a `mutex`. In a case when the value of the `count` field is `1`, a `mutex` is in `unlocked` state. When the value of the `count` field is `zero`, a `mutex` is in the `locked` state. Additionally value of the `count` field may be `negative`. In this case a `mutex` is in the `locked` state and has possible waiters.

The next two fields of the `mutex` structure - `wait_lock` and `wait_list` are [spinlock](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/mutex.h) for the protection of a `wait queue` and list of waiters which represents this `wait queue` for a certain lock. As you may notice, the similarity of the `mutex` and `semaphore` structures ends. Remaining fields of the `mutex` structure, as we may see depends on different configuration options of the Linux kernel.

The first field - `owner` represents [process](https://en.wikipedia.org/wiki/Process_%28computing%29) which acquired a lock. As we may see, existence of this field in the `mutex` structure depends on the `CONFIG_DEBUG_MUTEXES` or `CONFIG_MUTEX_SPIN_ON_OWNER` kernel configuration options. Main point of this field and the next `osq` fields is support of `optimistic spinning` which we will see later. The last two fields - `magic` and `dep_map` are used only in [debugging](https://en.wikipedia.org/wiki/Debugging) mode. The `magic` field is to storing a `mutex` related information for debugging and the second field - `lockdep_map` is for [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) of the Linux kernel.

Now, after we have considered the `mutex` structure, we may consider how this synchronization primitive works in the Linux kernel. As you may guess, a process who wants to acquire a lock, must to decrease value of the `mutex->count` if possible. And if a process wants to release a lock, it must to increase the same value. That's true. But as you may also guess, it is not so simple in the Linux kernel.

Actually, when a process try to acquire a `mutex`, there three possible paths:

* `fastpath`;
* `midpath`;
* `slowpath`.

which may be taken, depending on the current state of the `mutex`. The first path or `fastpath` is the fastest as you may understand from its name. Everything is easy in this case. Nobody acquired a `mutex`, so the value of the `count` field of the `mutex` structure may be directly decremented. In a case of unlocking of a `mutex`, the algorithm is the same. A process just increments the value of the `count` field of the `mutex` structure. Of course, all of these operations must be [atomic](https://en.wikipedia.org/wiki/Linearizability).

Yes, this looks pretty easy. But what happens if a process wants to acquire a `mutex` which is already acquired by other process? In this case, the control will be transferred to the second path - `midpath`. The `midpath` or `optimistic spinning` tries to [spin](https://en.wikipedia.org/wiki/Spinlock) with already familiar for us [MCS lock](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf) while the lock owner is running. This path will be executed only if there are no other processes ready to run that have higher priority. This path is called `optimistic` because the waiting task will not sleep and be rescheduled. This allows to avoid expensive [context switch](https://en.wikipedia.org/wiki/Context_switch).

In the last case, when the `fastpath` and `midpath` may not be executed, the last path - `slowpath` will be executed. This path acts like a [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29) lock. If the lock is unable to be acquired by a process, this process will be added to `wait queue` which is represented by the following:

```C
struct mutex_waiter {
        struct list_head        list;
        struct task_struct      *task;
#ifdef CONFIG_DEBUG_MUTEXES
        void                    *magic;
#endif
};
```

structure from the [include/linux/mutex.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/mutex.h) header file and will sleep. Before we will consider [API](https://en.wikipedia.org/wiki/Application_programming_interface) which is provided by the Linux kernel for manipulation of `mutexes`, let's consider the `mutex_waiter` structure. If you have read the [previous part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-3) of this chapter, you may notice that the `mutex_waiter` structure is similar to the `semaphore_waiter` structure from the [kernel/locking/semaphore.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/semaphore.c) source code file:

```C
struct semaphore_waiter {
        struct list_head list;
        struct task_struct *task;
        bool up;
};
```

It also contains `list` and `task` fields which represent entry of the mutex wait queue. The one difference here that the `mutex_waiter` does not contains `up` field, but contains the `magic` field which depends on the `CONFIG_DEBUG_MUTEXES` kernel configuration option and used to store a `mutex` related information for debugging purpose.

Now we know what is a `mutex` and how it is represented the Linux kernel. In this case, we may go ahead and start to look at the [API](https://en.wikipedia.org/wiki/Application_programming_interface) which the Linux kernel provides for manipulation of `mutexes`.

Mutex API
--------------------------------------------------------------------------------

Ok, in the previous paragraph we knew what is a `mutex` synchronization primitive and saw the `mutex` structure which represents `mutex` in the Linux kernel. Now it's time to consider [API](https://en.wikipedia.org/wiki/Application_programming_interface) for manipulation of mutexes. Description of the `mutex` API is located in the [include/linux/mutex.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/mutex.h) header file. As always, before we will consider how to acquire and release a `mutex`, we need to know how to initialize it.

There are two approaches to initializing a `mutex`. The first is to do it statically. For this purpose the Linux kernel provides following:

```C
#define DEFINE_MUTEX(mutexname) \
        struct mutex mutexname = __MUTEX_INITIALIZER(mutexname)
```

macro. Let's consider implementation of this macro. As we may see, the `DEFINE_MUTEX` macro takes name for the `mutex` and expands to the definition of the new `mutex` structure. Additionally new `mutex` structure get initialized with the `__MUTEX_INITIALIZER` macro. Let's look at the implementation of the `__MUTEX_INITIALIZER`:

```C
#define __MUTEX_INITIALIZER(lockname)         \
{                                                             \
       .count = ATOMIC_INIT(1),                               \
       .wait_lock = __SPIN_LOCK_UNLOCKED(lockname.wait_lock), \
       .wait_list = LIST_HEAD_INIT(lockname.wait_list)        \
}
```

This macro is defined in the [same](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/mutex.h) header file and as we may understand it initializes fields of the `mutex` structure to their initial values. The `count` field get initialized with the `1` which represents `unlocked` state of a mutex. The `wait_lock` [spinlock](https://en.wikipedia.org/wiki/Spinlock) get initialized to the unlocked state and the last field `wait_list` to empty [doubly linked list](https://0xax.gitbook.io/linux-insides/summary/datastructures/linux-datastructures-1).

The second approach allows us to initialize a `mutex` dynamically. To do this we need to call the `__mutex_init` function from the [kernel/locking/mutex.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/mutex.c) source code file. Actually, the `__mutex_init` function is rarely called directly. Instead of the `__mutex_init`, the:

```C
# define mutex_init(mutex)                \
do {                                                    \
        static struct lock_class_key __key;             \
                                                        \
        __mutex_init((mutex), #mutex, &__key);          \
} while (0)
```

macro is used. We may see that the `mutex_init` macro just defines the `lock_class_key` and call the `__mutex_init` function. Let's look at the implementation of this function:

```C
void
__mutex_init(struct mutex *lock, const char *name, struct lock_class_key *key)
{
        atomic_set(&lock->count, 1);
        spin_lock_init(&lock->wait_lock);
        INIT_LIST_HEAD(&lock->wait_list);
        mutex_clear_owner(lock);
#ifdef CONFIG_MUTEX_SPIN_ON_OWNER
        osq_lock_init(&lock->osq);
#endif
        debug_mutex_init(lock, name, key);
}
```

As we may see the `__mutex_init` function takes three arguments:

* `lock` - a mutex itself;
* `name` - name of mutex for debugging purpose;
* `key`  - key for [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt).

At the beginning of the `__mutex_init` function, we may see initialization of the `mutex` state. We set it to `unlocked` state with the `atomic_set` function which atomically sets the variable to the given value. After this we may see initialization of the `spinlock` to the unlocked state which will protect `wait queue` of the `mutex` and initialization of the `wait queue` of the `mutex`. After this we clear owner of the `lock` and initialize optimistic queue by the call of the `osq_lock_init` function from the [include/linux/osq_lock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/osq_lock.h) header file. This function just sets the tail of the optimistic queue to the unlocked state:

```C
static inline bool osq_is_locked(struct optimistic_spin_queue *lock)
{
        return atomic_read(&lock->tail) != OSQ_UNLOCKED_VAL;
}
```

In the end of the `__mutex_init` function we may see the call of the `debug_mutex_init` function, but as I already wrote in previous parts of this [chapter](https://0xax.gitbook.io/linux-insides/summary/syncprim), we will not consider debugging related stuff in this chapter.

After the `mutex` structure is initialized, we may go ahead and will look at the `lock` and `unlock` API of `mutex` synchronization primitive. Implementation of `mutex_lock` and `mutex_unlock` functions is located in the [kernel/locking/mutex.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/mutex.c) source code file. First of all let's start from the implementation of the `mutex_lock`. It looks:

```C
void __sched mutex_lock(struct mutex *lock)
{
        might_sleep();
        __mutex_fastpath_lock(&lock->count, __mutex_lock_slowpath);
        mutex_set_owner(lock);
}
```

We may see the call of the `might_sleep` macro from the [include/linux/kernel.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/kernel.h) header file at the beginning of the `mutex_lock` function. Implementation of this macro depends on the `CONFIG_DEBUG_ATOMIC_SLEEP` kernel configuration option and if this option is enabled, this macro just prints a stack trace if it was executed in [atomic](https://en.wikipedia.org/wiki/Linearizability) context. This macro is helper for debugging purposes. In other way this macro does nothing.

After the `might_sleep` macro, we may see the call of the `__mutex_fastpath_lock` function. This function is architecture-specific and as we consider [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture in this book, the implementation of the `__mutex_fastpath_lock` is located in the [arch/x86/include/asm/mutex_64.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/mutex_64.h) header file. As we may understand from the name of the `__mutex_fastpath_lock` function, this function will try to acquire lock in a fast path or in other words this function will try to decrement the value of the `count` of the given mutex.

Implementation of the `__mutex_fastpath_lock` function consists of two parts. The first part is [inline assembly](https://0xax.gitbook.io/linux-insides/summary/theory/linux-theory-3) statement. Let's look at it:

```C
asm_volatile_goto(LOCK_PREFIX "   decl %0\n"
                              "   jns %l[exit]\n"
                              : : "m" (v->counter)
                              : "memory", "cc"
                              : exit);
```

First of all, let's pay attention to the `asm_volatile_goto`. This macro is defined in the [include/linux/compiler-gcc.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/compiler-gcc.h) header file and just expands to the two inline assembly statements:

```C
#define asm_volatile_goto(x...) do { asm goto(x); asm (""); } while (0)
```

The first assembly statement contains `goto` specificator and the second empty inline assembly statement is [barrier](https://en.wikipedia.org/wiki/Memory_barrier). Now let's return to the our inline assembly statement. As we may see it starts from the definition of the `LOCK_PREFIX` macro which just expands to the [lock](http://x86.renejeschke.de/html/file_module_x86_id_159.html) instruction:

```C
#define LOCK_PREFIX LOCK_PREFIX_HERE "\n\tlock; "
```

As we already know from the previous parts, this instruction allows to execute prefixed instruction [atomically](https://en.wikipedia.org/wiki/Linearizability). So, at the first step in the our assembly statement we try decrement value of the given `mutex->counter`. At the next step the [jns](http://unixwiz.net/techtips/x86-jumps.html) instruction will execute jump at the `exit` label if the value of the decremented `mutex->counter` is not negative. The `exit` label is the second part of the `__mutex_fastpath_lock` function and it just points to the exit from this function:

```C
exit:
        return;
```

For this moment the implementation of the `__mutex_fastpath_lock` function looks pretty easy. But the value of the `mutex->counter` may be negative after decrement. In this case the: 

```C
fail_fn(v);
```

will be called after our inline assembly statement. The `fail_fn` is the second parameter of the `__mutex_fastpath_lock` function and represents pointer to function which represents `midpath/slowpath` paths to acquire the given lock. In our case the `fail_fn` is the `__mutex_lock_slowpath` function. Before we look at the implementation of the `__mutex_lock_slowpath` function, let's finish with the implementation of the `mutex_lock` function. In the simplest way, the lock will be acquired successfully by a process and the `__mutex_fastpath_lock` will be finished. In this case, we just call the

```C
mutex_set_owner(lock);
```

in the end of the `mutex_lock`. The `mutex_set_owner` function is defined in the [kernel/locking/mutex.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/mutex.h) header file and just sets owner of a lock to the current process:

```C
static inline void mutex_set_owner(struct mutex *lock)
{
        lock->owner = current;
}
```

In other way, let's consider situation when a process which wants to acquire a lock is unable to do it, because another process already acquired the same lock. We already know that the `__mutex_lock_slowpath` function will be called in this case. Let's consider implementation of this function. This function is defined in the [kernel/locking/mutex.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/mutex.c) source code file and starts from the obtaining of the proper mutex by the mutex state given from the `__mutex_fastpath_lock` with the `container_of` macro:

```C
__visible void __sched
__mutex_lock_slowpath(atomic_t *lock_count)
{
        struct mutex *lock = container_of(lock_count, struct mutex, count);

        __mutex_lock_common(lock, TASK_UNINTERRUPTIBLE, 0,
                            NULL, _RET_IP_, NULL, 0);
}
```

and call the `__mutex_lock_common` function with the obtained `mutex`. The `__mutex_lock_common` function starts from [preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29) disabling until rescheduling:

```C
preempt_disable();
```

After this comes the stage of optimistic spinning. As we already know this stage depends on the `CONFIG_MUTEX_SPIN_ON_OWNER` kernel configuration option. If this option is disabled, we skip this stage and move at the last path - `slowpath` of a `mutex` acquisition:

```C
if (mutex_optimistic_spin(lock, ww_ctx, use_ww_ctx)) {
        preempt_enable();
        return 0;
}
```

First of all, `mutex_optimistic_spin` checks that we don't need to reschedule or in other words there are no other tasks ready to run that have higher priority. If this check was successful we need to update `MCS` lock wait queue with the current spin. In this way only one spinner can complete for the mutex at one time:

```C
osq_lock(&lock->osq)
```

At the next step we start to spin in the next loop:

```C
while (true) {
    owner = READ_ONCE(lock->owner);

    if (owner && !mutex_spin_on_owner(lock, owner))
        break;

    if (mutex_try_to_acquire(lock)) {
        lock_acquired(&lock->dep_map, ip);

        mutex_set_owner(lock);
        osq_unlock(&lock->osq);
        return true;
    }
}
```

and try to acquire a lock. First of all we try to take current owner and if the owner exists (it may not exist in a case when a process already released a mutex) and we wait for it in the `mutex_spin_on_owner` function before the owner will release a lock. If new task with higher priority have appeared during wait of the lock owner, we break the loop and go to sleep. In other case, the process already may release a lock, so we try to acquire a lock with the `mutex_try_to_acquired`. If this operation finished successfully, we set new owner for the given mutex, removes ourself from the `MCS` wait queue and exit from the `mutex_optimistic_spin` function. At this stage, a lock will be acquired by a process and we enable [preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29) and exit from the `__mutex_lock_common` function:

```C
if (mutex_optimistic_spin(lock, ww_ctx, use_ww_ctx)) {
    preempt_enable();
    return 0;
}

```

That's all for this case.

In other case all may not be so successful. For example new task may occur during we spinning in the loop from the `mutex_optimistic_spin` or even we may not get to this loop from the `mutex_optimistic_spin` in a case when there were task(s) with higher priority before this loop. Or finally the `CONFIG_MUTEX_SPIN_ON_OWNER` kernel configuration option disabled. In this case the `mutex_optimistic_spin` will do nothing:

```C
#ifndef CONFIG_MUTEX_SPIN_ON_OWNER
static bool mutex_optimistic_spin(struct mutex *lock,
                                  struct ww_acquire_ctx *ww_ctx, const bool use_ww_ctx)
{
    return false;
}
#endif
```

In all of these cases, the `__mutex_lock_common` function will act like a `semaphore`. We try to acquire a lock again because the owner of a lock might already release a lock before this time:

```C
if (!mutex_is_locked(lock) &&
   (atomic_xchg_acquire(&lock->count, 0) == 1))
      goto skip_wait;
```

In a failure case the process which wants to acquire a lock will be added to the waiters list

```C
list_add_tail(&waiter.list, &lock->wait_list);
waiter.task = task;
```

In a successful case we update the owner of a lock, enable preemption and exit from the `__mutex_lock_common` function:

```C
skip_wait:
        mutex_set_owner(lock);
        preempt_enable();
        return 0;
```

In this case a lock will be acquired. If can't acquire a lock for now, we enter into the following loop:

```C
for (;;) {

    if (atomic_read(&lock->count) >= 0 && (atomic_xchg_acquire(&lock->count, -1) == 1))
        break;

    if (unlikely(signal_pending_state(state, task))) {
        ret = -EINTR;
        goto err;
    }

    __set_task_state(task, state);

     schedule_preempt_disabled();
}
```

where try to acquire a lock again and exit if this operation was successful. Yes, we try to acquire a lock again right after unsuccessful try  before the loop. We need to do it to make sure that we get a wakeup once a lock will be unlocked. Besides this, it allows us to acquire a lock after sleep.  In other case we check the current process for pending [signals](https://en.wikipedia.org/wiki/Unix_signal) and exit if the process was interrupted by a `signal` during wait for a lock acquisition. In the end of loop we didn't acquire a lock, so we set the task state for `TASK_UNINTERRUPTIBLE` and go to sleep with call of the `schedule_preempt_disabled` function.

That's all. We have considered all three possible paths through which a process may pass when it will want to acquire a lock. Now let's consider how `mutex_unlock` is implemented. When the `mutex_unlock` is called by a process which wants to release a lock, the `__mutex_fastpath_unlock` will be called from the  [arch/x86/include/asm/mutex_64.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/mutex_64.h)  header file:

```C
void __sched mutex_unlock(struct mutex *lock)
{
    __mutex_fastpath_unlock(&lock->count, __mutex_unlock_slowpath);
}
```

Implementation of the `__mutex_fastpath_unlock` function is very similar to the implementation of the `__mutex_fastpath_lock` function:

```C
static inline void __mutex_fastpath_unlock(atomic_t *v,
                                           void (*fail_fn)(atomic_t *))
{
       asm_volatile_goto(LOCK_PREFIX "   incl %0\n"
                         "   jg %l[exit]\n"
                         : : "m" (v->counter)
                         : "memory", "cc"
                         : exit);
       fail_fn(v);
exit:
       return;
}
```

Actually, there is only one difference. We increment value if the `mutex->count`. So it will represent `unlocked` state after this operation. As `mutex` released, but we have something in the `wait queue` we need to update it. In this case the `fail_fn` function will be called which is `__mutex_unlock_slowpath`. The `__mutex_unlock_slowpath` function just gets the correct `mutex` instance by the given `mutex->count` and calls the `__mutex_unlock_common_slowpath` function:

```C
__mutex_unlock_slowpath(atomic_t *lock_count)
{
      struct mutex *lock = container_of(lock_count, struct mutex, count);

      __mutex_unlock_common_slowpath(lock, 1);
}
```

In the `__mutex_unlock_common_slowpath` function we will get the first entry from the wait queue if the wait queue is not empty and wake up related process:

```C
if (!list_empty(&lock->wait_list)) {
    struct mutex_waiter *waiter =
           list_entry(lock->wait_list.next, struct mutex_waiter, list);
                wake_up_process(waiter->task);
}
```

After this, a mutex will be released by previous process and will be acquired by another process from a wait queue.

That's all. We have considered main `API` for manipulation with `mutexes`: `mutex_lock` and `mutex_unlock`. Besides this the Linux kernel provides following API:

* `mutex_lock_interruptible`;
* `mutex_lock_killable`;
* `mutex_trylock`.

and corresponding versions of `unlock` prefixed functions. This part will not describe this `API`, because it is similar to corresponding `API` of `semaphores`. More about it you may read in the [previous part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-3).

That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the fourth part of the [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) chapter in the Linux kernel. In this part we met with new synchronization primitive which is called - `mutex`. From the theoretical side, this synchronization primitive very similar on a [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29). Actually, `mutex` represents binary semaphore. But its implementation differs from the implementation of `semaphore` in the Linux kernel. In the next part we will continue to dive into synchronization primitives in the Linux kernel.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](mailto:anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Mutex](https://en.wikipedia.org/wiki/Mutual_exclusion)
* [Spinlock](https://en.wikipedia.org/wiki/Spinlock)
* [Semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29)
* [Synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29)
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [Locking mechanism](https://en.wikipedia.org/wiki/Lock_%28computer_science%29)
* [Context switches](https://en.wikipedia.org/wiki/Context_switch)
* [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt)
* [Atomic](https://en.wikipedia.org/wiki/Linearizability)
* [MCS lock](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf)
* [Doubly linked list](https://0xax.gitbook.io/linux-insides/summary/datastructures/linux-datastructures-1)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [Inline assembly](https://0xax.gitbook.io/linux-insides/summary/theory/linux-theory-3)
* [Memory barrier](https://en.wikipedia.org/wiki/Memory_barrier)
* [Lock instruction](http://x86.renejeschke.de/html/file_module_x86_id_159.html)
* [JNS instruction](http://unixwiz.net/techtips/x86-jumps.html)
* [preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29)
* [Unix signals](https://en.wikipedia.org/wiki/Unix_signal)
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-3)
