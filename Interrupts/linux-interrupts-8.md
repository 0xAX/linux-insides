Interrupts and Interrupt Handling. Part 8.
================================================================================

Non-early initialization of the IRQs
--------------------------------------------------------------------------------

This is the eighth part of the Interrupts and Interrupt Handling in the Linux kernel [chapter](https://0xax.gitbook.io/linux-insides/summary/interrupts) and in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-7) we started to dive into the external hardware [interrupts](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29). We looked on the implementation of the `early_irq_init` function from the [kernel/irq/irqdesc.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/irq/irqdesc.c) source code file and saw the initialization of the `irq_desc` structure in this function. Remind that `irq_desc` structure (defined in the [include/linux/irqdesc.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/irqdesc.h#L46) is the foundation of interrupt management code in the Linux kernel and represents an interrupt descriptor. In this part we will continue to dive into the initialization stuff which is related to the external hardware interrupts.

Right after the call of the `early_irq_init` function in the [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c) we can see the call of the `init_IRQ` function. This function is architecture-specific and defined in the [arch/x86/kernel/irqinit.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/irqinit.c). The `init_IRQ` function makes initialization of the `vector_irq` [percpu](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1) variable that defined in the same [arch/x86/kernel/irqinit.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/irqinit.c) source code file:

```C
...
DEFINE_PER_CPU(vector_irq_t, vector_irq) = {
         [0 ... NR_VECTORS - 1] = -1,
};
...
```

and represents `percpu` array of the interrupt vector numbers. The `vector_irq_t` defined in the [arch/x86/include/asm/hw_irq.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/hw_irq.h) and expands to the:

```C
typedef int vector_irq_t[NR_VECTORS];
```

where `NR_VECTORS` is count of the vector number and as you can remember from the first [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-1) of this chapter it is `256` for the [x86_64](https://en.wikipedia.org/wiki/X86-64):

```C
#define NR_VECTORS                       256
```

So, in the start of the `init_IRQ` function we fill the `vector_irq` [percpu](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1) array with the vector number of the `legacy` interrupts:

```C
void __init init_IRQ(void)
{
	int i;

	for (i = 0; i < nr_legacy_irqs(); i++)
		per_cpu(vector_irq, 0)[IRQ0_VECTOR + i] = i;
...
...
...
}
```

This `vector_irq` will be used during the first steps of an external hardware interrupt handling in the `do_IRQ` function from the [arch/x86/kernel/irq.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/irq.c):

```C
__visible unsigned int __irq_entry do_IRQ(struct pt_regs *regs)
{
	...
	...
	...
	irq = __this_cpu_read(vector_irq[vector]);

	if (!handle_irq(irq, regs)) {
		...
		...
		...
	}

	exiting_irq();
	...
	...
	return 1;
}
```

Why is `legacy` here? Actually all interrupts are handled by the modern [IO-APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller#I.2FO_APICs) controller. But these interrupts (from `0x30` to `0x3f`) by legacy interrupt-controllers like [Programmable Interrupt Controller](https://en.wikipedia.org/wiki/Programmable_Interrupt_Controller). If these interrupts are handled by the `I/O APIC` then this vector space will be freed and re-used. Let's look on this code closer. First of all the `nr_legacy_irqs` defined in the [arch/x86/include/asm/i8259.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/i8259.h) and just returns the `nr_legacy_irqs` field from the `legacy_pic` structure:

```C
static inline int nr_legacy_irqs(void)
{
        return legacy_pic->nr_legacy_irqs;
}
```

This structure defined in the same header file and represents non-modern programmable interrupts controller:

```C
struct legacy_pic {
        int nr_legacy_irqs;
        struct irq_chip *chip;
        void (*mask)(unsigned int irq);
        void (*unmask)(unsigned int irq);
        void (*mask_all)(void);
        void (*restore_mask)(void);
        void (*init)(int auto_eoi);
        int (*irq_pending)(unsigned int irq);
        void (*make_irq)(unsigned int irq);
};
```

Actual default maximum number of the legacy interrupts represented by the `NR_IRQ_LEGACY` macro from the [arch/x86/include/asm/irq_vectors.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/irq_vectors.h):

```C
#define NR_IRQS_LEGACY                    16
```

In the loop we are accessing the `vecto_irq` per-cpu array with the `per_cpu` macro by the `IRQ0_VECTOR + i` index and write the legacy vector number there. The `IRQ0_VECTOR` macro defined in the [arch/x86/include/asm/irq_vectors.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/irq_vectors.h) header file and expands to the `0x30`:

```C
#define FIRST_EXTERNAL_VECTOR           0x20

#define IRQ0_VECTOR                     ((FIRST_EXTERNAL_VECTOR + 16) & ~15)
```

Why is `0x30` here? You can remember from the first [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-1) of this chapter that first 32 vector numbers from `0` to `31` are reserved by the processor and used for the processing of architecture-defined exceptions and interrupts. Vector numbers from `0x30` to `0x3f` are reserved for the [ISA](https://en.wikipedia.org/wiki/Industry_Standard_Architecture). So, it means that we fill the `vector_irq` from the `IRQ0_VECTOR` which is equal to the `32` to the `IRQ0_VECTOR + 16` (before the `0x30`).

In the end of the `init_IRQ` function we can see the call of the following function:

```C
x86_init.irqs.intr_init();
```

from the [arch/x86/kernel/x86_init.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/x86_init.c) source code file. If you have read [chapter](https://0xax.gitbook.io/linux-insides/summary/initialization) about the Linux kernel initialization process, you can remember the `x86_init` structure. This structure contains a couple of files which point to the function related to the platform setup (`x86_64` in our case), for example `resources` - related with the memory resources, `mpparse` - related with the parsing of the [MultiProcessor Configuration Table](https://en.wikipedia.org/wiki/MultiProcessor_Specification) table, etc.). As we can see the `x86_init` also contains the `irqs` field which contains the three following fields:

```C
struct x86_init_ops x86_init __initdata
{
	...
	...
	...
    .irqs = {
                .pre_vector_init        = init_ISA_irqs,
                .intr_init              = native_init_IRQ,
                .trap_init              = x86_init_noop,
	},
	...
	...
	...
}
```

Now, we are interesting in the `native_init_IRQ`. As we can note, the name of the `native_init_IRQ` function contains the `native_` prefix which means that this function is architecture-specific. It defined in the [arch/x86/kernel/irqinit.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/irqinit.c) and executes general initialization of the [Local APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller#Integrated_local_APICs) and initialization of the [ISA](https://en.wikipedia.org/wiki/Industry_Standard_Architecture) irqs. Let's look at the implementation of the `native_init_IRQ` function and try to understand what occurs there. The `native_init_IRQ` function starts from the execution of the following function:

```C
x86_init.irqs.pre_vector_init();
```

As we can see above, the `pre_vector_init` points to the `init_ISA_irqs` function that defined in the same [source code](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/irqinit.c) file and as we can understand from the function's name, it makes initialization of the `ISA` related interrupts. The `init_ISA_irqs` function starts from the definition of the `chip` variable which has a `irq_chip` type:

```C
void __init init_ISA_irqs(void)
{
	struct irq_chip *chip = legacy_pic->chip;
	...
	...
	...
```

The `irq_chip` structure defined in the [include/linux/irq.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/irq.h) header file and represents hardware interrupt chip descriptor. It contains:

* `name` - name of a device. Used in the `/proc/interrupts`:

```C
$ cat /proc/interrupts
           CPU0       CPU1       CPU2       CPU3       CPU4       CPU5       CPU6       CPU7
  0:         16          0          0          0          0          0          0          0   IO-APIC   2-edge      timer
  1:          2          0          0          0          0          0          0          0   IO-APIC   1-edge      i8042
  8:          1          0          0          0          0          0          0          0   IO-APIC   8-edge      rtc0
```

look at the last column;

* `(*irq_mask)(struct irq_data *data)`  - mask an interrupt source;
* `(*irq_ack)(struct irq_data *data)` - start of a new interrupt;
* `(*irq_startup)(struct irq_data *data)` - start up the interrupt;
* `(*irq_shutdown)(struct irq_data *data)` - shutdown the interrupt
* etc.

fields. Note that the `irq_data` structure represents set of the per irq chip data passed down to chip functions. It contains `mask` - precomputed bitmask for accessing the chip registers, `irq` - interrupt number, `hwirq` - hardware interrupt number, local to the interrupt domain chip low level interrupt hardware access, etc.

After this depends on the `CONFIG_X86_64` and `CONFIG_X86_LOCAL_APIC` kernel configuration option call the `init_bsp_APIC` function from the [arch/x86/kernel/apic/apic.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/apic/apic.c):

```C
#if defined(CONFIG_X86_64) || defined(CONFIG_X86_LOCAL_APIC)
	init_bsp_APIC();
#endif
```

This function makes initialization of the [APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller) of `bootstrap processor` (or processor which starts first). It starts from the check that we found [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) config (read more about it in the sixth [part](https://0xax.gitbook.io/linux-insides/summary/initialization/linux-initialization-6) of the Linux kernel initialization process chapter) and the processor has `APIC`:

```C
if (smp_found_config || !cpu_has_apic)
	return;
```

Otherwise, we return from this function. In the next step we call the `clear_local_APIC` function from the same source code file that shuts down the local `APIC` (more on it in the `Advanced Programmable Interrupt Controller` chapter) and enable `APIC` of the first processor by the setting `unsigned int value` to the `APIC_SPIV_APIC_ENABLED`:

```C
value = apic_read(APIC_SPIV);
value &= ~APIC_VECTOR_MASK;
value |= APIC_SPIV_APIC_ENABLED;
```

and writing it with the help of the `apic_write` function:

```C
apic_write(APIC_SPIV, value);
```

After we have enabled `APIC` for the bootstrap processor, we return to the `init_ISA_irqs` function and in the next step we initialize legacy `Programmable Interrupt Controller` and set the legacy chip and handler for each legacy irq:

```C
legacy_pic->init(0);

for (i = 0; i < nr_legacy_irqs(); i++)
    irq_set_chip_and_handler(i, chip, handle_level_irq);
```

Where can we find `init` function? The `legacy_pic` defined in the [arch/x86/kernel/i8259.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/i8259.c) and it is:

```C
struct legacy_pic *legacy_pic = &default_legacy_pic;
```

Where the `default_legacy_pic` is:

```C
struct legacy_pic default_legacy_pic = {
	...
	...
	...
	.init = init_8259A,
	...
	...
	...
}
```

The `init_8259A` function defined in the same source code file and executes initialization of the [Intel 8259](https://en.wikipedia.org/wiki/Intel_8259) `Programmable Interrupt Controller` (more about it will be in the separate chapter about `Programmable Interrupt Controllers` and `APIC`).

Now we can return to the `native_init_IRQ` function, after the `init_ISA_irqs` function finished its work. The next step is the call of the `apic_intr_init` function that allocates special interrupt gates which are used by the [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) architecture for the [Inter-processor interrupt](https://en.wikipedia.org/wiki/Inter-processor_interrupt). The `alloc_intr_gate` macro from the [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/desc.h) used for the interrupt descriptor allocation:

```C
#define alloc_intr_gate(n, addr)                        \
do {                                                    \
        alloc_system_vector(n);                         \
        set_intr_gate(n, addr);                         \
} while (0)
```

As we can see, first of all it expands to the call of the `alloc_system_vector` function that checks the given vector number in the `used_vectors` bitmap (read previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-7) about it) and if it is not set in the `used_vectors` bitmap we set it. After this we test that the `first_system_vector` is greater than given interrupt vector number and if it is greater we assign it:

```C
if (!test_bit(vector, used_vectors)) {
	set_bit(vector, used_vectors);
    if (first_system_vector > vector)
		first_system_vector = vector;
} else {
	BUG();
}
```

We already saw the `set_bit` macro, now let's look at the `test_bit` and the `first_system_vector`. The first `test_bit` macro defined in the [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) and looks like this:

```C
#define test_bit(nr, addr)                      \
        (__builtin_constant_p((nr))             \
         ? constant_test_bit((nr), (addr))      \
         : variable_test_bit((nr), (addr)))
```

We can see the [ternary operator](https://en.wikipedia.org/wiki/Ternary_operation) here makes a test with the [gcc](https://en.wikipedia.org/wiki/GNU_Compiler_Collection) built-in function `__builtin_constant_p` tests that given vector number (`nr`) is known at compile time. If you're feeling misunderstanding of the `__builtin_constant_p`, we can make simple test:

```C
#include <stdio.h>

#define PREDEFINED_VAL 1

int main() {
	int i = 5;
	printf("__builtin_constant_p(i) is %d\n", __builtin_constant_p(i));
	printf("__builtin_constant_p(PREDEFINED_VAL) is %d\n", __builtin_constant_p(PREDEFINED_VAL));
	printf("__builtin_constant_p(100) is %d\n", __builtin_constant_p(100));

	return 0;
}
```

and look at the result:

```
$ gcc test.c -o test
$ ./test
__builtin_constant_p(i) is 0
__builtin_constant_p(PREDEFINED_VAL) is 1
__builtin_constant_p(100) is 1
```

Now I think it must be clear for you. Let's get back to the `test_bit` macro. If the `__builtin_constant_p` returns non-zero, we call `constant_test_bit` function:

```C
static inline int constant_test_bit(int nr, const void *addr)
{
	const u32 *p = (const u32 *)addr;

	return ((1UL << (nr & 31)) & (p[nr >> 5])) != 0;
}
```

and the `variable_test_bit` in other way:

```C
static inline int variable_test_bit(int nr, const void *addr)
{
        u8 v;
        const u32 *p = (const u32 *)addr;

        asm("btl %2,%1; setc %0" : "=qm" (v) : "m" (*p), "Ir" (nr));
        return v;
}
```

What's the difference between two these functions and why do we need in two different functions for the same purpose? As you already can guess main purpose is optimization. If we write simple example with these functions:

```C
#define CONST 25

int main() {
	int nr = 24;
	variable_test_bit(nr, (int*)0x10000000);
	constant_test_bit(CONST, (int*)0x10000000)
	return 0;
}
```

and will look at the assembly output of our example we will see following assembly code:

```assembly
pushq	%rbp
movq	%rsp, %rbp

movl	$268435456, %esi
movl	$25, %edi
call	constant_test_bit
```

for the `constant_test_bit`, and:

```assembly
pushq	%rbp
movq	%rsp, %rbp

subq	$16, %rsp
movl	$24, -4(%rbp)
movl	-4(%rbp), %eax
movl	$268435456, %esi
movl	%eax, %edi
call	variable_test_bit
```

for the `variable_test_bit`. These two code listings starts with the same part, first of all we save base of the current stack frame in the `%rbp` register. But after this code for both examples is different. In the first example we put `$268435456` (here the `$268435456` is our second parameter - `0x10000000`) to the `esi` and `$25` (our first parameter) to the `edi` register and call `constant_test_bit`. We put function parameters to the `esi` and `edi` registers because as we are learning Linux kernel for the `x86_64` architecture we use `System V AMD64 ABI` [calling convention](https://en.wikipedia.org/wiki/X86_calling_conventions). All is pretty simple. When we are using predefined constant, the compiler can just substitute its value. Now let's look at the second part. As you can see here, the compiler can not substitute value from the `nr` variable. In this case compiler must calculate its offset on the program's [stack frame](https://en.wikipedia.org/wiki/Call_stack). We subtract `16` from the `rsp` register to allocate stack for the local variables data and put the `$24` (value of the `nr` variable) to the `rbp` with offset `-4`. Our stack frame will be like this:

```
         <- stack grows

	          %[rbp]
                 |
+----------+ +---------+ +---------+ +--------+
|          | |         | | return  | |        |
|    nr    |-|         |-|         |-|  argc  |
|          | |         | | address | |        |
+----------+ +---------+ +---------+ +--------+
                 |
              %[rsp]
```

After this we put this value to the `eax`, so `eax` register now contains value of the `nr`. In the end we do the same that in the first example, we put the `$268435456` (the first parameter of the `variable_test_bit` function) and the value of the `eax` (value of `nr`) to the `edi` register (the second parameter of the `variable_test_bit function`).

The next step after the `apic_intr_init` function will finish its work is the setting interrupt gates from the `FIRST_EXTERNAL_VECTOR` or `0x20` up to `0x100`:

```C
i = FIRST_EXTERNAL_VECTOR;

#ifndef CONFIG_X86_LOCAL_APIC
#define first_system_vector NR_VECTORS
#endif

for_each_clear_bit_from(i, used_vectors, first_system_vector) {
	set_intr_gate(i, irq_entries_start + 8 * (i - FIRST_EXTERNAL_VECTOR));
}
```

But as we are using the `for_each_clear_bit_from` helper, we set only non-initialized interrupt gates. After this we use the same `for_each_clear_bit_from` helper to fill the non-filled interrupt gates in the interrupt table with the `spurious_interrupt`:

```C
#ifdef CONFIG_X86_LOCAL_APIC
for_each_clear_bit_from(i, used_vectors, NR_VECTORS)
    set_intr_gate(i, spurious_interrupt);
#endif
```

Where the `spurious_interrupt` function represent interrupt handler for the `spurious` interrupt. Here the `used_vectors` is the `unsigned long` that contains already initialized interrupt gates. We already filled first `32` interrupt vectors in the `trap_init` function from the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c) source code file:

```C
for (i = 0; i < FIRST_EXTERNAL_VECTOR; i++)
    set_bit(i, used_vectors);
```

You can remember how we did it in the sixth [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-6) of this chapter.

In the end of the `native_init_IRQ` function we can see the following check:

```C
if (!acpi_ioapic && !of_ioapic && nr_legacy_irqs())
	setup_irq(2, &irq2);
```

First of all let's deal with the condition. The `acpi_ioapic` variable represents existence of [I/O APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller#I.2FO_APICs). It defined in the [arch/x86/kernel/acpi/boot.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/acpi/boot.c). This variable set in the `acpi_set_irq_model_ioapic` function that called during the processing `Multiple APIC Description Table`. This occurs during initialization of the architecture-specific stuff in the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c) (more about it we will know in the other chapter about [APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller)). Note that the value of the `acpi_ioapic` variable depends on the `CONFIG_ACPI` and `CONFIG_X86_LOCAL_APIC` Linux kernel configuration options. If these options were not set, this variable will be just zero:

```C
#define acpi_ioapic 0
```

The second condition - `!of_ioapic && nr_legacy_irqs()` checks that we do not use [Open Firmware](https://en.wikipedia.org/wiki/Open_Firmware) `I/O APIC` and legacy interrupt controller. We already know about the `nr_legacy_irqs`. The second is `of_ioapic` variable defined in the [arch/x86/kernel/devicetree.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/devicetree.c) and initialized in the `dtb_ioapic_setup` function that build information about `APICs` in the [devicetree](https://en.wikipedia.org/wiki/Device_tree). Note that `of_ioapic` variable depends on the `CONFIG_OF` Linux kernel configuration option. If this option is not set, the value of the `of_ioapic` will be zero too:

```C
#ifdef CONFIG_OF
extern int of_ioapic;
...
...
...
#else
#define of_ioapic 0
...
...
...
#endif
```

If the condition returns non-zero value we call the:

```C
setup_irq(2, &irq2);
```

function. First of all about the `irq2`. The `irq2` is the `irqaction` structure that defined in the [arch/x86/kernel/irqinit.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/irqinit.c) source code file and represents `IRQ 2` line that is used to query devices connected cascade:

```C
static struct irqaction irq2 = {
	.handler = no_action,
    .name = "cascade",
    .flags = IRQF_NO_THREAD,
};
```

Some time ago interrupt controller consisted of two chips and one was connected to second. The second chip that was connected to the first chip via this `IRQ 2` line. This chip serviced lines from `8` to `15` and after this lines of the first chip. So, for example [Intel 8259A](https://en.wikipedia.org/wiki/Intel_8259) has following lines:

* `IRQ 0`  - system time;
* `IRQ 1`  - keyboard;
* `IRQ 2`  - used for devices which are cascade connected;
* `IRQ 8`  - [RTC](https://en.wikipedia.org/wiki/Real-time_clock);
* `IRQ 9`  - reserved;
* `IRQ 10` - reserved;
* `IRQ 11` - reserved;
* `IRQ 12` - `ps/2` mouse;
* `IRQ 13` - coprocessor;
* `IRQ 14` - hard drive controller;
* `IRQ 1`  - reserved;
* `IRQ 3`  - `COM2` and `COM4`;
* `IRQ 4`  - `COM1` and `COM3`;
* `IRQ 5`  - `LPT2`;
* `IRQ 6`  - drive controller;
* `IRQ 7`  - `LPT1`.

The `setup_irq` function is defined in the [kernel/irq/manage.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/irq/manage.c) and takes two parameters:

* vector number of an interrupt;
* `irqaction` structure related with an interrupt.

This function initializes interrupt descriptor from the given vector number at the beginning:

```C
struct irq_desc *desc = irq_to_desc(irq);
```

And call the `__setup_irq` function that sets up given interrupt:

```C
chip_bus_lock(desc);
retval = __setup_irq(irq, desc, act);
chip_bus_sync_unlock(desc);
return retval;
```

Note that the interrupt descriptor is locked during `__setup_irq` function will work. The `__setup_irq` function does many different things: it creates a handler thread when a thread function is supplied and the interrupt does not nest into another interrupt thread, sets the flags of the chip, fills the `irqaction` structure and many many more.

All of the above it creates `/prov/vector_number` directory and fills it, but if you are using modern computer all values will be zero there:

```
$ cat /proc/irq/2/node
0

$cat /proc/irq/2/affinity_hint
00

cat /proc/irq/2/spurious
count 0
unhandled 0
last_unhandled 0 ms
```

because probably `APIC` handles interrupts on the machine.

That's all.

Conclusion
--------------------------------------------------------------------------------

It is the end of the eighth part of the [Interrupts and Interrupt Handling](https://0xax.gitbook.io/linux-insides/summary/interrupts) chapter and we continued to dive into external hardware interrupts in this part. In the previous part we started to do it and saw early initialization of the `IRQs`. In this part we already saw non-early interrupts initialization in the `init_IRQ` function. We saw initialization of the `vector_irq` per-cpu array which is store vector numbers of the interrupts and will be used during interrupt handling and initialization of other stuff which is related to the external hardware interrupts.

In the next part we will continue to learn interrupts handling related stuff and will see initialization of the `softirqs`.

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [IRQ](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29)
* [percpu](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [Intel 8259](https://en.wikipedia.org/wiki/Intel_8259)
* [Programmable Interrupt Controller](https://en.wikipedia.org/wiki/Programmable_Interrupt_Controller)
* [ISA](https://en.wikipedia.org/wiki/Industry_Standard_Architecture)
* [MultiProcessor Configuration Table](https://en.wikipedia.org/wiki/MultiProcessor_Specification)
* [Local APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller#Integrated_local_APICs)
* [I/O APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller#I.2FO_APICs)
* [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing)
* [Inter-processor interrupt](https://en.wikipedia.org/wiki/Inter-processor_interrupt)
* [ternary operator](https://en.wikipedia.org/wiki/Ternary_operation)
* [gcc](https://en.wikipedia.org/wiki/GNU_Compiler_Collection)
* [calling convention](https://en.wikipedia.org/wiki/X86_calling_conventions)
* [PDF. System V Application Binary Interface AMD64](http://x86-64.org/documentation/abi.pdf)
* [Call stack](https://en.wikipedia.org/wiki/Call_stack)
* [Open Firmware](https://en.wikipedia.org/wiki/Open_Firmware)
* [devicetree](https://en.wikipedia.org/wiki/Device_tree)
* [RTC](https://en.wikipedia.org/wiki/Real-time_clock)
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-7)
