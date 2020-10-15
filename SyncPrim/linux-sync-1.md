Synchronization primitives in the Linux kernel. Part 1.
================================================================================

Introduction
--------------------------------------------------------------------------------

This part opens a new chapter in the [linux-insides](https://github.com/0xAX/linux-insides/blob/master/SUMMARY.md) book. Timers and time management related stuff was described in the previous [chapter](https://0xax.gitbook.io/linux-insides/summary/timers/). Now it's time to move on to the next topic. As you probably recognized from the title, this chapter will describe the [synchronization](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) primitives in the Linux kernel.

As always, we will try to know what a `synchronization primitive` in general is before we deal with any synchronization-related issues. Actually, a synchronization primitive is a software mechanism, that ensures that two or more [parallel](https://en.wikipedia.org/wiki/Parallel_computing) processes or threads are not running simultaneously on the same code segment. For example, let's look at the following piece of code:

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

from the [kernel/time/clocksource.c](https://github.com/torvalds/linux/blob/master/kernel/time/clocksource.c) source code file. This code is from the `__clocksource_register_scale` function which adds the given [clocksource](https://0xax.gitbook.io/linux-insides/summary/timers/linux-timers-2) to the clock sources list. This function produces different operations on a list with registered clock sources. For example, the `clocksource_enqueue` function adds the given clock source to the list with registered clocksources - `clocksource_list`. Note that these lines of code wrapped to two functions: `mutex_lock` and `mutex_unlock` which takes one parameter - the `clocksource_mutex` in our case.

These functions represent locking and unlocking based on [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion) synchronization primitive. As `mutex_lock` will be executed, it allows us to prevent the situation when two or more threads will execute this code while the `mutex_unlock` will not be executed by process-owner of the mutex. In other words, we prevent parallel operations on a `clocksource_list`. Why do we need `mutex` here? What if two parallel processes will try to register a clock source. As we already know, the `clocksource_enqueue` function adds the given clock source to the `clocksource_list` list right after a clock source in the list which has the biggest rating (a registered clock source which has the highest frequency in the system):

```C
static void clocksource_enqueue(struct clocksource *cs)
{
	struct list_head *entry = &clocksource_list;
	struct clocksource *tmp;

	list_for_each_entry(tmp, &clocksource_list, list) {
		if (tmp->rating < cs->rating)
			break;
		entry = &tmp->list;
	}
	list_add(&cs->list, entry);
}
```

If two parallel processes will try to do it simultaneously, both process may found the same `entry` may occur [race condition](https://en.wikipedia.org/wiki/Race_condition) or in other words, the second process which will execute `list_add`, will overwrite a clock source from the first thread.

Besides this simple example, synchronization primitives are ubiquitous in the Linux kernel. If we will go through the previous [chapter](https://0xax.gitbook.io/linux-insides/summary/timers/) or other chapters again or if we will look at the Linux kernel source code in general, we will meet many places like this. We will not consider how `mutex` is implemented in the Linux kernel. Actually, the Linux kernel provides a set of different synchronization primitives like:

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

and located in the [include/linux/spinlock_types.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_types.h) header file. We may see that its implementation depends on the state of the `CONFIG_DEBUG_LOCK_ALLOC` kernel configuration option. We will skip this now, because all debugging related stuff will be in the end of this part. So, if the `CONFIG_DEBUG_LOCK_ALLOC` kernel configuration option is disabled, the `spinlock_t` contains [union](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B) with one field which is - `raw_spinlock`:

```C
typedef struct spinlock {
        union {
              struct raw_spinlock rlock;
        };
} spinlock_t;
```

The `raw_spinlock` structure defined in the [same](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_types.h) header file represents the implementation of `normal` spinlock. Let's look how the `raw_spinlock` structure is defined:

```C
typedef struct raw_spinlock {
        arch_spinlock_t raw_lock;
#ifdef CONFIG_DEBUG_SPINLOCK
	unsigned int magic, owner_cpu;
	void *owner;
#endif
#ifdef CONFIG_DEBUG_LOCK_ALLOC
	struct lockdep_map dep_map;
#endif
} raw_spinlock_t;
```

where the `arch_spinlock_t` represents architecture-specific `spinlock` implementation. As we mentioned above, we will skip debugging kernel configuration options. As we focus on [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture in this book, the `arch_spinlock_t` that we will consider is defined in the [include/asm-generic/qspinlock_types.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/qspinlock_types.h) header file and looks:

```C
typedef struct qspinlock {
        union {
		atomic_t val;
		struct {
			u8	locked;
			u8	pending;
		};
		struct {
			u16	locked_pending;
			u16	tail;
		};
        };
} arch_spinlock_t;
```

We will not stop on this structures for now. Let's look at the operations on a `spinlock`. The Linux kernel provides following main operations on a `spinlock`:

* `spin_lock_init` - produces initialization of the given `spinlock`;
* `spin_lock` - acquires given `spinlock`;
* `spin_lock_bh` - disables software [interrupts](https://en.wikipedia.org/wiki/Interrupt) and acquire given `spinlock`;
* `spin_lock_irqsave` and `spin_lock_irq` - disable interrupts on local processor, preserve/not preserve previous interrupt state in the `flags` and acquire given `spinlock`;
* `spin_unlock` - releases given `spinlock`;
* `spin_unlock_bh` - releases given `spinlock` and enables software interrupts;
* `spin_is_locked` - returns the state of the given `spinlock`;
* and etc.

Let's look on the implementation of the `spin_lock_init` macro. As I already wrote, this and other macro are defined in the [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock.h) header file and the `spin_lock_init` macro looks:

```C
#define spin_lock_init(_lock)			\
do {						\
	spinlock_check(_lock);		        \
	raw_spin_lock_init(&(_lock)->rlock);	\
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
do {						\
    *(lock) = __RAW_SPIN_LOCK_UNLOCKED(lock);	\
} while (0)					\
```

assigns the value of the `__RAW_SPIN_LOCK_UNLOCKED` with the given `spinlock` to the given `raw_spinlock_t`. As we may understand from the name of the `__RAW_SPIN_LOCK_UNLOCKED` macro, this macro does initialization of the given `spinlock` and set it to `released` state. This macro is defined in the [include/linux/spinlock_types.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_types.h) header file and expands to the following macros:

```C
#define __RAW_SPIN_LOCK_UNLOCKED(lockname)      \
         (raw_spinlock_t) __RAW_SPIN_LOCK_INITIALIZER(lockname)

#define __RAW_SPIN_LOCK_INITIALIZER(lockname)			\
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
#define __ARCH_SPIN_LOCK_UNLOCKED       { { .val = ATOMIC_INIT(0) } }
```

for the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture. So, after the expansion of the `spin_lock_init` macro, a given `spinlock` will be initialized and its state will be - `unlocked`.

From this moment we know how to initialize a `spinlock`, now let's consider [API](https://en.wikipedia.org/wiki/Application_programming_interface) which Linux kernel provides for manipulations of `spinlocks`. The first is:

```C
static __always_inline void spin_lock(spinlock_t *lock)
{
	raw_spin_lock(&lock->rlock);
}
```

function which allows us to `acquire` a `spinlock`. The `raw_spin_lock` macro is defined in the same header file and expands to the call of `_raw_spin_lock`:

```C
#define raw_spin_lock(lock)	_raw_spin_lock(lock)
```

Where `_raw_spin_lock` is defined depends on whether `CONFIG_SMP` option is set and `CONFIG_INLINE_SPIN_LOCK` option is set. If the [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) is disabled, `_raw_spin_lock` is defined in the [include/linux/spinlock_api_up.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_api_up.h) header file as a macro and looks like:

```C
#define _raw_spin_lock(lock)	__LOCK(lock)
```

If the SMP is enabled and `CONFIG_INLINE_SPIN_LOCK` is set, it is defined in [include/linux/spinlock_api_smp.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_api_smp.h) header file as the following:

```C
#define _raw_spin_lock(lock) __raw_spin_lock(lock)
```

If the SMP is enabled and `CONFIG_INLINE_SPIN_LOCK` is not set, it is defined in [kernel/locking/spinlock.c](https://github.com/torvalds/linux/blob/master/kernel/locking/spinlock.c) source code file as the following:

```C
void __lockfunc _raw_spin_lock(raw_spinlock_t *lock)
{
	__raw_spin_lock(lock);
}
```

Here we will consider the latter form of `_raw_spin_lock`. The `__raw_spin_lock` function looks:

```C
static inline void __raw_spin_lock(raw_spinlock_t *lock)
{
        preempt_disable();
        spin_acquire(&lock->dep_map, 0, 0, _RET_IP_);
        LOCK_CONTENDED(lock, do_raw_spin_trylock, do_raw_spin_lock);
}
```

As you may see, first of all we disable [preemption](https://en.wikipedia.org/wiki/Preemption_%28computing%29) by the call of the `preempt_disable` macro from the [include/linux/preempt.h](https://github.com/torvalds/linux/blob/master/include/linux/preempt.h) (more about this you may read in the ninth [part](https://0xax.gitbook.io/linux-insides/summary/initialization/linux-initialization-9) of the Linux kernel initialization process chapter). When we unlock the given `spinlock`, preemption will be enabled again:

```C
static inline void __raw_spin_unlock(raw_spinlock_t *lock)
{
        ...
        ...
        ...
        preempt_enable();
}
```

We need to do this to prevent the process from other processes to preempt it while it is spinning on a lock. The `spin_acquire` macro which through a chain of other macros expands to the call of the:

```C
#define spin_acquire(l, s, t, i)                lock_acquire_exclusive(l, s, t, NULL, i)
#define lock_acquire_exclusive(l, s, t, n, i)           lock_acquire(l, s, t, 0, 1, n, i)
```

The `lock_acquire` function:

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

As I wrote above, we will not consider stuff here which is related to debugging or tracing. The main point of the `lock_acquire` function is to disable hardware interrupts by the call of the `raw_local_irq_save` macro, because the given spinlock might be acquired with enabled hardware interrupts. In this way the process will not be preempted. Note that in the end of the `lock_acquire` function we will enable hardware interrupts again with the help of the `raw_local_irq_restore` macro. As you already may guess, the main work will be in the `__lock_acquire` function which is defined in the [kernel/locking/lockdep.c](https://github.com/torvalds/linux/blob/master/kernel/locking/lockdep.c) source code file.

The `__lock_acquire` function looks big. We will try to understand what this function does, but not in this part. Actually this function is mostly related to the Linux kernel [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) and it is not topic of this part. If we will return to the definition of the `__raw_spin_lock` function, we will see that it contains the following definition in the end:

```C
LOCK_CONTENDED(lock, do_raw_spin_trylock, do_raw_spin_lock);
```

The `LOCK_CONTENDED` macro is defined in the [include/linux/lockdep.h](https://github.com/torvalds/linux/blob/master/include/linux/lockdep.h) header file and just calls the given function with the given `spinlock`:

```C
#define LOCK_CONTENDED(_lock, try, lock) \
         lock(_lock)
```

In our case, the `lock` is `do_raw_spin_lock` function from the [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/master/include/linux/spnlock.h) header file and the `_lock` is the given `raw_spinlock_t`:

```C
static inline void do_raw_spin_lock(raw_spinlock_t *lock) __acquires(lock)
{
        __acquire(lock);
         arch_spin_lock(&lock->raw_lock);
}
```

The `__acquire` here is just [Sparse](https://en.wikipedia.org/wiki/Sparse) related macro and we are not interested in it in this moment. The `arch_spin_lock` macro is defined in the [include/asm-generic/qspinlock.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/qspinlocks.h) header file as the following:

```C
#define arch_spin_lock(l)               queued_spin_lock(l)
```

We stop here for this part. In the next part, we'll dive into how queued spinlocks works and related concepts.

Conclusion
--------------------------------------------------------------------------------

This concludes the first part covering synchronization primitives in the Linux kernel. In this part, we met first synchronization primitive `spinlock` provided by the Linux kernel. In the next part we will continue to dive into this interesting theme and will see other `synchronization` related stuff.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](mailto:anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Concurrent computing](https://en.wikipedia.org/wiki/Concurrent_computing)
* [Synchronization](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29)
* [Clocksource framework](https://0xax.gitbook.io/linux-insides/summary/timers/linux-timers-2)
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
* [Previous chapter](https://0xax.gitbook.io/linux-insides/summary/timers/)
