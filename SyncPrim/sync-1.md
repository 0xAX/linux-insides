Synchronization primitives in the Linux kernel. Part 1.
================================================================================

Introduction
--------------------------------------------------------------------------------

This part opens new chapter in the [linux-insides](http://0xax.gitbooks.io/linux-insides/content/) book. Timers and time management related stuff was described in the previous [chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html). This chapter will describe [synchronization](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) primitives in the Linux kernel.

As always, before we consider something synchronization related, we will look at the concept of a`synchronization primitive` in general. A synchronization primitive is a software mechanism which provides ability to two or more [parallel](https://en.wikipedia.org/wiki/Parallel_computing) processes or threads to coordinate. For example, to not execute simultaneously one the same segment of a code (such as writing different values to a shared variable). Let's look on the following piece of code:

```C
mutex_lock(&clocksource_mutex);
...
...
...
clocksource_enqueue(cs);
clocksource_enqueue_watchdog(cs);
clocksource_select();
...
...
...
mutex_unlock(&clocksource_mutex);
```

from the [kernel/time/clocksource.c](https://github.com/torvalds/linux/blob/master/kernel/time/clocksource.c) source code file. This code is from the `__clocksource_register_scale` function which adds the given [clocksource](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-2.html) to a list shared by more than one process. It's the `mutex_lock` and `mutex_unlock` functions we're interested in here, which take one parameter - the `clocksource_mutex` in our case. These functions provide [mutual exclusion](https://en.wikipedia.org/wiki/Mutual_exclusion) with the mutex synchronization primitive; enabling proccesses or threads to coordinate use of a shared resource. The clocksource is added with the `clocksource_enqueue` function (after the clock source in the list which has the biggest rating, the highest frequency clocksource regestered in the system):

```C
static void clocksource_enqueue(struct clocksource *cs)
{
	struct list_head *entry = &clocksource_list;
	struct clocksource *tmp;

	list_for_each_entry(tmp, &clocksource_list, list)
		if (tmp->rating >= cs->rating)
			entry = &tmp->list;
	list_add(&cs->list, entry);
}
```

If two parallel processes execute this function simultaneously, some [nasty things](https://en.wikipedia.org/wiki/Race_condition) can happen. In the above, the clocksource is added to a sorted list; the correct place to add the clocksource is found, and the entry is added. Two proccesses executing this code at the same time may chose the same place to add an entry; and the second process calling `list_add` may un-intentionally overwrite the clocksource just added by the first process.

Synchronization primitives are ubiquitous in the Linux kernel. A quick look through any of the chapters of this book will demonstrate their extensive use. The following set of synchronization primitives are provided:

* `mutex`;
* `semaphores`;
* `seqlocks`;
* `atomic operations`;
* etc.

We will start this chapter with the `spinlock`.

Spinlocks in the Linux kernel.
--------------------------------------------------------------------------------

The `spinlock` is a low-level synchronization mechanism; simply a variable with two possible states:

* `acquired`;
* `released`.

A process attempting to acquire or release a `spinlock`, must write the associated value to the spinlock variable. A process trying to execute code which is protected by a `spinlock` which another process has already aquired, it will be locked until the spinlock variable is released. To safely aquire or release a spinlock, the write operation performed to the spinlock must be  [atomic](https://en.wikipedia.org/wiki/Linearizability) to prevent [race conditions](https://en.wikipedia.org/wiki/Race_condition). The `spinlock` is represented by the `spinlock_t` type in the Linux kernel. If we will look at the Linux kernel code, we will see that this type is [widely](http://lxr.free-electrons.com/ident?i=spinlock_t) used. The `spinlock_t` is defined as:

```C
typedef struct spinlock {
        union {
              struct raw_spinlock rlock;

#ifdef CONFIG_DEBUG_LOCK_ALLOC
# define LOCK_PADSIZE (offsetof(struct raw_spinlock, dep_map))
                struct {
                        u8 __padding[LOCK_PADSIZE];
                        struct lockdep_map dep_map;
                };
#endif
        };
} spinlock_t;
```

and located in the [include/linux/spinlock_types.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_types.h) header file. We may see that its implementation depends on the state of the `CONFIG_DEBUG_LOCK_ALLOC` kernel configuration option. We will skip this now, because all debugging related stuff will be at the end of this part. So, if the `CONFIG_DEBUG_LOCK_ALLOC` kernel configuration option is disabled, the `spinlock_t` contains a union [union](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B) with one field - `raw_spinlock`:

```C
typedef struct spinlock {
        union {
              struct raw_spinlock rlock;
        };
} spinlock_t;
```

The `raw_spinlock` structure is defined in the [same](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_types.h) header file:

```C
typedef struct raw_spinlock {
        arch_spinlock_t raw_lock;
#ifdef CONFIG_GENERIC_LOCKBREAK
        unsigned int break_lock;
#endif
} raw_spinlock_t;
```

where the `arch_spinlock_t` represents architecture-specific `spinlock` implementation.The `break_lock` field is set to value - `1` when one processor starts to wait while the lock is held by another processor (on [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) systems). This helps prevent locks of exessive duration. We focus on the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture in this book, so the `arch_spinlock_t` is defined in the [arch/x86/include/asm/spinlock_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/spinlock_types.h) header file and looks like:

```C
#ifdef CONFIG_QUEUED_SPINLOCKS
#include <asm-generic/qspinlock_types.h>
#else
typedef struct arch_spinlock {
        union {
                __ticketpair_t head_tail;
                struct __raw_tickets {
                        __ticket_t head, tail;
                } tickets;
        };
} arch_spinlock_t;
```

The definition of the `arch_spinlock` structure depends on the value of the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option. This configuration option provides a specialized spinlock with a queue. This special type of `spinlocks` which instead of `acquired` and `released` [atomic](https://en.wikipedia.org/wiki/Linearizability) values used `atomic` operation on a `queue`. If the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option is enabled, the `arch_spinlock_t` will be represented by the following structure:

```C
typedef struct qspinlock {
	atomic_t	val;
} arch_spinlock_t;
```

from the [include/asm-generic/qspinlock_types.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/qspinlock_types.h) header file.

We will not stop on this structure for now and before we will consider both `arch_spinlock` and the `qspinlock`,

Let's look at the operations that can performed on a spinlock:

* `spin_lock_init` - produces initialization of the given `spinlock`;
* `spin_lock` - acquires given `spinlock`;
* `spin_lock_bh` - disables software [interrupts](https://en.wikipedia.org/wiki/Interrupt) and acquire given `spinlock`.
* `spin_lock_irqsave` and `spin_lock_irq` - disable interrupts on local processor and preserve/not preserve previous interrupt state in the `flags`;
* `spin_unlock` - releases given `spinlock`;
* `spin_unlock_bh` - releases given `spinlock` and enables software interrupts;
* `spin_is_locked` - returns the state of the given `spinlock`;
* and etc.

and the implementation of the `spin_lock_init` macro (from [include/linux/spinlock.h](https://github.com/torvalds/linux/master/include/linux/spinlock.h)):

```C
#define spin_lock_init(_lock)		\
do {							                \
	spinlock_check(_lock);				        \
	raw_spin_lock_init(&(_lock)->rlock);		\
} while (0)
```

Here `spinlock_check` just returns the `raw_spinlock_t` of the given `spinlock`, ensuring that a `normal` raw spinlock has been provided as an argument:

```C
static __always_inline raw_spinlock_t *spinlock_check(spinlock_t *lock)
{
	return &lock->rlock;
}
```

And the `raw_spin_lock_init` macro:

```C
# define raw_spin_lock_init(lock)		\
do {                                                  \
    *(lock) = __RAW_SPIN_LOCK_UNLOCKED(lock);         \
} while (0)                                           \
```

assigns the value of `__RAW_SPIN_LOCK_UNLOCKED` to the given `spinlock`. As we may understand from the name of the `__RAW_SPIN_LOCK_UNLOCKED` macro; initializatingthe given `spinlock` and setting it in a `released` state. This macro defined in the [include/linux/spinlock_types.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_types.h) header file and expands to the following macros:

```C
#define __RAW_SPIN_LOCK_UNLOCKED(lockname)      \
         (raw_spinlock_t) __RAW_SPIN_LOCK_INITIALIZER(lockname)

#define __RAW_SPIN_LOCK_INITIALIZER(lockname)   \
         {                                                      \
             .raw_lock = __ARCH_SPIN_LOCK_UNLOCKED,             \
             SPIN_DEBUG_INIT(lockname)                          \
             SPIN_DEP_MAP_INIT(lockname)                        \
         }
```

We won't consider the debugging `SPIN_DEBUG_INIT` and the `SPIN_DEP_MAP_INIT` macros, the `__RAW_SPINLOCK_UNLOCKED` macro expands to:

```C
*(&(_lock)->rlock) = __ARCH_SPIN_LOCK_UNLOCKED;
```

where the `__ARCH_SPIN_LOCK_UNLOCKED` is:

```C
#define __ARCH_SPIN_LOCK_UNLOCKED       { { 0 } }
```

and:

```C
#define __ARCH_SPIN_LOCK_UNLOCKED       { ATOMIC_INIT(0) }
```

So here we see (for the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture with the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option enabled) that the `spin_lock_init` macro simmply initializes a given `spinlock` atomically with the value 0 (corresponding to an `unlocked` state).

Now we know how to a `spinlock` is initalized, let's consider the [API](https://en.wikipedia.org/wiki/Application_programming_interface) which Linux kernel provides for operating with `spinlocks`. Starting with:

```C
static __always_inline void spin_lock(spinlock_t *lock)
{
	raw_spin_lock(&lock->rlock);
}
```

the function used to `acquire` a spinlock, from  [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock.h). The `raw_spin_lock` macro is defined in the same header file and expands to the call of the `_raw_spin_lock` function:

```C
#define raw_spin_lock(lock)	_raw_spin_lock(lock)
```

The definition of the `_raw_spin_lock` macro depends on the `CONFIG_SMP` kernel configuration parameter:

```C
#if defined(CONFIG_SMP) || defined(CONFIG_DEBUG_SPINLOCK)
# include <linux/spinlock_api_smp.h>
#else
# include <linux/spinlock_api_up.h>
#endif
```

if the [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) is enabled in the Linux kernel, the `_raw_spin_lock` macro is defined in the [arch/x86/include/asm/spinlock.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/spinlock.h) header file and looks like:

```C
#define _raw_spin_lock(lock) __raw_spin_lock(lock)
```

The `__raw_spin_lock` function looks:

```C
static inline void __raw_spin_lock(raw_spinlock_t *lock)
{
        preempt_disable();
        spin_acquire(&lock->dep_map, 0, 0, _RET_IP_);
        LOCK_CONTENDED(lock, do_raw_spin_trylock, do_raw_spin_lock);
}
```

this, first of all, disables [preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29) by calling the `preempt_disable` macro (from [include/linux/preempt.h](https://github.com/torvalds/linux/blob/master/include/linux/preempt.h), more about this in [part](https://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-9.html) nine  of the Linux kernel initialization process chapter). When we unlock the given `spinlock`, preemption will be reenabled:

```C
static inline void __raw_spin_unlock(raw_spinlock_t *lock)
{
        ...
        ...
        ...
        preempt_enable();
}
```

We need to do this while a process is spinning on a lock, other processes must be prevented to preempt the process which acquired a lock. The `spin_acquire` macro which through a chain of other macros expands to the call of the:

```C
#define spin_acquire(l, s, t, i)                lock_acquire_exclusive(l, s, t, NULL, i)
#define lock_acquire_exclusive(l, s, t, n, i)           lock_acquire(l, s, t, 0, 1, n, i)
```

looking at the lock `lock_acquire` function:

```C
void lock_acquire(struct lockdep_map *lock, unsigned int subclass,
                  int trylock, int read, int check,
                  struct lockdep_map *nest_lock, unsigned long ip)
{
         unsigned long flags;

         if (unlikely(current->lockdep_recursion))
                return;

         raw_local_irq_save(flags);
         check_flags(flags);

         current->lockdep_recursion = 1;
         trace_lock_acquire(lock, subclass, trylock, read, check, nest_lock, ip);
         __lock_acquire(lock, subclass, trylock, read, check,
                        irqs_disabled_flags(flags), nest_lock, ip, 0, 0);
         current->lockdep_recursion = 0;
         raw_local_irq_restore(flags);
}
```

The `lock_acquire`function disables hardware interrupts by calling the `raw_local_irq_save` macro. This is to ensure the process is not preempted until the `spinlock` has been safely aquired. Hardware interrupts are reenabled before the function exits with the `raw_local_irq_restore` macro.

The interesting work here is being done by the `__lock_acquire` function (defined in [kernel/locking/lockdep.c](https://github.com/torvalds/linux/blob/master/kernel/locking/lockdep.c)), which is large, so we won't get into it right away. It's mostly related to the Linux kernel [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt).

Returning to the `__raw_spin_lock` function, we will see that it contains the following:

```C
LOCK_CONTENDED(lock, do_raw_spin_trylock, do_raw_spin_lock);
```

The `LOCK_CONTENDED` macro is defined in the [include/linux/lockdep.h](https://github.com/torvalds/linux/blob/master/include/linux/lockdep.h) header file and is defined as:

```C
#define LOCK_CONTENDED(_lock, try, lock) \
         lock(_lock)
```

In our case, the `lock` is `do_raw_spin_lock` function from [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/master/include/linux/spnlock.h) and the `_lock` is the given `raw_spinlock_t`:

```C
static inline void do_raw_spin_lock(raw_spinlock_t *lock) __acquires(lock)
{
        __acquire(lock);
         arch_spin_lock(&lock->raw_lock);
}
```

`__acquire` here is just [sparse](https://en.wikipedia.org/wiki/Sparse) related macro and is not immediately interesting. The definition of the `arch_spin_lock` function is dependant on the architecture of system and whether queued spinlocks are supported.

For the `x86_64` architecture without queued spin locks (we'll get there later) it's defined in arch/x86/include/asm/spinlock.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/spinlock.h). Let's quickly look at the definition of the `arch_spinlock` structure again:

```C
typedef struct arch_spinlock {
         union {
                __ticketpair_t head_tail;
                struct __raw_tickets {
                        __ticket_t head, tail;
                } tickets;
        };
} arch_spinlock_t;
```
This variant of the `spinlock` is called a [ticket spinlock](https://en.wikipedia.org/wiki/Ticket_lock). A process wanting to aquire the spinlock will increment `tail`. If the `tail` field is not equal to `head`, the process will hang, waiting for the spinlock a matching `head` value. Let's look on the implementation of the `arch_spin_lock` function:

```C
static __always_inline void arch_spin_lock(arch_spinlock_t *lock)
{
        register struct __raw_tickets inc = { .tail = TICKET_LOCK_INC };

        inc = xadd(&lock->tickets, inc);

        if (likely(inc.head == inc.tail))
                goto out;

        for (;;) {
                 unsigned count = SPIN_THRESHOLD;

                 do {
                       inc.head = READ_ONCE(lock->tickets.head);
                       if (__tickets_equal(inc.head, inc.tail))
                                goto clear_slowpath;
                        cpu_relax();
                 } while (--count);
                 __ticket_lock_spinning(lock, inc.tail);
         }
clear_slowpath:
        __ticket_check_and_clear_slowpath(lock, inc.head);
out:
        barrier();
}
```

At the beginning of the `arch_spin_lock` function `__raw_tickets` is initializated with `tail` = `1`:

```C
#define __TICKET_LOCK_INC       1
```

[xadd](http://x86.renejeschke.de/html/file_module_x86_id_327.html) (exchange and add) on `inc` and `lock->tickets`; sets `inc` to `lock->tickets` of the given `lock` and increments `tickets.tail` by the previous value of `inc` (one). If `head` and `tail` are equal the lock has been aquired and the function exits with `goto out`.

Otherwise the function `spins`; periodically checking the value of `head` until the `head == tail` condition is met, and the spinlock is aquired.

Note: `cpu_relax` is simply a [NOP](https://en.wikipedia.org/wiki/NOP) instruction:

```C
#define cpu_relax()     asm volatile("rep; nop")
```

The `barrier` macro, called just before the function exits ensures the compiler will not to change the order of operations that access memory (more about memory barriers can be found in the kernel [documentation](https://www.kernel.org/doc/Documentation/memory-barriers.txt)).


The `spin_unlock` operation goes through the a similar set of macros/function as `spin_lock` (disabling hardware interrupts etc.) before the `arch_spin_unlock` function is called; which simply increments `arch_spinlock->ticket->head`:

```C
__add(&lock->tickets.head, TICKET_LOCK_INC, UNLOCK_LOCK_PREFIX);
```

In brief, the ticketed spinlock is simply a fair queuing mechanisms; where processes waiting to aquire a lock gain [first-in first-out](https://en.wikipedia.org/wiki/FIFO_(computing_and_electronics)) access. `head` contains an index number correspinding to the process currently holding the lock currently executed process which holds a lock and the `tail` maps to the last process which queued to gain access to the lock:

```
     +-------+       +-------+
     |       |       |       |
head |   7   | - - - |   7   |
     |       |       |       |
     +-------+       +-------+
                         |
                     +-------+
                     |       |
                     |   8   |
                     |       |
                     +-------+
                         |
                     +-------+
                     |       |
                     |   9   | tail
                     |       |
                     +-------+
```

We won't cover more of the `spinlock` API in in this part, but hopefully the the mechanism provided by the linux kernel spinlock and the basics of it's implimentation on x86 are clear.

Conclusion
--------------------------------------------------------------------------------

This concludes the first part covering synchronization primitives in the Linux kernel. In this part, we met first synchronization primitive `spinlock` provided by the Linux kernel. In the next part we will continue to dive into this interesting theme and will see other `synchronization` related stuff.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Concurrent computing](https://en.wikipedia.org/wiki/Concurrent_computing)
* [Synchronization](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29)
* [Clocksource framework](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-2.html)
* [Mutex](https://en.wikipedia.org/wiki/Mutual_exclusion)
* [Race condition](https://en.wikipedia.org/wiki/Race_condition)
* [Atomic operations](https://en.wikipedia.org/wiki/Linearizability)
* [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [Interrupts](https://en.wikipedia.org/wiki/Interrupt)
* [Preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29)
* [Linux kernel lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt)
* [Sparse](https://en.wikipedia.org/wiki/Sparse)
* [xadd instruction](http://x86.renejeschke.de/html/file_module_x86_id_327.html)
* [NOP](https://en.wikipedia.org/wiki/NOP)
* [Memory barriers](https://www.kernel.org/doc/Documentation/memory-barriers.txt)
* [Previous chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html)
