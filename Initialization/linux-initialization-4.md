Kernel initialization. Part 4.
================================================================================

Kernel entry point
================================================================================

If you have read the previous part - [Last preparations before the kernel entry point](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-3.md), you can remember that we finished all pre-initialization stuff and stopped right before the call of the `start_kernel` function from the [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c). The `start_kernel` is the entry of the generic and architecture independent kernel code, although we will return to the `arch/` folder many times. If you will look inside of the `start_kernel` function, you will see that this function is very big. For this moment it contains about `86` calls of functions. Yes, it's very big and of course this part will not cover all processes which are occur in this function. In the current part we will only start to do it. This part and all the next which will be in the [Kernel initialization process](https://github.com/0xAX/linux-insides/blob/master/Initialization/README.md) chapter will cover it.

The main purpose of the `start_kernel` to finish kernel initialization process and launch first `init` process. Before the first process will be started, the `start_kernel` must do many things as: to enable [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt), to initialize processor id, to enable early [cgroups](http://en.wikipedia.org/wiki/Cgroups) subsystem, to setup per-cpu areas, to initialize different caches in [vfs](http://en.wikipedia.org/wiki/Virtual_file_system), to initialize memory manager, rcu, vmalloc, scheduler, IRQs, ACPI and many many more. Only after these steps we will see the launch of the first `init` process in the last part of this chapter. So many kernel code waits us, let's start.

**NOTE: All parts from this big chapter `Linux Kernel initialization process` will not cover anything about debugging. There will be separate chapter about kernel debugging tips.**

A little about function attributes
---------------------------------------------------------------------------------

As I wrote above, the `start_kernel` funcion defined in the [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c). This function defined with the `__init` attribute and as you already may know from other parts, all function which are defined with this attributed are necessary during kernel initialization.

```C
#define __init      __section(.init.text) __cold notrace
```

After initilization process will be finished, the kernel will release these sections with the call of the `free_initmem` function. Note also that `__init` defined with two attributes: `__cold` and `notrace`. Purpose of the first `cold` attribute is to mark the function that it is rarely used and compiler will optimize this function for size. The second `notrace` is defined as:

```C
#define notrace __attribute__((no_instrument_function))
```

where `no_instrument_function` says to compiler to not generate profiling function calls.

In the definition of the `start_kernel` function, you can also see the `__visible` attribute which expands to the:

```
#define __visible __attribute__((externally_visible))
```

where `externally_visible` tells to the compiler that something uses this function or variable, to prevent marking this function/variable as `unusable`. Definition of this and other macro attributes you can find in the [include/linux/init.h](https://github.com/torvalds/linux/blob/master/include/linux/init.h).

First steps in the start_kernel
--------------------------------------------------------------------------------

At the beginning of the `start_kernel` you can see definition of the two variables:

```C
char *command_line;
char *after_dashes;
```

The first presents pointer to the kernel command line and the second will contain result of the `parse_args` function which parses an input string with parameters in the form `name=value`, looking for specific keywords and invoking the right handlers. We will not go into details at this time related with these two variables, but will see it in the next parts. In the next step we can see call of:

```C
lockdep_init();
```

function. `lockdep_init` initializes [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt). It's implementation is pretty easy, it just initializes two [list_head](https://github.com/0xAX/linux-insides/blob/master/DataStructures/dlist.md) hashes and set global variable `lockdep_initialized` to `1`. Lock validator detects circular lock dependecies and called when any [spinlock](http://en.wikipedia.org/wiki/Spinlock) or [mutex](http://en.wikipedia.org/wiki/Mutual_exclusion) is acquired.

The next function is `set_task_stack_end_magic` which takes address of the `init_task` and sets `STACK_END_MAGIC` (`0x57AC6E9D`) as canary for it. `init_task` presents initial task structure:

```C
struct task_struct init_task = INIT_TASK(init_task);
```

where `task_struct` structure stores all informantion about a process. I will not definition of this structure in this book, because it's very big. You can find its definition in the [include/linux/sched.h](https://github.com/torvalds/linux/blob/master/include/linux/sched.h#L1278). For this moment `task_struct` contains more than `100` fields! Although you will not see definition of the `task_struct` in this book, we will use it very often, since it is the fundamental structure which describes the `process` in the Linux kernel. I will describe the meaning of the fields of this structure as we will meet with them in practice.

You can see the definition of the `init_task` and it initialized by `INIT_TASK` macro. This macro is from the [include/linux/init_task.h](https://github.com/torvalds/linux/blob/master/include/linux/init_task.h) and it just fills the `init_task` with the values for the first process. For example it sets:

* init process state to zero or `runnable`. A runnable process is one which is waiting only for a CPU to run on;
* init process flags - `PF_KTHREAD` which means - kernel thread;
* a list of runnable task;
* process address space;
* init process stack to the `&init_thread_info` which is `init_thread_union.thread_info` and `initthread_union` has type - `thread_union` which contains `thread_info` and process stack:

```C
union thread_union {
	struct thread_info thread_info;
    unsigned long stack[THREAD_SIZE/sizeof(long)];
};
```

Every process has own stack and it is 16 killobytes or 4 page frames. in `x86_64`. We can note that it defined as array of `unsigned long`. The next field of the `thread_union` is - `thread_info` defined as:

```C
struct thread_info {
        struct task_struct      *task;
        struct exec_domain      *exec_domain;
        __u32                   flags; 
        __u32                   status;
        __u32                   cpu;
        int                     saved_preempt_count;
        mm_segment_t            addr_limit;
        struct restart_block    restart_block;
        void __user             *sysenter_return;
        unsigned int            sig_on_uaccess_error:1;
        unsigned int            uaccess_err:1;
};
```

and occupies 52 bytes. `thread_info` structure contains archetecture-specific inforamtion the thread. We know that on `x86_64` stack grows down and `thread_union.thread_info` is stored at the bottom of the stack in our case. So the process stack is 16 killobytes and `thread_info` is at the bottom. Remaining thread_size will be `16 killobytes - 62 bytes = 16332 bytes`. Note that `thread_unioun` represented as the [union](http://en.wikipedia.org/wiki/Union_type) and not structure, it means that `thread_info` and stack share the memory space.

Schematically it can be represented as follows:

```C
+-----------------------+
|                       |
|                       |
|        stack          |
|                       |
|_______________________|
|          |            |
|          |            |
|          |            |
|__________↓____________|             +--------------------+
|                       |             |                    |
|      thread_info      |<----------->|     task_struct    |
|                       |             |                    |
+-----------------------+             +--------------------+
```

http://www.quora.com/In-Linux-kernel-Why-thread_info-structure-and-the-kernel-stack-of-a-process-binds-in-union-construct

So `INIT_TASK` macro fills these `task_struct's` fields and many many more. As i already wrote about, I will not describe all fields and its values in the `INIT_TASK` macro, but we will see it soon.

Now let's back to the `set_task_stack_end_magic` function. This function defined in the [kernel/fork.c](https://github.com/torvalds/linux/blob/master/kernel/fork.c#L297) and sets a [canary](http://en.wikipedia.org/wiki/Stack_buffer_overflow) to the `init` process stack to prevent stack overflow.

```C
void set_task_stack_end_magic(struct task_struct *tsk)
{
	unsigned long *stackend;
	stackend = end_of_stack(tsk);
	*stackend = STACK_END_MAGIC; /* for overflow detection */
}
```

Its implementation is easy. `set_task_stack_end_magic` gets the end of the stack for the give `task_struct` with the `end_of_stack` function. End of a process stack depends on `CONFIG_STACK_GROWSUP` configuration option. As we learning `x86_64` architecture, stack grows down. So the end of the process stack will be:

```C
(unsigned long *)(task_thread_info(p) + 1);
```

where `task_thread_info` just returns the stack which we filled with the `INIT_TASK` macro:

```C
#define task_thread_info(task)  ((struct thread_info *)(task)->stack)
```

As we got end of the init process stack, we write `STACK_END_MAGIC` there. After `canary` set, we can check it like this:

```C
if (*end_of_stack(task) != STACK_END_MAGIC) {
        //
        // handle stack overflow here
		//
}
```

The next function after the `set_task_stack_end_magic` is `smp_setup_processor_id`. This function has empty body for `x86_64`:

```C
void __init __weak smp_setup_processor_id(void)
{
}
```

as it implemented not for all architectures, but for [s390](http://en.wikipedia.org/wiki/IBM_ESA/390), [arm64](http://en.wikipedia.org/wiki/ARM_architecture#64.2F32-bit_architecture) and etc...

The next function is - `debug_objects_early_init` in the `start_kernel`. Implementation of these function is almost the same as `lockdep_init`, but fills hashes for object debugging. As i wrote about, we will not see description of this and other functions which are for debugging purposes in this chapter.

After `debug_object_early_init` function we can see the call of the `boot_init_stack_canary` function which fills `task_struct->canary` with the canary value for the `-fstack-protector` gcc feature. This function depends on `CONFIG_CC_STACKPROTECTOR` configuration option and if this option is disabled `boot_init_stack_canary` does not anything, in another way it generate random number based on random pool and the [TSC](http://en.wikipedia.org/wiki/Time_Stamp_Counter):

```C
get_random_bytes(&canary, sizeof(canary));
tsc = __native_read_tsc();
canary += tsc + (tsc << 32UL);
```

After we got a random number, we fill `stack_canary` field of the `task_struct` with it:

```C
current->stack_canary = canary;
```

and writes this value to the top of the IRQ stack with the:

```C
this_cpu_write(irq_stack_union.stack_canary, canary); // read bellow about this_cpu_write
```

Again, we will not dive into details here, will cover it in the part about [IRQs](http://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29). As canary set, we disable local and early boot IRQs and register the bootstrap cpu in the cpu maps. We disable local irqs (interrupts for current CPU) with the `local_irq_disable` macro which expands to the call of the `arch_local_irq_disable` function from the [include/linux/percpu-defs.h](https://github.com/torvalds/linux/blob/master/include/linux/percpu-defs.h):

```C
static inline notrace void arch_local_irq_enable(void)
{
        native_irq_enable();
}
```

Where `native_irq_enable` is `cli` instruction for `x86_64`. As interrupts are disabled we can register current cpu with the given ID in the cpu bitmap.

The first processor activation
---------------------------------------------------------------------------------

Current function from the `start_kernel` is the - `boot_cpu_init`. This function initalizes various cpu masks for the boostrap processor. First of all it gets the bootstrap processor id with the call of:

```C
int cpu = smp_processor_id();
```

For now it is just zero. If `CONFIG_DEBUG_PREEMPT` configuration option is disabled, `smp_processor_id` just expands to the call of the `raw_smp_processor_id` which expands to the:

```C
#define raw_smp_processor_id() (this_cpu_read(cpu_number))
```

`this_cpu_read` as many other function like this (`this_cpu_write`, `this_cpu_add` and etc...) defined in the [include/linux/percpu-defs.h](https://github.com/torvalds/linux/blob/master/include/linux/percpu-defs.h) and presents `this_cpu` operation. These operations provide a way of opmizing access to the [per-cpu](http://0xax.gitbooks.io/linux-insides/content/Theory/per-cpu.html) variables which are associated with the current processor. In our case it is - `this_cpu_read` expands to the of the:

```
__pcpu_size_call_return(this_cpu_read_, pcp)
```

Remember that we have passed `cpu_number` as `pcp` to the `this_cpu_read` from the `raw_smp_processor_id`. Now let's look on `__pcpu_size_call_return` implementation:

```C
#define __pcpu_size_call_return(stem, variable)                         \
({                                                                      \
        typeof(variable) pscr_ret__;                                    \
        __verify_pcpu_ptr(&(variable));                                 \
        switch(sizeof(variable)) {                                      \
        case 1: pscr_ret__ = stem##1(variable); break;                  \
        case 2: pscr_ret__ = stem##2(variable); break;                  \
        case 4: pscr_ret__ = stem##4(variable); break;                  \
        case 8: pscr_ret__ = stem##8(variable); break;                  \
        default:                                                        \
                __bad_size_call_parameter(); break;                     \
        }                                                               \
        pscr_ret__;                                                     \
}) 
```

Yes, it look a little strange, but it's easy. First of all we can see defintion of the `pscr_ret__` variable with the `int` type. Why int? Ok, `variable` is `common_cpu` and it was declared as per-cpu int variable:

```C
DECLARE_PER_CPU_READ_MOSTLY(int, cpu_number);
```

In the next step we call `__verify_pcpu_ptr` with the address of `cpu_number`. `__veryf_pcpu_ptr` used to verifying that given paramter is an per-cpu pointer. After that we set `pscr_ret__` value which depends on the size of the variable. Our `common_cpu` variable is `int`, so it 4 bytes size. It means that we will get `this_cpu_read_4(common_cpu)` in `pscr_ret__`. In the end of the `__pcpu_size_call_return` we just call it. `this_cpu_read_4` is a macro:

```C
#define this_cpu_read_4(pcp)       percpu_from_op("mov", pcp)
```

which calls `percpu_from_op` and pass `mov` instruction and per-cpu variable there. `percpu_from_op` will expand to the inline assembly call:

```C
asm("movl %%gs:%1,%0" : "=r" (pfo_ret__) : "m" (common_cpu))
```

Let's try to understand how it works and what it does. `gs` segment register contains the base of per-cpu area. Here we just copy `common_cpu` which is in memory to the `pfo_ret__` with the `movl` instruction. Or with another words:

```C
this_cpu_read(common_cpu)
```

is the same that:

```C
movl %gs:$common_cpu, $pfo_ret__
```

As we didn't setup per-cpu area, we have only one - for the current running CPU, we will get `zero` as a result of the `smp_processor_id`.

As we got current processor id, `boot_cpu_init` sets the given cpu online,active,present and possible with the:

```C
set_cpu_online(cpu, true);
set_cpu_active(cpu, true);
set_cpu_present(cpu, true);
set_cpu_possible(cpu, true);
```

All of these functions use the concept - `cpumask`. `cpu_possible` is a set of cpu ID's which can be plugged in anytime during the life of that system boot. `cpu_present` represents which CPUs are currently plugged in. `cpu_online` represents subset of the `cpu_present` and indicates CPUs which are available for scheduling. These masks depends on `CONFIG_HOTPLUG_CPU` configuration option and if this option is disabled `possible == present` and `active == online`. Implementation of the all of these functions are very similar. Every function checks the second paramter. If it is `true`, calls `cpumask_set_cpu` or `cpumask_clear_cpu` otherwise.

For example let's look on `set_cpu_possible`. As we passed `true` as the second paramter, the:

```C
cpumask_set_cpu(cpu, to_cpumask(cpu_possible_bits));
```

will be called. First of all let's try to understand `to_cpu_mask` macro. This macro casts a bitmap to a `struct cpumask *`. Cpu masks provide a bitmap suitable for representing the set of CPU's in a system, one bit position per CPU number. CPU mask presented by the `cpu_mask` structure:

```C
typedef struct cpumask { DECLARE_BITMAP(bits, NR_CPUS); } cpumask_t;
```

which is just bitmap declared with the `DECLARE_BITMAP` macro:

```C
#define DECLARE_BITMAP(name, bits) unsigned long name[BITS_TO_LONGS(bits)]
```

As we can see from its definition, `DECLARE_BITMAP` macro expands to the array of `unsigned long`. Now let's look on how `to_cpumask` macro implemented:

```C
#define to_cpumask(bitmap)                                              \
        ((struct cpumask *)(1 ? (bitmap)                                \
                            : (void *)sizeof(__check_is_bitmap(bitmap))))
```

I don't know how about you, but it looked really weird for me at the first time. We can see ternary operator operator here which is `true` everytime, but why the `__check_is_bitmap` here? It's simple, let's look on it:

```C
static inline int __check_is_bitmap(const unsigned long *bitmap)
{
        return 1;
}
```

Yeah, it just returns `1` everytime. Actually we need in it here only for one purpose: In compile time it checks that given `bitmap` is a bitmap, or with another words it checks that given `bitmap` has type - `unsigned long *`. So we just pass `cpu_possible_bits` to the `to_cpumask` macro for converting array of `unsigned long` to the `struct cpumask *`. Now we can call `cpumask_set_cpu` function with the `cpu` - 0 and `struct cpumask *cpu_possible_bits`. This function makes only one call of the `set_bit` function which sets the given `cpu` in the cpumask. All of these `set_cpu_*` functions work on the same principle.

If you're not sure that this `set_cpu_*` operations and `cpumask` are not clear for you, don't worry about it. You can get more info by reading of the special part about it -  [cpumask](http://0xax.gitbooks.io/linux-insides/content/Concepts/cpumask.html) or [documentation](https://www.kernel.org/doc/Documentation/cpu-hotplug.txt).

As we activated the bootstrap processor, time to go to the next function in the `start_kernel.` Now it is `page_address_init`, but this function does nothing in our case, because it executes only when all `RAM` can't be mapped directly.

Print linux banner
---------------------------------------------------------------------------------

The next call is `pr_notice`:

```C
#define pr_notice(fmt, ...) \
    printk(KERN_NOTICE pr_fmt(fmt), ##__VA_ARGS__)
```

as you can see it just expands to the `printk` call. For this moment we use `pr_notice` for printing linux banner:

```C
pr_notice("%s", linux_banner);
```

which is just kernel version with some additional paramters:

```
Linux version 4.0.0-rc6+ (alex@localhost) (gcc version 4.9.1 (Ubuntu 4.9.1-16ubuntu6) ) #319 SMP
```

Architecture-dependent parts of initialization
---------------------------------------------------------------------------------

The next step is architecture-specific initializations. Linux kernel does it with the call of the `setup_arch` function. This is very big function as the `start_kernel` and we do not have time to consider all of its implementation in this part. Here we'll only start to do it and continue in the next part. As it is `architecture-specific`, we need to go again to the `arch/` directory. `setup_arch` function defined in the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c) source code file and takes only one argument - address of the kernel command line.

This function starts from the reserving memory block for the kernel `_text` and `_data` which starts from the `_text` symbol (you can remember it from the [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S#L46)) and ends before `__bss_stop`. We are using `memblock` for the reserving of memory block:

```C
memblock_reserve(__pa_symbol(_text), (unsigned long)__bss_stop - (unsigned long)_text);
```

You can read about `memblock` in the [Linux kernel memory management Part 1.](http://0xax.gitbooks.io/linux-insides/content/mm/linux-mm-1.html). As you can remember `memblock_reserve` function takes two paramters:

* base physical address of a memory block;
* size of a memor block.

Base physical address of the `_text` symbol we will get with the `__pa_symbol` macro:

```C
#define __pa_symbol(x) \
	__phys_addr_symbol(__phys_reloc_hide((unsigned long)(x)))
```

First of all it calls `__phys_reloc_hide` macro on the given paramter. `__phys_reloc_hide` macro does nothing for `x86_64` and just returns the given paramter. Implementation of the `__phys_addr_symbol` macro is easy. It just substracts the symbol address from the base addres of the kernel text mapping base virtual address (you can remember that it is `__START_KERNEL_map`) and adds `phys_base` which is base address of the `_text`:

```C
#define __phys_addr_symbol(x) \
 ((unsigned long)(x) - __START_KERNEL_map + phys_base)
```

After we got physical address of the `_text` symbol, `memblock_reserve` can reserve memory block from the `_text` to the `__bss_stop - _text`.

Reserve memory for initrd
---------------------------------------------------------------------------------

In the next step after we reserved place for the kernel text and data is resering place for the [initrd](http://en.wikipedia.org/wiki/Initrd). We will not see details about `initrd` in this post, you just may know that it is temprary root file system stored in memory and used by the kernel during its startup. `early_reserve_initrd` function does all work. First of all this function get the base address of the ram disk, its size and the end address with:

```C
u64 ramdisk_image = get_ramdisk_image();
u64 ramdisk_size  = get_ramdisk_size();
u64 ramdisk_end   = PAGE_ALIGN(ramdisk_image + ramdisk_size);
```

All of these paramters it takes from the `boot_params`. If you have read chapter abot [Linux Kernel Booting Process](http://0xax.gitbooks.io/linux-insides/content/Booting/index.html), you must remember that we filled `boot_params` structure during boot time. Kerne setup header contains a couple of fields which describes ramdisk, for example:

```
Field name:	ramdisk_image
Type:		write (obligatory)
Offset/size:	0x218/4
Protocol:	2.00+

  The 32-bit linear address of the initial ramdisk or ramfs.  Leave at
  zero if there is no initial ramdisk/ramfs.
```

So we can get all information which interests us from the `boot_params`. For example let's look on `get_ramdisk_image`:

```C
static u64 __init get_ramdisk_image(void)
{
        u64 ramdisk_image = boot_params.hdr.ramdisk_image;

        ramdisk_image |= (u64)boot_params.ext_ramdisk_image << 32;

        return ramdisk_image;
}
```

Here we get address of the ramdisk from the `boot_params` and shift left it on `32`. We need to do it because as you can read in the [Documentation/x86/zero-page.txt](https://github.com/0xAX/linux/blob/master/Documentation/x86/zero-page.txt):

```
0C0/004	ALL	ext_ramdisk_image ramdisk_image high 32bits
```

So after shifting it on 32, we're getting 64-bit address in `ramdisk_image`. After we got it just return it. `get_ramdisk_size` works on the same principle as `get_ramdisk_image`, but it used `ext_ramdisk_size` instead of `ext_ramdisk_image`. After we got ramdisk's size, base address and end address, we check that bootloader provided ramdisk with the:

```C
if (!boot_params.hdr.type_of_loader ||
    !ramdisk_image || !ramdisk_size)
	return;
```

and reserve memory block with the calculated addresses for the initial ramdisk in the end:

```C
memblock_reserve(ramdisk_image, ramdisk_end - ramdisk_image);
```

Conclusion
---------------------------------------------------------------------------------

It is the end of the fourth part about linux kernel initialization process. We started to dive in the kernel generic code from the `start_kernel` function in this part and stopped on the architecture-specific initializations in the `setup_arch`. In next part we will continue with architecture-dependent initialization steps.

If you will have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you will find any mistakes please send me PR to [linux-internals](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

* [GCC function attributes](https://gcc.gnu.org/onlinedocs/gcc/Function-Attributes.html)
* [this_cpu operations](https://www.kernel.org/doc/Documentation/this_cpu_ops.txt)
* [cpumask](http://www.crashcourse.ca/wiki/index.php/Cpumask)
* [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt)
* [cgroups](http://en.wikipedia.org/wiki/Cgroups)
* [stack buffer overflow](http://en.wikipedia.org/wiki/Stack_buffer_overflow)
* [IRQs](http://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29)
* [initrd](http://en.wikipedia.org/wiki/Initrd)
* [Previous part](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-3.md)
