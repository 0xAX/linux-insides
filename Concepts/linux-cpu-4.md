Notification Chains in Linux Kernel
================================================================================

Introduction
--------------------------------------------------------------------------------

The Linux kernel is huge piece of [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) code which consists from many different subsystems. Each subsystem has its own purpose which is independent of other subsystems. But often one subsystem wants to know something from other subsystem(s). There is special mechanism in the Linux kernel which allows to solve this problem partly. The name of this mechanism is - `notification chains` and its main purpose to provide a way for different subsystems to subscribe on asynchronous events from other subsystems. Note that this mechanism is only for communication inside kernel, but there are other mechanisms for communication between kernel and userspace.

Before we will consider `notification chains` [API](https://en.wikipedia.org/wiki/Application_programming_interface) and implementation of this API, let's look at `Notification chains` mechanism from theoretical side as we did it in other parts of this book. Everything which is related to `notification chains` mechanism is located in the [include/linux/notifier.h](https://github.com/torvalds/linux/blob/master/include/linux/notifier.h) header file and [kernel/notifier.c](https://github.com/torvalds/linux/blob/master/kernel/notifier.c) source code file. So let's open them and start to dive.

Notification Chains related data structures
--------------------------------------------------------------------------------

Let's start to consider `notification chains` mechanism from related data structures. As I wrote above, main data structures should be located in the [include/linux/notifier.h](https://github.com/torvalds/linux/blob/master/include/linux/notifier.h) header file, so the Linux kernel provides generic API which does not depend on certain architecture. In general, the `notification chains` mechanism represents a list (that's why it named `chains`) of [callback](https://en.wikipedia.org/wiki/Callback_%28computer_programming%29) functions which are will be executed when an event will be occurred.

All of these callback functions are represented as `notifier_fn_t` type in the Linux kernel:

```C
typedef	int (*notifier_fn_t)(struct notifier_block *nb, unsigned long action, void *data);
```

So we may see that it takes three following arguments:

* `nb` - is linked list of function pointers (will see it now);
* `action` - is type of an event. A notification chain may support multiple events, so we need this parameter to distinguish an event from other events;
* `data` - is storage for private information. Actually it allows to provide additional data information about an event.

Additionally we may see that `notifier_fn_t` returns an integer value. This integer value maybe one of:

* `NOTIFY_DONE` - subscriber does not interested in notification;
* `NOTIFY_OK` - notification was processed correctly;
* `NOTIFY_BAD` - something went wrong;
* `NOTIFY_STOP` - notification is done, but no further callbacks should be called for this event.

All of these results defined as macros in the [include/linux/notifier.h](https://github.com/torvalds/linux/blob/master/include/linux/notifier.h) header file:

```C
#define NOTIFY_DONE		0x0000
#define NOTIFY_OK		0x0001
#define NOTIFY_BAD		(NOTIFY_STOP_MASK|0x0002)
#define NOTIFY_STOP		(NOTIFY_OK|NOTIFY_STOP_MASK)
```

Where `NOTIFY_STOP_MASK` represented by the:

```C
#define NOTIFY_STOP_MASK	0x8000
```

macro and means that callbacks will not be called during next notifications.

Each part of the Linux kernel which wants to be notified on a certain event will should provide own `notifier_fn_t` callback function. Main role of the `notification chains` mechanism is to call certain callbacks when an asynchronous event occurred.

The main building block of the `notification chains` mechanism is the `notifier_block` structure:

```C
struct notifier_block {
	notifier_fn_t notifier_call;
	struct notifier_block __rcu *next;
	int priority;
};
```

which is defined in the [include/linux/notifier.h](https://github.com/torvalds/linux/blob/master/include/linux/notifier.h) file. This struct contains pointer to callback function - `notifier_call`, link to the next notification callback and `priority` of a callback function as functions with higher priority are executed first.

The Linux kernel provides notification chains of four following types:

* Blocking notifier chains;
* SRCU notifier chains;
* Atomic notifier chains;
* Raw notifier chains.

Let's consider all of these types of notification chains by order:

In the first case for the `blocking notifier chains`, callbacks will be called/executed in process context. This means that the calls in a notification chain may be blocked.

The second `SRCU notifier chains` represent alternative form of `blocking notifier chains`. In the first case, blocking notifier chains uses `rw_semaphore` synchronization primitive to protect chain links. `SRCU` notifier chains run in process context too, but uses special form of [RCU](https://en.wikipedia.org/wiki/Read-copy-update) mechanism which is permissible to block in an read-side critical section.

In the third case for the `atomic notifier chains` runs in interrupt or atomic context and protected by [spinlock](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-1) synchronization primitive. The last `raw notifier chains` provides special type of notifier chains without any locking restrictions on callbacks. This means that protection rests on the shoulders of caller side. It is very useful when we want to protect our chain with very specific locking mechanism.

If we will look at the implementation of the `notifier_block` structure, we will see that it contains pointer to the `next` element from a notification chain list, but we have no head. Actually a head of such list is in separate structure depends on type of a notification chain. For example for the `blocking notifier chains`:

```C
struct blocking_notifier_head {
	struct rw_semaphore rwsem;
	struct notifier_block __rcu *head;
};
```

or for `atomic notification chains`:

```C
struct atomic_notifier_head {
	spinlock_t lock;
	struct notifier_block __rcu *head;
};
```

Now as we know a little about `notification chains` mechanism let's consider implementation of its API.

Notification Chains
--------------------------------------------------------------------------------

Usually there are two sides in a publish/subscriber mechanisms. One side who wants to get notifications and other side(s) who generates these notifications. We will consider notification chains mechanism from both sides. We will consider `blocking notification chains` in this part, because of other types of notification chains are similar to it and differs mostly in protection mechanisms.

Before a notification producer is able to produce notification, first of all it should initialize head of a notification chain. For example let's consider notification chains related to kernel [loadable modules](https://en.wikipedia.org/wiki/Loadable_kernel_module). If we will look in the [kernel/module.c](https://github.com/torvalds/linux/blob/master/kernel/module.c) source code file, we will see following definition:

```C
static BLOCKING_NOTIFIER_HEAD(module_notify_list);
```

which defines head for loadable modules blocking notifier chain. The `BLOCKING_NOTIFIER_HEAD` macro is defined in the [include/linux/notifier.h](https://github.com/torvalds/linux/blob/master/include/linux/notifier.h) header file and expands to the following code:

```C
#define BLOCKING_INIT_NOTIFIER_HEAD(name) do {	\
		init_rwsem(&(name)->rwsem);	                            \
		(name)->head = NULL;		                            \
	} while (0)
```

So we may see that it takes name of a name of a head of a blocking notifier chain and initializes read/write [semaphore](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-3) and set head to `NULL`. Besides the `BLOCKING_INIT_NOTIFIER_HEAD` macro, the Linux kernel additionally provides `ATOMIC_INIT_NOTIFIER_HEAD`, `RAW_INIT_NOTIFIER_HEAD` macros and `srcu_init_notifier` function for initialization atomic and other types of notification chains.

After initialization of a head of a notification chain, a subsystem which wants to receive notification from the given notification chain it should register with certain function which is depends on type of notification. If you will look in the [include/linux/notifier.h](https://github.com/torvalds/linux/blob/master/include/linux/notifier.h) header file, you will see following four function for this:

```C
extern int atomic_notifier_chain_register(struct atomic_notifier_head *nh,
		struct notifier_block *nb);

extern int blocking_notifier_chain_register(struct blocking_notifier_head *nh,
		struct notifier_block *nb);

extern int raw_notifier_chain_register(struct raw_notifier_head *nh,
		struct notifier_block *nb);

extern int srcu_notifier_chain_register(struct srcu_notifier_head *nh,
		struct notifier_block *nb);
```

As I already wrote above, we will cover only blocking notification chains in the part, so let's consider implementation of the `blocking_notifier_chain_register` function. Implementation of this function is located in the [kernel/notifier.c](https://github.com/torvalds/linux/blob/master/kernel/notifier.c) source code file and as we may see the `blocking_notifier_chain_register` takes two parameters:

* `nh` - head of a notification chain;
* `nb` - notification descriptor.

Now let's look at the implementation of the `blocking_notifier_chain_register` function:

```C
int raw_notifier_chain_register(struct raw_notifier_head *nh,
		struct notifier_block *n)
{
	return notifier_chain_register(&nh->head, n);
}
```

As we may see it just returns result of the `notifier_chain_register` function from the same source code file and as we may understand this function does all job for us. Definition of the `notifier_chain_register` function looks:

```C
int blocking_notifier_chain_register(struct blocking_notifier_head *nh,
		struct notifier_block *n)
{
	int ret;

	if (unlikely(system_state == SYSTEM_BOOTING))
		return notifier_chain_register(&nh->head, n);

	down_write(&nh->rwsem);
	ret = notifier_chain_register(&nh->head, n);
	up_write(&nh->rwsem);
	return ret;
}
```

As we may see implementation of the `blocking_notifier_chain_register` is pretty simple. First of all there is check which check current system state and if a system in rebooting state we just call the `notifier_chain_register`. In other way we do the same call of the `notifier_chain_register` but as you may see this call is protected with read/write semaphores. Now let's look at the implementation of the `notifier_chain_register` function:

```C
static int notifier_chain_register(struct notifier_block **nl,
		struct notifier_block *n)
{
	while ((*nl) != NULL) {
		if (n->priority > (*nl)->priority)
			break;
		nl = &((*nl)->next);
	}
	n->next = *nl;
	rcu_assign_pointer(*nl, n);
	return 0;
}
```

This function just inserts new `notifier_block` (given by a subsystem which wants to get notifications) to the notification chain list. Besides subscribing on an event, subscriber may unsubscribe from a certain events with the set of `unsubscribe` functions:

```C
extern int atomic_notifier_chain_unregister(struct atomic_notifier_head *nh,
		struct notifier_block *nb);

extern int blocking_notifier_chain_unregister(struct blocking_notifier_head *nh,
		struct notifier_block *nb);

extern int raw_notifier_chain_unregister(struct raw_notifier_head *nh,
		struct notifier_block *nb);

extern int srcu_notifier_chain_unregister(struct srcu_notifier_head *nh,
		struct notifier_block *nb);
```

When a producer of notifications wants to notify subscribers about an event, the `*.notifier_call_chain` function will be called. As you already may guess each type of notification chains provides own function to produce notification:

```C
extern int atomic_notifier_call_chain(struct atomic_notifier_head *nh,
		unsigned long val, void *v);

extern int blocking_notifier_call_chain(struct blocking_notifier_head *nh,
		unsigned long val, void *v);

extern int raw_notifier_call_chain(struct raw_notifier_head *nh,
		unsigned long val, void *v);

extern int srcu_notifier_call_chain(struct srcu_notifier_head *nh,
		unsigned long val, void *v);
```

Let's consider implementation of the `blocking_notifier_call_chain` function. This function is defined in the [kernel/notifier.c](https://github.com/torvalds/linux/blob/master/kernel/notifier.c) source code file:

```C
int blocking_notifier_call_chain(struct blocking_notifier_head *nh,
		unsigned long val, void *v)
{
	return __blocking_notifier_call_chain(nh, val, v, -1, NULL);
}
```

and as we may see it just returns result of the `__blocking_notifier_call_chain` function. As we may see, the `blocking_notifer_call_chain` takes three parameters:

* `nh` - head of notification chain list;
* `val` - type of a notification;
* `v` -  input parameter which may be used by handlers.

But the `__blocking_notifier_call_chain` function takes five parameters:

```C
int __blocking_notifier_call_chain(struct blocking_notifier_head *nh,
				   unsigned long val, void *v,
				   int nr_to_call, int *nr_calls)
{
    ...
    ...
    ...
}
```

Where `nr_to_call` and `nr_calls` are number of notifier functions to be called and number of sent notifications. As you may guess the main goal of the `__blocking_notifer_call_chain` function and other functions for other notification types is to call callback function when an event occurred. Implementation of the `__blocking_notifier_call_chain` is pretty simple, it just calls the `notifier_call_chain` function from the same source code file protected with read/write semaphore:

```C
int __blocking_notifier_call_chain(struct blocking_notifier_head *nh,
				   unsigned long val, void *v,
				   int nr_to_call, int *nr_calls)
{
	int ret = NOTIFY_DONE;

	if (rcu_access_pointer(nh->head)) {
		down_read(&nh->rwsem);
		ret = notifier_call_chain(&nh->head, val, v, nr_to_call,
					nr_calls);
		up_read(&nh->rwsem);
	}
	return ret;
}
```

and returns its result. In this case all job is done by the `notifier_call_chain` function. Main purpose of this function informs registered notifiers about an asynchronous event:

```C
static int notifier_call_chain(struct notifier_block **nl,
			       unsigned long val, void *v,
			       int nr_to_call, int *nr_calls)
{
    ...
    ...
    ...
    ret = nb->notifier_call(nb, val, v);
    ...
    ...
    ...
    return ret;
}
```

That's all. In general all looks pretty simple.

Now let's consider on a simple example related to [loadable modules](https://en.wikipedia.org/wiki/Loadable_kernel_module). If we will look in the [kernel/module.c](https://github.com/torvalds/linux/blob/master/kernel/module.c). As we already saw in this part, there is:

```C
static BLOCKING_NOTIFIER_HEAD(module_notify_list);
```

definition of the `module_notify_list` in the [kernel/module.c](https://github.com/torvalds/linux/blob/master/kernel/module.c) source code file. This definition determines head of list of blocking notifier chains related to kernel modules. There are at least three following events:

* MODULE_STATE_LIVE
* MODULE_STATE_COMING
* MODULE_STATE_GOING

in which maybe interested some subsystems of the Linux kernel. For example tracing of kernel modules states. Instead of direct call of the `atomic_notifier_chain_register`, `blocking_notifier_chain_register` and etc., most notification chains come with a set of wrappers used to register to them. Registatrion on these modules events is going with the help of such wrapper:

```C
int register_module_notifier(struct notifier_block *nb)
{
	return blocking_notifier_chain_register(&module_notify_list, nb);
}
```

If we will look in the [kernel/tracepoint.c](https://github.com/torvalds/linux/blob/master/kernel/tracepoint.c) source code file, we will see such registration during initialization of [tracepoints](https://www.kernel.org/doc/Documentation/trace/tracepoints.txt):

```C
static __init int init_tracepoints(void)
{
	int ret;

	ret = register_module_notifier(&tracepoint_module_nb);
	if (ret)
		pr_warn("Failed to register tracepoint module enter notifier\n");

	return ret;
}
```

Where `tracepoint_module_nb` provides callback function:

```C
static struct notifier_block tracepoint_module_nb = {
	.notifier_call = tracepoint_module_notify,
	.priority = 0,
};
```

When one of the `MODULE_STATE_LIVE`, `MODULE_STATE_COMING` or `MODULE_STATE_GOING` events occurred. For example the `MODULE_STATE_LIVE` the `MODULE_STATE_COMING` notifications will be sent during execution of the [init_module](http://man7.org/linux/man-pages/man2/init_module.2.html) [system call](https://0xax.gitbook.io/linux-insides/summary/syscall/linux-syscall-1). Or for example `MODULE_STATE_GOING` will be sent during execution of the [delete_module](http://man7.org/linux/man-pages/man2/delete_module.2.html) `system call`:

```C
SYSCALL_DEFINE2(delete_module, const char __user *, name_user,
		unsigned int, flags)
{
    ...
    ...
    ...
    blocking_notifier_call_chain(&module_notify_list,
				     MODULE_STATE_GOING, mod);
    ...
    ...
    ...
}
```

Thus when one of these system call will be called from userspace, the Linux kernel will send certain notification depends on a system call and the `tracepoint_module_notify` callback function will be called.

That's all.

Links
--------------------------------------------------------------------------------

* [C programming language](https://en.wikipedia.org/wiki/C_%28programming_language%29)
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [callback](https://en.wikipedia.org/wiki/Callback_%28computer_programming%29)
* [RCU](https://en.wikipedia.org/wiki/Read-copy-update)
* [spinlock](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-1)
* [loadable modules](https://en.wikipedia.org/wiki/Loadable_kernel_module)
* [semaphore](https://0xax.gitbook.io/linux-insides/summary/syncprim/linux-sync-3)
* [tracepoints](https://www.kernel.org/doc/Documentation/trace/tracepoints.txt)
* [system call](https://0xax.gitbook.io/linux-insides/summary/syscall/linux-syscall-1)
* [init_module system call](http://man7.org/linux/man-pages/man2/init_module.2.html)
* [delete_module](http://man7.org/linux/man-pages/man2/delete_module.2.html)
* [previous part](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-3)
