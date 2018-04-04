Synchronization primitives in the Linux kernel. Part 2.
================================================================================

Queued Spinlocks
--------------------------------------------------------------------------------

This is the second part of the [chapter](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/index.html) which describes synchronization primitives in the Linux kernel and in the first [part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/linux-sync-1.html) of this chapter we met the first - [spinlock](https://en.wikipedia.org/wiki/Spinlock). We will continue to learn this synchronization primitive in this part. If you have read the previous part, you may remember that besides normal spinlocks, the Linux kernel provides special type of `spinlocks` - `queued spinlocks`. In this part we will try to understand what does this concept represent.

We saw [API](https://en.wikipedia.org/wiki/Application_programming_interface) of `spinlock` in the previous [part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/linux-sync-1.html):

* `spin_lock_init` - produces initialization of the given `spinlock`;
* `spin_lock` - acquires given `spinlock`;
* `spin_lock_bh` - disables software [interrupts](https://en.wikipedia.org/wiki/Interrupt) and acquire given `spinlock`.
* `spin_lock_irqsave` and `spin_lock_irq` - disable interrupts on local processor and preserve/not preserve previous interrupt state in the `flags`;
* `spin_unlock` - releases given `spinlock`;
* `spin_unlock_bh` - releases given `spinlock` and enables software interrupts;
* `spin_is_locked` - returns the state of the given `spinlock`;
* and etc.

And we know that all of these macro which are defined in the [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/spinlock.h) header file will be expanded to the call of the functions with `arch_spin_.*` prefix from the  [arch/x86/include/asm/spinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/spinlock.h) for the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture. If we will look at this header fill with attention, we will that these functions (`arch_spin_is_locked`, `arch_spin_lock`, `arch_spin_unlock` and etc) defined only if the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option is disabled: 

```C
#ifdef CONFIG_QUEUED_SPINLOCKS
#include <asm/qspinlock.h>
#else
static __always_inline void arch_spin_lock(arch_spinlock_t *lock)
{
    ...
    ...
    ...
}
...
...
...
#endif
```

This means that the [arch/x86/include/asm/qspinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/qspinlock.h) header file provides own implementation of these functions. Actually they are macros and they are located in other header file. This header file is - [include/asm-generic/qspinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/asm-generic/qspinlock.h#L126). If we will look into this header file, we will find definition of these macros:

```C
#define arch_spin_is_locked(l)          queued_spin_is_locked(l)
#define arch_spin_is_contended(l)       queued_spin_is_contended(l)
#define arch_spin_value_unlocked(l)     queued_spin_value_unlocked(l)
#define arch_spin_lock(l)               queued_spin_lock(l)
#define arch_spin_trylock(l)            queued_spin_trylock(l)
#define arch_spin_unlock(l)             queued_spin_unlock(l)
#define arch_spin_lock_flags(l, f)      queued_spin_lock(l)
#define arch_spin_unlock_wait(l)        queued_spin_unlock_wait(l)
```

Before we will consider how queued spinlocks and their [API](https://en.wikipedia.org/wiki/Application_programming_interface) are implemented, we take a look on theoretical part at first.

Introduction to queued spinlocks
-------------------------------------------------------------------------------

Queued spinlocks is a [locking mechanism](https://en.wikipedia.org/wiki/Lock_%28computer_science%29) in the Linux kernel which is replacement for the standard `spinlocks`. At least this is true for the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture. If we will look at the following kernel configuration file - [kernel/Kconfig.locks](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/Kconfig.locks), we will see following configuration entries:

```
config ARCH_USE_QUEUED_SPINLOCKS
	bool

config QUEUED_SPINLOCKS
	def_bool y if ARCH_USE_QUEUED_SPINLOCKS
	depends on SMP
```

This means that the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option will be enabled by default if the `ARCH_USE_QUEUED_SPINLOCKS` is enabled. We may see that the `ARCH_USE_QUEUED_SPINLOCKS` is enabled by default in the `x86_64` specific kernel configuration file - [arch/x86/Kconfig](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/Kconfig):

```
config X86
    ...
    ...
    ...
    select ARCH_USE_QUEUED_SPINLOCKS
    ...
    ...
    ...
```

Before we will start to consider what is it queued spinlock concept, let's look on other types of `spinlocks`. For the start let's consider how `normal` spinlocks is implemented. Usually, implementation of `normal` spinlock is based on the [test and set](https://en.wikipedia.org/wiki/Test-and-set) instruction. Principle of work of this instruction is pretty simple. This instruction writes a value to the memory location and returns old value from this memory location. Both of these operations are in atomic context i.e. this instruction is non-interruptible. So if the first thread started to execute this instruction, second thread will wait until the first processor will not finish. Basic lock can be built on top of this mechanism. Schematically it may look like this:

```C
int lock(lock)
{
    while (test_and_set(lock) == 1)
        ;
    return 0;
}

int unlock(lock)
{
    lock=0;

    return lock;
}
```

The first thread will execute the `test_and_set` which will set the `lock` to `1`. When the second thread will call the `lock` function, it will spin in the `while` loop, until the first thread will not call the `unlock` function and the `lock` will be equal to `0`. This implementation is not very good for performance, because it has at least two problems. The first problem is that this implementation may be unfair and the thread from one processor may have long waiting time, even if it called the `lock` before other threads which are waiting for free lock too. The second problem is that all threads which want to acquire a lock, must to execute many `atomic` operations like `test_and_set` on a variable which is in shared memory. This leads to the cache invalidation as the cache of the processor will store `lock=1`, but the value of the `lock` in memory may be `1` after a thread will release this lock.

In the previous [part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/linux-sync-1.html) we saw the second type of spinlock implementation - `ticket spinlock`. This approach solves the first problem and may guarantee order of threads which want to acquire a lock, but still has a second problem.

The topic of this part is `queued spinlocks`. This approach may help to solve both of these problems. The `queued spinlocks` allows to each processor to use its own memory location to spin. The basic principle of a queue-based spinlock can best be understood by studying a classic queue-based spinlock implementation called the [MCS](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf) lock. Before we will look at implementation of the `queued spinlocks` in the Linux kernel, we will try to understand what is it `MCS` lock.

The basic idea of the `MCS` lock is in that as I already wrote in the previous paragraph, a thread spins on a local variable and each processor in the system has its own copy of these variable. In other words this concept is built on top of the [per-cpu](https://0xax.gitbooks.io/linux-insides/content/Concepts/linux-cpu-1.html) variables concept in the Linux kernel.

When the first thread wants to acquire a lock, it registers itself in the `queue` or in other words it will be added to the special `queue` and will acquire lock, because it is free for now. When the second thread will want to acquire the same lock before the first thread will release it, this thread adds its own copy of the lock variable into this `queue`. In this case the first thread will contain a `next` field which will point to the second thread. From this moment, the second thread will wait until the first thread will release its lock and notify `next` thread about this event. The first thread will be deleted from the `queue` and the second thread will be owner of a lock.

Schematically we can represent it like:

Empty queue:

```
+---------+
|         |
|  Queue  |
|         |
+---------+
```

First thread tries to acquire a lock:

```
+---------+     +----------------------------+
|         |     |                            |
|  Queue  |---->| First thread acquired lock |
|         |     |                            |
+---------+     +----------------------------+
```

Second thread tries to acquire a lock:

```
+---------+     +----------------------------------------+     +-------------------------+
|         |     |                                        |     |                         |
|  Queue  |---->|  Second thread waits for first thread  |<----| First thread holds lock |
|         |     |                                        |     |                         |
+---------+     +----------------------------------------+     +-------------------------+
```

Or the pseudocode:

```C
void lock(...)
{
    lock.next = NULL;
    ancestor = put_lock_to_queue_and_return_ancestor(queue, lock);

    // if we have ancestor, the lock already acquired and we
    // need to wait until it will be released
    if (ancestor)
    {
        lock.locked = 1;
        ancestor.next = lock;

        while (lock.is_locked == true)
            ;
    }

    // in other way we are owner of the lock and may exit
}

void unlock(...)
{
    // do we need to notify somebody or we are alonw in the
    // queue?
    if (lock.next != NULL) {
        // the while loop from the lock() function will be
        // finished
        lock.next.is_locked = false;
        // delete ourself from the queue and exit
        ...
        ...
        ...
        return;
    }

    // So, we have no next threads in the queue to notify about
    // lock releasing event. Let's just put `0` to the lock, will
    // delete ourself from the queue and exit.
}
```

The idea is simple, but the implementation of the `queued spinlocks` is must complex than this pseudocode. As I already wrote above, the `queued spinlock` mechanism is planned to be replacement for `ticket spinlocks` in the Linux kernel. But as you may remember, the usual `spinlock` fit into `32-bit` [word](https://en.wikipedia.org/wiki/Word_%28computer_architecture%29). But the `MCS` based lock does not fit to this size. As you may know `spinlock_t` type is [widely](http://lxr.free-electrons.com/ident?i=spinlock_t) used in the Linux kernel. In this case would have to rewrite a significant part of the Linux kernel, but this is unacceptable. Beside this, some kernel structures which contains a spinlock for protection can't grow. But anyway, implementation of the `queued spinlocks` in the Linux kernel based on this concept with some modifications which allows to fit it into `32` bits.

That's all about theory of the `queued spinlocks`, now let's consider how this mechanism is implemented in the Linux kernel. Implementation of the `queued spinlocks` looks more complex and tangled than implementation of `ticket spinlocks`, but the study with attention will lead to success.

API of queued spinlocks
-------------------------------------------------------------------------------

Now we know a little about `queued spinlocks` from the theoretical side, time to see the implementation of this mechanism in the Linux kernel. As we saw above, the [include/asm-generic/qspinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/asm-generic/qspinlock.h#L126) header files provides a set of macro which are represent API for  a spinlock acquiring, releasing and etc:

```C
#define arch_spin_is_locked(l)          queued_spin_is_locked(l)
#define arch_spin_is_contended(l)       queued_spin_is_contended(l)
#define arch_spin_value_unlocked(l)     queued_spin_value_unlocked(l)
#define arch_spin_lock(l)               queued_spin_lock(l)
#define arch_spin_trylock(l)            queued_spin_trylock(l)
#define arch_spin_unlock(l)             queued_spin_unlock(l)
#define arch_spin_lock_flags(l, f)      queued_spin_lock(l)
#define arch_spin_unlock_wait(l)        queued_spin_unlock_wait(l)
```

All of these macros expand to the call of functions from the same header file. Additionally, we saw the `qspinlock` structure from the [include/asm-generic/qspinlock_types.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/asm-generic/qspinlock_types.h) header file which represents a queued spinlock in the Linux kernel:

```C
typedef struct qspinlock {
	atomic_t	val;
} arch_spinlock_t;
```

As we may see, the `qspinlock` structure contains only one field - `val`. This field represents the state of a given `spinlock`. This `4` bytes field consists from following four parts:

* `0-7` - locked byte;
* `8` - pending bit;
* `16-17` - two bit index which represents entry of the `per-cpu` array of the `MCS` lock (will see it soon);
* `18-31` - contains number of processor which indicates tail of the queue.

and the `9-15` bytes are not used.

As we already know, each processor in the system has own copy of the lock. The lock is represented by the following structure:

```C
struct mcs_spinlock {
       struct mcs_spinlock *next;
       int locked;
       int count;
};
```

from the [kernel/locking/mcs_spinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/mcs_spinlock.h) header file. The first field represents a pointer to the next thread in the `queue`. The second field represents the state of the current thread in the `queue`, where `1` is `lock` already acquired and `0` in other way. And the last field of the `mcs_spinlock` structure represents nested locks. To understand what is it nested lock, imagine situation when a thread acquired lock, but was interrupted by the hardware [interrupt](https://en.wikipedia.org/wiki/Interrupt) and an [interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler) tries to take a lock too. For this case, each processor has not just copy of the `mcs_spinlock` structure but array of these structures:

```C
static DEFINE_PER_CPU_ALIGNED(struct mcs_spinlock, mcs_nodes[4]);
```

This array allows to make four attempts of a lock acquisition for the four events in following contexts:

* normal task context;
* hardware interrupt context;
* software interrupt context;
* non-maskable interrupt context.

Now let's return to the `qspinlock` structure and the `API` of the `queued spinlocks`. Before we will move to consider `API` of `queued spinlocks`, notice the `val` field of the `qspinlock` structure has type - `atomic_t` which represents atomic variable or one operation at a time variable. So, all operations with this field will be [atomic](https://en.wikipedia.org/wiki/Linearizability). For example let's look at the reading value of the `val` API:

```C
static __always_inline int queued_spin_is_locked(struct qspinlock *lock)
{
	return atomic_read(&lock->val);
}
```

Ok, now we know data structures which represents queued spinlock in the Linux kernel and now time is to look at the implementation of the `main` function from the `queued spinlocks` [API](https://en.wikipedia.org/wiki/Application_programming_interface).

```C
#define arch_spin_lock(l)               queued_spin_lock(l)
```

Yes, this function is - `queued_spin_lock`. As we may understand from the function's name, it allows to acquire lock by the thread. This function is defined in the [include/asm-generic/qspinlock_types.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/asm-generic/qspinlock_types.h) header file and its implementation looks:

```C
static __always_inline void queued_spin_lock(struct qspinlock *lock)
{
        u32 val;

        val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL);
        if (likely(val == 0))
                 return;
        queued_spin_lock_slowpath(lock, val);
}
```

Looks pretty easy, except the `queued_spin_lock_slowpath` function. We may see that it takes only one parameter. In our case this parameter will represent `queued spinlock` which will be locked. Let's consider the situation that `queue` with locks is empty for now and the first thread wanted to acquire lock. As we may see the `queued_spin_lock` function starts from the call of the `atomic_cmpxchg_acquire` macro. As you may guess from the name of this macro, it executes atomic [CMPXCHG](http://x86.renejeschke.de/html/file_module_x86_id_41.html) instruction which compares value of the second parameter (zero in our case) with the value of the first parameter (current state of the given spinlock) and if they are identical, it stores value of the `_Q_LOCKED_VAL` in the memory location which is pointed by the `&lock->val` and return the initial value from this memory location.

The `atomic_cmpxchg_acquire` macro is defined in the [include/linux/atomic.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/atomic.h) header file and expands to the call of the `atomic_cmpxchg` function:

```C
#define  atomic_cmpxchg_acquire         atomic_cmpxchg
```

which is architecture specific. We consider [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture, so in our case this header file will be [arch/x86/include/asm/atomic.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/atomic.h) and the implementation of the `atomic_cmpxchg` function is just returns the result of the `cmpxchg` macro:

```C
static __always_inline int atomic_cmpxchg(atomic_t *v, int old, int new)
{
        return cmpxchg(&v->counter, old, new);
}
```

This macro is defined in the [arch/x86/include/asm/cmpxchg.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/cmpxchg.h) header file and looks:

```C
#define cmpxchg(ptr, old, new) \
    __cmpxchg(ptr, old, new, sizeof(*(ptr)))

#define __cmpxchg(ptr, old, new, size) \
    __raw_cmpxchg((ptr), (old), (new), (size), LOCK_PREFIX)
```

As we may see, the `cmpxchg` macro expands to the `__cpmxchg` macro with the almost the same set of parameters. New additional parameter is the size of the atomic value. The `__cmpxchg` macro adds `LOCK_PREFIX` and expands to the `__raw_cmpxchg` macro where `LOCK_PREFIX` just [LOCK](http://x86.renejeschke.de/html/file_module_x86_id_159.html) instruction. After all, the `__raw_cmpxchg` does all job for us:

```C
#define __raw_cmpxchg(ptr, old, new, size, lock) \
({
    ...
    ...
    ...
    volatile u32 *__ptr = (volatile u32 *)(ptr);            \
    asm volatile(lock "cmpxchgl %2,%1"                      \
                 : "=a" (__ret), "+m" (*__ptr)              \
                 : "r" (__new), "" (__old)                  \
                 : "memory");                               \
    ...
    ...
    ...
})
```

After the `atomic_cmpxchg_acquire` macro will be executed, it returns the previous value of the memory location. Now only one thread tried to acquire a lock, so the `val` will be zero and we will return from the `queued_spin_lock` function:

```C
val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL);
if (likely(val == 0))
    return;
```

From this moment, our first thread will hold a lock. Notice that this behavior differs from the behavior which was described in the `MCS` algorithm. The thread acquired lock, but we didn't add it to the `queue`. As I already wrote the implementation of `queued spinlocks` concept is based on the `MCS` algorithm in the Linux kernel, but in the same time it has some difference like this for optimization purpose.

So the first thread have acquired lock and now let's consider that the second thread tried to acquire the same lock. The second thread will start from the same `queued_spin_lock` function, but the `lock->val` will contain `1` or `_Q_LOCKED_VAL`, because first thread already holds lock. So, in this case the `queued_spin_lock_slowpath` function will be called. The `queued_spin_lock_slowpath` function is defined in the [kernel/locking/qspinlock.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/locking/qspinlock.c) source code file and starts from the following checks:

```C
void queued_spin_lock_slowpath(struct qspinlock *lock, u32 val)
{
	if (pv_enabled())
	    goto queue;

    if (virt_spin_lock(lock))
		return;

    ...
    ...
    ...
}
```

which check the state of the `pvqspinlock`. The `pvqspinlock` is `queued spinlock` in [paravirtualized](https://en.wikipedia.org/wiki/Paravirtualization) environment. As this chapter is related only to synchronization primitives in the Linux kernel, we skip these and other parts which are not directly related to the topic of this chapter. After these checks we compare our value which represents lock with the value of the `_Q_PENDING_VAL` macro and do nothing while this is true:

```C
if (val == _Q_PENDING_VAL) {
	while ((val = atomic_read(&lock->val)) == _Q_PENDING_VAL)
		cpu_relax();
}
```

where `cpu_relax` is just [NOP](https://en.wikipedia.org/wiki/NOP) instruction. Above, we saw that the lock contains - `pending` bit. This bit represents thread which wanted to acquire lock, but it is already acquired by the other thread and in the same time `queue` is empty. In this case, the `pending` bit will be set and the `queue` will not be touched. This is done for optimization, because there are no need in unnecessary latency which will be caused by the cache invalidation in a touching of own `mcs_spinlock` array.

At the next step we enter into the following loop:

```C
for (;;) {
	if (val & ~_Q_LOCKED_MASK)
		goto queue;

	new = _Q_LOCKED_VAL;
	if (val == new)
		new |= _Q_PENDING_VAL;

	old = atomic_cmpxchg_acquire(&lock->val, val, new);
	if (old == val)
		break;

	val = old;
}
```

The first `if` clause here checks that state of the lock (`val`) is in locked or pending state. This means that first thread already acquired lock, second thread tried to acquire lock too, but now it is in pending state. In this case we need to start to build queue. We will consider this situation little later. In our case we are first thread holds lock and the second thread tries to do it too. After this check we create new lock in a locked state and compare it with the state of the previous lock. As you remember, the `val` contains state of the `&lock->val` which after the second thread will call the `atomic_cmpxchg_acquire` macro will be equal to `1`. Both `new` and `val` values are equal so we set pending bit in the lock of the second thread. After this we need to check value of the `&lock->val` again, because the first thread may release lock before this moment. If the first thread did not released lock yet, the value of the `old` will be equal to the value of the `val` (because `atomic_cmpxchg_acquire` will return the value from the memory location which is pointed by the `lock->val` and now it is `1`) and we will exit from the loop. As we exited from this loop, we are waiting for the first thread until it will release lock, clear pending bit, acquire lock and return:

```C
smp_cond_acquire(!(atomic_read(&lock->val) & _Q_LOCKED_MASK));
clear_pending_set_locked(lock);
return;
```

Notice that we did not touch `queue` yet. We no need in it, because for two threads it just leads to unnecessary latency for memory access. In other case, the first thread may release it lock before this moment. In this case the `lock->val` will contain `_Q_LOCKED_VAL | _Q_PENDING_VAL` and we will start to build `queue`. We start to build `queue` by the getting the local copy of the `mcs_nodes` array of the processor which executes thread:

```C
node = this_cpu_ptr(&mcs_nodes[0]);
idx = node->count++;
tail = encode_tail(smp_processor_id(), idx);
```

Additionally we calculate `tail` which will indicate the tail of the `queue` and `index` which represents an entry of the `mcs_nodes` array. After this we set the `node` to point to the correct of the `mcs_nodes` array, set `locked` to zero because this thread didn't acquire lock yet and `next` to `NULL` because we don't know anything about other `queue` entries:

```C
node += idx;
node->locked = 0;
node->next = NULL;
```

We already touch `per-cpu` copy of the queue for the processor which executes current thread which wants to acquire lock, this means that owner of the lock may released it before this moment. So we may try to acquire lock again by the call of the `queued_spin_trylock` function.

```C
if (queued_spin_trylock(lock))
		goto release;
```

The `queued_spin_trylock` function is defined in the  [include/asm-generic/qspinlock.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/asm-generic/qspinlock.h) header file and just does the same `queued_spin_lock` function that does:

```C
static __always_inline int queued_spin_trylock(struct qspinlock *lock)
{
	if (!atomic_read(&lock->val) &&
	   (atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL) == 0))
		return 1;
	return 0;
}
```

If the lock was successfully acquired we jump to the `release` label to release a node of the `queue`:

```C
release:
	this_cpu_dec(mcs_nodes[0].count);
```

because we no need in it anymore as lock is acquired. If the `queued_spin_trylock` was unsuccessful, we update tail of the queue:

```C
old = xchg_tail(lock, tail);
```

and retrieve previous tail. The next step is to check that `queue` is not empty. In this case we need to link previous entry with the new:

```C
if (old & _Q_TAIL_MASK) {
	prev = decode_tail(old);
	WRITE_ONCE(prev->next, node);

    arch_mcs_spin_lock_contended(&node->locked);
}
```

After queue entries linked, we start to wait until reaching the head of queue. As we As we reached this, we need to do a check for new node which might be added during this wait:

```C
next = READ_ONCE(node->next);
if (next)
	prefetchw(next);
```

If the new node was added, we prefetch cache line from memory pointed by the next queue entry with the [PREFETCHW](http://www.felixcloutier.com/x86/PREFETCHW.html) instruction. We preload this pointer now for optimization purpose. We just became a head of queue and this means that there is upcoming `MCS` unlock operation and the next entry will be touched.

Yes, from this moment we are in the head of the `queue`. But before we are able to acquire a lock, we need to wait at least two events: current owner of a lock will release it and the second thread with `pending` bit will acquire a lock too:

```C
smp_cond_acquire(!((val = atomic_read(&lock->val)) & _Q_LOCKED_PENDING_MASK));
```

After both threads will release a lock, the head of the `queue` will hold a lock. In the end we just need to update the tail of the `queue` and remove current head from it. 

That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the second part of the [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) chapter in the Linux kernel. In the previous [part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/linux-sync-1.html) we already met the first synchronization primitive `spinlock` provided by the Linux kernel which is implemented as `ticket spinlock`. In this part we saw another implementation of the `spinlock` mechanism - `queued spinlock`. In the next part we will continue to dive into synchronization primitives in the Linux kernel. 

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [spinlock](https://en.wikipedia.org/wiki/Spinlock)
* [interrupt](https://en.wikipedia.org/wiki/Interrupt)
* [interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler) 
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [Test and Set](https://en.wikipedia.org/wiki/Test-and-set)
* [MCS](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf)
* [per-cpu variables](https://0xax.gitbooks.io/linux-insides/content/Concepts/linux-cpu-1.html)
* [atomic instruction](https://en.wikipedia.org/wiki/Linearizability)
* [CMPXCHG instruction](http://x86.renejeschke.de/html/file_module_x86_id_41.html) 
* [LOCK instruction](http://x86.renejeschke.de/html/file_module_x86_id_159.html)
* [NOP instruction](https://en.wikipedia.org/wiki/NOP)
* [PREFETCHW instruction](http://www.felixcloutier.com/x86/PREFETCHW.html)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [Previous part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/linux-sync-1.html)
