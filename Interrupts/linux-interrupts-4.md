Interrupts and Interrupt Handling. Part 4.
================================================================================

Initialization of non-early interrupt gates
--------------------------------------------------------------------------------

This is fourth part about an interrupts and exceptions handling in the Linux kernel and in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-3) we saw first early `#DB` and `#BP` exceptions handlers from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). We stopped on the right after the `early_trap_init` function that called in the `setup_arch` function which defined in the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/setup.c). In this part we will continue to dive into an interrupts and exceptions handling in the Linux kernel for `x86_64` and continue to do it from the place where we left off in the last part. First thing which is related to the interrupts and exceptions handling is the setup of the `#PF` or [page fault](https://en.wikipedia.org/wiki/Page_fault) handler with the `early_trap_pf_init` function. Let's start from it.

Early page fault handler
--------------------------------------------------------------------------------

The `early_trap_pf_init` function defined in the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). It uses `set_intr_gate` macro that fills [Interrupt Descriptor Table](https://en.wikipedia.org/wiki/Interrupt_descriptor_table) with the given entry:

```C
void __init early_trap_pf_init(void)
{
#ifdef CONFIG_X86_64
         set_intr_gate(X86_TRAP_PF, page_fault);
#endif
}
```

This macro defined in the [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/tree/master/arch/x86/include/asm/desc.h). We already saw macros like this in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-3) - `set_system_intr_gate` and `set_intr_gate_ist`. This macro checks that given vector number is not greater than `255` (maximum vector number) and calls `_set_gate` function as `set_system_intr_gate` and `set_intr_gate_ist` did it:

```C
#define set_intr_gate(n, addr)                                  \
do {                                                            \
        BUG_ON((unsigned)n > 0xFF);                             \
        _set_gate(n, GATE_INTERRUPT, (void *)addr, 0, 0,        \
                  __KERNEL_CS);                                 \
        _trace_set_gate(n, GATE_INTERRUPT, (void *)trace_##addr,\
                        0, 0, __KERNEL_CS);                     \
} while (0)
```

The `set_intr_gate` macro takes two parameters:

* vector number of a interrupt;
* address of an interrupt handler;

In our case they are:

* `X86_TRAP_PF` - `14`;
* `page_fault` - the interrupt handler entry point.

The `X86_TRAP_PF` is the element of enum which defined in the [arch/x86/include/asm/traprs.h](https://github.com/torvalds/linux/tree/master/arch/x86/include/asm/traprs.h):

```C
enum {
	...
	...
	...
	...
	X86_TRAP_PF,            /* 14, Page Fault */
	...
	...
	...
}
```

When the `early_trap_pf_init` will be called, the `set_intr_gate` will be expanded to the call of the `_set_gate` which will fill the `IDT` with the handler for the page fault. Now let's look on the implementation of the `page_fault` handler. The `page_fault` handler defined in the [arch/x86/entry/entry_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/entry/entry_64.S) assembly source code file as all exceptions handlers. Let's look on it:

```assembly
trace_idtentry page_fault do_page_fault has_error_code=1
```

We saw in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-3) how `#DB` and `#BP` handlers defined. They were defined with the `idtentry` macro, but here we can see `trace_idtentry`. This macro defined in the same source code file and depends on the `CONFIG_TRACING` kernel configuration option:

```assembly
#ifdef CONFIG_TRACING
.macro trace_idtentry sym do_sym has_error_code:req
idtentry trace(\sym) trace(\do_sym) has_error_code=\has_error_code
idtentry \sym \do_sym has_error_code=\has_error_code
.endm
#else
.macro trace_idtentry sym do_sym has_error_code:req
idtentry \sym \do_sym has_error_code=\has_error_code
.endm
#endif
```

We will not dive into exceptions [Tracing](https://en.wikipedia.org/wiki/Tracing_%28software%29) now. If `CONFIG_TRACING` is not set, we can see that `trace_idtentry` macro just expands to the normal `idtentry`. We already saw implementation of the `idtentry` macro in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-3), so let's start from the `page_fault` exception handler.

As we can see in the `idtentry` definition, the handler of the `page_fault` is `do_page_fault` function which defined in the [arch/x86/mm/fault.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/mm/fault.c) and as all exceptions handlers it takes two arguments:

* `regs` - `pt_regs` structure that holds state of an interrupted process;
* `error_code` - error code of the page fault exception.

Let's look inside this function. First of all we read content of the [cr2](https://en.wikipedia.org/wiki/Control_register) control register:

```C
dotraplinkage void notrace
do_page_fault(struct pt_regs *regs, unsigned long error_code)
{
	unsigned long address = read_cr2();
	...
	...
	...
}
```

This register contains a linear address which caused `page fault`. In the next step we make a call of the `exception_enter` function from the [include/linux/context_tracking.h](https://github.com/torvalds/linux/blob/master/include/linux/context_tracking.h). The `exception_enter` and `exception_exit` are functions from context tracking subsystem in the Linux kernel used by the [RCU](https://en.wikipedia.org/wiki/Read-copy-update) to remove its dependency on the timer tick while a processor runs in userspace. Almost in every exception handler we will see similar code:

```C
enum ctx_state prev_state;
prev_state = exception_enter();
...
... // exception handler here
...
exception_exit(prev_state);
```

The `exception_enter` function checks that `context tracking` is enabled with the `context_tracking_is_enabled` and if it is in enabled state, we get previous context with the `this_cpu_read` (more about `this_cpu_*` operations you can read in the [Documentation](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/Documentation/this_cpu_ops.txt)). After this it calls `context_tracking_user_exit` function which informs the context tracking that the processor is exiting userspace mode and entering the kernel:

```C
static inline enum ctx_state exception_enter(void)
{
        enum ctx_state prev_ctx;

        if (!context_tracking_is_enabled())
                return 0;

        prev_ctx = this_cpu_read(context_tracking.state);
        context_tracking_user_exit();

        return prev_ctx;
}
```

The state can be one of the:

```C
enum ctx_state {
    IN_KERNEL = 0,
	IN_USER,
} state;
```

And in the end we return previous context. Between the `exception_enter` and `exception_exit` we call actual page fault handler:

```C
__do_page_fault(regs, error_code, address);
```

The `__do_page_fault` is defined in the same source code file as `do_page_fault` - [arch/x86/mm/fault.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/mm/fault.c). In the beginning of the `__do_page_fault` we check state of the [kmemcheck](https://www.kernel.org/doc/Documentation/kmemcheck.txt) checker. The `kmemcheck` detects warns about some uses of uninitialized memory. We need to check it because page fault can be caused by kmemcheck:

```C
if (kmemcheck_active(regs))
		kmemcheck_hide(regs);
	prefetchw(&mm->mmap_sem);
```

After this we can see the call of the `prefetchw` which executes instruction with the same [name](http://www.felixcloutier.com/x86/PREFETCHW.html) which fetches [X86_FEATURE_3DNOW](https://en.wikipedia.org/?title=3DNow!) to get exclusive [cache line](https://en.wikipedia.org/wiki/CPU_cache). The main purpose of prefetching is to hide the latency of a memory access. In the next step we check that we got page fault not in the kernel space with the following condition:

```C
if (unlikely(fault_in_kernel_space(address))) {
...
...
...
}
```

where `fault_in_kernel_space` is:

```C
static int fault_in_kernel_space(unsigned long address)
{
        return address >= TASK_SIZE_MAX;
}
```

The `TASK_SIZE_MAX` macro expands to the:

```C
#define TASK_SIZE_MAX   ((1UL << 47) - PAGE_SIZE)
```

or `0x00007ffffffff000`. Pay attention on `unlikely` macro. There are two macros in the Linux kernel:

```C
#define likely(x)      __builtin_expect(!!(x), 1)
#define unlikely(x)    __builtin_expect(!!(x), 0)
```

You can [often](http://lxr.free-electrons.com/ident?i=unlikely) find these macros in the code of the Linux kernel. Main purpose of these macros is optimization. Sometimes this situation is that we need to check the condition of the code and we know that it will rarely be `true` or `false`. With these macros we can tell to the compiler about this. For example

```C
static int proc_root_readdir(struct file *file, struct dir_context *ctx)
{
        if (ctx->pos < FIRST_PROCESS_ENTRY) {
                int error = proc_readdir(file, ctx);
                if (unlikely(error <= 0))
                        return error;
...
...
...
}
```

Here we can see `proc_root_readdir` function which will be called when the Linux [VFS](https://en.wikipedia.org/wiki/Virtual_file_system) needs to read the `root` directory contents. If condition marked with `unlikely`, compiler can put `false` code right after branching. Now let's back to the our address check. Comparison between the given address and the `0x00007ffffffff000` will give us to know, was page fault in the kernel mode or user mode. After this check we know it. After this `__do_page_fault` routine will try to understand the problem that provoked page fault exception and then will pass address to the appropriate routine. It can be `kmemcheck` fault, spurious fault, [kprobes](https://www.kernel.org/doc/Documentation/kprobes.txt) fault and etc. Will not dive into implementation details of the page fault exception handler in this part, because we need to know many different concepts which are provided by the Linux kernel, but will see it in the chapter about the [memory management](https://0xax.gitbook.io/linux-insides/summary/mm) in the Linux kernel.

Back to start_kernel
--------------------------------------------------------------------------------

There are many different function calls after the `early_trap_pf_init` in the `setup_arch` function from different kernel subsystems, but there are no one interrupts and exceptions handling related. So, we have to go back where we came from - `start_kernel` function from the [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c#L492). The first things after the `setup_arch` is the `trap_init` function from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). This function makes initialization of the remaining exceptions handlers (remember that we already setup 3 handlers for the `#DB` - debug exception, `#BP` - breakpoint exception and `#PF` - page fault exception). The `trap_init` function starts from the check of the [Extended Industry Standard Architecture](https://en.wikipedia.org/wiki/Extended_Industry_Standard_Architecture):

```C
#ifdef CONFIG_EISA
        void __iomem *p = early_ioremap(0x0FFFD9, 4);

        if (readl(p) == 'E' + ('I'<<8) + ('S'<<16) + ('A'<<24))
                EISA_bus = 1;
        early_iounmap(p, 4);
#endif
```

Note that it depends on the `CONFIG_EISA` kernel configuration parameter which represents `EISA` support. Here we use `early_ioremap` function to map `I/O` memory on the page tables. We use `readl` function to read first `4` bytes from the mapped region and if they are equal to `EISA` string we set `EISA_bus` to one. In the end we just unmap previously mapped region. More about `early_ioremap` you can read in the part which describes [Fix-Mapped Addresses and ioremap](https://0xax.gitbook.io/linux-insides/summary/mm/linux-mm-2).

After this we start to fill the `Interrupt Descriptor Table` with the different interrupt gates. First of all we set `#DE` or `Divide Error` and `#NMI` or `Non-maskable Interrupt`:

```C
set_intr_gate(X86_TRAP_DE, divide_error);
set_intr_gate_ist(X86_TRAP_NMI, &nmi, NMI_STACK);
```

We use `set_intr_gate` macro to set the interrupt gate for the `#DE` exception and `set_intr_gate_ist` for the `#NMI`. You can remember that we already used these macros when we have set the interrupts gates for the page fault handler, debug handler and etc, you can find explanation of it in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-3). After this we setup exception gates for the following exceptions:

```C
set_system_intr_gate(X86_TRAP_OF, &overflow);
set_intr_gate(X86_TRAP_BR, bounds);
set_intr_gate(X86_TRAP_UD, invalid_op);
set_intr_gate(X86_TRAP_NM, device_not_available);
```

Here we can see:

* `#OF` or `Overflow` exception. This exception indicates that an overflow trap occurred when an special [INTO](http://x86.renejeschke.de/html/file_module_x86_id_142.html) instruction was executed;
* `#BR` or `BOUND Range exceeded` exception. This exception indicates that a `BOUND-range-exceed` fault occurred when a [BOUND](http://pdos.csail.mit.edu/6.828/2005/readings/i386/BOUND.htm) instruction was executed;
* `#UD` or `Invalid Opcode` exception. Occurs when a processor attempted to execute invalid or reserved [opcode](https://en.wikipedia.org/?title=Opcode), processor attempted to execute instruction with invalid operand(s) and etc;
* `#NM` or `Device Not Available` exception. Occurs when the processor tries to execute `x87 FPU` floating point instruction while `EM` flag in the [control register](https://en.wikipedia.org/wiki/Control_register#CR0) `cr0` was set.

In the next step we set the interrupt gate for the `#DF` or `Double fault` exception:

```C
set_intr_gate_ist(X86_TRAP_DF, &double_fault, DOUBLEFAULT_STACK);
```

This exception occurs when processor detected a second exception while calling an exception handler for a prior exception. In usual way when the processor detects another exception while trying to call an exception handler, the two exceptions can be handled serially. If the processor cannot handle them serially, it signals the double-fault or `#DF` exception.

The following set of the interrupt gates is:

```C
set_intr_gate(X86_TRAP_OLD_MF, &coprocessor_segment_overrun);
set_intr_gate(X86_TRAP_TS, &invalid_TSS);
set_intr_gate(X86_TRAP_NP, &segment_not_present);
set_intr_gate_ist(X86_TRAP_SS, &stack_segment, STACKFAULT_STACK);
set_intr_gate(X86_TRAP_GP, &general_protection);
set_intr_gate(X86_TRAP_SPURIOUS, &spurious_interrupt_bug);
set_intr_gate(X86_TRAP_MF, &coprocessor_error);
set_intr_gate(X86_TRAP_AC, &alignment_check);
```

Here we can see setup for the following exception handlers:

* `#CSO` or `Coprocessor Segment Overrun` - this exception indicates that math [coprocessor](https://en.wikipedia.org/wiki/Coprocessor) of an old processor detected a page or segment violation. Modern processors do not generate this exception
* `#TS` or `Invalid TSS` exception - indicates that there was an error related to the [Task State Segment](https://en.wikipedia.org/wiki/Task_state_segment).
* `#NP` or `Segment Not Present` exception indicates that the `present flag` of a segment or gate descriptor is clear during attempt to load one of `cs`, `ds`, `es`, `fs`, or `gs` register.
* `#SS` or `Stack Fault` exception indicates one of the stack related conditions was detected, for example a not-present stack segment is detected when attempting to load the `ss` register.
* `#GP` or `General Protection` exception indicates that the processor detected one of a class of protection violations called general-protection violations. There are many different conditions that can cause general-protection exception. For example loading the `ss`, `ds`, `es`, `fs`, or `gs` register with a segment selector for a system segment, writing to a code segment or a read-only data segment, referencing an entry in the `Interrupt Descriptor Table` (following an interrupt or exception) that is not an interrupt, trap, or task gate and many many more.
* `Spurious Interrupt` - a hardware interrupt that is unwanted.
* `#MF` or `x87 FPU Floating-Point Error` exception caused when the [x87 FPU](https://en.wikipedia.org/wiki/X86_instruction_listings#x87_floating-point_instructions) has detected a floating point error.
* `#AC` or `Alignment Check` exception Indicates that the processor detected an unaligned memory operand when alignment checking was enabled.

After that we setup this exception gates, we can see setup of the `Machine-Check` exception:

```C
#ifdef CONFIG_X86_MCE
	set_intr_gate_ist(X86_TRAP_MC, &machine_check, MCE_STACK);
#endif
```

Note that it depends on the `CONFIG_X86_MCE` kernel configuration option and indicates that the processor detected an internal [machine error](https://en.wikipedia.org/wiki/Machine-check_exception) or a bus error, or that an external agent detected a bus error. The next exception gate is for the [SIMD](https://en.wikipedia.org/?title=SIMD) Floating-Point exception:

```C
set_intr_gate(X86_TRAP_XF, &simd_coprocessor_error);
```

which indicates the processor has detected an `SSE` or `SSE2` or `SSE3` SIMD floating-point exception. There are six classes of numeric exception conditions that can occur while executing an SIMD floating-point instruction:

* Invalid operation
* Divide-by-zero
* Denormal operand
* Numeric overflow
* Numeric underflow
* Inexact result (Precision)

In the next step we fill the `used_vectors` array which defined in the [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/tree/master/arch/x86/include/asm/desc.h) header file and represents `bitmap`:

```C
DECLARE_BITMAP(used_vectors, NR_VECTORS);
```

of the first `32` interrupts (more about bitmaps in the Linux kernel you can read in the part which describes [cpumasks and bitmaps](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-2))

```C
for (i = 0; i < FIRST_EXTERNAL_VECTOR; i++)
	set_bit(i, used_vectors)
```

where `FIRST_EXTERNAL_VECTOR` is:

```C
#define FIRST_EXTERNAL_VECTOR           0x20
```

After this we setup the interrupt gate for the `ia32_syscall` and add `0x80` to the `used_vectors` bitmap:

```C
#ifdef CONFIG_IA32_EMULATION
        set_system_intr_gate(IA32_SYSCALL_VECTOR, ia32_syscall);
        set_bit(IA32_SYSCALL_VECTOR, used_vectors);
#endif
```

There is `CONFIG_IA32_EMULATION` kernel configuration option on `x86_64` Linux kernels. This option provides ability to execute 32-bit processes in compatibility-mode. In the next parts we will see how it works, in the meantime we need only to know that there is yet another interrupt gate in the `IDT` with the vector number `0x80`. In the next step we maps `IDT` to the fixmap area:

```C
__set_fixmap(FIX_RO_IDT, __pa_symbol(idt_table), PAGE_KERNEL_RO);
idt_descr.address = fix_to_virt(FIX_RO_IDT);
```

and write its address to the `idt_descr.address` (more about fix-mapped addresses you can read in the second part of the [Linux kernel memory management](https://0xax.gitbook.io/linux-insides/summary/mm/linux-mm-2) chapter). After this we can see the call of the `cpu_init` function that defined in the [arch/x86/kernel/cpu/common.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/cpu/common.c). This function makes initialization of the all `per-cpu` state. In the beginning of the `cpu_init` we do the following things: First of all we wait while current cpu is initialized and than we call the `cr4_init_shadow` function which stores shadow copy of the `cr4` control register for the current cpu and load CPU microcode if need with the following function calls:

```C
wait_for_master_cpu(cpu);
cr4_init_shadow();
load_ucode_ap();
```

Next we get the `Task State Segment` for the current cpu and `orig_ist` structure which represents origin `Interrupt Stack Table` values with the:

```C
t = &per_cpu(cpu_tss, cpu);
oist = &per_cpu(orig_ist, cpu);
```

As we got values of the `Task State Segment` and `Interrupt Stack Table` for the current processor, we clear following bits in the `cr4` control register:

```C
cr4_clear_bits(X86_CR4_VME|X86_CR4_PVI|X86_CR4_TSD|X86_CR4_DE);
```

with this we disable `vm86` extension, virtual interrupts, timestamp ([RDTSC](https://en.wikipedia.org/wiki/Time_Stamp_Counter) can only be executed with the highest privilege) and debug extension. After this we reload the `Global Descriptor Table` and `Interrupt Descriptor table` with the:

```C
	switch_to_new_gdt(cpu);
	loadsegment(fs, 0);
	load_current_idt();
```

After this we setup array of the Thread-Local Storage Descriptors, configure [NX](https://en.wikipedia.org/wiki/NX_bit) and load CPU microcode. Now is time to setup and load `per-cpu` Task State Segments. We are going in a loop through the all exception stack which is `N_EXCEPTION_STACKS` or `4` and fill it with `Interrupt Stack Tables`:

```C
	if (!oist->ist[0]) {
		char *estacks = per_cpu(exception_stacks, cpu);

		for (v = 0; v < N_EXCEPTION_STACKS; v++) {
			estacks += exception_stack_sizes[v];
			oist->ist[v] = t->x86_tss.ist[v] =
					(unsigned long)estacks;
			if (v == DEBUG_STACK-1)
				per_cpu(debug_stack_addr, cpu) = (unsigned long)estacks;
		}
	}
```

As we have filled `Task State Segments` with the `Interrupt Stack Tables` we can set `TSS` descriptor for the current processor and load it with the:

```C
set_tss_desc(cpu, t);
load_TR_desc();
```

where `set_tss_desc` macro from the [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/desc.h) writes given  descriptor to the `Global Descriptor Table` of the given processor:

```C
#define set_tss_desc(cpu, addr) __set_tss_desc(cpu, GDT_ENTRY_TSS, addr)
static inline void __set_tss_desc(unsigned cpu, unsigned int entry, void *addr)
{
        struct desc_struct *d = get_cpu_gdt_table(cpu);
        tss_desc tss;
        set_tssldt_descriptor(&tss, (unsigned long)addr, DESC_TSS,
                              IO_BITMAP_OFFSET + IO_BITMAP_BYTES +
                              sizeof(unsigned long) - 1);
        write_gdt_entry(d, entry, &tss, DESC_TSS);
}
```

and `load_TR_desc` macro expands to the `ltr` or `Load Task Register` instruction:

```C
#define load_TR_desc()                          native_load_tr_desc()
static inline void native_load_tr_desc(void)
{
        asm volatile("ltr %w0"::"q" (GDT_ENTRY_TSS*8));
}
```

In the end of the `trap_init` function we can see the following code:

```C
set_intr_gate_ist(X86_TRAP_DB, &debug, DEBUG_STACK);
set_system_intr_gate_ist(X86_TRAP_BP, &int3, DEBUG_STACK);
...
...
...
#ifdef CONFIG_X86_64
        memcpy(&nmi_idt_table, &idt_table, IDT_ENTRIES * 16);
        set_nmi_gate(X86_TRAP_DB, &debug);
        set_nmi_gate(X86_TRAP_BP, &int3);
#endif
```

Here we copy `idt_table` to the `nmi_dit_table` and setup exception handlers for the `#DB` or `Debug exception` and `#BR` or `Breakpoint exception`. You can remember that we already set these interrupt gates in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-3), so why do we need to setup it again? We setup it again because when we initialized it before in the `early_trap_init` function, the `Task State Segment` was not ready yet, but now it is ready after the call of the `cpu_init` function.

That's all. Soon we will consider all handlers of these interrupts/exceptions.

Conclusion
--------------------------------------------------------------------------------

It is the end of the fourth part about interrupts and interrupt handling in the Linux kernel. We saw the initialization of the [Task State Segment](https://en.wikipedia.org/wiki/Task_state_segment) in this part and initialization of the different interrupt handlers as `Divide Error`, `Page Fault` exception and etc. You can note that we saw just initialization stuff, and will dive into details about handlers for these exceptions. In the next part we will start to do it.

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [page fault](https://en.wikipedia.org/wiki/Page_fault)
* [Interrupt Descriptor Table](https://en.wikipedia.org/wiki/Interrupt_descriptor_table)
* [Tracing](https://en.wikipedia.org/wiki/Tracing_%28software%29)
* [cr2](https://en.wikipedia.org/wiki/Control_register)
* [RCU](https://en.wikipedia.org/wiki/Read-copy-update)
* [this_cpu_* operations](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/Documentation/this_cpu_ops.txt)
* [kmemcheck](https://www.kernel.org/doc/Documentation/kmemcheck.txt)
* [prefetchw](http://www.felixcloutier.com/x86/PREFETCHW.html)
* [3DNow](https://en.wikipedia.org/?title=3DNow!)
* [CPU caches](https://en.wikipedia.org/wiki/CPU_cache)
* [VFS](https://en.wikipedia.org/wiki/Virtual_file_system)
* [Linux kernel memory management](https://0xax.gitbook.io/linux-insides/summary/mm)
* [Fix-Mapped Addresses and ioremap](https://0xax.gitbook.io/linux-insides/summary/mm/linux-mm-2)
* [Extended Industry Standard Architecture](https://en.wikipedia.org/wiki/Extended_Industry_Standard_Architecture)
* [INT instruction](https://en.wikipedia.org/wiki/INT_%28x86_instruction%29)
* [INTO](http://x86.renejeschke.de/html/file_module_x86_id_142.html)
* [BOUND](http://pdos.csail.mit.edu/6.828/2005/readings/i386/BOUND.htm)
* [opcode](https://en.wikipedia.org/?title=Opcode)
* [control register](https://en.wikipedia.org/wiki/Control_register#CR0)
* [x87 FPU](https://en.wikipedia.org/wiki/X86_instruction_listings#x87_floating-point_instructions)
* [MCE exception](https://en.wikipedia.org/wiki/Machine-check_exception)
* [SIMD](https://en.wikipedia.org/?title=SIMD)
* [cpumasks and bitmaps](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-2)
* [NX](https://en.wikipedia.org/wiki/NX_bit)
* [Task State Segment](https://en.wikipedia.org/wiki/Task_state_segment)
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-3)
