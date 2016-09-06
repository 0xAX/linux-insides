Synchronization primitives in the Linux kernel. Part 5.
================================================================================

Introduction
--------------------------------------------------------------------------------

This is the fifth part of the [chapter](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/index.html) which describes synchronization primitives in the Linux kernel and in the previous parts we finished to consider different types [spinlocks](https://en.wikipedia.org/wiki/Spinlock), [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29) and [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion) synchronization primitives. We will continue to learn [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) in this part and start to consider special type of synchronization primitives - [readers–writer lock](https://en.wikipedia.org/wiki/Readers%E2%80%93writer_lock).

The first synchronization primitive of this type will be already familiar for us - [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29). As in all previous parts of this [book](https://0xax.gitbooks.io/linux-insides/content), before we will consider implementation of the `reader/writer semaphores` in the Linux kernel, we will start from the theoretical side and will try to understand what is the difference between `reader/writer semaphores` and `normal semaphores`.

So, let's start.

Reader/Writer semaphore
--------------------------------------------------------------------------------

Actually there are two types of operations may be performed on the data. We may read data and make changes in data. Two fundamental operations - `read` and `write`. Usually (but not always), `read` operation is performed more often than `write` operation. In this case, it would be logical to we may lock data in such way, that some processes may read locked data in one time, on condition that no one will not change the data. The [readers/writer lock](https://en.wikipedia.org/wiki/Readers%E2%80%93writer_lock) allows us to get this lock.

When a process which wants to write something into data, all other `writer` and `reader` processes will be blocked until the process which acquired a lock, will not release it. When a process reads data, other processes which want to read the same data too, will not be locked and will be able to do this. As you may guess, implementation of the `reader/writer semaphore` is based on the implementation of the `normal semaphore`. We already familiar with the [semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29) synchronization primitive from the third [part]((https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-4.html) of this chapter. From the theoretical side everything looks pretty simple. Let's look how `reader/writer semaphore` is represented in the Linux kernel.

The `semaphore` is represented by the:

```C
struct semaphore {
	raw_spinlock_t		lock;
	unsigned int		count;
	struct list_head	wait_list;
};
```

structure. If you will look in the [include/linux/rwsem.h](https://github.com/torvalds/linux/blob/master/include/linux/rwsem.h) header file, you will find definition of the `rw_semaphore` structure which represents `reader/writer semaphore` in the Linux kernel. Let's look at the definition of this structure:

```C
#ifdef CONFIG_RWSEM_GENERIC_SPINLOCK
#include <linux/rwsem-spinlock.h>
#else
struct rw_semaphore {
        long count;
        struct list_head wait_list;
        raw_spinlock_t wait_lock;
#ifdef CONFIG_RWSEM_SPIN_ON_OWNER
        struct optimistic_spin_queue osq;
        struct task_struct *owner;
#endif
#ifdef CONFIG_DEBUG_LOCK_ALLOC
        struct lockdep_map      dep_map;
#endif
};
```

Before we will consider fields of the `rw_semaphore` structure, we may notice, that declaration of the `rw_semaphore` structure depends on the `CONFIG_RWSEM_GENERIC_SPINLOCK` kernel configuration option. This option is disabled for the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture by default. We can be sure in this by looking at the corresponding kernel configuration file. In our case, this configuration file is - [arch/x86/um/Kconfig](https://github.com/torvalds/linux/blob/master/arch/x86/um/Kconfig):

```
config RWSEM_XCHGADD_ALGORITHM
	def_bool 64BIT

config RWSEM_GENERIC_SPINLOCK
	def_bool !RWSEM_XCHGADD_ALGORITHM
```

So, as this [book](https://0xax.gitbooks.io/linux-insides/content) describes only [x86_64](https://en.wikipedia.org/wiki/X86-64) related stuff, we will skip the case when the `CONFIG_RWSEM_GENERIC_SPINLOCK` kernel configuration is enabled and consider definition of the `rw_semaphore` structure only from the [include/linux/rwsem.h](https://github.com/torvalds/linux/blob/master/include/linux/rwsem.h) header file.

If we will take a look at the definition of the `rw_semaphore` structure, we will notice that first three fields are the same that in the `semaphore` structure. It contains `count` field which represents amount of available resources, the `wait_list` field which represents [doubly linked list](https://0xax.gitbooks.io/linux-insides/content/DataStructures/dlist.html) of processes which are waiting to acquire a lock and `wait_lock` [spinlock](https://en.wikipedia.org/wiki/Spinlock) for protection of this list. Notice that `rw_semaphore.count` field is `long` type unlike the same field in the `semaphore` structure.

The `count` field of a `rw_semaphore` structure may have following values:

* `0x0000000000000000` - `reader/writer semaphore` is in unlocked state and no one is waiting for a lock;
* `0x000000000000000X` - `X` readers are active or attempting to acquire a lock and no writer waiting;
* `0xffffffff0000000X` - may represent different cases. The first is - `X` readers are active or attempting to acquire a lock with waiters for the lock. The second is - one writer attempting a lock, no waiters for the lock. And the last - one writer is active and no waiters for the lock;
* `0xffffffff00000001` - may represented two different cases. The first is - one reader is active or attempting to acquire a lock and exist waiters for the lock. The second case is one writer is active or attempting to acquire a lock and no waiters for the lock;
* `0xffffffff00000000` - represents situation when there are readers or writers are queued, but no one is active or is in the process of acquire of a lock;
* `0xfffffffe00000001` - a writer is active or attempting to acquire a lock and waiters are in queue.

So, besides the `count` field, all of these fields are similar to fields of the `semaphore` structure. Last three fields depend on the two configuration options of the Linux kernel: the `CONFIG_RWSEM_SPIN_ON_OWNER` and `CONFIG_DEBUG_LOCK_ALLOC`. The first two fields may be familiar us by declaration of the [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion) structure from the [previous part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-4.html). The first `osq` field represents [MCS lock](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf) spinner for `optimistic spinning` and the second represents process which is current owner of a lock.

The last field of the `rw_semaphore` structure is - `dep_map` - debugging related, and as I already wrote in previous parts, we will skip debugging related stuff in this chapter.

That's all. Now we know a little about what is it `reader/writer lock` in general and `reader/writer semaphore` in particular. Additionally we saw how a `reader/writer semaphore` is represented in the Linux kernel. In this case, we may go ahead and start to look at the [API](https://en.wikipedia.org/wiki/Application_programming_interface) which the Linux kernel provides for manipulation of `reader/writer semaphores`.

Reader/Writer semaphore API
--------------------------------------------------------------------------------

So, we know a little about `reader/writer semaphores` from theoretical side, let's look on its implementation in the Linux kernel. All `reader/writer semaphores` related [API](https://en.wikipedia.org/wiki/Application_programming_interface) is located in the [include/linux/rwsem.h](https://github.com/torvalds/linux/blob/master/include/linux/rwsem.h) header file.

As always Before we will consider an [API](https://en.wikipedia.org/wiki/Application_programming_interface) of the `reader/writer semaphore` mechanism in the Linux kernel, we need to know how to initialize the `rw_semaphore` structure. As we already saw in previous parts of this [chapter](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/index.html), all [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) may be initialized in two ways:

* `statically`;
* `dynamically`.

And `reader/writer semaphore` is not an exception. First of all, let's take a look at the first approach. We may initialize `rw_semaphore` structure with the help of the `DECLARE_RWSEM` macro in compile time. This macro is defined in the [include/linux/rwsem.h](https://github.com/torvalds/linux/blob/master/include/linux/rwsem.h) header file and looks:

```C
#define DECLARE_RWSEM(name) \
        struct rw_semaphore name = __RWSEM_INITIALIZER(name)
```

As we may see, the `DECLARE_RWSEM` macro just expands to the definition of the `rw_semaphore` structure with the given name. Additionally new `rw_semaphore` structure is initialized with the value of the `__RWSEM_INITIALIZER` macro:

```C
#define __RWSEM_INITIALIZER(name)              \
{                                                              \
        .count = RWSEM_UNLOCKED_VALUE,                         \
        .wait_list = LIST_HEAD_INIT((name).wait_list),         \
        .wait_lock = __RAW_SPIN_LOCK_UNLOCKED(name.wait_lock)  \
         __RWSEM_OPT_INIT(name)                                \
         __RWSEM_DEP_MAP_INIT(name)
} 
```

and expands to the initialization of fields of `rw_semaphore` structure. First of all we initialize `count` field of the `rw_semaphore` structure to the `unlocked` state with `RWSEM_UNLOCKED_VALUE` macro from the [arch/x86/include/asm/rwsem.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/rwsem.h) architecture specific header file:

```C
#define RWSEM_UNLOCKED_VALUE            0x00000000L
```

After this we initialize list of a lock waiters with the empty linked list and [spinlock](https://en.wikipedia.org/wiki/Spinlock) for protection of this list with the `unlocked` state too. The `__RWSEM_OPT_INIT` macro depends on the state of the `CONFIG_RWSEM_SPIN_ON_OWNER` kernel configuration option and if this option is enabled it expands to the initialization of the `osq` and `owner` fields of the `rw_semaphore` structure. As we already saw above, the `CONFIG_RWSEM_SPIN_ON_OWNER` kernel configuration option is enabled by default for [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture, so let's take a look at the definition of the `__RWSEM_OPT_INIT` macro:

```C
#ifdef CONFIG_RWSEM_SPIN_ON_OWNER
    #define __RWSEM_OPT_INIT(lockname) , .osq = OSQ_LOCK_UNLOCKED, .owner = NULL
#else
    #define __RWSEM_OPT_INIT(lockname)
#endif
```

As we may see, the `__RWSEM_OPT_INIT` macro initializes the [MCS lock](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf) lock with `unlocked` state and initial `owner` of a lock with `NULL`. From this moment, a `rw_semaphore` structure will be initialized in a compile time and may be used for data protection.

The second way to initialize a `rw_semaphore` structure is `dynamically` or use the `init_rwsem` macro from the [include/linux/rwsem.h](https://github.com/torvalds/linux/blob/master/include/linux/rwsem.h) header file. This macro declares an instance of the `lock_class_key` which is related to the [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) of the Linux kernel and to the call of the `__init_rwsem` function with the given `reader/writer semaphore`:

```C
#define init_rwsem(sem)                         \
do {                                                            \
        static struct lock_class_key __key;                     \
                                                                \
        __init_rwsem((sem), #sem, &__key);                      \
} while (0)
```

If you will start definition of the `__init_rwsem` function, you will notice that there are couple of source code files which contain it. As you may guess, sometimes we need to initialize additional fields of the `rw_semaphore` structure, like the `osq` and `owner`. But sometimes not. All of this depends on some kernel configuration options. If we will look at the [kernel/locking/Makefile](https://github.com/torvalds/linux/blob/master/kernel/locking/Makefile) makefile, we will see following lines:

```Makefile
obj-$(CONFIG_RWSEM_GENERIC_SPINLOCK) += rwsem-spinlock.o
obj-$(CONFIG_RWSEM_XCHGADD_ALGORITHM) += rwsem-xadd.o
```

As we already know, the Linux kernel for `x86_64` architecture has enabled `CONFIG_RWSEM_XCHGADD_ALGORITHM` kernel configuration option by default:

```
config RWSEM_XCHGADD_ALGORITHM
	def_bool 64BIT
```

in the [arch/x86/um/Kconfig](https://github.com/torvalds/linux/blob/master/arch/x86/um/Kconfig) kernel configuration file. In this case, implementation of the `__init_rwsem` function will be located in the [kernel/locking/rwsem-xadd.c](https://github.com/torvalds/linux/blob/master/locking/rwsem-xadd.c) source code file for us. Let's take a look at this function:

```C
void __init_rwsem(struct rw_semaphore *sem, const char *name,
                    struct lock_class_key *key)
{
#ifdef CONFIG_DEBUG_LOCK_ALLOC
        debug_check_no_locks_freed((void *)sem, sizeof(*sem));
        lockdep_init_map(&sem->dep_map, name, key, 0);
#endif
        sem->count = RWSEM_UNLOCKED_VALUE;
        raw_spin_lock_init(&sem->wait_lock);
        INIT_LIST_HEAD(&sem->wait_list);
#ifdef CONFIG_RWSEM_SPIN_ON_OWNER
        sem->owner = NULL;
        osq_lock_init(&sem->osq);
#endif
}
```

We may see here almost the same as in `__RWSEM_INITIALIZER` macro with difference that all of this will be executed in [runtime](https://en.wikipedia.org/wiki/Run_time_%28program_lifecycle_phase%29).

So, from now we are able to initialize a `reader/writer semaphore` let's look at the `lock` and `unlock` API. The Linux kernel provides following primary [API](https://en.wikipedia.org/wiki/Application_programming_interface) to manipulate `reader/writer semaphores`:

* `void down_read(struct rw_semaphore *sem)` - lock for reading;
* `int down_read_trylock(struct rw_semaphore *sem)` - try lock for reading;
* `void down_write(struct rw_semaphore *sem)` - lock for writing;
* `int down_write_trylock(struct rw_semaphore *sem)` - try lock for writing;
* `void up_read(struct rw_semaphore *sem)` - release a read lock;
* `void up_write(struct rw_semaphore *sem)` - release a write lock;

Let's start as always from the locking. First of all let's consider implementation of the `down_write` function which executes a try of acquiring of a lock for `write`. This function is [kernel/locking/rwsem.c](https://github.com/torvalds/linux/blob/master/kernel/locking/rwsem.c) source code file and starts from the call of the macro from the [include/linux/kernel.h](https://github.com/torvalds/linux/blob/master/include/linux/kernel.h) header file:

```C
void __sched down_write(struct rw_semaphore *sem)
{
        might_sleep();
        rwsem_acquire(&sem->dep_map, 0, 0, _RET_IP_);

        LOCK_CONTENDED(sem, __down_write_trylock, __down_write);
        rwsem_set_owner(sem);
}
```

We already met the `might_sleep` macro in the [previous part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-4.html). In short words, Implementation of the `might_sleep` macro depends on the `CONFIG_DEBUG_ATOMIC_SLEEP` kernel configuration option and if this option is enabled, this macro just prints a stack trace if it was executed in [atomic](https://en.wikipedia.org/wiki/Linearizability) context. As this macro is mostly for debugging purpose we will skip it and will go ahead. Additionally we will skip the next macro from the `down_read` function - `rwsem_acquire` which is related to the [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) of the Linux kernel, because this is topic of other part.

The only two things that remained in the `down_write` function is the call of the `LOCK_CONTENDED` macro which is defined in the [include/linux/lockdep.h](https://github.com/torvalds/linux/blob/master/include/linux/lockdep.h) header file and setting of owner of a lock with the `rwsem_set_owner` function which sets owner to currently running process:

```C
static inline void rwsem_set_owner(struct rw_semaphore *sem)
{
        sem->owner = current;
}
```

As you already may guess, the `LOCK_CONTENDED` macro does all job for us. Let's look at the implementation of the `LOCK_CONTENDED` macro:

```C
#define LOCK_CONTENDED(_lock, try, lock) \
        lock(_lock)
```

As we may see it just calls the `lock` function which is third parameter of the `LOCK_CONTENDED` macro with the given `rw_semaphore`. In our case the third parameter of the `LOCK_CONTENDED` macro is the `__down_write` function which is architecture specific function and located in the [arch/x86/include/asm/rwsem.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/rwsem.h) header file. Let's look at the implementation of the `__down_write` function:

```C
static inline void __down_write(struct rw_semaphore *sem)
{
        __down_write_nested(sem, 0);
}
```

which just executes a call of the `__down_write_nested` function from the same source code file. Let's take a look at the implementation of the `__down_write_nested` function:

```C
static inline void __down_write_nested(struct rw_semaphore *sem, int subclass)
{
        long tmp;

        asm volatile("# beginning down_write\n\t"
                     LOCK_PREFIX "  xadd      %1,(%2)\n\t"
                     "  test " __ASM_SEL(%w1,%k1) "," __ASM_SEL(%w1,%k1) "\n\t"
                     "  jz        1f\n"
                     "  call call_rwsem_down_write_failed\n"
                     "1:\n"
                     "# ending down_write"
                     : "+m" (sem->count), "=d" (tmp)
                     : "a" (sem), "1" (RWSEM_ACTIVE_WRITE_BIAS)
                     : "memory", "cc");
}
```

As for other synchronization primitives which we saw in this chapter, usually `lock/unlock` functions consists only from an [inline assembly](https://0xax.gitbooks.io/linux-insides/content/Theory/asm.html) statement. As we may see, in our case the same for `__down_write_nested` function. Let's try to understand what does this function do. The first line of our assembly statement is just a comment, let's skip it. The second like contains `LOCK_PREFIX` which will be expanded to the [LOCK](http://x86.renejeschke.de/html/file_module_x86_id_159.html) instruction as we already know. The next [xadd](http://x86.renejeschke.de/html/file_module_x86_id_327.html) instruction executes `add` and `exchange` operations. In other words, `xadd` instruction adds value of the `RWSEM_ACTIVE_WRITE_BIAS`:

```C
#define RWSEM_ACTIVE_WRITE_BIAS         (RWSEM_WAITING_BIAS + RWSEM_ACTIVE_BIAS)

#define RWSEM_WAITING_BIAS              (-RWSEM_ACTIVE_MASK-1)
#define RWSEM_ACTIVE_BIAS               0x00000001L
```

or `0xffffffff00000001` to the `count` of the given `reader/writer semaphore` and returns previous value of it. After this we check the active mask in the `rw_semaphore->count`. If it was zero before, this means that there were no-one writer before, so we acquired a lock. In other way we call the `call_rwsem_down_write_failed` function from the [arch/x86/lib/rwsem.S](https://github.com/torvalds/linux/blob/master/arch/x86/lib/rwsem.S) assembly file. The the `call_rwsem_down_write_failed` function just calls the `rwsem_down_write_failed` function from the [kernel/locking/rwsem-xadd.c](https://github.com/torvalds/linux/blob/master/locking/rwsem-xadd.c) source code file anticipatorily save general purpose registers:

```assembly
ENTRY(call_rwsem_down_write_failed)
	FRAME_BEGIN
	save_common_regs
	movq %rax,%rdi
	call rwsem_down_write_failed
	restore_common_regs
	FRAME_END
	ret
    ENDPROC(call_rwsem_down_write_failed)
```

The `rwsem_down_write_failed` function starts from the [atomic](https://en.wikipedia.org/wiki/Linearizability) update of the `count` value:

```C
 __visible
struct rw_semaphore __sched *rwsem_down_write_failed(struct rw_semaphore *sem)
{
    count = rwsem_atomic_update(-RWSEM_ACTIVE_WRITE_BIAS, sem);
    ...
    ...
    ...
}
```

with the `-RWSEM_ACTIVE_WRITE_BIAS` value. The `rwsem_atomic_update` function is defined in the [arch/x86/include/asm/rwsem.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/rwsem.h) header file and implement exchange and add logic:

```C
static inline long rwsem_atomic_update(long delta, struct rw_semaphore *sem)
{
        return delta + xadd(&sem->count, delta);
}
```

This function atomically adds the given delta to the `count` and returns old value of the count. After this it just returns sum of the given `delta` and old value of the `count` field. In our case we undo write bias from the `count` as we didn't acquire a lock. After this step we try to do `optimistic spinning` by the call of the `rwsem_optimistic_spin` function:

```C
if (rwsem_optimistic_spin(sem))
      return sem;
```

We will skip implementation of the `rwsem_optimistic_spin` function, as it is similar on the `mutex_optimistic_spin` function which we saw in the [previous part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-4.html). In short words we check existence other tasks ready to run that have higher priority in the `rwsem_optimistic_spin` function. If there are such tasks, the process will be added to the [MCS](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf) `waitqueue` and start to spin in the loop until a lock will be able to be acquired. If `optimistic spinning` is disabled, a process will be added to the and marked as waiting for write:

```C
waiter.task = current;
waiter.type = RWSEM_WAITING_FOR_WRITE;

if (list_empty(&sem->wait_list))
    waiting = false;

list_add_tail(&waiter.list, &sem->wait_list);
```

waiters list and start to wait until it will successfully acquire the lock. After we have added a process to the waiters list which was empty before this moment, we update the value of the `rw_semaphore->count` with the `RWSEM_WAITING_BIAS`:

```C
count = rwsem_atomic_update(RWSEM_WAITING_BIAS, sem);
```

with this we mark `rw_semaphore->counter` that it is already locked and exists/waits one `writer` which wants to acquire the lock. In other way we try to wake `reader` processes from the `wait queue` that were queued before this `writer` process and there are no active readers. In the end of the `rwsem_down_write_failed` a `writer` process will go to sleep which didn't acquire a lock in the following loop:

```C
while (true) {
    if (rwsem_try_write_lock(count, sem))
        break;
    raw_spin_unlock_irq(&sem->wait_lock);
    do {
        schedule();
        set_current_state(TASK_UNINTERRUPTIBLE);
    } while ((count = sem->count) & RWSEM_ACTIVE_MASK);
    raw_spin_lock_irq(&sem->wait_lock);
}
```

I will skip explanation of this loop as we already met similar functional in the [previous part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-4.html).

That's all. From this moment, our `writer` process will acquire or not acquire a lock depends on the value of the `rw_semaphore->count` field. Now if we will look at the implementation of the `down_read` function which executes a try of acquiring of a lock. We will see similar actions which we saw in the `down_write` function. This function calls different debugging and lock validator related functions/macros:

```C
void __sched down_read(struct rw_semaphore *sem)
{
        might_sleep();
        rwsem_acquire_read(&sem->dep_map, 0, 0, _RET_IP_);

        LOCK_CONTENDED(sem, __down_read_trylock, __down_read);
}
```

and does all job in the `__down_read` function. The `__down_read` consists of inline assembly statement:

```C
static inline void __down_read(struct rw_semaphore *sem)
{
         asm volatile("# beginning down_read\n\t"
                     LOCK_PREFIX _ASM_INC "(%1)\n\t"
                     "  jns        1f\n"
                     "  call call_rwsem_down_read_failed\n"
                     "1:\n\t"
                     "# ending down_read\n\t"
                     : "+m" (sem->count)
                     : "a" (sem)
                     : "memory", "cc");
}
```

which increments value of the given `rw_semaphore->count` and call the `call_rwsem_down_read_failed` if this value is negative. In other way we jump at the label `1:` and exit. After this `read` lock will be successfully acquired. Notice that we check a sign of the `count` value as it may be negative, because as you may remember most significant [word](https://en.wikipedia.org/wiki/Word_%28computer_architecture%29) of the `rw_semaphore->count` contains negated number of active writers.

Let's consider case when a process wants to acquire a lock for `read` operation, but it is already locked. In this case the `call_rwsem_down_read_failed` function from the [arch/x86/lib/rwsem.S](https://github.com/torvalds/linux/blob/master/arch/x86/lib/rwsem.S)  assembly file will be called. If you will look at the implementation of this function, you will notice that it does the same that `call_rwsem_down_read_failed` function does. Except it calls the `rwsem_down_read_failed` function instead of `rwsem_dow_write_failed`. Now let's consider implementation of the `rwsem_down_read_failed` function. It starts from the adding a process to the `wait queue` and updating of value of the `rw_semaphore->counter`:

```C
long adjustment = -RWSEM_ACTIVE_READ_BIAS;

waiter.task = tsk;
waiter.type = RWSEM_WAITING_FOR_READ;

if (list_empty(&sem->wait_list))
    adjustment += RWSEM_WAITING_BIAS;
list_add_tail(&waiter.list, &sem->wait_list);

count = rwsem_atomic_update(adjustment, sem);
```

Notice that if the `wait queue` was empty before we clear the `rw_semaphore->counter` and undo `read` bias in other way. At the next step we check that there are no active locks and we are first in the `wait queue` we need to join currently active `reader` processes. In other way we go to sleep until a lock will not be able to acquired.

That's all. Now we know how `reader` and `writer` processes will behave in different cases during a lock acquisition. Now let's take a short look at `unlock` operations. The `up_read` and `up_write` functions allows us to unlock a `reader` or `writer` lock. First of all let's take a look at the implementation of the `up_write` function which is defined in the [kernel/locking/rwsem.c](https://github.com/torvalds/linux/blob/master/kernel/locking/rwsem.c) source code file:

```C
void up_write(struct rw_semaphore *sem)
{
        rwsem_release(&sem->dep_map, 1, _RET_IP_);

        rwsem_clear_owner(sem);
        __up_write(sem);
}
```

First of all it calls the `rwsem_release` macro which is related to the lock validator of the Linux kernel, so we will skip it now. And at the next line the `rwsem_clear_owner` function which as you may understand from the name of this function, just clears the `owner` field of the given `rw_semaphore`:

```C
static inline void rwsem_clear_owner(struct rw_semaphore *sem)
{
	sem->owner = NULL;
}
```

The `__up_write` function does all job of unlocking of the lock. The `_up_write` is architecture-specific function, so for our case it will be located in the [arch/x86/include/asm/rwsem.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/rwsem.h) source code file. If we will take a look at the implementation of this function, we will see that it does almost the same that `__down_write` function, but conversely. Instead of adding of the `RWSEM_ACTIVE_WRITE_BIAS` to the `count`, we subtract the same value and check the `sign` of the previous value.

If the previous value of the `rw_semaphore->count` is not negative, a writer process released a lock and now it may be acquired by someone else. In other case, the `rw_semaphore->count` will contain negative values. This means that there is at least one `writer` in a wait queue. In this case the `call_rwsem_wake` function will be called. This function acts like similar functions which we already saw above. It store general purpose registers at the stack for preserving and call the `rwsem_wake` function.

First of all the `rwsem_wake` function checks if a spinner is present. In this case it will just acquire a lock which is just released by lock owner. In other case there must be someone in the `wait queue` and we need to wake or writer process if it exists at the top of the `wait queue` or all `reader` processes. The `up_read` function which release a `reader` lock acts in similar way like `up_write`, but with a little difference. Instead of subtracting of `RWSEM_ACTIVE_WRITE_BIAS` from the `rw_semaphore->count`, it subtracts `1` from it, because less significant word of the `count` contains number active locks. After this it checks `sign` of the `count` and calls the `rwsem_wake` like `__up_write` if the `count` is negative or in other way lock will be successfully released.

That's all. We have considered API for manipulation with `reader/writer semaphore`: `up_read/up_write` and `down_read/down_write`. We saw that the Linux kernel provides additional API, besides this functions, like the ``, `` and etc. But I will not consider implementation of these function in this part because it must be similar on that we have seen in this part of except few subtleties.

Conclusion
--------------------------------------------------------------------------------

This is the end of the fifth part of the [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) chapter in the Linux kernel. In this part we met with special type of `semaphore` - `readers/writer` semaphore which provides access to data for multiply process to read or for one process to writer. In the next part we will continue to dive into synchronization primitives in the Linux kernel.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29)
* [Readers/Writer lock](https://en.wikipedia.org/wiki/Readers%E2%80%93writer_lock)
* [Spinlocks](https://en.wikipedia.org/wiki/Spinlock)
* [Semaphore](https://en.wikipedia.org/wiki/Semaphore_%28programming%29)
* [Mutex](https://en.wikipedia.org/wiki/Mutual_exclusion)
* [x86_64 architecture](https://en.wikipedia.org/wiki/X86-64)
* [Doubly linked list](https://0xax.gitbooks.io/linux-insides/content/DataStructures/dlist.html)
* [MCS lock](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf)
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [Linux kernel lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt)
* [Atomic operations](https://en.wikipedia.org/wiki/Linearizability)
* [Inline assembly](https://0xax.gitbooks.io/linux-insides/content/Theory/asm.html)
* [XADD instruction](http://x86.renejeschke.de/html/file_module_x86_id_327.html)
* [LOCK instruction](http://x86.renejeschke.de/html/file_module_x86_id_159.html)
* [Previous part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-4.html)
