Interrupts and Interrupt Handling. Part 1.
================================================================================

Introduction
--------------------------------------------------------------------------------

This is the first part of new the chapter of the [linux insides](http://0xax.gitbooks.io/linux-insides/content/) book. We have come a long way in the previous [chapter](http://0xax.gitbooks.io/linux-insides/content/Initialization/index.html) of this book. We started from the earliest [steps](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-1.html) of kernel initialization and finished with the [launch](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-10.html) of the first `init` process. Yes, we saw many different initialization steps which are related to the different kernel subsystems. But we did not deep into details about these subsystems. Since this chapter, we will try to understand how different kernel subsytems work and how they are implemented. As you already can understand from the chapter's title, the first subsytem will be [interrupts](http://en.wikipedia.org/wiki/Interrupt).

What is it interrupt?
--------------------------------------------------------------------------------

We already heard `interrupt` word in the different parts of this book and even saw a couple of examples of the interrupts handlers. In the current chapter we will start from the theory what are `interrupts` and what are `interrupts handlers` and will contiue to deep into details about `interrupts` and how the linux kernel handles it.

So..., First of all what is it interrupt? An interrupt is an `event` which needs in attention emitted by software or hardware. So, for example we press a button on the keyboard and what is the next? What operating system and computer must to do after this? Each device has interrupt line. A device can use it to signal a CPU about interrupt. But interrupts do not fall directly to the CPU. In the old machines there was a [PIC](http://en.wikipedia.org/wiki/Programmable_Interrupt_Controller) which is a chip  responsible for sequential processing interrupt requests from different devices. In the new machines there is [Advanced Programmable Interrupt Controller](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller) or how we will call it next - `APIC`. An `APIC` controller consists from two separate devices:

* `Local APIC`
* `I/O APIC`

The first - `Local APIC` locates on the each CPU core. The local APIC is responsible for the handling cpu-specific interrupt configuration. Local APIC can recive interrupts from the APIC timer generated interrupts, thermal sensor interrupts, locally connected I/O devices and etc... The second - `I/O APIC` provides multi-processor interrupt management and used to distribute external interrupts. More about the local and I/O APICs we will know in the next parts of this chapter. As you can understand, interrupts can occur in any time. When an interrupt occurs operating system kernel must handle it. But what is it `to handle interrupt`? When an interrupt occurs operating system must:

* kernel must stop execution of the current process;
* kernel searches handler for the interrupt and transfers control to it; 
* after an interrupt handler finished its work, processor must regain control of the interrupted process;

of course there are many different details behind this like priority of interrupts and many other details, but in general these three points are main.

Address of the interrupts handlers are stored in the special system table called - `Interrupt Descriptor Table` or `IDT`. The processor uses an unique number for recognizing the type of interruption or exception. This number is called - `vector number`. A vector number is an index in the `IDT`. There is limited amount of the verctor numbers and it can be from `0` to `255`. You can note the check of the vector number in the linux kernel source code:

```C
BUG_ON((unsigned)n > 0xFF);
```

You can find this check in the linux kernel source code which is related to the interrupts setup (for example you can find it in the `set_intr_gate` macro, `void set_system_intr_gate` and etc... from the [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/desc.h)). First 32 vector numbers from `0` to `31` are reserved by the processor and used for the architecture-defined exceptions and interrupts. You can find table with the description of these verctor numbers in the second part of the linux kernel initialization process - [Early interrupt and exception handling](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-2.html). Vector numbers from `32` to `255` are designated as user-defined interrupts and are not reserved by the processor. These interrupts are generally assigned to external I/O devices to enable those devices to send interrupts to the processor.

Now let's talk about interrupts and its types. We can split interrupts on two big classes:

* External or hardware generated interrupts;
* Software-generated interrupts.

The first - external interrupts are received through the `Local APIC` or pins on the processor which are connected to the `Local APIC`. The second - software-generated interrupts are caused by the exceptional condition in the processor itself or with the special architecture-specific instruction. For example it can be division by zero in the first case and exit from a program with the `syscall` instruction.

There is additional view of an interrupt - `exception`. As I wrote above, an interrupts can occur at any time for a reason the code and CPU has no control over. Exceptions are `synchronous` with program execution and can be splitted on three leves:

* `faults`;
* `traps`;
* `aborts`.

A `fault` is exceptions that can be corrected. And if it corrected, it allows the program to be restarted. A `trap` is an exception which reported immediately following the execution of the `trap` instruction. Traps allow execution of a program to be continued too as it a `fault` does, but with loss of continuty. And an `boort` is an exception that does not always report location of the instruction which caused the execption and does not allow to restart a program.

Also we already know from the previous [part](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-3.html) that interrupts can be `maskable` and `non-maskable`. A maskable interrupts are interrupts which can be banned with the two following instructions for `x86_64` - `sti` and `cli`. We can find they in the linux kernel source code:

```C
static inline void native_irq_disable(void)
{
        asm volatile("cli": : :"memory");
}
```

and

```C
static inline void native_irq_enable(void)
{
        asm volatile("sti": : :"memory");
}
```

These two instructions affects on the `IF` bit from the register flag. The `sti` instruction sets the `IF` flag and the `cli` instruction clears this flag. Non-maskable interrupts are always processed. For example such interrupt can be caused by a failure in a hardware.

If more than one exception or interrupt are occured in the same time, the processor handles them by the predifined priority. We can see priorities from the highest to lowest in the following table:

```
+----------------------------------------------------------------+
|              |                                                 |
|   Priority   | Description                                     |
|              |                                                 |
+--------------+-------------------------------------------------+
|              | Hardware Reset and Machine Checks               |
|     1        | - RESET                                         |
|              | - Machine Check                                 |
+--------------+-------------------------------------------------+
|              | Trap on Task Switch                             |
|     2        | - T flag in TSS is set                          |
|              |                                                 |
+--------------+-------------------------------------------------+
|              | External Hardware Interventions                 |
|              | - FLUSH                                         |
|     3        | - STOPCLK                                       |
|              | - SMI                                           |
|              | - INIT                                          |
+--------------+-------------------------------------------------+
|              | Traps on the Previous Instruction               |
|     4        | - Breakpoints                                   |
|              | - Debug Trap Exceptions                         |
+--------------+-------------------------------------------------+
|     5        | Nonmaskable Interrupts                          |
+--------------+-------------------------------------------------+
|     6        | Maskable Hardware Interrupts                    |
+--------------+-------------------------------------------------+
|     7        | Code Breakpoint Fault                           |
+--------------+-------------------------------------------------+
|     8        | Faults from Fetching Next Instruction           |
|              | Code-Segment Limit Violation                    |
|              | Code Page Fault                                 |
+--------------+-------------------------------------------------+
|              | Faults from Decoding the Next Instruction       |
|              | Instruction length > 15 bytes                   |
|     9        | Invalid Opcode                                  |
|              | Coprocessor Not Available                       |
|              |                                                 |
+--------------+-------------------------------------------------+
|     10       | Faults on Executing an Instruction              |
|              | Overflow                                        |
|              | Bound error                                     |
|              | Invalid TSS                                     |
|              | Segment Not Present                             |
|              | Stack fault                                     |
|              | General Protection                              |
|              | Data Page Fault                                 |
|              | Alignment Check                                 |
|              | x87 FPU Floating-point exception                |
|              | SIMD floating-point exception                   |
|              | Virtualization exception                        |
+--------------+-------------------------------------------------+
```

Now we know a little about different types of the interrupts and exceptions, it means that it is time to move on to a more practical part. We start with the description of the `Interrupt Descriptor Table`. I already wrote above that `IDT` stores entry points of the interrupts and exceptions handlers. The `IDT` is similar by structure to the `Global Descriptior Table` which we saw in the second part of the [Kernel booting process](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-2.html). But of course it has some differences. Instead of `descriptors`, the `IDT` entries are called `gates`. It can contain one of the following gates:

* interrupt gates;
* task gates;
* trap gates.

in the `x86`. Only [long mode](http://en.wikipedia.org/wiki/Long_mode) interrupt gates and trap gates can be referenced in the `x86_64`. Like the `Global Descriptor Table`, the `Interrupt Descriptor table` is an array of the 8-bytes gates in the `x86` and an array of the 16-bytes gates in the `x86_64`. We can remember from the second part of the [Kernel booting process](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-2.html), that `Global Descriptor Table` must contain `NULL` descriptor in the first element of array. Unlike the `Global Descriptor Table`, the `Interrupt Descriptor Table` may contain a gate. But it is not necessary. For example you can remember as we have loaded Interrupt Descriptor table only with the `NULL` gates in the earliest [part](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-3.html) about trqansition into [protected mode](http://en.wikipedia.org/wiki/Protected_mode):

```C
/*
 * Set up the IDT
 */
static void setup_idt(void)
{
	static const struct gdt_ptr null_idt = {0, 0};
	asm volatile("lidtl %0" : : "m" (null_idt));
}
```

from the [arch/x86/boot/pm.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/pm.c). The `Interrupt Descriptor table` can be located anywhere in the linear address space and the base address of it must be aligned on an 8-byte boundary in the `x86` or 16-byte bounday in the `x86_64`. Base address of the `IDT` is stored in the special register which is called - `IDTR`. There are two instructions in the `x86` compatible processors to control `IDTR` register:

* `LIDT`
* `SIDT`

The first instruction is for loads base address of the `IDT` to the `IDTR` and the second `SIDT` instruction stores the contents of the `IDTR`. The `IDTR` register is 48-bytes size in the `x86` and contains following information:

```
+-----------------------------------+----------------------+
|                                   |                      |
|     Base address of the IDT       |   Limit of the IDT   |
|                                   |                      |
+-----------------------------------+----------------------+
47                                16 15                    0
```

You can see in the code above (look on the `setup_idt` function implementation) that we filled `null_idt` and load it to the `IDTR` register with the `lidt` instruction. Note that `null_idt` has `gdt_ptr` type which is defined as:

```C
struct gdt_ptr {
        u16 len;
        u32 ptr;
} __attribute__((packed));
```

Here we can see definition of the structure with the two fields with 2-bytes and 4-bytes sizes or 48-bytes structure as we can see it on the diagram. Now let's look on the `IDT` entries structure. As I already wrote above, `IDT` is an array of the 16-byte entries which are called gates in the `x86_64`. They have following structure:

```
127                                                                             96
+-------------------------------------------------------------------------------+
|                                                                               |
|                                Reserved                                       |
|                                                                               |
+--------------------------------------------------------------------------------
95                                                                              64
+-------------------------------------------------------------------------------+
|                                                                               |
|                               Offset 63..32                                   |
|                                                                               |
+-------------------------------------------------------------------------------+
63                               48 47      46  44   42    39             34    32
+-------------------------------------------------------------------------------+
|                                  |       |  D  |   |     |      |   |   |     |
|       Offset 31..16              |   P   |  P  | 0 |Type |0 0 0 | 0 | 0 | IST |
|                                  |       |  L  |   |     |      |   |   |     |
 -------------------------------------------------------------------------------+
31                                   16 15                                      0
+-------------------------------------------------------------------------------+
|                                      |                                        |
|          Segment Selector            |                 Offset 15..0           |
|                                      |                                        |
+-------------------------------------------------------------------------------+
```

To form an index into the IDT, the processor scales the exception or interrupt vector by sixteen. The processor handles appearance of an exception and an interrupt in the similar way as it handles calls  of a procedure or a task when it sees `call` instruction. A processor uses an unique number or `vector number` of the interrupt or the exception as index to find the necessary `Interrupt Descriptor Table` entry. Now let's take a closer look on a `IDT` entry.

As we can see, `IDT` entry on the diagram consists from the following fields:

* `0-15` bits  - offset from the segment selector which is used by the processor as base address of the entry point of the interrupt handler;
* `16-31` bits - base address of the segment select which contains entry pint of the interrupt handler;
* `IST` - new special mechanism in the `x86_64`, will see it later; 
* `DPL` - Descriptor Privilege Level;
* `P` - Segment Present flag;
* `48-63` bits - second part of the handler base address;
* `64-95` bits - third part of the base address of the handler;
* `96-127` bits - and the last bits are reserved by the CPU.

And the last `Type` field describes type of the `IDT` entry. There are three different kinds of handlers for interrupts:

* Interrupt gate
* Trap gate

The `IST` or `Interrupt Stack Table` is a new mechanism in the `x86_64`. It used as an alternative to the the legacy stack-switch mechanism. Previously The `x86` architecture provided a mechanism to automatically switch stack frames in response to an interrupt. The `IST` is a modified version of the `x86` Stack switching mode. This mechanism unconditionally switches stacks when it is enabled and can be enabled for an any interrupt in the `IDT` entry related with the certain interrupt (soon we will see it). From this we can understand that `IST` is not necessary for the all interrupts, but some interrupts can use old legacy stack switching mode. The `IST` mechanism provides up to seven `IST` pointers in the [Task State Segement](http://en.wikipedia.org/wiki/Task_state_segment) or `TSS` which is the special structure which contains information about a process. The `TSS` is used for stack switching during and interrupt or an exception handling in the linux kernel. Each pointer referenced by an interrupt gate from the `IDT`.

The `Interrupt Descriptor Table` represented by the array of the `gate_desc` structures:

```C
extern gate_desc idt_table[];
```

where `gate_desc` is:

```C
#ifdef CONFIG_X86_64
...
...
...
typedef struct gate_struct64 gate_desc;
...
...
...
#endif
```

and `gate_struct64` defined as:

```C
struct gate_struct64 {
        u16 offset_low;
        u16 segment;
        unsigned ist : 3, zero0 : 5, type : 5, dpl : 2, p : 1;
        u16 offset_middle;
        u32 offset_high;
        u32 zero1;
} __attribute__((packed));
```

Each active thread has a very big stack in the linux kernel for the `x86_64` architecture. The stack size is defined as `THREAD_SIZE` and equal to the:

```C
#define PAGE_SHIFT      12
#define PAGE_SIZE       (_AC(1,UL) << PAGE_SHIFT)
...
...
...
#define THREAD_SIZE_ORDER       (2 + KASAN_STACK_ORDER)
#define THREAD_SIZE  (PAGE_SIZE << THREAD_SIZE_ORDER)
```

The `PAGE_SIZE` is `4096` and the `THREAD_SIZE_ORDER` depends on the `KASAN_STACK_ORDER`. As we can see, the `KASAN_STACK` depends on the `CONFIG_KASAN` kernel configuration parameter and equal to the: 

```C
#ifdef CONFIG_KASAN
    #define KASAN_STACK_ORDER 1
#else
    #define KASAN_STACK_ORDER 0
#endif
```

`KASan` is a runtime memory [debugger](http://lwn.net/Articles/618180/). So... the `THREAD_SIZE` will be `16384` bytes if `CONFIG_KASAN` is disabled or `32768` if this kernel configuration option is enabled. These stacks contain useful data as long as a thread is alive or in zombie state. While the thread is in user space the kernel stack is empty except for the `thread_info` (some details about this structure you can find in the fourth [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-4.html) about linux kernel initialization process) structure at the bottom of the stack. Not only active or zombie threads have own stack. There are also specialized stacks which are associated with the each available CPU and these stacks are active when the kernel is under control on that CPU. When a CPU in the user space, these stacks do not contain any useful information too. Each CPU has amount of the special per-cpu stack. The first is `interrupt stack` used for the external hardware interrupts. Its size is:

```C
#define IRQ_STACK_ORDER (2 + KASAN_STACK_ORDER)
#define IRQ_STACK_SIZE (PAGE_SIZE << IRQ_STACK_ORDER)
```

or `16384` bytes too. The per-cpu interrupt stack represented by the `irq_stack_union` unioun in the linux kernel for `x86_64`:

```C
union irq_stack_union {
	char irq_stack[IRQ_STACK_SIZE];

    struct {
		char gs_base[40];
		unsigned long stack_canary;
	};
};
```

The first `irq_stack` field is an 16 killobytes array which is directly stack. Also you can see that `irq_stack_union` contains structure with the two fields:

* `gs_base` - actually `gs` register always points to the bottom of the `irqstack` union. On the `x86_64`, the `gs` register is shared by percpu area and stack canary (more about `percpu` variables you can read in the special [part](http://0xax.gitbooks.io/linux-insides/content/Concepts/per-cpu.html)).  All percpu symbols are zero based and the `gs` points to the base of percpu area. You already know that [segmented memory model](http://en.wikipedia.org/wiki/Memory_segmentation) abolished in the long mode, but we can set base address for the two segment registers - `fs` and `gs` with the [Model specific registers](http://en.wikipedia.org/wiki/Model-specific_register) and these registers can be still used as kind of address registers. If you remember the first [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-1.html) of the linux kernel initialization process, you can remember that we have set the `gs` register:

```assembly
	movl	$MSR_GS_BASE,%ecx
	movl	initial_gs(%rip),%eax
	movl	initial_gs+4(%rip),%edx
	wrmsr
```

where `initial_gs` points to the `irq_stack_union`:

```assembly
GLOBAL(initial_gs)
.quad	INIT_PER_CPU_VAR(irq_stack_union)
```
    
* `stack_canary` - [Stack canary](http://en.wikipedia.org/wiki/Stack_buffer_overflow#Stack_canaries) for the interrupt stack. We need in `stack protector`
to protect our stack and verify that it hasn't been overwritten. Note that `gs_base` is an 40 bytes array. `GCC` requires that stack canary will be on the fixed offset from the base of the `gs` and its value must be `40` for the `x86_64` and `20` for the `x86`.

The `irq_stack_union` is the first data in the `percpu` area, we can see it in the `System.map`:

```
0000000000000000 D __per_cpu_start
0000000000000000 D irq_stack_union
0000000000004000 d exception_stacks
0000000000009000 D gdt_page
...
...
...
```

We can see its definition in the code:

```C
DECLARE_PER_CPU_FIRST(union irq_stack_union, irq_stack_union) __visible;
```

Now, time to look on the initialization of the `irq_stack_union`. First of all besides the `irq_stack_union` definition, we can see the definition of the following per-cpu variables in the [arch/x86/include/asm/processor.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/processor.h):

```C
DECLARE_PER_CPU(char *, irq_stack_ptr);
DECLARE_PER_CPU(unsigned int, irq_count);
```

The first is the `irq_stack_ptr` and as you can understand from the variable's name, it is pointer to the top of the stack. The second - `irq_count` is used to check if a CPU is already on an interrupt stack or not. Initialization of the `irq_stack_ptr` is located in the `setup_per_cpu_areas` function from the [arch/x86/kernel/setup_percpu.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup_percpu.c):

```C
void __init setup_per_cpu_areas(void)
{
...
...
#ifdef CONFIG_X86_64
for_each_possible_cpu(cpu) {
    ...
    ...
    ...
    per_cpu(irq_stack_ptr, cpu) =
            per_cpu(irq_stack_union.irq_stack, cpu) +
            IRQ_STACK_SIZE - 64;
    ...
    ...
    ...
#endif
...
...
}
```

Here we goes through all possobile cpu and setup `irq_stack_ptr`. As you can see it will be equal to the top of the interrupt stack minus `64`. Why `64` is here? If you remember, we set the stack canary in the beginning of the `start_kernel` function from the [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c) with the call of the `boot_init_stack_canary` function:

```C
static __always_inline void boot_init_stack_canary(void)
{
    u64 canary;
    ...
    ...
    ...

#ifdef CONFIG_X86_64
    BUILD_BUG_ON(offsetof(union irq_stack_union, stack_canary) != 40);
#endif
    //
    // getting canary value here
    //

    this_cpu_write(irq_stack_union.stack_canary, canary);
    ...
    ...
    ...
}
```

Note that `canary` is `64` bits value. That's why we need to substract `64` from the size of the interrupt stack to avoid stack canary value. Initialization of the `irq_stack_union.gs_base` is in the `load_percpu_segment` function from the [arch/x86/kernel/cpu/common.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/cpu/common.c):
TODO maybe more about the wrmsl
```C
void load_percpu_segment(int cpu)
{
        ...
        ...
        ...
        loadsegment(gs, 0);
        wrmsrl(MSR_GS_BASE, (unsigned long)per_cpu(irq_stack_union.gs_base, cpu));
}
```

and as we already know `gs` register points to the bottom of the interrupt stack:

```assembly
	movl	$MSR_GS_BASE,%ecx
	movl	initial_gs(%rip),%eax
	movl	initial_gs+4(%rip),%edx
	wrmsr	

	GLOBAL(initial_gs)
	.quad	INIT_PER_CPU_VAR(irq_stack_union)
```

Here we can see `wrmsr` instruction which loads data from the `edx:eax` into the [Model specific register](http://en.wikipedia.org/wiki/Model-specific_register) pointed by the `ecx` register. In our case model specific register is `MSR_GS_BASE` which contains the base address of the memory segment pointed by the `gs` register and `edx:eax` point to the address of the `initial_gs` which is base address of the our `irq_stack_union`.

We already know that `x86_64` has a feature called `Interrupt Stack Table` or `IST` and this feature provides ability to switch to a new stack for events non-maskable interrupt, double fault and etc... There can be up to seven `IST` entries per-cpu. They are:

* `DOUBLEFAULT_STACK`
* `NMI_STACK`
* `DEBUG_STACK`
* `MCE_STACK`

or

```C
#define DOUBLEFAULT_STACK 1
#define NMI_STACK 2
#define DEBUG_STACK 3
#define MCE_STACK 4
```

All interrupt-gate descriptors which switch to a new stack with the `IST` are initialized with the `set_intr_gate_ist` function. For example:

```C
set_intr_gate_ist(X86_TRAP_NMI, &nmi, NMI_STACK);
...
...
...
set_intr_gate_ist(X86_TRAP_DF, &double_fault, DOUBLEFAULT_STACK);
```

where `&nmi` and `&double_fault` are addresses of the entries to the given interrupts handlers:

```C
asmlinkage void nmi(void);
asmlinkage void double_fault(void);
```

and defined in the [arch/x86/kernel/entry_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/entry_64.S) 

```assembly
idtentry double_fault do_double_fault has_error_code=1 paranoid=2
...
...
...
ENTRY(nmi)
...
...
...
END(nmi)
```

When an interrupt or an exception occurs the new `ss` selector is forced to `NULL` and the `ss` selector’s `rpl` field is set to the new `cpl`. The old `ss`, `rsp`, register flags, `cs`, `rip` are pushed onto the new stack. 64-bit mode, the size of interrupt stack-frame pushes is fixed at eightbytes, so we will get following stack:

```
+---------------+
|               |
|      SS       | 40
|      RSP      | 32
|     RFLAGS    | 24
|      CS       | 16
|      RIP      | 8 
|   Error code  | 0
|               |
+---------------+ 
```

If `IST` field in interrupt gate is not `0`, we read `IST` pointer into the `rsp`. If the interrupt vector number has an error code associated with it, pushes the error code onto the stack. If the interrupt vector number has no an error code, anyway we push dummy error code to the stack. We need to do it for the stack consistency. After this we loads the segment-selector field from the gate descriptor into the CS register and processor must check that the target code-segment is a 64-bit mode code segment by the checking `21` bit or `L` bit in the `Global Descriptor Table`. In the last step we loads the offset field from the gate descriptor into the `rip` which will be entry of the interrupt handler. After this the interrupt handler begins execution. After an interrupt handler finished its execution, it must return control to the interrupted process with the `iret` instruction. The `iret` instruction pops the stack pointer (`ss:rsp`) only unconditionally and does not depend on the `cpl` change and restores the stack of the interrupted process. 

That's all.

Conclusion
--------------------------------------------------------------------------------

It is the end of the first part about interrupts and interrupt handling in the linux kernel. We saw the some theory and first steps of the initialization of the interrupts and exceptions related stuff. In the next part we will continue to dive into interrupts and interrupts handling, but there will be more practice.

If you will have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you will find any mistakes please send me PR to [linux-internals](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

* [Advanced Programmable Interrupt Controller](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller)
* [protected mode](http://en.wikipedia.org/wiki/Protected_mode)
* [long mode](http://en.wikipedia.org/wiki/Long_mode)
* [kernel stacks](https://www.kernel.org/doc/Documentation/x86/x86_64/kernel-stacks)
* [PIC](http://en.wikipedia.org/wiki/Programmable_Interrupt_Controller)
* [Advanced Programmable Interrupt Controller](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller)
* [long mode](http://en.wikipedia.org/wiki/Long_mode)
* [protected mode](http://en.wikipedia.org/wiki/Protected_mode)
* [Task State Segement](http://en.wikipedia.org/wiki/Task_state_segment)
* [segmented memory model](http://en.wikipedia.org/wiki/Memory_segmentation)
* [Model specific registers](http://en.wikipedia.org/wiki/Model-specific_register)
* [Stack canary](http://en.wikipedia.org/wiki/Stack_buffer_overflow#Stack_canaries)
* [Previous chapter](http://0xax.gitbooks.io/linux-insides/content/Initialization/index.html)
