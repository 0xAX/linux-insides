Synchronization primitives in the Linux kernel. Part 6.
================================================================================

Introduction
--------------------------------------------------------------------------------

This is the sixth part of the chapter which describes [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_(computer_science)) in the Linux kernel and in the previous parts we finished to consider different [readers-writer lock](https://en.wikipedia.org/wiki/Readers%E2%80%93writer_lock) synchronization primitives. We will continue to learn synchronization primitives in this part and start to consider a similar synchronization primitive which can be used to avoid the `writer starvation` problem. The name of this synchronization primitive is - `seqlock` or `sequential locks`.

We know from the previous [part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-5.html) that [readers-writer lock](https://en.wikipedia.org/wiki/Readers%E2%80%93writer_lock) is a special lock mechanism which allows concurrent access for read-only operations, but an exclusive lock is needed for writing or modifying data. As we may guess, it may lead to a problem which is called `writer starvation`. In other words, a writer process can't acquire a lock as long as at least one reader process which aqcuired a lock holds it. So, in the situation when contention is high, it will lead to situation when a writer process which wants to acquire a lock will wait for it for a long time.

The `seqlock` synchronization primitive can help solve this problem.

As in all previous parts of this [book](https://0xax.gitbooks.io/linux-insides/content), we will try to consider this synchronization primitive from the theoretical side and only than we will consider [API](https://en.wikipedia.org/wiki/Application_programming_interface) provided by the Linux kernel to manipulate with `seqlocks`.

So, let's start.

Sequential lock
--------------------------------------------------------------------------------

So, what is a `seqlock` synchronization primitive and how does it work? Let's try to answer on these questions in this paragraph. Actually `sequential locks` were introduced in the Linux kernel 2.6.x. Main point of this synchronization primitive is to provide fast and lock-free access to shared resources. Since the heart of `sequential lock` synchronization primitive is [spinlock](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-1.html) synchronization primitive, `sequential locks` work in situations where the protected resources are small and simple. Additionally write access must be rare and also should be fast. 

Work of this synchronization primitive is based on the sequence of events counter. Actually a `sequential lock` allows free access to a resource for readers, but each reader must check existence of conflicts with a writer. This synchronization primitive introduces a special counter. The main algorithm of work of `sequential locks` is simple: Each writer which acquired a sequential lock increments this counter and additionally acquires a [spinlock](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-1.html). When this writer finishes, it will release the acquired spinlock to give access to other writers and increment the counter of a sequential lock again.

Read only access works on the following principle, it gets the value of a `sequential lock` counter before it will enter into [critical section](https://en.wikipedia.org/wiki/Critical_section) and compares it with the value of the same `sequential lock` counter at the exit of critical section. If their values are equal, this means that there weren't writers for this period. If their values are not equal, this means that a writer has incremented the counter during the [critical section](https://en.wikipedia.org/wiki/Critical_section). This conflict means that reading of protected data must be repeated.

That's all. As we may see principle of work of `sequential locks` is simple.

```C
unsigned int seq_counter_value;

do {
    seq_counter_value = get_seq_counter_val(&the_lock);
    //
    // do as we want here
    //
} while (__retry__);
```

Actually the Linux kernel does not provide `get_seq_counter_val()` function. Here it is just a stub. Like a `__retry__` too. As I already wrote above, we will see actual the [API](https://en.wikipedia.org/wiki/Application_programming_interface) for this in the next paragraph of this part.

Ok, now we know what a `seqlock` synchronization primitive is and how it is represented in the Linux kernel. In this case, we may go ahead and start to look at the [API](https://en.wikipedia.org/wiki/Application_programming_interface) which the Linux kernel provides for manipulation of synchronization primitives of this type.

Sequential lock API
--------------------------------------------------------------------------------

So, now we know a little about `sequentional lock` synchronization primitive from theoretical side, let's look at its implementation in the Linux kernel. All `sequentional locks` [API](https://en.wikipedia.org/wiki/Application_programming_interface) are located in the [include/linux/seqlock.h](https://github.com/torvalds/linux/blob/master/include/linux/seqlock.h) header file.

First of all we may see that the a `sequential lock` machanism is represented by the following type:

```C
typedef struct {
	struct seqcount seqcount;
	spinlock_t lock;
} seqlock_t;
```

As we may see the `seqlock_t` provides two fields. These fields represent a sequential lock counter, description of which we saw above and also a [spinlock](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-1.html) which will protect data from other writers. Note that the `seqcount` counter represented as `seqcount` type. The `seqcount` is structure:

```C
typedef struct seqcount {
	unsigned sequence;
#ifdef CONFIG_DEBUG_LOCK_ALLOC
	struct lockdep_map dep_map;
#endif
} seqcount_t;
```

which holds counter of a sequential lock and [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) related field.

As always in previous parts of this [chapter](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/), before we will consider an [API](https://en.wikipedia.org/wiki/Application_programming_interface) of `sequential lock` mechanism in the Linux kernel, we need to know how to initialize an instance of `seqlock_t`.

We saw in the previous parts that often the Linux kernel provides two approaches to execute initialization of the given synchronization primitive. The same situation with the `seqlock_t` structure. These approaches allows to initialize a `seqlock_t` in two following:

* `statically`;
* `dynamically`.

ways. Let's look at the first approach. We are able to intialize a `seqlock_t` statically with the `DEFINE_SEQLOCK` macro:

```C
#define DEFINE_SEQLOCK(x) \
		seqlock_t x = __SEQLOCK_UNLOCKED(x)
```

which is defined in the [include/linux/seqlock.h](https://github.com/torvalds/linux/blob/master/include/linux/seqlock.h) header file. As we may see, the `DEFINE_SEQLOCK` macro takes one argument and expands to the definition and initialization of the `seqlock_t` structure. Initialization occurs with the help of the `__SEQLOCK_UNLOCKED` macro which is defined in the same source code file. Let's look at the implementation of this macro:

```C
#define __SEQLOCK_UNLOCKED(lockname)			\
	{						\
		.seqcount = SEQCNT_ZERO(lockname),	\
		.lock =	__SPIN_LOCK_UNLOCKED(lockname)	\
	}
```

As we may see the, `__SEQLOCK_UNLOCKED` macro executes initialization of fields of the given `seqlock_t` structure. The first field is `seqcount` initialized with the `SEQCNT_ZERO` macro which expands to the:

```C
#define SEQCNT_ZERO(lockname) { .sequence = 0, SEQCOUNT_DEP_MAP_INIT(lockname)}
```

So we just initialize counter of the given sequential lock to zero and additionally we can see [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) related initialization which depends on the state of the `CONFIG_DEBUG_LOCK_ALLOC` kernel configuration option:

```C
#ifdef CONFIG_DEBUG_LOCK_ALLOC
# define SEQCOUNT_DEP_MAP_INIT(lockname) \
    .dep_map = { .name = #lockname } \
    ...
    ...
    ...
#else
# define SEQCOUNT_DEP_MAP_INIT(lockname)
    ...
    ...
    ...
#endif
```

As I already wrote in previous parts of this [chapter](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/) we will not consider [debugging](https://en.wikipedia.org/wiki/Debugging) and [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt) related stuff in this part. So for now we just skip the `SEQCOUNT_DEP_MAP_INIT` macro. The second field of the given `seqlock_t` is `lock` initialized with the `__SPIN_LOCK_UNLOCKED` macro which is defined in the [include/linux/spinlock_types.h](https://github.com/torvalds/linux/blob/master/include/linux/spinlock_types.h) header file. We will not consider implementation of this macro here as it just initialize [rawspinlock](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-1.html) with architecture-specific methods (More abot spinlocks you may read in first parts of this [chapter](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/)).

We have considered the first way to initialize a sequential lock. Let's consider second way to do the same, but do it dynamically. We can initialize a sequentional lock with the `seqlock_init` macro which is defined in the same  [include/linux/seqlock.h](https://github.com/torvalds/linux/blob/master/include/linux/seqlock.h) header file.

Let's look at the implementation of this macro:

```C
#define seqlock_init(x)					\
	do {						\
		seqcount_init(&(x)->seqcount);		\
		spin_lock_init(&(x)->lock);		\
	} while (0)
```

As we may see, the `seqlock_init` expands into two macros. The first macro `seqcount_init` takes counter of the given sequential lock and expands to the call of the `__seqcount_init` function:

```C
# define seqcount_init(s)				\
	do {						\
		static struct lock_class_key __key;	\
		__seqcount_init((s), #s, &__key);	\
	} while (0)
```

from the same header file. This function

```C
static inline void __seqcount_init(seqcount_t *s, const char *name,
					  struct lock_class_key *key)
{
    lockdep_init_map(&s->dep_map, name, key, 0);
    s->sequence = 0;
}
```

just initializes counter of the given `seqcount_t` with zero. The second call from the `seqlock_init` macro is the call of the `spin_lock_init` macro which we saw in the [first part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-1.html) of this chapter.

So, now we know how to initialize a `sequential lock`, now let's look at how to use it. The Linux kernel provides following [API](https://en.wikipedia.org/wiki/Application_programming_interface) to manipulate `sequential locks`:

```C
static inline unsigned read_seqbegin(const seqlock_t *sl);
static inline unsigned read_seqretry(const seqlock_t *sl, unsigned start);
static inline void write_seqlock(seqlock_t *sl);
static inline void write_sequnlock(seqlock_t *sl);
static inline void write_seqlock_irq(seqlock_t *sl);
static inline void write_sequnlock_irq(seqlock_t *sl);
static inline void read_seqlock_excl(seqlock_t *sl)
static inline void read_sequnlock_excl(seqlock_t *sl)
```

and others. Before we move on to considering the implementation of this [API](https://en.wikipedia.org/wiki/Application_programming_interface), we must know that actually there are two types of readers. The first type of reader never blocks a writer process. In this case writer will not wait for readers. The second type of reader which can lock. In this case, the locking reader will block the writer as it will wait while reader will not release its lock.

First of all let's consider the first type of readers. The `read_seqbegin` function begins a seq-read [critical section](https://en.wikipedia.org/wiki/Critical_section).

As we may see this function just returns value of the `read_seqcount_begin` function:

```C
static inline unsigned read_seqbegin(const seqlock_t *sl)
{
	return read_seqcount_begin(&sl->seqcount);
}
```

In its turn the `read_seqcount_begin` function calls the `raw_read_seqcount_begin` function:

```C
static inline unsigned read_seqcount_begin(const seqcount_t *s)
{
	return raw_read_seqcount_begin(s);
}
```

which just returns value of the `sequential lock` counter:

```C
static inline unsigned raw_read_seqcount(const seqcount_t *s)
{
	unsigned ret = READ_ONCE(s->sequence);
	smp_rmb();
	return ret;
}
```

After we have the initial value of the given `sequential lock` counter and did some stuff, we know from the previous paragraph of this function, that we need to compare it with the current value of the counter the same `sequential lock` before we will exit from the critical section. We can achieve this by the call of the `read_seqretry` function. This function takes a `sequential lock`, start value of the counter and through a chain of functions:

```C
static inline unsigned read_seqretry(const seqlock_t *sl, unsigned start)
{
	return read_seqcount_retry(&sl->seqcount, start);
}

static inline int read_seqcount_retry(const seqcount_t *s, unsigned start)
{
	smp_rmb();
	return __read_seqcount_retry(s, start);
}
```

it calls the `__read_seqcount_retry` function:

```C
static inline int __read_seqcount_retry(const seqcount_t *s, unsigned start)
{
	return unlikely(s->sequence != start);
}
```

which just compares value of the counter of the given `sequential lock` with the initial value of this counter. If the initial value of the counter which is obtained from `read_seqbegin()` function is odd, this means that a writer was in the middle of updating the data when our reader began to act. In this case the value of the data can be in inconsistent state, so we need to try to read it again.

This is a common pattern in the Linux kernel. For example, you may remember the `jiffies` concept from the [first part](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-1.html) of the [timers and time management in the Linux kernel](https://0xax.gitbooks.io/linux-insides/content/Timers/) chapter. The sequential lock is used to obtain value of `jiffies` at [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture:

```C
u64 get_jiffies_64(void)
{
	unsigned long seq;
	u64 ret;

	do {
		seq = read_seqbegin(&jiffies_lock);
		ret = jiffies_64;
	} while (read_seqretry(&jiffies_lock, seq));
	return ret;
}
```

Here we just read the value of the counter of the `jiffies_lock` sequential lock and then we write value of the `jiffies_64` system variable to the `ret`. As here we may see `do/while` loop, the body of the loop will be executed at least one time. So, as the body of loop was executed, we read and compare the current value of the counter of the `jiffies_lock` with the initial value. If these values are not equal, execution of the loop will be repeated, else `get_jiffies_64` will return its value in `ret`.

We just saw the first type of readers which do not block writer and other readers. Let's consider second type. It does not update value of a `sequential lock` counter, but just locks `spinlock`:

```C
static inline void read_seqlock_excl(seqlock_t *sl)
{
	spin_lock(&sl->lock);
}
```

So, no one reader or writer can't access protected data. When a reader finishes, the lock must be unlocked with the:

```C
static inline void read_sequnlock_excl(seqlock_t *sl)
{
	spin_unlock(&sl->lock);
}
```

function.

Now we know how `sequential lock` work for readers. Let's consider how does writer act when it wants to acquire a `sequential lock` to modify data. To acquire a `sequential lock`, writer should use `write_seqlock` function. If we look at the implementation of this function:

```C
static inline void write_seqlock(seqlock_t *sl)
{
	spin_lock(&sl->lock);
	write_seqcount_begin(&sl->seqcount);
}
```

We will see that it acquires `spinlock` to prevent access from other writers and calls the `write_seqcount_begin` function. This function just increments value of the `sequential lock` counter:

```C
static inline void raw_write_seqcount_begin(seqcount_t *s)
{
	s->sequence++;
	smp_wmb();
}
```

When a writer process will finish to modify data, the `write_sequnlock` function must be called to release a lock and give access to other writers or readers. Let's consider at the implementation of the `write_sequnlock` function. It looks pretty simple:

```C
static inline void write_sequnlock(seqlock_t *sl)
{
	write_seqcount_end(&sl->seqcount);
	spin_unlock(&sl->lock);
}
```

First of all it just calls `write_seqcount_end` function to increase value of the counter of the `sequential` lock again:

```C
static inline void raw_write_seqcount_end(seqcount_t *s)
{
	smp_wmb();
	s->sequence++;
}
```

and in the end we just call the `spin_unlock` macro to give access for other readers or writers.

That's all about `sequential lock` mechanism in the Linux kernel. Of course we did not consider full [API](https://en.wikipedia.org/wiki/Application_programming_interface) of this mechanism in this part. But all other functions are based on these which we described here. For example, Linux kernel also provides some safe macros/functions to use `sequential lock` mechanism in [interrupt handlers](https://en.wikipedia.org/wiki/Interrupt_handler) of [softirq](https://0xax.gitbooks.io/linux-insides/content/interrupts/interrupts-9.html): `write_seqclock_irq` and `write_sequnlock_irq`:

```C
static inline void write_seqlock_irq(seqlock_t *sl)
{
	spin_lock_irq(&sl->lock);
	write_seqcount_begin(&sl->seqcount);
}

static inline void write_sequnlock_irq(seqlock_t *sl)
{
	write_seqcount_end(&sl->seqcount);
	spin_unlock_irq(&sl->lock);
}
```

As we may see, these functions differ only in the initialization of spinlock. They call `spin_lock_irq` and `spin_unlock_irq` instead of `spin_lock` and `spin_unlock`.

Or for example `write_seqlock_irqsave` and `write_sequnlock_irqrestore` functions which are the same but used `spin_lock_irqsave` and `spin_unlock_irqsave` macro to use in [IRQ](https://en.wikipedia.org/wiki/Interrupt_request_(PC_architecture)) handlers.

That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the sixth part of the [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_%28computer_science%29) chapter in the Linux kernel. In this part we met with new synchronization primitive which is called - `sequential lock`. From the theoretical side, this synchronization primitive very similar on a [readers-writer lock](https://en.wikipedia.org/wiki/Readers%E2%80%93writer_lock) synchronization primitive, but allows to avoid `writer-starving` issue.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [synchronization primitives](https://en.wikipedia.org/wiki/Synchronization_(computer_science))
* [readers-writer lock](https://en.wikipedia.org/wiki/Readers%E2%80%93writer_lock) 
* [spinlock](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-1.html)
* [critical section](https://en.wikipedia.org/wiki/Critical_section)
* [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt)
* [debugging](https://en.wikipedia.org/wiki/Debugging)
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [Timers and time management in the Linux kernel](https://0xax.gitbooks.io/linux-insides/content/Timers/)
* [interrupt handlers](https://en.wikipedia.org/wiki/Interrupt_handler)
* [softirq](https://0xax.gitbooks.io/linux-insides/content/interrupts/interrupts-9.html)
* [IRQ](https://en.wikipedia.org/wiki/Interrupt_request_(PC_architecture))
* [Previous part](https://0xax.gitbooks.io/linux-insides/content/SyncPrim/sync-5.html)
