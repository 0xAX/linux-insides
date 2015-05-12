Per-CPU variables
================================================================================

Per-CPU variables are one of the kernel features. You can understand what this feature means by reading its name. We can create a variable and each processor core will have its own copy of this variable. We take a closer look on this feature and try to understand how it is implemented and how it works in this part.

The kernel provides API for creating per-cpu variables - `DEFINE_PER_CPU` macro:

```C
#define DEFINE_PER_CPU(type, name) \
        DEFINE_PER_CPU_SECTION(type, name, "")
```

This macro defined in the [include/linux/percpu-defs.h](https://github.com/torvalds/linux/blob/master/include/linux/percpu-defs.h) as many other macros for work with per-cpu variables. Now we will see how this feature is implemented.

Take a look at the `DECLARE_PER_CPU` definition. We see that it takes 2 parameters: `type` and `name`, so we can use it to create per-cpu variable, for example like this:

```C
DEFINE_PER_CPU(int, per_cpu_n)
```

We pass the type and the name of our variable. `DEFI_PER_CPU` calls `DEFINE_PER_CPU_SECTION` macro and passes the same two paramaters and empty string to it. Let's look at the definition of the `DEFINE_PER_CPU_SECTION`:

```C
#define DEFINE_PER_CPU_SECTION(type, name, sec)    \
         __PCPU_ATTRS(sec) PER_CPU_DEF_ATTRIBUTES  \
         __typeof__(type) name
```

```C
#define __PCPU_ATTRS(sec)                                                \
         __percpu __attribute__((section(PER_CPU_BASE_SECTION sec)))     \
         PER_CPU_ATTRIBUTES
```

where section is:

```C
#define PER_CPU_BASE_SECTION ".data..percpu"
```

After all macros are expanded we will get global per-cpu variable:

```C
__attribute__((section(".data..percpu"))) int per_cpu_n
```

It means that we will have `per_cpu_n` variable in the `.data..percpu` section. We can find this section in the `vmlinux`:

```
.data..percpu 00013a58  0000000000000000  0000000001a5c000  00e00000  2**12
              CONTENTS, ALLOC, LOAD, DATA
```

Ok, now we know that when we use `DEFINE_PER_CPU` macro, per-cpu variable in the `.data..percpu` section will be created. When the kernel initilizes it calls `setup_per_cpu_areas` function which loads `.data..percpu` section multiply times, one section per CPU.

Let's look on the per-CPU areas initialization process. It start in the [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c) from the call of the `setup_per_cpu_areas` function which defined in the [arch/x86/kernel/setup_percpu.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup_percpu.c).

```C
pr_info("NR_CPUS:%d nr_cpumask_bits:%d nr_cpu_ids:%d nr_node_ids:%d\n",
        NR_CPUS, nr_cpumask_bits, nr_cpu_ids, nr_node_ids);
```

The `setup_per_cpu_areas` starts from the output information about the Maximum number of CPUs set during kernel configuration with `CONFIG_NR_CPUS` configuration option, actual number of CPUs, `nr_cpumask_bits` is the same that `NR_CPUS` bit for the new `cpumask` operators and number of `NUMA` nodes.

We can see this output in the dmesg:

```
$ dmesg | grep percpu
[    0.000000] setup_percpu: NR_CPUS:8 nr_cpumask_bits:8 nr_cpu_ids:8 nr_node_ids:1
```

In the next step we check `percpu` first chunk allocator. All percpu areas are allocated in chunks. First chunk is used for the static percpu variables. Linux kernel has `percpu_alloc` command line parameters which provides type of the first chunk allocator. We can read about it in the kernel documentation:

```
percpu_alloc=	Select which percpu first chunk allocator to use.
		Currently supported values are "embed" and "page".
		Archs may support subset or none of the	selections.
		See comments in mm/percpu.c for details on each
		allocator.  This parameter is primarily	for debugging
		and performance comparison.
```

The [mm/percpu.c](https://github.com/torvalds/linux/blob/master/mm/percpu.c) contains handler of this command line option:

```C
early_param("percpu_alloc", percpu_alloc_setup);
```

Where `percpu_alloc_setup` function sets the `pcpu_chosen_fc` variable depends on the `percpu_alloc` parameter value. By default first chunk allocator is `auto`:

```C
enum pcpu_fc pcpu_chosen_fc __initdata = PCPU_FC_AUTO;
```

If `percpu_alooc` parameter not given to the kernel command line, the `embed` allocator will be used wich as you can understand embed the first percpu chunk into bootmem with the [memblock](http://0xax.gitbooks.io/linux-insides/content/mm/linux-mm-1.html). The last allocator is first chunk `page` allocator which maps first chunk with `PAGE_SIZE` pages.

As I wrote about first of all we make a check of the first chunk allocator type in the `setup_per_cpu_areas`. First of all we check that first chunk allocator is not page:

```C
if (pcpu_chosen_fc != PCPU_FC_PAGE) {
    ...
    ...
    ...
}
```

If it is not `PCPU_FC_PAGE`, we will use `embed` allocator and allocate space for the first chunk with the `pcpu_embed_first_chunk` function:

```C
rc = pcpu_embed_first_chunk(PERCPU_FIRST_CHUNK_RESERVE,
					    dyn_size, atom_size,
					    pcpu_cpu_distance,
					    pcpu_fc_alloc, pcpu_fc_free);
```

As I wrote above, the `pcpu_embed_first_chunk` function embeds the first percpu chunk into bootmem. As you can see we pass a couple of parameters to the `pcup_embed_first_chunk`, they are

* `PERCPU_FIRST_CHUNK_RESERVE` - the size of the reserved space for the static `percpu` variables;
* `dyn_size` - minimum free size for dynamic allocation in byte;
* `atom_size` - all allocations are whole multiples of this and aligned to this parameter;
* `pcpu_cpu_distance` - callback to determine distance between cpus;
* `pcpu_fc_alloc` - function to allocate `percpu` page;
* `pcpu_fc_free` - function to release `percpu` page.

All of this parameters we calculat before the call of the `pcpu_embed_first_chunk`:

```C
const size_t dyn_size = PERCPU_MODULE_RESERVE + PERCPU_DYNAMIC_RESERVE - PERCPU_FIRST_CHUNK_RESERVE;
size_t atom_size;
#ifdef CONFIG_X86_64
		atom_size = PMD_SIZE;
#else
		atom_size = PAGE_SIZE;
#endif
```

If first chunk allocator is `PCPU_FC_PAGE`, we will use the `pcpu_page_first_chunk` instead of the `pcpu_embed_first_chunk`. After that `percpu` areas up, we setup `percpu` offset and its segment for the every CPU with the `setup_percpu_segment` function (only for `x86` systems) and move some early data from the arrays to the `percpu` variables (`x86_cpu_to_apicid`, `irq_stack_ptr` and etc...). After the kernel finished the initialization process, we have loaded N `.data..percpu` sections, where N is the number of CPU, and section used by bootstrap processor will contain uninitialized variable created with `DEFINE_PER_CPU` macro.

The kernel provides API for per-cpu variables manipulating:

* get_cpu_var(var)
* put_cpu_var(var)


Let's look at `get_cpu_var` implementation:

```C
#define get_cpu_var(var)     \
(*({                         \
         preempt_disable();  \
         this_cpu_ptr(&var); \
}))
```

Linux kernel is preemptible and accessing a per-cpu variable requires to know which processor kernel running on. So, current code must not be preempted and moved to the another CPU while accessing a per-cpu variable. That's why first of all we can see call of the `preempt_disable` function. After this we can see call of the `this_cpu_ptr` macro, which looks as:

```C
#define this_cpu_ptr(ptr) raw_cpu_ptr(ptr)
```

and

```C
#define raw_cpu_ptr(ptr)        per_cpu_ptr(ptr, 0)
```

where `per_cpu_ptr` returns a pointer to the per-cpu variable for the given cpu (second parameter). After that we got per-cpu variables and made any manipulations on it, we must call `put_cpu_var` macro which enables preemption with call of `preempt_enable` function. So the typical usage of a per-cpu variable is following:

```C
get_cpu_var(var);
...
//Do something with the 'var'
...
put_cpu_var(var);
```

Let's look at `per_cpu_ptr` macro:

```C
#define per_cpu_ptr(ptr, cpu)                             \
({                                                        \
        __verify_pcpu_ptr(ptr);                           \
         SHIFT_PERCPU_PTR((ptr), per_cpu_offset((cpu)));  \
})
```

As I wrote above, this macro returns per-cpu variable for the given cpu. First of all it calls `__verify_pcpu_ptr`:

```C
#define __verify_pcpu_ptr(ptr)
do {
	const void __percpu *__vpp_verify = (typeof((ptr) + 0))NULL;
	(void)__vpp_verify; 
} while (0)
```

which makes given `ptr` type of `const void __percpu *`, 

After this we can see the call of the `SHIFT_PERCPU_PTR` macro with two parameters. At first parameter we pass our ptr and sencond we pass cpu number to the `per_cpu_offset` macro which:

```C
#define per_cpu_offset(x) (__per_cpu_offset[x])
```

expands to getting `x` element from the `__per_cpu_offset` array:


```C
extern unsigned long __per_cpu_offset[NR_CPUS];
```

where `NR_CPUS` is the number of CPUs. `__per_cpu_offset` array filled with the distances between cpu-variables copies. For example all per-cpu data is `X` bytes size, so if we access `__per_cpu_offset[Y]`, so `X*Y` will be accessed. Let's look at the `SHIFT_PERCPU_PTR` implementation:

```C
#define SHIFT_PERCPU_PTR(__p, __offset)                                 \
         RELOC_HIDE((typeof(*(__p)) __kernel __force *)(__p), (__offset))
```

`RELOC_HIDE` just returns offset `(typeof(ptr)) (__ptr + (off))` and it will be pointer of the variable.

That's all! Of course it is not the full API, but the general part. It can be hard for the start, but to understand per-cpu variables feature need to understand mainly [include/linux/percpu-defs.h](https://github.com/torvalds/linux/blob/master/include/linux/percpu-defs.h) magic.

Let's again look at the algorithm of getting pointer on per-cpu variable:

* The kernel creates multiply `.data..percpu` sections (ones perc-pu) during initialization process;
* All variables created with the `DEFINE_PER_CPU` macro will be reloacated to the first section or for CPU0;
* `__per_cpu_offset` array filled with the distance (`BOOT_PERCPU_OFFSET`) between `.data..percpu` sections;
* When `per_cpu_ptr` called for example for getting pointer on the certain per-cpu variable for the third CPU, `__per_cpu_offset` array will be accessed, where every index points to the certain CPU.

That's all.
