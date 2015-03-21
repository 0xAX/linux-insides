Data Structures in the Linux Kernel
================================================================================

Doubly linked list
--------------------------------------------------------------------------------

Linux kernel provides it's own doubly linked list implementation which you can find in the [include/linux/list.h](https://github.com/torvalds/linux/blob/master/include/linux/list.h). We will start `Data Structures in the Linux kernel` from the doubly linked list data structure. Why? Because it is very popular in the kernel, just try to [search](http://lxr.free-electrons.com/ident?i=list_head)

First of all let's look on the main structure:

```C
struct list_head {
	struct list_head *next, *prev;
};
```

You can note that it is different from many lists implementations which you could see. For example this doubly linked list structure from the [glib](http://www.gnu.org/software/libc/):

```C
struct GList {
  gpointer data;
  GList *next;
  GList *prev;
};
```

Usually linked list structure contains pointer to the item. Linux kernel implementation of the list has not. So the main question is here - `where list stores data?`. Actually implementation of lists in the kernel is - `Intrusive list`. An intrusive linked list does not contain data in it's nodes and nodes just contain pointers to the to the next and previous node and list nodes part of the data that are added to the list. This makes data structure generic, so it does not care about entry data type anymore.

For example:

```C
struct nmi_desc {
    spinlock_t lock;
    struct list_head head;
};
```

Let's look on some examples, how `list_head` uses in the kernel. As i already wrote about, there are many, really many different places where lists are used in the kernel. Let's look for example in miscellaneous character drivers. Misc character drivers API from the [drivers/char/misc.c](https://github.com/torvalds/linux/blob/master/drivers/char/misc.c) for writing small drivers for handling simple hardware or virtual devices. This drivers share major number:

```C
#define MISC_MAJOR              10
```

but has own minor number. For example you can see it with:

```
ls -l /dev |  grep 10
crw-------   1 root root     10, 235 Mar 21 12:01 autofs
drwxr-xr-x  10 root root         200 Mar 21 12:01 cpu
crw-------   1 root root     10,  62 Mar 21 12:01 cpu_dma_latency
crw-------   1 root root     10, 203 Mar 21 12:01 cuse
drwxr-xr-x   2 root root         100 Mar 21 12:01 dri
crw-rw-rw-   1 root root     10, 229 Mar 21 12:01 fuse
crw-------   1 root root     10, 228 Mar 21 12:01 hpet
crw-------   1 root root     10, 183 Mar 21 12:01 hwrng
crw-rw----+  1 root kvm      10, 232 Mar 21 12:01 kvm
crw-rw----   1 root disk     10, 237 Mar 21 12:01 loop-control
crw-------   1 root root     10, 227 Mar 21 12:01 mcelog
crw-------   1 root root     10,  59 Mar 21 12:01 memory_bandwidth
crw-------   1 root root     10,  61 Mar 21 12:01 network_latency
crw-------   1 root root     10,  60 Mar 21 12:01 network_throughput
crw-r-----   1 root kmem     10, 144 Mar 21 12:01 nvram
brw-rw----   1 root disk      1,  10 Mar 21 12:01 ram10
crw--w----   1 root tty       4,  10 Mar 21 12:01 tty10
crw-rw----   1 root dialout   4,  74 Mar 21 12:01 ttyS10
crw-------   1 root root     10,  63 Mar 21 12:01 vga_arbiter
crw-------   1 root root     10, 137 Mar 21 12:01 vhci
```

Now let's look how lists are used in the misc device drivers. First of all let's look on `miscdevice` structure:

```C
struct miscdevice
{
      int minor;
      const char *name;
      const struct file_operations *fops;
      struct list_head list;
      struct device *parent;
      struct device *this_device;
      const char *nodename;
      mode_t mode;
};
```

We can see the fourth field in the `miscdevice` structure - `list` which is list of registered devices. In the beginning of the source code file we can see definition of the:

```C
static LIST_HEAD(misc_list);
```

which expands to definition of the variables with `list_head` type:

```C
#define LIST_HEAD(name) \
	struct list_head name = LIST_HEAD_INIT(name)
```

and initializes it with the `LIST_HEAD_INIT` macro which set previous and next entries:

```C
#define LIST_HEAD_INIT(name) { &(name), &(name) }
```

Now let's look on the `misc_register` function which registers a miscellaneous device. At the start it initializes `miscdevice->list` with the `INIT_LIST_HEAD` function:

```C
INIT_LIST_HEAD(&misc->list);
```

which does the same that `LIST_HEAD_INIT` macro:

```C
static inline void INIT_LIST_HEAD(struct list_head *list)
{
	list->next = list;
	list->prev = list;
}
```

In the next step after device created with the `device_create` function we add it to the miscellaneous devices list with:

```
list_add(&misc->list, &misc_list);
```

Kernel `list.h` provides this API for the addition of new entry to the list. Let's look on it's implementation:

```C
static inline void list_add(struct list_head *new, struct list_head *head)
{
	__list_add(new, head, head->next);
}
```

It just calls internal function `__list_add` with the 3 given paramters:

* new  - new entry;
* head - list head after which will be inserted new item;
* head->next - next item after list head.

Implementation of the `__list_add` is pretty simple:

```C
static inline void __list_add(struct list_head *new,
			      struct list_head *prev,
			      struct list_head *next)
{
	next->prev = new;
	new->next = next;
	new->prev = prev;
	prev->next = new;
}
```

Here we set new item between `prev` and `next`. So `misc` list which we defined at the start with the `LIST_HEAD_INIT` macro will contain previous and next pointers to the `miscdevice->list`.

There is still only one question how to get list's entry. There is special special macro for this point:

```C
#define list_entry(ptr, type, member) \
	container_of(ptr, type, member)
```

which gets three parameters:

* ptr - the structure list_head pointer;
* type - structure type;
* member - the name of the list_head within the struct; 

For example:

```C
const struct miscdevice *p = list_entry(v, struct miscdevice, list)
```

After this we can access to the any `miscdevice` field with `p->minor` or `p->name` and etc...

Of course `list_add` and `list_entry` is not only functions which provides `<linux/list.h>`. Implementation of the doubly linked list provides the following API:

* list_add
* list_add_tail
* list_del
* list_replace
* list_move
* list_is_last
* list_empty
* list_cut_position
* list_splice

and many more.
