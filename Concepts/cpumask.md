CPU masks
================================================================================

Introduction
--------------------------------------------------------------------------------

`Cpumasks` is a special way provided by the Linux kernel to store information about CPUs in the system. The relevant source code and header files which are contains API for `Cpumasks` manipulating:

* [include/linux/cpumask.h](https://github.com/torvalds/linux/blob/master/include/linux/cpumask.h)
* [lib/cpumask.c](https://github.com/torvalds/linux/blob/master/lib/cpumask.c)
* [kernel/cpu.c](https://github.com/torvalds/linux/blob/master/kernel/cpu.c)

As comment says from the [include/linux/cpumask.h](https://github.com/torvalds/linux/blob/master/include/linux/cpumask.h): Cpumasks provide a bitmap suitable for representing the set of CPU's in a system, one bit position per CPU number. We already saw a bit about cpumask in the `boot_cpu_init` function from the [Kernel entry point](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-4.html) part. This function makes first boot cpu online, active and etc...:

```C
set_cpu_online(cpu, true);
set_cpu_active(cpu, true);
set_cpu_present(cpu, true);
set_cpu_possible(cpu, true);
```

`set_cpu_possible` is a set of cpu ID's which can be plugged in anytime during the life of that system boot. `cpu_present` represents which CPUs are currently plugged in. `cpu_online` represents subset of the `cpu_present` and indicates CPUs which are available for scheduling. These masks depends on `CONFIG_HOTPLUG_CPU` configuration option and if this option is disabled `possible == present` and `active == online`. Implementation of the all of these functions are very similar. Every function checks the second paramter. If it is `true`, calls `cpumask_set_cpu` or `cpumask_clear_cpu` otherwise.

There are two ways for a `cpumask` creation. First is to use `cpumask_t`. It defined as:

```C
typedef struct cpumask { DECLARE_BITMAP(bits, NR_CPUS); } cpumask_t;
```

It wraps `cpumask` structure which contains one bitmak `bits` field. `DECLARE_BITMAP` macro gets two paramters:

* bitmap name;
* number of bits.

and creates an array of `unsigned long` with the give name. It's implementation is pretty easy:

```C
#define DECLARE_BITMAP(name,bits) \
        unsigned long name[BITS_TO_LONGS(bits)]
```

where `BITS_TO_LONG`:

```C
#define BITS_TO_LONGS(nr)       DIV_ROUND_UP(nr, BITS_PER_BYTE * sizeof(long))
#define DIV_ROUND_UP(n,d) (((n) + (d) - 1) / (d))
```

As we learning `x86_64` architecture, `unsigned long` is 8-bytes size and our array will contain only one element:

```
(((8) + (8) - 1) / (8)) = 1
```

`NR_CPUS` macro presents the number of the CPUs in the system and depends on the `CONFIG_NR_CPUS` macro which defined in the [include/linux/threads.h](https://github.com/torvalds/linux/blob/master/include/linux/threads.h) and looks like this:

```C
#ifndef CONFIG_NR_CPUS
        #define CONFIG_NR_CPUS  1
#endif

#define NR_CPUS         CONFIG_NR_CPUS
```

The second way to define cpumask is to use `DECLARE_BITMAP` macro directly and `to_cpumask` macro which convertes given bitmap to the `struct cpumask *`:

```C
#define to_cpumask(bitmap)                                              \
        ((struct cpumask *)(1 ? (bitmap)                                \
                            : (void *)sizeof(__check_is_bitmap(bitmap))))
```

We can see ternary operator operator here which is `true` everytime. `__check_is_bitmap` inline function defined as:

```C
static inline int __check_is_bitmap(const unsigned long *bitmap)
{
        return 1;
}
```

And returns `1` everytime. We need in it here only for one purpose: In compile time it checks that given `bitmap` is a bitmap, or with another words it checks that given `bitmap` has type - `unsigned long *`. So we just pass `cpu_possible_bits` to the `to_cpumask` macro for converting array of `unsigned long` to the `struct cpumask *`.

cpumask API
--------------------------------------------------------------------------------

As we can define cpumask with one of the method, Linux kernel provides API for manipulating a cpumask. Let's consider one of the function which presented above. For example `set_cpu_online`. This function takes two parameters:

* Number of CPU;
* CPU status;

Implementation of this function looks as:

```C
void set_cpu_online(unsigned int cpu, bool online)
{
	if (online) {
		cpumask_set_cpu(cpu, to_cpumask(cpu_online_bits));
		cpumask_set_cpu(cpu, to_cpumask(cpu_active_bits));
	} else {
		cpumask_clear_cpu(cpu, to_cpumask(cpu_online_bits));
	}
}
```

First of all it checks the second `state` paramter and calls `cpumask_set_cpu` or `cpumask_clear_cpu` depends on it. Here we can see casting to the `struct cpumask *` of the second paramter in the `cpumask_set_cpu`. In our case it is `cpu_online_bits` which is bitmap and defined as:

```C
static DECLARE_BITMAP(cpu_online_bits, CONFIG_NR_CPUS) __read_mostly;
```

`cpumask_set_cpu` function makes only one call of the `set_bit` function inside:

```C
static inline void cpumask_set_cpu(unsigned int cpu, struct cpumask *dstp)
{
        set_bit(cpumask_check(cpu), cpumask_bits(dstp));
}
```

`set_bit` function takes two paramter too, and sets a given bit (first paramter) in the memory (second paramter or `cpu_online_bits` bitmap). We can see here that before `set_bit` will be called, its two paramter will be passed to the

* cpumask_check;
* cpumask_bits.

Let's consider these two macro. First if `cpumask_check` does nothing in our case and just returns given parameter. The second `cpumask_bits` just returns `bits` field from the given `struct cpumask *` structure:

```C
#define cpumask_bits(maskp) ((maskp)->bits)
```

Now let's look on the `set_bit` implementation:

```C
 static __always_inline void
 set_bit(long nr, volatile unsigned long *addr)
 {
         if (IS_IMMEDIATE(nr)) {
                asm volatile(LOCK_PREFIX "orb %1,%0"
                        : CONST_MASK_ADDR(nr, addr)
                        : "iq" ((u8)CONST_MASK(nr))
                        : "memory");
        } else {
                asm volatile(LOCK_PREFIX "bts %1,%0"
                        : BITOP_ADDR(addr) : "Ir" (nr) : "memory");
        }
 }
```

This function looks scarry, but it is not so hard as it seems. First of all it passes `nr` or number of the bit to the `IS_IMMEDIATE` macro which just makes call of the GCC internal `__builtin_constant_p` function:

```C
#define IS_IMMEDIATE(nr)    (__builtin_constant_p(nr))
```

`__builtin_constant_p` checks that given paramter is known constant at compile-time. As our `cpu` is not compile-time constant, `else` clause will be executed:

```C
asm volatile(LOCK_PREFIX "bts %1,%0" : BITOP_ADDR(addr) : "Ir" (nr) : "memory");
```

Let's try to understand how it works step by step:

`LOCK_PREFIX` is a x86 `lock` instruction. This instruction tells to the cpu to occupy the system bus while instruction will be executed. This allows to synchronize memory access, preventing simultaneous access of multiple processors (or devices - DMA controller for example) to one memory cell.

`BITOP_ADDR` casts given paramter to the `(*(volatile long *)` and adds `+m` constraints. `+` means that this operand is bot read and written by the instruction. `m` shows that this is memory operand. `BITOP_ADDR` is defined as:

```C
#define BITOP_ADDR(x) "+m" (*(volatile long *) (x))
```

Next is the `memory` clobber. It tells the compiler that the assembly code performs memory reads or writes to items other than those listed in the input and output operands (for example, accessing the memory pointed to by one of the input parameters).

`Ir` - immideate register operand. 


`bts` instruction sets given bit in a bit string and stores the value of a given bit in the `CF` flag. So we passed cpu number which is zero in our case and after `set_bit` will be executed, it sets zero bit in the `cpu_online_bits` cpumask. It would mean that the first cpu is online at this moment.

Besides the `set_cpu_*` API, cpumask ofcourse provides another API for cpumasks manipulation. Let's consider it in shoft.

Additional cpumask API
--------------------------------------------------------------------------------

cpumask provides the set of macro for getting amount of the CPUs with different state. For example:

```C
#define num_online_cpus()	cpumask_weight(cpu_online_mask)
```

This macro returns amount of the `online` CPUs. It calls `cpumask_weight` function with the `cpu_online_mask` bitmap (read about about it). `cpumask_wieght` function makes an one call of the `bitmap_wiegt` function with two paramters:

* cpumask bitmap;
* `nr_cpumask_bits` - which is `NR_CPUS` in our case.

```C
static inline unsigned int cpumask_weight(const struct cpumask *srcp)
{
	return bitmap_weight(cpumask_bits(srcp), nr_cpumask_bits);
}
```

and calculates amount of the bits in the given bitmap. Besides the `num_online_cpus`, cpumask provides macros for the all CPU states:

* num_possible_cpus;
* num_active_cpus;
* cpu_online;
* cpu_possible.

and many more.

Besides that Linux kernel provides following API for the manipulating of `cpumask`:

* for_each_cpu - iterates over every cpu in a mask;
* for_each_cpu_not - iterates over every cpu in a complemented mask;
* cpumask_clear_cpu - clears a cpu in a cpumask;
* cpumask_test_cpu - tests a cpu in a mask;
* cpumask_setall - set all cpus in a mask;
* cpumask_size - returns size to allocate for a 'struct cpumask' in bytes;

and many many more...

Links
--------------------------------------------------------------------------------

* [cpumask documentation](https://www.kernel.org/doc/Documentation/cpu-hotplug.txt)
