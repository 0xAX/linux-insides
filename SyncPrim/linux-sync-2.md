Synchronization primitives in the Linux kernel. Part 2.
================================================================================

Queued Spinlocks
--------------------------------------------------------------------------------

This is the second part of the [chapter](https://0xax.gitbook.io/linux-insides/summary/syncprim) which describes synchronization primitives in the Linux kernel.  In the first [part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-1) of this chapter we meet the first [spinlock](https://en.wikipedia.org/wiki/Spinlock). We will continue to learn about this synchronization primitive here. If you have read the previous part, you may remember that besides normal spinlocks, the Linux kernel provides a special type of `spinlocks` - `queued spinlocks`. Here we will try to understand what this concept represents.

We saw the [API](https://en.wikipedia.org/wiki/Application_programming_interface) of `spinlock` in the previous [part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-1):

* `spin_lock_init` - produces initialization of the given `spinlock`;
* `spin_lock` - acquires given `spinlock`;
* `spin_lock_bh` - disables software [interrupts](https://en.wikipedia.org/wiki/Interrupt) and acquire given `spinlock`;
* `spin_lock_irqsave` and `spin_lock_irq` - disable interrupts on local processor and preserve/not preserve previous interrupt state in the `flags`;
* `spin_unlock` - releases given `spinlock` and acquire given `spinlock`;
* `spin_unlock_bh` - releases given `spinlock` and enables software interrupts;
* `spin_is_locked` - returns the state of the given `spinlock`;
* and etc.

And we know that all of these macros with the `arch_*` prefix which are defined in the [include/linux/spinlock.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock.h) header file will be expanded to the call of the functions  from the [include/asm-generic/qspinlock.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/qspinlock.h):

```C
#define arch_spin_is_locked(l)          queued_spin_is_locked(l)
#define arch_spin_is_contended(l)       queued_spin_is_contended(l)
#define arch_spin_value_unlocked(l)     queued_spin_value_unlocked(l)
#define arch_spin_lock(l)               queued_spin_lock(l)
#define arch_spin_trylock(l)            queued_spin_trylock(l)
#define arch_spin_unlock(l)             queued_spin_unlock(l)
```

Before we consider how queued spinlocks and their [API](https://en.wikipedia.org/wiki/Application_programming_interface) are implemented, let's first take a look at the theory.

Introduction to queued spinlocks
-------------------------------------------------------------------------------

Queued spinlocks is a [locking mechanism](https://en.wikipedia.org/wiki/Lock_%28computer_science%29) in the Linux kernel which is replacement for the standard `spinlocks`. At least this is true for the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture. If we will look at the following kernel configuration file - [kernel/Kconfig.locks](https://github.com/torvalds/linux/blob/master/kernel/Kconfig.locks), we will see following configuration entries:

```
config ARCH_USE_QUEUED_SPINLOCKS
	bool

config QUEUED_SPINLOCKS
	def_bool y if ARCH_USE_QUEUED_SPINLOCKS
	depends on SMP
```

This means that the `CONFIG_QUEUED_SPINLOCKS` kernel configuration option will be enabled by default if the `ARCH_USE_QUEUED_SPINLOCKS` is enabled. We may see that the `ARCH_USE_QUEUED_SPINLOCKS` is enabled by default in the `x86_64` specific kernel configuration file - [arch/x86/Kconfig](https://github.com/torvalds/linux/blob/master/arch/x86/Kconfig):

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

Before we start to consider what queued spinlock concept is, let's look on other types of `spinlocks`. For the start let's consider how a `normal` spinlock is implemented. Usually, the implementation of a `normal` spinlock is based on the [test and set](https://en.wikipedia.org/wiki/Test-and-set) instruction. The principle of how this instruction works is pretty simple. It writes a value to the memory location and returns the old value from it. Together these instructions are atomic i.e. non-interruptible instructions. So if the first thread starts to execute this instruction, second thread will wait until the first processor has finished its instruction. A basic lock can be built on top of this mechanism. Schematically it may look like this:

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

The first thread will execute the `test_and_set` which will set the `lock` to `1`. When the second thread calls the `lock` function, it will spin in the `while` loop, until the first thread calls the `unlock` function and the `lock` will be equal to `0`. This implementation is not very good for performance reasons, due to (at least) two problems. The first problem is that this implementation may be unfair since other threads which arrived later at the lock may acquire it first. The second problem is that all threads which want to acquire a lock must execute many `atomic` operations like `test_and_set` on a variable which is in shared memory. This leads to the cache invalidation as the cache of the processor will store `lock=1`, but the value of the `lock` in memory may not be `1` after a thread will release this lock.

The topic of this part is `queued spinlocks`. This approach may help to solve both of these problems. The `queued spinlocks` allows each processor to spin while checking its own memory location. The basic principle of a queue-based spinlock can best be understood by studying a classic queue-based spinlock implementation called the [MCS](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf) lock. Before we look at implementation of the `queued spinlocks` in the Linux kernel, we will try to understand how `MCS` lock works.

The basic idea of the `MCS` lock is that a thread spins on a local variable and each processor in the system has its own copy of this variable (see the previous paragraph). In other words this concept is built on top of the [per-cpu](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1) variables concept in the Linux kernel.

When the first thread wants to acquire a lock, it registers itself in the `queue`. In other words it will be added to the special `queue` and will acquire lock, because it is free for now. When the second thread wants to acquire the same lock before the first thread releases it, this thread adds its own copy of the lock variable into this `queue`. In this case the first thread will contain a `next` field which will point to the second thread. From this moment, the second thread will wait until the first thread releases its lock and notifies `next` thread about this event. The first thread will be deleted from the `queue` and the second thread will be owner of a lock.

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

    // if we have ancestor, the lock is already acquired and we
    // need to wait until it is released
    if (ancestor)
    {
        lock.is_locked = 1;
        ancestor.next = lock;

        while (lock.is_locked == true)
            ;
    }

    // otherwise we are owner of the lock and may exit
}

void unlock(...)
{
    // do we need to notify somebody or we are alone in the
    // queue?
    if (lock.next != NULL) {
        // the while loop from the lock() function will be
        // finished
        lock.next.is_locked = false;
    }

    // So, we have no next threads in the queue to notify about
    // lock releasing event. Let's just put `0` to the lock, will
    // delete ourself from the queue and exit.
}
```

That's all we'll say about the theory of the `queued spinlocks`.  Now let's consider how this mechanism is implemented in the Linux kernel. Unlike above pseudocode, the implementation of the `queued spinlocks` looks complex and tangled. But the study with attention will lead to success.

API of queued spinlocks
-------------------------------------------------------------------------------

Now that we know a little about `queued spinlocks` from the theoretical side, it's time to see the implementation of this mechanism in the Linux kernel. As we saw above, the [include/asm-generic/qspinlock.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/qspinlock.h) header file provides a set of macros which represents the API for a spinlock acquiring, releasing, etc:

```C
#define arch_spin_is_locked(l)          queued_spin_is_locked(l)
#define arch_spin_is_contended(l)       queued_spin_is_contended(l)
#define arch_spin_value_unlocked(l)     queued_spin_value_unlocked(l)
#define arch_spin_lock(l)               queued_spin_lock(l)
#define arch_spin_trylock(l)            queued_spin_trylock(l)
#define arch_spin_unlock(l)             queued_spin_unlock(l)
```

All of these macros expand to the call of functions from the same header file. Additionally, we saw the `qspinlock` structure from the [include/asm-generic/qspinlock_types.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/qspinlock_types.h) header file which represents a queued spinlock in the Linux kernel:

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

The `val` field represents the state of a given `spinlock`. This `4` bytes field consists from following parts:

* `0-7` - locked byte;
* `8` - pending bit;
* `9-15` - not used;
* `16-17` - two bit index which represents entry of the `per-cpu` array of the `MCS` lock (will see it soon);
* `18-31` - contains number of processor which indicates tail of the queue.

Before we move on to consider the `API` of `queued spinlocks`, notice the `val` field of the `qspinlock` structure has type - `atomic_t` which represents atomic variable aka a "one operation at a time" variable. So, all operations with this field will be [atomic](https://en.wikipedia.org/wiki/Linearizability). For example let's look at the reading value of the `val` API:

```C
static __always_inline int queued_spin_is_locked(struct qspinlock *lock)
{
	return atomic_read(&lock->val);
}
```

Ok, now we know data structures which represents queued spinlock in the Linux kernel and now is the time to look at the implementation of the main function from the `queued spinlocks` [API](https://en.wikipedia.org/wiki/Application_programming_interface):

```C
#define arch_spin_lock(l)               queued_spin_lock(l)
```

Yes, this function is - `queued_spin_lock`. As we may understand from the function's name, it allows a thread to acquire a lock. This function is defined in the [include/asm-generic/qspinlock_types.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/qspinlock_types.h) header file and its implementation is:

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

Looks pretty easy, except for the `queued_spin_lock_slowpath` function. We see that it takes only one parameter. In our case this parameter represents `queued spinlock`, which will be locked. Let's consider the situation where `queue` with locks is empty for now and the first thread wanted to acquire lock. As we may see the `queued_spin_lock` function starts from the call of the `atomic_cmpxchg_acquire` macro. As you may guess from its name, it executes atomic [CMPXCHG](http://x86.renejeschke.de/html/file_module_x86_id_41.html) instruction. Ultimately, the `atomic_cmpxchg_acquire` macro expands to the call of the `__raw_cmpxchg` macro almost like the following:

```C
#define __raw_cmpxchg(ptr, old, new, size, lock)		\
({								\
	__typeof__(*(ptr)) __ret;				\
	__typeof__(*(ptr)) __old = (old);			\
	__typeof__(*(ptr)) __new = (new);			\
								\
	volatile u32 *__ptr = (volatile u32 *)(ptr);		\
	asm volatile(lock "cmpxchgl %2,%1"			\
		     : "=a" (__ret), "+m" (*__ptr)		\
		     : "r" (__new), "0" (__old)			\
		     : "memory");				\
								\
	__ret;							\
})
```

which compares the `old` with the value pointed to by `ptr`.  If they are equal, it stores the `new` in the memory location which is pointed by the `ptr` and returns the initial value in this memory location.

Let's back to the `queued_spin_lock` function. Assuming that we are the first one who tried to acquire the lock, the `val` will be zero and we will return from the `queued_spin_lock` function:

```C
	val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL);
	if (likely(val == 0))
		return;
```

So far, we've only considered uncontended case (i.e. fast-path). Now let's consider contended case (i.e. slow-path). Suppose that one thread tried to acquire a lock, but the lock is already held, then `queued_spin_lock_slowpath` will be called. The `queued_spin_lock_slowpath` function is defined in the [kernel/locking/qspinlock.c](https://github.com/torvalds/linux/blob/master/kernel/locking/qspinlock.c) source code file:

```C
void queued_spin_lock_slowpath(struct qspinlock *lock, u32 val)
{
	...
	...
	...
	if (val == _Q_PENDING_VAL) {
		int cnt = _Q_PENDING_LOOPS;
		val = atomic_cond_read_relaxed(&lock->val,
					       (VAL != _Q_PENDING_VAL) || !cnt--);
	}
	...
	...
	...
}
```

which waits for in-progress lock acquisition to be done with a bounded number of spins so that we guarantee forward progress. Above, we saw that the lock contains - pending bit. This bit represents thread which wanted to acquire lock, but it is already acquired by the other thread and `queue` is empty at the same time. In this case, the pending bit will be set and the `queue` will not be touched. This is done for optimization, because there are no need in unnecessary latency which will be caused by the cache invalidation in a touching of own `mcs_spinlock` array.

If we observe contention, then we have no choice other than queueing, so jump to `queue` label that we'll see later:

```C
	if (val & ~_Q_LOCKED_MASK)
		goto queue;
```

So, the lock is already held. That is, we set the pending bit of the lock:

```C
	val = queued_fetch_set_pending_acquire(lock);
```

Again if we observe contention, undo the pending and queue.

```C
	if (unlikely(val & ~_Q_LOCKED_MASK)) {
		if (!(val & _Q_PENDING_MASK))
			clear_pending(lock);
		goto queue;
	}
```

Now, we're pending, wait for the lock owner to release it.

```C
	if (val & _Q_LOCKED_MASK)
		atomic_cond_read_acquire(&)
```

We are allowed to take the lock. So, we clear the pending bit and set the locked bit. Now we have nothing to do with the `queued_spin_lock_slowpath` function, return from it.

```C
	clear_pending_set_locked(lock);
	return;
```

Before diving into queueing, we'll see about `MCS` lock mechanism first. As we already know, each processor in the system has own copy of the lock. The lock is represented by the following structure:

```C
struct mcs_spinlock {
       struct mcs_spinlock *next;
       int locked;
       int count;
};
```

from the [kernel/locking/mcs_spinlock.h](https://github.com/torvalds/linux/blob/master/kernel/locking/mcs_spinlock.h) header file. The first field represents a pointer to the next thread in the `queue`. The second field represents the state of the current thread in the `queue`, where `1` is `lock` already acquired and `0` in other way. And the last field of the `mcs_spinlock` structure represents nested locks. To understand what nested lock is, imagine situation when a thread acquired lock, but was interrupted by the hardware [interrupt](https://en.wikipedia.org/wiki/Interrupt) and an [interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler) tries to take a lock too. For this case, each processor has not just copy of the `mcs_spinlock` structure but array of these structures:

```C
static DEFINE_PER_CPU_ALIGNED(struct qnode, qnodes[MAX_NODES]);
```

This array allows to make four attempts of a lock acquisition for the four events in following contexts:

* normal task context;
* hardware interrupt context;
* software interrupt context;
* non-maskable interrupt context.

Notice that we did not touch `queue` yet. We do not need it, because for two threads it just leads to unnecessary latency for memory access. In other case, the first thread may release it lock before this moment. In this case the `lock->val` will contain `_Q_LOCKED_VAL | _Q_PENDING_VAL` and we will start to build `queue`. We start to build `queue` by the getting the local copy of the `qnodes` array of the processor which executes thread and calculate `tail` which will indicate the tail of the `queue` and `idx` which represents an index of the `qnodes` array:

```C
queue:
	node = this_cpu_ptr(&qnodes[0].mcs);
	idx = node->count++;
	tail = encode_tail(smp_processer_id(), idx);

	node = grab_mcs_node(node, idx);
```

After this, we set `locked` to zero because this thread didn't acquire lock yet and `next` to `NULL` because we don't know anything about other `queue` entries:

```C
	node->locked = 0;
	node->next = NULL;
```

We already touched `per-cpu` copy of the queue for the processor which executes current thread which wants to acquire lock, this means that owner of the lock may released it before this moment. So we may try to acquire lock again by the call of the `queued_spin_trylock` function:

```C
	if (queued_spin_trylock(lock))
		goto release;
```

It does the almost same thing `queued_spin_lock` function does.

If the lock was successfully acquired we jump to the `release` label to release a node of the `queue`:

```C
release:
	__this_cpu_dec(qnodes[0].mcs.count);
```

because we no need in it anymore as lock is acquired. If the `queued_spin_trylock` was unsuccessful, we update tail of the queue:

```C
	old = xchg_tail(lock, tail);
	next = NULL;
```

and retrieve previous tail. The next step is to check that `queue` is not empty. In this case we need to link previous entry with the new. While waiting for the MCS lock, the next pointer may have been set by another lock waiter. We optimistically load the next pointer & prefetch the cacheline for writing to reduce latency in the upcoming MCS unlock operation:

```C
	if (old & _Q_TAIL_MASK) {
		prev = decode_tail(old);
		WRITE_ONCE(prev->next, node);

		arch_mcs_spin_lock_contended(&node->locked);

		next = READ_ONCE(node->next);
		if (next)
			prefetchw(next);
	}
```

If the new node was added, we prefetch cache line from memory pointed by the next queue entry with the [PREFETCHW](http://www.felixcloutier.com/x86/PREFETCHW.html) instruction. We preload this pointer now for optimization purpose. We just became a head of queue and this means that there is upcoming `MCS` unlock operation and the next entry will be touched.

Yes, from this moment we are in the head of the `queue`. But before we are able to acquire a lock, we need to wait at least two events: current owner of a lock will release it and the second thread with `pending` bit will acquire a lock too:

```C
	val = atomic_cond_read_acquire(&lock->val, !(VAL & _Q_LOCKED_PENDING_MASK));
```

After both threads will release a lock, the head of the `queue` will hold a lock. In the end we just need to update the tail of the `queue` and remove current head from it.

That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the second part of the [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) chapter in the Linux kernel. In the previous [part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-1) we already met the first synchronization primitive `spinlock` provided by the Linux kernel which is implemented as `ticket spinlock`. In this part we saw another implementation of the `spinlock` mechanism - `queued spinlock`. In the next part we will continue to dive into synchronization primitives in the Linux kernel.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](mailto:anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [spinlock](https://en.wikipedia.org/wiki/Spinlock)
* [interrupt](https://en.wikipedia.org/wiki/Interrupt)
* [interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler)
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [Test and Set](https://en.wikipedia.org/wiki/Test-and-set)
* [MCS](http://www.cs.rochester.edu/~scott/papers/1991_TOCS_synch.pdf)
* [per-cpu variables](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1)
* [atomic instruction](https://en.wikipedia.org/wiki/Linearizability)
* [CMPXCHG instruction](http://x86.renejeschke.de/html/file_module_x86_id_41.html)
* [LOCK instruction](http://x86.renejeschke.de/html/file_module_x86_id_159.html)
* [NOP instruction](https://en.wikipedia.org/wiki/NOP)
* [PREFETCHW instruction](http://www.felixcloutier.com/x86/PREFETCHW.html)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-1)
