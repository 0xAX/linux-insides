Synchronization primitives in the Linux kernel. Part 1.
================================================================================

Introduction
--------------------------------------------------------------------------------

This part opens a new chapter in the [linux-insides](https://0xax.gitbooks.io/linux-insides/content/) book. Timers and time management related stuff was described in the previous [chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html). Now time to go next. As you may understand from the part's title, this chapter will describe [synchronization](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) primitives in the Linux kernel.

As always, before we will consider something synchronization related, we will try to know what is `synchronization primitive` in general. Actually, synchronization primitive is a software mechanism which provides the ability to two or more [parallel](https://en.wikipedia.org/wiki/Parallel_computing) processes or threads to not execute simultaneously on the same segment of a code. For example, let's look on the following piece of code:

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

from the [kernel/time/clocksource.c](https://github.com/torvalds/linux/master/kernel/time/clocksource.c) source code file. This code is from the `__clocksource_register_scale` function which adds the given [clocksource](https://0xax.gitbooks.io/linux-insides/content/Timers/linux-timers-2.html) to the clock sources list. This function produces different operations on a list with registered clock sources. For example, the `clocksource_enqueue` function adds the given clock source to the list with registered clocksources - `clocksource_list`. Note that these lines of code wrapped to two functions: `mutex_lock` and `mutex_unlock` which takes one parameter - the `clocksource_mutex` in our case.

These functions represent locking and unlocking based on [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion) synchronization primitive. As `mutex_lock` will be executed, it allows us to prevent the situation when two or more threads will execute this code while the `mutex_unlock` will not be executed by process-owner of the mutex. In other words, we prevent parallel operations on a `clocksource_list`. Why do we need `mutex` here? What if two parallel processes will try to register a clock source. As we already know, the `clocksource_enqueue` function adds the given clock source to the `clocksource_list` list right after a clock source in the list which has the biggest rating (a registered clock source which has the highest frequency in the system):

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

If two parallel processes will try to do it simultaneously, both process may found the same `entry` may occur [race condition](https://en.wikipedia.org/wiki/Race_condition) or in other words, the second process which will execute `list_add`, will overwrite a clock source from the first thread.

Besides this simple example, synchronization primitives are ubiquitous in the Linux kernel. If we will go through the previous [chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html) or other chapters again or if we will look at the Linux kernel source code in general, we will meet many places like this. We will not consider how `mutex` is implemented in the Linux kernel. Actually, the Linux kernel provides a set of different synchronization primitives like:

* `mutex`;
* `semaphores`; 
* `seqlocks`;
* `atomic operations`;
* etc.

We will start this chapter from the `spinlock`.

Spinlocks in the Linux kernel.
--------------------------------------------------------------------------------

The `spinlock` is a low-level synchronization mechanism which in simple words, represents a variable which can be in two states:

* `acquired`;
* `released`.

Each process which wants to acquire a `spinlock`, must write a value which represents `spinlock acquired` state to this variable and write `spinlock released` state to the variable. If a process tries to execute code which is protected by a `spinlock`, it will be locked while a process which holds this lock will release it. In this case all related operations must be [atomic](https://en.wikipedia.org/wiki/Linearizability) to prevent [race conditions](https://en.wikipedia.org/wiki/Race_condition) state. The `spinlock` is represented by the `spinlock_t` type in the Linux kernel. If we will look at the Linux kernel code, we will see that this type is [widely](http://lxr.free-electrons.com/ident?i=spinlock_t) used. The `spinlock_t` is defined as:

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

and located in the [include/linux/spinlock_types.h](https://github.com/torvalds/linux/master/include/linux/spinlock_types.h) header file. We may see that its implementation depends on the state of the `CONFIG_DEBUG_LOCK_ALLOC` kernel configuration option. We will skip this now, because all debugging related stuff will be in the end of this part. So, if the `CONFIG_DEBUG_LOCK_ALLOC` kernel configuration option is disabled, the `spinlock_t` contains [union](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B) with one field which is - `raw_spinlock`:

```C
typedef struct spinlock {
        union {
              struct raw_spinlock rlock;
        };
} spinlock_t;
```

The `raw_spinlock` structure defined in the [same](https://github.com/torvalds/linux/master/include/linux/spinlock_types.h) header file and represents the implementation of `normal` spinlock. Let's look how the `raw_spinlock` structure is defined:

```C
typedef struct raw_spinlock {
        arch_spinlock_t raw_lock;
#ifdef CONFIG_GENERIC_LOCKBREAK
        unsigned int break_lock;
#endif
} raw_spinlock_t;
```

where the `arch_spinlock_t` represents architecture-specific `spinlock` implementation and the `break_lock` field which holds value - `1` in a case when  one processor starts to wait while the lock is held on another processor on [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) systems. This allows prevent long time locking. As consider the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture in this books, so the `arch_spinlock_t` is defined in the [arch/x86/include/asm/spinlock_types.h](https://github.com/torvalds/linux/master/arch/x86/include/asm/spinlock_types.h) header file and looks:

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

As we may see, the definition of the `arch_spinlock` structure depends on the value of the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option. This configuration option the Linux kernel supports `spinlocks` with queue. This special type of `spinlocks` which instead of `acquired` and `released` [atomic](https://en.wikipedia.org/wiki/Linearizability) values used `atomic` operation on a `queue`. If the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option is enabled, the `arch_spinlock_t` will be represented by the following structure:

```C
typedef struct qspinlock {
	atomic_t	val;
} arch_spinlock_t;
```

from the [include/asm-generic/qspinlock_types.h](https://github.com/torvalds/linux/master/include/asm-generic/qspinlock_types.h) header file.

We will not stop on this structures for now and before we will consider both `arch_spinlock` and the `qspinlock`, let's look at the operations on a spinlock. The Linux kernel provides following main operations on a `spinlock`:

* `spin_lock_init` - produces initialization of the given `spinlock`;
* `spin_lock` - acquires given `spinlock`;
* `spin_lock_bh` - disables software [interrupts](https://en.wikipedia.org/wiki/Interrupt) and acquire given `spinlock`.
* `spin_lock_irqsave` and `spin_lock_irq` - disable interrupts on local processor and preserve/not preserve previous interrupt state in the `flags`;
* `spin_unlock` - releases given `spinlock`;
* `spin_unlock_bh` - releases given `spinlock` and enables software interrupts;
* `spin_is_locked` - returns the state of the given `spinlock`;
* and etc.

Let's look on the implementation of the `spin_lock_init` macro. As I already wrote, this and other macro are defined in the [include/linux/spinlock.h](https://github.com/torvalds/linux/master/include/linux/spinlock.h) header file and the `spin_lock_init` macro looks:

```C
#define spin_lock_init(_lock)		\
do {							                \
	spinlock_check(_lock);				        \
	raw_spin_lock_init(&(_lock)->rlock);		\
} while (0)
```

As we may see, the `spin_lock_init` macro takes a `spinlock` and executes two operations: check the given `spinlock` and execute the `raw_spin_lock_init`. The implementation of the `spinlock_check` is pretty easy, this function just returns the `raw_spinlock_t` of the given `spinlock` to be sure that we got exactly `normal` raw spinlock:

```C
static __always_inline raw_spinlock_t *spinlock_check(spinlock_t *lock)
{
	return &lock->rlock;
}
```

The `raw_spin_lock_init` macro:

```C
# define raw_spin_lock_init(lock)		\
do {                                                  \
    *(lock) = __RAW_SPIN_LOCK_UNLOCKED(lock);         \
} while (0)                                           \
```

assigns the value of the `__RAW_SPIN_LOCK_UNLOCKED` with the given `spinlock` to the given `raw_spinlock_t`. As we may understand from the name of the `__RAW_SPIN_LOCK_UNLOCKED` macro, this macro does initialization of the given `spinlock` and set it to `released` state. This macro defined in the [include/linux/spinlock_types.h](https://github.com/torvalds/linux/master/include/linux/spinlock_types.h) header file and expands to the following macros:

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

As I already wrote above, we will not consider stuff which is related to debugging of synchronization primitives. In this case we will not consider the `SPIN_DEBUG_INIT` and the `SPIN_DEP_MAP_INIT` macros. So the `__RAW_SPINLOCK_UNLOCKED` macro will be expanded to the:

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

for the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture. if the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option is enabled. So, after the expansion of the `spin_lock_init` macro, a given `spinlock` will be initialized and its state will be - `unlocked`.

From this moment we know how to initialize a `spinlock`, now let's consider [API](https://en.wikipedia.org/wiki/Application_programming_interface) which Linux kernel provides for manipulations of `spinlocks`. The first is:

```C
static __always_inline void spin_lock(spinlock_t *lock)
{
	raw_spin_lock(&lock->rlock);
}
```

function which allows us to `acquire` a spinlock. The `raw_spin_lock` macro is defined in the same header file and expands to the call of the `_raw_spin_lock` function:

```C
#define raw_spin_lock(lock)	_raw_spin_lock(lock)
```

As we may see in the [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/spinlock.h) header file, definition of the `_raw_spin_lock` macro depends on the `CONFIG_SMP` kernel configuration parameter:

```C
#if defined(CONFIG_SMP) || defined(CONFIG_DEBUG_SPINLOCK)
# include <linux/spinlock_api_smp.h>
#else
# include <linux/spinlock_api_up.h>
#endif
```

So, if the [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) is enabled in the Linux kernel, the `_raw_spin_lock` macro is defined in the [arch/x86/include/asm/spinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/spinlock.h) header file and looks like:

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

As you may see, first of all we disable [preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29) by the call of the `preempt_disable` macro from the [include/linux/preempt.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/preempt.h) (more about this you may read in the ninth [part](https://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-9.html) of the Linux kernel initialization process chapter). When we will unlock the given `spinlock`, preemption will be enabled again:

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

`lock_acquire` function:

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

As I wrote above, we will not consider stuff here which is related to debugging or tracing. The main point of the `lock_acquire` function is to disable hardware interrupts by the call of the `raw_local_irq_save` macro, because the given spinlock might be acquired with enabled hardware interrupts. In this way the process will not be preempted. Note that in the end of the `lock_acquire` function we will enable hardware interrupts again with the help of the `raw_local_irq_restore` macro. As you already may guess, the main work will be in the `__lock_acquire` function which is defined in the [kernel/locking/lockdep.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/lockdep.c) source code file.

The `__lock_acquire` function looks big. We will try to understand what does this function do, but not in this part. Actually this function mostly related to the Linux kernel [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) and it is not topic of this part. If we will return to the definition of the `__raw_spin_lock` function, we will see that it contains the following definition in the end:

```C
LOCK_CONTENDED(lock, do_raw_spin_trylock, do_raw_spin_lock);
```

The `LOCK_CONTENDED` macro is defined in the [include/linux/lockdep.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/lockdep.h) header file and just calls the given function with the given `spinlock`:

```C
#define LOCK_CONTENDED(_lock, try, lock) \
         lock(_lock)
```

In our case, the `lock` is `do_raw_spin_lock` function from the [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/spnlock.h) header file and the `_lock` is the given `raw_spinlock_t`:

```C
static inline void do_raw_spin_lock(raw_spinlock_t *lock) __acquires(lock)
{
        __acquire(lock);
         arch_spin_lock(&lock->raw_lock);
}
```

The `__acquire` here is just [sparse](https://en.wikipedia.org/wiki/Sparse) related macro and we are not interested in it in this moment. Location of the definition of the `arch_spin_lock` function depends on two things: the first is the architecture of the system and the second do we use `queued spinlocks` or not. In our case we consider only `x86_64` architecture, so the definition of the `arch_spin_lock` is represented as the macro from the [include/asm-generic/qspinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/asm-generic/qspinlocks.h) header file:

```C
#define arch_spin_lock(l)               queued_spin_lock(l)
```

if we are using `queued spinlocks`. Or in other case, the `arch_spin_lock` function is defined in the [arch/x86/include/asm/spinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/spinlock.h) header file. Now we will consider only `normal spinlock` and information related to `queued spinlocks` we will see later. Let's look again on the definition of the `arch_spinlock` structure, to understand the implementation of the `arch_spin_lock` function:

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

This variant of `spinlock` is called - `ticket spinlock`. As we may see, it consists from two parts. When lock is acquired, it increments a `tail` by one every time when a process wants to hold a `spinlock`. If the `tail` is not equal to `head`, the process will be locked, until values of these variables will not be equal. Let's look on the implementation of the `arch_spin_lock` function: 

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

At the beginning of the `arch_spin_lock` function we can initialization of the `__raw_tickets` structure with `tail` - `1`:

```C
#define __TICKET_LOCK_INC       1
```

In the next line we execute [xadd](http://x86.renejeschke.de/html/file_module_x86_id_327.html) operation on the `inc` and `lock->tickets`. After this operation the `inc` will store value of the `tickets` of the given `lock` and the `tickets.tail` will be increased on `inc` or `1`. The `tail` value was increased on `1` which means that one process started to try to hold a lock. In the next step we do the check that checks that `head` and `tail` have the same value. If these values are equal, this means that nobody holds lock and we go to the `out` label. In the end of the `arch_spin_lock` function we may see the `barrier` macro which represents `barrier instruction` which guarantees that compiler will not change the order of operations that access memory (more about memory barriers you can read in the kernel [documentation](https://www.kernel.org/doc/Documentation/memory-barriers.txt)).

If one process held a lock and a second process started to execute the `arch_spin_lock` function, the `head` will not be `equal` to `tail`, because the `tail` will be greater than `head` on `1`. In this way, the process will occur in the loop. There will be comparison between `head` and the `tail` values at each loop iteration. If these values are not equal, the `cpu_relax` will be called which is just [NOP](https://en.wikipedia.org/wiki/NOP) instruction:


```C
#define cpu_relax()     asm volatile("rep; nop")
```

and the next iteration of the loop will be started. If these values will be equal, this means that the process which held this lock, released this lock and the next process may acquire the lock.

The `spin_unlock` operation goes through the all macros/function as `spin_lock`, of course with `unlock` prefix. In the end the `arch_spin_unlock` function will be called. If we will look at the implementation of the `arch_spin_unlock` function, we will see that it increases `head` of the `lock tickets` list:

```C
__add(&lock->tickets.head, TICKET_LOCK_INC, UNLOCK_LOCK_PREFIX);
```

In a combination of the `spin_lock` and `spin_unlock`, we get kind of queue where `head` contains an index number which maps currently executed process which holds a lock and the `tail` which contains an index number which maps last process which tried to hold the lock:

```
     +-------+       +-------+
     |       |       |       |
head |   7   | - - - |   7   | tail
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
                     |   9   |
                     |       |
                     +-------+
```

That's all for now. We didn't cover `spinlock` API in full in this part, but I think that the main idea behind this concept must be clear now.

Conclusion
--------------------------------------------------------------------------------

This concludes the first part covering synchronization primitives in the Linux kernel. In this part, we met first synchronization primitive `spinlock` provided by the Linux kernel. In the next part we will continue to dive into this interesting theme and will see other `synchronization` related stuff.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Concurrent computing](https://en.wikipedia.org/wiki/Concurrent_computing)
* [Synchronization](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29)
* [Clocksource framework](https://0xax.gitbooks.io/linux-insides/content/Timers/linux-timers-2.html)
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
