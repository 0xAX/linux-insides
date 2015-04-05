Linux kernel memory management Part 1.
================================================================================

Introduction
--------------------------------------------------------------------------------

Memory management is a one of the most complex (and I think that it is the most complex) parts of the operating system kernel. In the [last preparations before the kernel entry point](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-3.html) part we stopped right before call of the `start_kernel` function. This function initializes all the kernel features (including architecture-dependent features) before the kernel runs the first `init` process. You may remember as we built early page tables, identity page tables and fixmap page tables in the boot time. No compilcated memory management is working yet. When the `start_kernel` function is called we will see the transition to more complex data structures and techniques for memory management. For a good understanding of the initialization process in the linux kernel we need to have clear understanding of the techniques. This chapter will provide an overview of the different parts of the linux kernel memory management framework and its API, starting from the `memblock`.

Memblock
--------------------------------------------------------------------------------

Memblock is one of methods of managing memory regions during the early bootstrap period while the usual kernel memory allocators are not up and
running yet. Previously it was called - `Logical Memory Block`, but from the [patch](https://lkml.org/lkml/2010/7/13/68) by Yinghai Lu, it was renamed to the `memblock`. As Linux kernel for `x86_64` architecture uses this method. We already met `memblock` in the [Last preparations before the kernel entry point](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-3.html) part. And now time to get acquainted with it closer. We will see how it is implemented.

We will start to learn `memblock` from the data structures. Definitions of the all data structures can be found in the [include/linux/memblock.h](https://github.com/torvalds/linux/blob/master/include/linux/memblock.h) header file.

The first structure has the same name as this part and it is:

```C
struct memblock {
         bool bottom_up;
         phys_addr_t current_limit;
         struct memblock_type memory;   --> array of memblock_region
         struct memblock_type reserved; --> array of memblock_region
#ifdef CONFIG_HAVE_MEMBLOCK_PHYS_MAP
         struct memblock_type physmem;
#endif
};
```

This structure contains five fields. First is `bottom_up` which allows to allocate memory in bottom-up mode when it is `true`. Next field is `current_limit`. This field describes the limit size of the memory block. The next three fields describes the type of the memory block. It can be: reserved, memory and physical memory if `CONFIG_HAVE_MEMBLOCK_PHYS_MAP` configuration option is enabled. Now we met yet another data structure - `memblock_type`. Let's look on its definition:

```C
struct memblock_type {
	unsigned long cnt;
	unsigned long max;
	phys_addr_t total_size;
	struct memblock_region *regions;
};
```

This structure provides information about memory type. It contains fields which describe number of memory regions which are inside current memory block, size of the all memory regions, size of the allocated array of the memory regions and pointer to the array of the `memblock_region` structures. `memblock_region` is a structure which describes memory region. Its definition looks:

```C
struct memblock_region {
        phys_addr_t base;
        phys_addr_t size;
        unsigned long flags;
#ifdef CONFIG_HAVE_MEMBLOCK_NODE_MAP
        int nid;
#endif
};
```

`memblock_region` provides base address and size of the memory region, flags which can be:

```C
#define MEMBLOCK_ALLOC_ANYWHERE	(~(phys_addr_t)0)
#define MEMBLOCK_ALLOC_ACCESSIBLE	0
#define MEMBLOCK_HOTPLUG	0x1
```

Also `memblock_region` provides integer field - [numa](http://en.wikipedia.org/wiki/Non-uniform_memory_access) node selector, if `CONFIG_HAVE_MEMBLOCK_NODE_MAP` configuration option is enabled.

Schematically we can imagine it as:

```
+---------------------------+   +---------------------------+
|         memblock          |   |                           |
|  _______________________  |   |                           |
| |        memory         | |   |       Array of the        |
| |      memblock_type    |-|-->|      membock_region       |
| |_______________________| |   |                           |
|                           |   +---------------------------+
|  _______________________  |   +---------------------------+
| |       reserved        | |   |                           |
| |      memblock_type    |-|-->|       Array of the        |
| |_______________________| |   |      memblock_region      |
|                           |   |                           |
+---------------------------+   +---------------------------+
```

These three structures: `memblock`, `memblock_type` and `memblock_region` are main in the `Memblock`. Now we know about it and can look at Memblock initialization process.

Memblock initialization
--------------------------------------------------------------------------------

As all API of the `memblock` described in the [include/linux/memblock.h](https://github.com/torvalds/linux/blob/master/include/linux/memblock.h) header file, all implementation of these function is in the [mm/memblock.c]([include/linux/memblock.h](https://github.com/torvalds/linux/blob/master/mm/memblock.c) source code file. Let's look on the top of source code file and we will look there initialization of the `memblock` structure:

```C
struct memblock memblock __initdata_memblock = {
	.memory.regions		= memblock_memory_init_regions,
	.memory.cnt		    = 1,
	.memory.max		    = INIT_MEMBLOCK_REGIONS,

	.reserved.regions	= memblock_reserved_init_regions,
	.reserved.cnt		= 1,
	.reserved.max		= INIT_MEMBLOCK_REGIONS,

#ifdef CONFIG_HAVE_MEMBLOCK_PHYS_MAP
	.physmem.regions	= memblock_physmem_init_regions,
	.physmem.cnt		= 1,
	.physmem.max		= INIT_PHYSMEM_REGIONS,
#endif
	.bottom_up		    = false,
	.current_limit		= MEMBLOCK_ALLOC_ANYWHERE,
};
```

Here we can see initialization of the `memblock` structure which has the same name as structure - `memblock`. First of all note on `__initdata_memblock`. Defenition of this macro looks like:

```C
#ifdef CONFIG_ARCH_DISCARD_MEMBLOCK
    #define __init_memblock __meminit
    #define __initdata_memblock __meminitdata
#else
    #define __init_memblock
    #define __initdata_memblock
#endif
```

You can note that it depends on `CONFIG_ARCH_DISCARD_MEMBLOCK`. If this configuration option is enabled, memblock code will be put to the `.init` section and it will be released after the kernel is booted up.

Next we can see initialization of the `memblock_type memory`, `memblock_type reserved` and `memblock_type physmem` fields of the `memblock` structure. Here we interesting only in the `memblock_type.regions` initialization process. Note that every `memblock_type` field initialized by the arrays of the `memblock_region`:

```C
static struct memblock_region memblock_memory_init_regions[INIT_MEMBLOCK_REGIONS] __initdata_memblock;
static struct memblock_region memblock_reserved_init_regions[INIT_MEMBLOCK_REGIONS] __initdata_memblock;
#ifdef CONFIG_HAVE_MEMBLOCK_PHYS_MAP
static struct memblock_region memblock_physmem_init_regions[INIT_PHYSMEM_REGIONS] __initdata_memblock;
#endif
```

Every array contains 128 memory regions. We can see it in the `INIT_MEMBLOCK_REGIONS` macro definition:

```C
#define INIT_MEMBLOCK_REGIONS   128
```

Note that all arrays are also defined with the `__initdata_memblock` macro which we already saw in the `memblock` strucutre initialization (read above if you've forgot).

The last two fields describe that `bottom_up` allocation is disabled and the limit of the current Memblock is:

```C
#define MEMBLOCK_ALLOC_ANYWHERE (~(phys_addr_t)0)
```

which is `0xffffffffffffffff`.

On this step initialization of the `memblock` structure finished and we can look on the Memblock API.

Memblock API
--------------------------------------------------------------------------------

Ok we have finished with initilization of the `memblock` structure and now we can look on the Memblock API and its implementation. As i said about, all implementation of the `memblock` presented in the [mm/memblock.c](https://github.com/torvalds/linux/blob/master/mm/memblock.c). To understand how `memblock` works and implemented, let's look on it's usage first of all. There are a couple of [places](http://lxr.free-electrons.com/ident?i=memblock) in the linux kernel where memblock is used. For example let's take `memblock_x86_fill` function from the [arch/x86/kernel/e820.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/e820.c#L1061). This function goes through the memory map provided by the [e820](http://en.wikipedia.org/wiki/E820) and adds memory regions reserved by the kernel to the `memblock` with the `memblock_add` function. As we met `memblock_add` function first, let's start from it.

This function takes physical base address and size of the memory region and adds it to the `memblock`. `memblock_add` function does not anything special in its body, but just calls:

```C
memblock_add_range(&memblock.memory, base, size, MAX_NUMNODES, 0);
```

function. We pass memory block type - `memory`, physical base address and size of the memory region, maximum number of nodes which are zero if `CONFIG_NODES_SHIFT` is not set in the configuration file or `CONFIG_NODES_SHIFT` if it is set, and flags. `memblock_add_range` function adds new memory region to the memory block. It starts from check the size of the given region and if it is zero just return. After this, `memblock_add_range` check existence of the memory regions in the `memblock` structure with the given `memblock_type`. If there are no memory regions, we just fill new `memory_region` with the given values and return (we already saw implementation of this in the [First touch of the linux kernel memory manager framework](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-3.html)). If `memblock_type` is no empty, we start to add new memory region to the `memblock` with the given `memblock_type`.

First of all we get the end of the memory region with the:

```C
phys_addr_t end = base + memblock_cap_size(base, &size);
```

`memblock_cap_size` adjusts `size` that `base + size` will not overflow. Its implementation pretty easy:

```C
static inline phys_addr_t memblock_cap_size(phys_addr_t base, phys_addr_t *size)
{
	return *size = min(*size, (phys_addr_t)ULLONG_MAX - base);
}
```

`memblock_cap_size` returns new size which is the smallest value between the given `size` and base.

After that we got end address of the new memory region, `memblock_add_region` checks overlap and merge condititions with already added memory regions. Insertion of the new memory region to the `memblcok` consists from two steps:

* Adding of non-overlapping parts of the new memory area as separate regions;  
* Merging of all neighbouring regions.

We are going throuth the all already stored memory regions and check overlapping:

```C
	for (i = 0; i < type->cnt; i++) {
		struct memblock_region *rgn = &type->regions[i];
		phys_addr_t rbase = rgn->base;
		phys_addr_t rend = rbase + rgn->size;

		if (rbase >= end)
			break;
		if (rend <= base)
			continue;
        ...
		...
		...
	}
```

if new memory region does not overlap regions which are already stored in the `memblock`, insert this region into the memblock with and this is first step, we check that new region can fit into the memory block and call `memblock_double_array` in other way:

```C
while (type->cnt + nr_new > type->max)
	if (memblock_double_array(type, obase, size) < 0)
		return -ENOMEM;
	insert = true;
	goto repeat;
```

`memblock_double_array` doubles the size of the given regions array. Than we set insert to the `true` and go to the `repeat` label. In the second step, starting from the `repeat` label we go through the same loop and insert current memory region into the memory block with the `memblock_insert_region` function:

```C
	if (base < end) {
		nr_new++;
		if (insert)
			memblock_insert_region(type, i, base, end - base,
					       nid, flags);
	}
```

As we set `insert` to `true` in the first step, now `memblock_insert_region` will be called. `memblock_insert_region` has almost the same implemetation that we saw when we insert new region to the empty `memblock_type` (see above). This function get the last memory region:

```C
struct memblock_region *rgn = &type->regions[idx];
```

and copies memory area with `memmove`:

```C
memmove(rgn + 1, rgn, (type->cnt - idx) * sizeof(*rgn));
```

After this fills `memblock_region` fields of the new memory region base, size and etc... and increase size of the `memblock_type`. In the end of the exution, `memblock_add_range` calls `memblock_merge_regions` which merges neighboring compatible regions in the second step.

In the second case new memory region can overlap already stored regions. For example we already have `region1` in the `memblock`:

```
0                    0x1000
+-----------------------+
|                       |
|                       |
|        region1        |
|                       |
|                       |
+-----------------------+
```

And now we want to add `region2` to the `memblock` with the following base address and size:

```
0x100                 0x2000
+-----------------------+
|                       |
|                       |
|        region2        |
|                       |
|                       |
+-----------------------+
```

In this case set the base address of the new memory region as the end address of the overlapped region with:

```C
base = min(rend, end);
```

So it will be `0x1000` in our case. And insert it as we did it already in the second step with:

```
if (base < end) {
	nr_new++;
	if (insert)
		memblock_insert_region(type, i, base, end - base, nid, flags);
}
```

In this case we insert `overlapping portion` (we insert only higher portion, because lower already in the overlapped memory region), than remaining portion and merge these portions with `memblock_merge_regions`. As i said above `memblock_merge_regions` function merges neighboring compatible regions. It goes through the all memory regions from the given `memblock_type`, takes two neighboring memory regions - `type->regions[i]` and `type->regions[i + 1]` and checks that these regions have the same flags, belong to the same node and that end address of the first regions is not equal to the base address of the second region:

```C
while (i < type->cnt - 1) {
	struct memblock_region *this = &type->regions[i];
	struct memblock_region *next = &type->regions[i + 1];
	if (this->base + this->size != next->base ||
	    memblock_get_region_node(this) !=
	    memblock_get_region_node(next) ||
	    this->flags != next->flags) {
		BUG_ON(this->base + this->size > next->base);
		i++;
		continue;
	}
```

If none of these conditions are not true, we update the size of the first region with the size of the next region:

```C
this->size += next->size;
```

As we update the size of the first memory region with the size of the next memory region, we copy every (in the loop) memory region which is after the current (`this`) memory region on the one index ago with the `memmove` function:

```C
memmove(next, next + 1, (type->cnt - (i + 2)) * sizeof(*next));
```

And decrease the count of the memory regions which are belongs to the `memblock_type`:

```C
type->cnt--;
```

After this we will get two memory regions merged into one:

```
0                                             0x2000
+------------------------------------------------+
|                                                |
|                                                |
|                   region1                      |
|                                                |
|                                                |
+------------------------------------------------+
```

That's all. This is the whole principle of the work of the `memblock_add_range` function.

There is also `memblock_reserve` function which does the same as `memblock_add`, but only with one difference. It stores `memblock_type.reserved` in the memblock instead of `memblock_type.memory`.

Of course it is not full API. Memblock provides API for not only adding `memory` and `reserved` memory regions, but also:

* memblock_remove - removes memory region from memblock;
* memblock_find_in_range - finds free area in given range;
* memblock_free - releases memory region in memblock;
* for_each_mem_range - iterates through memblock areas.

and many more....

Getting info about memory regions
--------------------------------------------------------------------------------

Memblock also provides API for the getting information about allocated memorey regions in the `memblcok`. It splitted on two parts:

* get_allocated_memblock_memory_regions_info - getting info about memory regions;
* get_allocated_memblock_reserved_regions_info - getting info about reserved regions.

Implementation of these function is easy. Let's look on `get_allocated_memblock_reserved_regions_info` for example:

```C
phys_addr_t __init_memblock get_allocated_memblock_reserved_regions_info(
					phys_addr_t *addr)
{
	if (memblock.reserved.regions == memblock_reserved_init_regions)
		return 0;

	*addr = __pa(memblock.reserved.regions);

	return PAGE_ALIGN(sizeof(struct memblock_region) *
			  memblock.reserved.max);
}
```

First of all this function checks that `memblock` contains reserved memory regions. If `memblock` does not contain reserved memory regions we just return zero. In other way we write physical address of the reserved memory regions array to the given address and return aligned size of the allicated aray. Note that there is `PAGE_ALIGN` macro used for align. Actually it depends on size of page:

```C
#define PAGE_ALIGN(addr) ALIGN(addr, PAGE_SIZE)
```

Implementation of the `get_allocated_memblock_memory_regions_info` function is the same. It has only one difference, `memblock_type.memory` used instead of `memblock_type.memory`.

Memblock debugging
--------------------------------------------------------------------------------

There are many calls of the `memblock_dbg` in the memblock implementation. If you will pass `memblock=debug` option to the kernel command line, this function will be called. Actually `memblock_dbg` is just a macro which expands to the `printk`:

```C
#define memblock_dbg(fmt, ...) \
         if (memblock_debug) printk(KERN_INFO pr_fmt(fmt), ##__VA_ARGS__)
```

For example you can see call of this macro in the `memblock_reserve` function:

```C
memblock_dbg("memblock_reserve: [%#016llx-%#016llx] flags %#02lx %pF\n",
		     (unsigned long long)base,
		     (unsigned long long)base + size - 1,
		     flags, (void *)_RET_IP_);
```

And you must see something like this:

![Memblock](http://oi57.tinypic.com/1zoj589.jpg)

Memblock has also support in [debugfs](http://en.wikipedia.org/wiki/Debugfs). If you run kernel not in `X86` architecture you can access:

* /sys/kernel/debug/memblock/memory
* /sys/kernel/debug/memblock/reserved
* /sys/kernel/debug/memblock/physmem

for getting dump of the `memblock` contents.

Conclusion
--------------------------------------------------------------------------------

This is the end of the first part about linux kernel memory management. If you have questions or suggestions, ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-internals/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-internals](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

* [e820](http://en.wikipedia.org/wiki/E820)
* [numa](http://en.wikipedia.org/wiki/Non-uniform_memory_access)
* [debugfs](http://en.wikipedia.org/wiki/Debugfs)
* [First touch of the linux kernel memory manager framework](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-3.html)
