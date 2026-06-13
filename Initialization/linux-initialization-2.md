# Linux kernel initialization - Part 2

In the previous [part](linux-initialization-1.md), we have seen the first assembly instructions of the Linux kernel code. The kernel performed the first early initializations, like:

- Early stack setup 
- Loading of the kernel Global Descriptor Table
- Initialization of the kernel page tables

After these initializations, we finally can leave the assembly code (but only for some time) and switch to C code. We have stopped at the call of the `x86_64_start_kernel` function from [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head64.c). From this function, we will continue our journey in this chapter.

At this point, some important structures are already loaded or re-intialized by the kernel, but majority of them still not yet. The next structure which has to be initialized by the Linux kernel is [Interrup Descriptor Table](https://en.wikipedia.org/wiki/Interrupt_descriptor_table). The Interrupt Descriptor Table or IDT is a special structure that stores addresses of interrupt handlers. We will see how this structure is built further in this chapter.

Now, when we know an approximate plan what we should expect next, let's continue to dive into the Linux kernel internals.

## First steps in the C code

The assembly code is now behind us and we are back in C. However, the kernel is still far from its normal working state. We even have not reached the generic kernel code, but still in the early architecture-specific kernel setup. Interrupts are disabled and the early page tables built in the previous part map only the kernel image itself which means any access outside of it leads to a [page fault](https://en.wikipedia.org/wiki/Page_fault), which the kernel also can not handle yet. The goal of the `x86_64_start_kernel` function is to finish this early preparation, so the kernel can move on to its main initialization.

First C code meets us with build-time sanity checks:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head64.c#L228-L234 -->
```C
	BUILD_BUG_ON(MODULES_VADDR < __START_KERNEL_map);
	BUILD_BUG_ON(MODULES_VADDR - __START_KERNEL_map < KERNEL_IMAGE_SIZE);
	BUILD_BUG_ON(MODULES_LEN + KERNEL_IMAGE_SIZE > 2*PUD_SIZE);
	BUILD_BUG_ON((__START_KERNEL_map & ~PMD_MASK) != 0);
	BUILD_BUG_ON((MODULES_VADDR & ~PMD_MASK) != 0);
	BUILD_BUG_ON(!(MODULES_VADDR > __START_KERNEL));
	MAYBE_BUILD_BUG_ON(!(((MODULES_END - 1) & PGDIR_MASK) ==
				(__START_KERNEL & PGDIR_MASK)));
	BUILD_BUG_ON(__fix_to_virt(__end_of_fixed_addresses) <= MODULES_END);
```

The `BUILD_BUG_ON` macro validates its condition at compile time. If the condition passed to this macro is true, compilation of the kernel fails. Using this macro, the kernel verifies the layout of its virtual address space. For example, that the area reserved for kernel modules does not overlap the kernel image.

The next step after these sanity checks can be quite interesting. Did you know that to access a CPU register can be more expensive than accessing memory? If you haven't delved deeply into system programming and especially into Intel manuals, but only have relatively superficial experience in these areas, this statement may sound quite surprising. The next function that we can see after the sanity checks is a good example:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head64.c#L238-L238 -->
```C
	cr4_init_shadow();
```

We have already met the [`cr4` control register](https://en.wikipedia.org/wiki/Control_register) in the previous parts. This register contains flags that enable or disable certain processor features, among others:

- [Physical address extension](https://en.wikipedia.org/wiki/Physical_Address_Extension)
- [Page Size Extension](https://en.wikipedia.org/wiki/Page_Size_Extension)

The kernel preserves the value of this register because this value is used quite often. We will see a lot of examples in future. Since reading and writing the value of this register is expensive operation. [Intel® 64 and IA-32 Architectures Software Developer's Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html) says:

> MOV CR* instructions, except for MOV CR8, are serializing instructions

And:

> The Intel 64 and IA-32 architectures define several serializing instructions. These instructions force the processor to complete all modifications to flags, registers, and memory by previous instructions and to drain all buffered writes to memory before the next instruction is fetched and executed

To avoid paying extra CPU cycles, Linux kernel saves the value of the `cr4` control register in memory. From this point, the kernel changes bits of the `cr4` register only using special helpers like `cr4_set_bits` and `cr4_clear_bits`, which update the shadow copy and write the new value to the actual register only if it differs from the stored one.

## Preparing the kernel memory layout

Before the kernel can move on to the generic initialization, it has to bring its memory into a known and consistent state. So far the kernel runs on top of the page tables and the memory layout that were prepared just enough to get the C code running. Some of these early structures are temporary and have to be cleaned up, others have to be initialized for the first time.

In the next few steps we will see how the kernel:

- [Gets rid of the leftover identity mapping in the early page tables](#resetting-the-early-page-tables)
- [Clears the memory regions that must start zeroed, such as the `BSS` section](#clearing-the-initial-memory-state)
- [Prepare the top-level page table that the kernel will use after the early boot](#preparing-the-final-top-level-page-table)
- [Flushing the global TLB](#flushing-the-global-tlb)

Let's go through these steps one by one.

### Resetting the early page tables

One of the previous steps of the kernel was to set up the new page tables. The kernel still has identity mapping page tables which are a left-over from the earliest page tables structure. If you have read the previous part, you can remember that these identity mapping page tables were temporary and existed only to not cause page fault during swtiching to the new page tables.

Since the kernel switched to running from its high virtual addresses, this identity mapping is no longer needed. The top-level page table is pointed by the `early_top_pgt`. The entries of this page table look like this:

![early_top_pgt entries](./images/early-top-pgt-entries.svg)

It contains `PTRS_PER_PGD` entries, which is `512` on `x86_64`. Only the last entry points to the next page table that holds the entries to map the kernel image. All other entries are or empty or maps these identity mapping addresses. The `reset_early_page_tables` function wipes all of these first `511` entries:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head64.c#L71-L76 -->
```C
static void __init reset_early_page_tables(void)
{
	memset(early_top_pgt, 0, sizeof(pgd_t)*(PTRS_PER_PGD-1));
	next_early_pgt = 0;
	write_cr3(__sme_pa_nodebug(early_top_pgt));
}
```

After clearing these entries, the function resets `next_early_pgt` to `0`. This variable is an index into `early_dynamic_pgts` which is a small pool of reserved page table buffers. We will meet it again later in this part, when the page fault handler builds new page tables on demand.

Finally, the function reloads the `cr3` control register with the physical address of `early_top_pgt`. The `cr3` register holds the physical address of the top-level page table, so writing to it makes the processor use the updated tables and flushes the `TLB`.

Starting from this point on, only the kernel high mapping is left. Any access to an address that is not mapped yet. For example the `boot_params` structure that may be located above the four gigabytes limit, will trigger a page fault. The page fault handler that we will see later in this part will build the missing page tables on demand.

### Clearing the initial memory state

The next thing to clear is the kernel's [BSS](https://en.wikipedia.org/wiki/.bss) section. The `clear_bss` function as it is easy to guess by its name, zeroes it:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head64.c#L177-L183 -->
```C
void __init clear_bss(void)
{
	memset(__bss_start, 0,
	       (unsigned long) __bss_stop - (unsigned long) __bss_start);
	memset(__brk_base, 0,
	       (unsigned long) __brk_limit - (unsigned long) __brk_base);
}
```

As we may see, this function clears not only the `BSS` area. The first `memset` definitely zeroes the `BSS` section. The second one clears the `brk` area. We already have met `BSS` section in the previous chapters. This is a memory region that contains global and static variables that must be initialized with zeroes. We can check the symbols related to this section using the following simple command:

```bash
$ nm -n vmlinux | awk '/ __bss_start$/,/ __bss_stop$/ { if (n++ < 11 || / __bss_stop$/) print }'
```

Te output should be something like this:

```
ffffffff82f6b000 B __bss_start
ffffffff82f6b000 b idt_table
ffffffff82f6b000 D __nosave_end
ffffffff82f6c000 b espfix_pud_page
ffffffff82f6d000 b bm_pte
ffffffff82f6e000 B empty_zero_page
ffffffff82f6f000 B initcall_debug
ffffffff82f6f004 B reset_devices
ffffffff82f6f008 b initcall_calltime
ffffffff82f6f010 b panic_param
ffffffff82f6f018 b panic_later
ffffffff8309a000 B __bss_stop
```

The second memory area is `brk`. This is a region of memory that the early kernel uses as a primitive allocator before the real memory allocators are available. Both of these regions are reserved in the kernel's [linker script](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S), so all the kernel needs to do here is to set their content to zero.

### Preparing the final top-level page table

The next thing to clear is the final top-level page table to which the Linux kernel will switch for normal operation. 

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head64.c#L324-L328 -->
```C
	/*
	 * This needs to happen *before* kasan_early_init() because latter maps stuff
	 * into that page.
	 */
	clear_page(init_top_pgt);
```

For now on, the `early_top_pgt` page table is in use and it will continue to be used while the kernel is still in the initialization stage. But as the comment above the call says, the page must be cleared before the next initialization steps map something into it. We will see how the kernel finishes filling this table and switches to it later, but for now it is enough to know that the kernel has zeroed it out.

### Flushing the global TLB

The last memory cleanup related step before the kernel turns to interrupt handling is to flush the global [TLB](https://en.wikipedia.org/wiki/Translation_lookaside_buffer) entries. The `TLB` or Translation Lookaside Buffer is a cache that the processor uses to speed up the translation of virtual addresses to physical ones. Whenever the kernel changes the page tables, the entries cached in the `TLB` may become stale and must be invalidated.

The early page tables that we have seen above had two kinds of mappings:

- the high kernel mapping
- the identity mapping

This identity mapping was needed during the switch to long mode and to the high kernel mapping, but the `reset_early_page_tables` function has already removed it. The problem is that these identity mappings are global, which means that the processor may keep them in the `TLB` even across a reload of the `cr3` register. Usually writing to the `cr3` register flushes the `TLB`, but global entries are intentionally excluded from this flush. This information we can find in the [Intel® 64 and IA-32 Architectures Software Developer's Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html) as well:

> MOV to CR3. The behavior of the instruction depends on the value of CR4.PCIDE:
>
> If CR4.PCIDE = 0, the instruction invalidates all TLB entries associated with PCID 000H except those for global pages. It also invalidates all entries in all paging-structure caches associated with PCID 000H.

So even after the identity mapping is gone from the page tables, stale translations for it might still be cached. To get rid of them, the kernel forces a flush of the global entries with the `__native_tlb_flush_global` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head64.c#L274-L274 -->
```C
	__native_tlb_flush_global(this_cpu_read(cpu_tlbstate.cr4));
```

An additional reason to flush the `TLB` is the so-called `trampoline page table`. This is a separate page table that establishes the very same kind of global identity mappings, but it is used to bring up the secondary processors if they exist in the system. We will meet it later when we will talk about the [`SMP`](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) initialization. For now it is enough to know that the boot processor itself was running on the early page tables we discussed above, and the goal of this step is to drop any stale global translation of the identity mapping from the `TLB`.

With this, the early preparation of the kernel memory layout is finished. The kernel can now move on to setting up the handlers for interrupts and exceptions.

## Early interrupt and exception handling

The next thing to initialize is the Interrupt Descriptor Table. But before we will jump directly to the code, we need to know what is an interrupt and why this table is uesd by the Linux kernel.

### Interrupt Descriptor Table

An interrupt is an event caused by the software or hardware to the CPU. For example a user has pressed a key on the keyboard. Conditionally we can split interrupts on three types: 

- Software interrupts - when a software signals CPU that it needs kernel attention. These interrupts are generally used for [system calls](https://en.wikipedia.org/wiki/System_call)
- Hardware interrupts - when a hardware event happens, for example button is pressed on a keyboard
- Exceptions - interrupts generated by CPU, when the CPU detects an error, for example a division by zero or accessing a memory page which is not in RAM

When an interrupt or exception is triggered, the CPU stops the execution of the current task and transfers control to a special routine called [interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler). An interrupt handler handles an interrupt and transfers control back to the previously stopped task. The CPU accesses such interrupt handler through an entry (or more traditionally - gate) in the special table, called - Interrupt Descriptor Table or IDT.

Every interrupt and exception has assigned a unique number called a `vector number`. A vector number can be any value from `0` to `255`. First `32` (starting from zero) numbers reserved for CPU exceptions, like divide error, page fault and so on:

| Vector | Mnemonic | Description          | Type  | Error Code | Source                                |
|--------|----------|----------------------|-------|------------|---------------------------------------|
| 0      | #DE      | Divide Error         | Fault | NO         | DIV and IDIV                          |
| 1      | #DB      | Reserved             | F/T   | NO         |                                       |
| 2      | ---      | NMI                  | INT   | NO         | external NMI                          |
| 3      | #BP      | Breakpoint           | Trap  | NO         | INT 3                                 |
| 4      | #OF      | Overflow             | Trap  | NO         | INTO instruction                      |
| 5      | #BR      | Bound Range Exceeded | Fault | NO         | BOUND instruction                     |
| 6      | #UD      | Invalid Opcode       | Fault | NO         | UD2 instruction                       |
| 7      | #NM      | Device Not Available | Fault | NO         | Floating point or [F]WAIT             |
| 8      | #DF      | Double Fault         | Abort | YES        | An instruction which can generate NMI |
| 9      | ---      | Reserved             | Fault | NO         |                                       |
| 10     | #TS      | Invalid TSS          | Fault | YES        | Task switch or TSS access             |
| 11     | #NP      | Segment Not Present  | Fault | NO         | Accessing segment register            |
| 12     | #SS      | Stack-Segment Fault  | Fault | YES        | Stack operations                      |
| 13     | #GP      | General Protection   | Fault | YES        | Memory reference                      |
| 14     | #PF      | Page fault           | Fault | YES        | Memory reference                      |
| 15     | ---      | Reserved             |       | NO         |                                       |
| 16     | #MF      | x87 FPU fp error     | Fault | NO         | Floating point or [F]Wait             |
| 17     | #AC      | Alignment Check      | Fault | YES        | Data reference                        |
| 18     | #MC      | Machine Check        | Abort | NO         |                                       |
| 19     | #XM      | SIMD fp exception    | Fault | NO         | SSE[2,3] instructions                 |
| 20     | #VE      | Virtualization exc.  | Fault | NO         | EPT violations                        |
| 21-31  | ---      | Reserved             | INT   | NO         | External interrupts                   |

The vector numbers from `32` to `255` available for hardware interrupts.

When an interrupt or exception occurs, the CPU uses the vector number as an index into the `Interrupt Descriptor Table`. The selected descriptor contains a pointer to the interrupt or exception handler. The base address of the `Interrupt Descriptor Table` is held in a special register called `IDTR`. This register is loaded with the `LIDT` instruction, which takes a pointer to a descriptor holding the base address and the size limit of the `IDT`.

The structure of the Interrupt Descriptor Table on x86_64 is:

![IDT gate descriptor](./images/idt-gate-descriptor.svg)

Here:

- `Offset` - the 64-bit virtual address of the interrupt or exception handler
- `Segment Selector` - a code segment selector that the processor loads into the `cs` register before it jumps to the handler. It must point to a valid code segment in the Global Descriptor Table. How we will see later, in the Linux kernel it points to the kernel code segment `__KERNEL_CS`.
- `IST` - the Interrupt Stack Table index. It lets the processor run the handler on a dedicated, reserved stack instead of the stack that was in use when the interrupt happened. This matters for a few critical handlers that must work even if the current stack is broken, such as a double fault. When this field is zero, the handler just runs on the normal kernel stack.
- `Type` - the kind of the gate. In 64-bit mode the `IDT` may hold two kinds of gates:
  - `Interrupt gate` - when the processor enters the handler through it, it clears the `IF` interrupt flag. This flag tells the processor whether it is allowed to deliver hardware interrupts or not. Clearing it, prevents other hardware interrupts from interrupting the handler while it runs.
  - `Trap gate` - works like an interrupt gate, but the processor leaves the `IF` flag unchanged, so the handler can still be interrupted by hardware interrupts.
- `DPL` - the Descriptor Privilege Level. It is the minimum privilege level a task must have to invoke this gate with a software instruction like [`int n`](https://en.wikipedia.org/wiki/INT_(x86_instruction)). Hardware interrupts and processor exceptions ignore this field.
- `P` - the present flag. It must be set for a valid descriptor. A reference to a gate whose `P` flag is clear raises a segment-not-present (`#NP`) exception.

The remaining bits, including the topmost `Reserved` part, must be zero.

The structure of the descriptor pointing to the Interrupt Descriptor Table is:

![IDT descriptor](./images/idt-descriptor.svg)

The processor uses this descriptor to find the `IDT` in memory. The `Limit` field holds the size of the table in bytes minus one, and the `Base Address` field holds the virtual address of the first entry of the table. This is exactly the descriptor that the `LIDT` instruction loads into the `IDTR` register.

### Handling of interrupts on x86_64

Knowing how the Interrupt Descriptor Table is structured, we can take a short look how an interrupt or exception is handled by the processor in the 64-bit mode. 

> [!NOTE]
> If you are interested in more details, the exact algorithm is described in the [Intel® 64 and IA-32 Architectures Software Developer's Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html), Volume 3A, in the sections `7.12 Exception and Interrupt Handling` and `7.14 Exception and Interrupt Handling in 64-bit Mode`. The processor performs the following steps.

When an interrupt or exception occurs, the processor takes the vector number of the interrupt or exception and multiplies it by `16` to get the offset of the gate/entry inside the `IDT`. It reads the gate at this offset and checks that it is an interrupt or a trap gate that points to a 64-bit code segment. Then it decides which stack the handler will run on, following the rules we have already seen for the `IST` field. It can be a dedicated stack from the `IST`, or the current stack. After the stack is choosen, the state of the interrupted code is saved on that stack, so the code can be resumed later. The processor pushes the following registers, from higher to lower addresses:

![Interrupt stack frame](./images/interrupt-stack-frame.svg)

After the state is saved, the processor loads the handler's code segment selector and offset from the gate into the `cs` and `rip` registers and switches to the execution of the handler.

When the handler is done, it returns with the special instruction called `iretq`. This instruction pops the saved registers back, restores the saved flags and resumes the interrupted code from the point where it was stopped.

### Set up early Interrupt Descriptor Table

With the theory behind us, let's return to the kernel code. We stopped in the `x86_64_start_kernel` function, right before the call of:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head64.c#L276-L276 -->
```C
	idt_setup_early_handler();
```

At this early stage the kernel does not need a complete `IDT` yet. Interrupts are still disabled, so no hardware interrupt is going to arrive. What can still happen - is an exception. For example a page fault, that, as we will see later in this part. So the kernel needs at least a minimal `IDT` that knows how to catch the processor exceptions. This is exactly what the `idt_setup_early_handler` function does. This function is defined in [arch/x86/kernel/idt.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/idt.c) and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/idt.c#L330-L341 -->
```C
void __init idt_setup_early_handler(void)
{
	int i;

	for (i = 0; i < NUM_EXCEPTION_VECTORS; i++)
		set_intr_gate(i, early_idt_handler_array[i]);
#ifdef CONFIG_X86_32
	for ( ; i < NR_VECTORS; i++)
		set_intr_gate(i, early_ignore_irq);
#endif
	load_idt(&idt_descr);
}
```

The `NUM_EXCEPTION_VECTORS` as we know is `32`. This function goes over the all avialable vector numbers assigned to the CPU exceptions and calls the `set_intr_gate` function which initializes the given gate descriptor with the vector number, the handler address and flags:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/idt.c#L209-L216 -->
```C
static __init void set_intr_gate(unsigned int n, const void *addr)
{
	struct idt_data data;

	init_idt_data(&data, n, addr);

	idt_setup_from_table(idt_table, &data, 1, false);
}
```

The `idt_data` structure is defined in [arch/x86/include/asm/desc_defs.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/desc_defs.h) and contains the following fields:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/desc_defs.h#L127-L132 -->
```C
struct idt_data {
	unsigned int	vector;
	unsigned int	segment;
	struct idt_bits	bits;
	const void	*addr;
};
```

The Interrupt Descriptor Table itself is represented by the array of the following structures defined in the same [arch/x86/include/asm/desc_defs.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/desc_defs.h):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/desc_defs.h#L134-L143 -->
```C
struct gate_struct {
	u16		offset_low;
	u16		segment;
	struct idt_bits	bits;
	u16		offset_middle;
#ifdef CONFIG_X86_64
	u32		offset_high;
	u32		reserved;
#endif
} __attribute__((packed));
```

After all the entries are initialized and copied to the Interrupt Descriptor Table, the `load_idt` function executes the `lidt` instruction to load the address of the newly built Interrupt Descriptor Table.

Starting from this point, the interrupt table is initialized and loaded, so the kernel can handle interrupts and exceptions. But what interrupts it can handle now? The answer on this question can give us only `early_idt_handler_array`. This array is defined in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S):

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L488-L505 -->
```assembly
SYM_CODE_START(early_idt_handler_array)
	i = 0
	.rept NUM_EXCEPTION_VECTORS
	.if ((EXCEPTION_ERRCODE_MASK >> i) & 1) == 0
		UNWIND_HINT_IRET_REGS
		ENDBR
		pushq $0	# Dummy error code, to make stack frame uniform
	.else
		UNWIND_HINT_IRET_REGS offset=8
		ENDBR
	.endif
	pushq $i		# 72(%rsp) Vector number
	jmp early_idt_handler_common
	UNWIND_HINT_IRET_REGS
	i = i + 1
	.fill early_idt_handler_array + i*EARLY_IDT_HANDLER_SIZE - ., 1, 0xcc
	.endr
SYM_CODE_END(early_idt_handler_array)
```

This macro can look scary at the first glance, but do not worry. Let's go through it and try to understand what it does. This macro generates a contiguous block of executable code containing `32` fixed-size exception entry stubs. The [`.rept`](https://sourceware.org/binutils/docs/as/Rept.html) directive is a basic loop which is executed `32` times and generates a push on the stack of a dummy error code for exceptions for which CPU does not push any. This is done to have unified stack layout for all exception handlers. The next generated instructions are the push to stack of the vector number and jump on the `early_idt_handler_common` label. Under this label we will see the code of the actual exception handler later. In the end of this macro we can see the padding filled with `0xcc` bytes until the generated code has exactly `EARLY_IDT_HANDLER_SIZE` bytes. There is one interesting moment with this padding. `0xcc` is the opcode for [INT3](https://en.wikipedia.org/wiki/INT_(x86_instruction)#INT3) instruction, so if the padding will be accidentally executed, it will causes a breakpoint exception rather than running random bytes.

If we will inspect the kernel image with [`objdump`](https://man7.org/linux/man-pages/man1/objdump.1.html), we can see these generated instructions:

```bash
objdump -d vmlinux | grep '<early_idt_handler_array>:' -A 24
```

The output should look similar to this:

```
ffffffff83d3fd10 <early_idt_handler_array>:
ffffffff83d3fd10:	f3 0f 1e fa          	endbr64
ffffffff83d3fd14:	6a 00                	push   $0x0
ffffffff83d3fd16:	6a 00                	push   $0x0
ffffffff83d3fd18:	e9 93 01 00 00       	jmp    ffffffff83d3feb0 <early_idt_handler_common>
ffffffff83d3fd1d:	f3 0f 1e fa          	endbr64
ffffffff83d3fd21:	6a 00                	push   $0x0
ffffffff83d3fd23:	6a 01                	push   $0x1
ffffffff83d3fd25:	e9 86 01 00 00       	jmp    ffffffff83d3feb0 <early_idt_handler_common>
ffffffff83d3fd2a:	f3 0f 1e fa          	endbr64
ffffffff83d3fd2e:	6a 00                	push   $0x0
ffffffff83d3fd30:	6a 02                	push   $0x2
ffffffff83d3fd32:	e9 79 01 00 00       	jmp    ffffffff83d3feb0 <early_idt_handler_common>
ffffffff83d3fd37:	f3 0f 1e fa          	endbr64
ffffffff83d3fd3b:	6a 00                	push   $0x0
ffffffff83d3fd3d:	6a 03                	push   $0x3
ffffffff83d3fd3f:	e9 6c 01 00 00       	jmp    ffffffff83d3feb0 <early_idt_handler_common>
ffffffff83d3fd44:	f3 0f 1e fa          	endbr64
ffffffff83d3fd48:	6a 00                	push   $0x0
ffffffff83d3fd4a:	6a 04                	push   $0x4
ffffffff83d3fd4c:	e9 5f 01 00 00       	jmp    ffffffff83d3feb0 <early_idt_handler_common>
ffffffff83d3fd51:	f3 0f 1e fa          	endbr64
ffffffff83d3fd55:	6a 00                	push   $0x0
ffffffff83d3fd57:	6a 05                	push   $0x5
ffffffff83d3fd59:	e9 52 01 00 00       	jmp    ffffffff83d3feb0 <early_idt_handler_common>
```

TODO

Fill and load IDT
--------------------------------------------------------------------------------


The `early_idt_handler_array` array is declared in the [arch/x86/include/asm/segment.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/segment.h) header file and contains addresses of the first `32` exception handlers:

```C
#define EARLY_IDT_HANDLER_SIZE   9
#define NUM_EXCEPTION_VECTORS	32

extern const char early_idt_handler_array[NUM_EXCEPTION_VECTORS][EARLY_IDT_HANDLER_SIZE];
```

The `early_idt_handler_array` is a `288` bytes array containing addresses of exception entry points every nine bytes. Every nine bytes of this array consist of two optional bytes for the instruction for pushing dummy error code if an exception does not provide it, two bytes instruction for pushing vector number to the stack and five bytes of `jump` to the common exception handler code. You will see more detail in the next paragraph.

Early interrupt handlers
--------------------------------------------------------------------------------

As you can read above, we filled `IDT` with the address of the `early_idt_handler_array`. In this section, we are going to look into it in detail. We can find it in the [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) assembly file:

```assembly
ENTRY(early_idt_handler_array)
	i = 0
	.rept NUM_EXCEPTION_VECTORS
	.if ((EXCEPTION_ERRCODE_MASK >> i) & 1) == 0
		UNWIND_HINT_IRET_REGS
		pushq $0	# Dummy error code, to make stack frame uniform
	.else
		UNWIND_HINT_IRET_REGS offset=8
	.endif
	pushq $i		# 72(%rsp) Vector number
	jmp early_idt_handler_common
	UNWIND_HINT_IRET_REGS
	i = i + 1
	.fill early_idt_handler_array + i*EARLY_IDT_HANDLER_SIZE - ., 1, 0xcc
	.endr
	UNWIND_HINT_IRET_REGS offset=16
END(early_idt_handler_array)
```

As we can see above, interrupt handlers generation is done for the first `32` exceptions. We check here, if the exception has an error code and then we do nothing. If an exception, however, does not return an error code, we push a zero to the stack. We do it so that the stack is uniform. After that we push `vector number` on the stack and jump to the `early_idt_handler_common` - a generic interrupt handler for the time being. After all, every nine bytes of the `early_idt_handler_array` array consist of an optional push of an error code, push of `vector number` and jump instruction to `early_idt_handler_common`. We can see it in the output of the `objdump` util:

```
$ objdump -D vmlinux
...
...
...
ffffffff81fe5000 <early_idt_handler_array>:
ffffffff81fe5000:       6a 00                   pushq  $0x0
ffffffff81fe5002:       6a 00                   pushq  $0x0
ffffffff81fe5004:       e9 17 01 00 00          jmpq   ffffffff81fe5120 <early_idt_handler_common>
ffffffff81fe5009:       6a 00                   pushq  $0x0
ffffffff81fe500b:       6a 01                   pushq  $0x1
ffffffff81fe500d:       e9 0e 01 00 00          jmpq   ffffffff81fe5120 <early_idt_handler_common>
ffffffff81fe5012:       6a 00                   pushq  $0x0
ffffffff81fe5014:       6a 02                   pushq  $0x2
...
...
...
```

As we may know, CPU pushes flag registers, `CS` and `RIP` on the stack before calling the interrupt handler. So before `early_idt_handler_common` will be executed, stack will contain the following data:

```
|--------------------|
| %rflags            |
| %cs                |
| %rip               |
| error code         |
| vector number      |<-- %rsp
|--------------------|
```

Now let's look at the `early_idt_handler_common` implementation. It is located in the same [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) assembly file. First of all we increment `early_recursion_flag` to prevent recursion in the `early_idt_handler_common`:

```assembly
	incl early_recursion_flag(%rip)
```

The `early_recursion_flag` is defined in the same assembly file as the `early_idt_handler_common` symbol as follows:

```assembly
	early_recursion_flag:
		.long 0
```

Next we save general registers on the stack:

```assembly
	pushq %rsi
	movq 8(%rsp), %rsi
	movq %rdi, 8(%rsp)
	pushq %rdx
	pushq %rcx
	pushq %rax
	pushq %r8
	pushq %r9
	pushq %r10
	pushq %r11
	pushq %rbx
	pushq %rbp
	pushq %r12
	pushq %r13
	pushq %r14
	pushq %r15
	UNWIND_HINT_REGS
```

Okay, now the stack contains following data:
```
High |-------------------------|
     | %rflags                 |
     | %cs                     |
     | %rip                    |
     | error code              |
     | %rdi                    |
     | %rsi                    |
     | %rdx                    |
     | %rax                    |
     | %r8                     |
     | %r9                     |
     | %r10                    |
     | %r11                    |
     | %rbx                    |
     | %rbp                    |
     | %r12                    |
     | %r13                    |
     | %r14                    |
     | %r15                    |<-- %rsp
Low  |-------------------------|
```

We need to do it to prevent wrong values of registers when we return from the interrupt handler. After this we check the vector number, and if it is `#PF` or a [Page Fault](https://en.wikipedia.org/wiki/Page_fault), we put value from the `cr2` to the `rdi` register and call `early_make_pgtable` (we'll see it soon):

```assembly
	cmpq $14,%rsi            /* Page fault? */
	jnz 10f
	GET_CR2_INTO(%rdi)
	call early_make_pgtable
	andl %eax,%eax           /* It is more efficient, the opcode is shorter than movl 1, %eax, only 2 bytes. */
	jz 20f                   /* All good */
```

otherwise we call `early_fixup_exception` function by passing kernel stack pointer:

```assembly
10:
	movq %rsp,%rdi
	call early_fixup_exception
```

We'll see the implementation of the `early_fixup_exception` function later.

```assembly
20:
	decl early_recursion_flag(%rip)
	jmp restore_regs_and_return_to_kernel
```

After we decrement the `early_recursion_flag`, we restore registers that we saved before on the stack and return from the handler with `iretq`.

That is the end of the interrupt handler. We will examine the page fault handling and the other exception handling in order.

Page fault handling
--------------------------------------------------------------------------------

In the previous paragraph we saw the early interrupt handler that checks if the vector number is a page fault and calls `early_make_pgtable` for building new page tables if it is. We need to have `#PF` handler in this step because there are plans to add an ability to load kernels above `4G` addresses and allow accesses to `boot_params` structure above the 4G addressing limit.

You can find the implementation of the `early_make_pgtable` in [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head64.c) that takes one parameter - the value of the `cr2` register, containing the address causing page fault. Let's look at it:

```C
int __init early_make_pgtable(unsigned long address)
{
	unsigned long physaddr = address - __PAGE_OFFSET;
	pmdval_t pmd;

	pmd = (physaddr & PMD_MASK) + early_pmd_flags;

	return __early_make_pgtable(address, pmd);
}
```

`__PAGE_OFFSET` is defined in the [arch/x86/include/asm/page_64_types.h](https://elixir.bootlin.com/linux/v3.10-rc1/source/arch/x86/include/asm/page_64_types.h#L33) header file, and the suffix `UL` forces the page offset to be an unsigned long data type.

```C
#define __PAGE_OFFSET           _AC(0xffff880000000000, UL)
```

And the `_AC` macro is defined in the [include/uapi/linux/const.h](https://elixir.bootlin.com/linux/v3.10-rc1/source/include/uapi/linux/const.h#L16) header file:

```C
/* Some constant macros are used in both assembler and
 * C code.  Therefore we cannot annotate them always with
 * 'UL' and other type specifiers unilaterally.  We
 * use the following macros to deal with this.
 *
 * Similarly, _AT() will cast an expression with a type in C, but
 * leave it unchanged in asm.
 */

#ifdef __ASSEMBLY__
#define _AC(X,Y)	X
#else
#define __AC(X,Y)	(X##Y)
#define _AC(X,Y)	__AC(X,Y)
#endif
```
Where `__PAGE_OFFSET` expands to `0xffff888000000000`. But, why is it possible to translate a virtual address to a physical address by subtracting `__PAGE_OFFSET`?  The answer is in the [Documentation/x86/x86_64/mm.rst](https://elixir.bootlin.com/linux/v5.10-rc5/source/Documentation/x86/x86_64/mm.rst#L45):

```
...
ffff888000000000 | -119.5  TB | ffffc87fffffffff |   64 TB | direct mapping of all physical memory (page_offset_base)
...
```

As explained above, the virtual address space `ffff888000000000-ffffc87fffffffff` is direct mapping of all physical memory. When the kernel wants to access all physical memory, it uses direct mapping.

Okay, let's get back to discussing `early_make_pgtable`. We initialize `pmd` and pass it to the `__early_make_pgtable` function along with an `address`. The `__early_make_pgtable` function is defined in the same file as the `early_make_pgtable` function as follows:

```C
int __init __early_make_pgtable(unsigned long address, pmdval_t pmd)
{
	unsigned long physaddr = address - __PAGE_OFFSET;
	pgdval_t pgd, *pgd_p;
	p4dval_t p4d, *p4d_p;
	pudval_t pud, *pud_p;
	pmdval_t *pmd_p;
	...
	...
	...
}
```

It starts from the definition of some variables having `*val_t` types. All of these types are declared as an alias of `unsigned long` using `typedef`.

After performing the check for invalid addresses, we're getting the address of the Page Global Directory entry containing base address of the Page Upper Directory and put its value into the `pgd` variable:

```C
again:
	pgd_p = &early_top_pgt[pgd_index(address)].pgd;
	pgd = *pgd_p;
```

And we check if `pgd` is present. If it is, we assign the base address of the page upper directory table to `pud_p`:

```C
	pud_p = (pudval_t *)((pgd & PTE_PFN_MASK) + __START_KERNEL_map - phys_base);
```

where `PTE_PFN_MASK` is a macro that masks lower `12` bits of `(pte|pmd|pud|pgd)val_t`.

If `pgd` is not present, we check if `next_early_pgt` is not greater than `EARLY_DYNAMIC_PAGE_TABLES` which is `64` and present a fixed number of buffers to set up new page tables on demand. If `next_early_pgt` is greater than `EARLY_DYNAMIC_PAGE_TABLES` we reset page tables and start again from `again` label. If `next_early_pgt` is less than `EARLY_DYNAMIC_PAGE_TABLES`, we assign the next entry of `early_dynamic_pgts` to `pud_p` and fill whole entry of the page upper directory with `0`, then fill the page global directory entry with the base address and some access rights:

```C
	if (next_early_pgt >= EARLY_DYNAMIC_PAGE_TABLES) {
		reset_early_page_tables();
		goto again;
	}

	pud_p = (pudval_t *)early_dynamic_pgts[next_early_pgt++];
	memset(pud_p, 0, sizeof(*pud_p) * PTRS_PER_PUD);
	*pgd_p = (pgdval_t)pud_p - __START_KERNEL_map + phys_base + _KERNPG_TABLE;
```

And we fix `pud_p` to point to correct entry and assign its value to `pud` with the following:

```C
	pud_p += pud_index(address);
	pud = *pud_p;
```

And then we do the same routine as above, but to the page middle directory.

In the end we assign the given `pmd` which is passed by the `early_make_pgtable` function to the certain entry of page middle directory which maps kernel text+data virtual addresses:

```C
	pmd_p[pmd_index(address)] = pmd;
```

After page fault handler finished its work, as a result, `early_top_pgt` contains entries which point to the valid addresses.

Other exception handling
--------------------------------------------------------------------------------

In the early interrupt phase, exceptions other than the page fault are handled by `early_fixup_exception` function defined in [arch/x86/mm/extable.c](https://github.com/torvalds/linux/blob/master/arch/x86/mm/extable.c) taking two parameters - a pointer to the kernel stack that consists of saved registers and a vector number:

```C
void __init early_fixup_exception(struct pt_regs *regs, int trapnr)
{
	...
	...
	...
}
```

First of all, we need to make some checks as following:

```C
	if (trapnr == X86_TRAP_NMI)
		return;

	if (early_recursion_flag > 2)
		goto halt_loop;

	if (!xen_pv_domain() && regs->cs != __KERNEL_CS)
		goto fail;
```

Here we just ignore [NMI](https://en.wikipedia.org/wiki/Non-maskable_interrupt) and make sure that we are not in recursive situation.

After that, we get into:

```C
	if (fixup_exception(regs, trapnr))
		return;
```

The `fixup_exception` function finds the actual handler and calls it. It is defined in the same file as `early_fixup_exception` function as follows:

```C
int fixup_exception(struct pt_regs *regs, int trapnr)
{
	const struct exception_table_entry *e;
	ex_handler_t handler;

	e = search_exception_tables(regs->ip);
	if (!e)
		return 0;

	handler = ex_fixup_handler(e);
	return handler(e, regs, trapnr);
}
```

The `ex_handler_t` is a type of function pointer, which is defined like:

```C
typedef bool (*ex_handler_t)(const struct exception_table_entry *,
                            struct pt_regs *, int)
```

The `search_exception_tables` function looks up the given address in the exception table (i.e. the contents of the ELF section, `__ex_table`). After that, we get the actual address by `ex_fixup_handler` function. At last we call the actual handler. For more information about the exception table, you can refer to [Documentation/x86/exception-tables.txt](https://github.com/torvalds/linux/blob/master/Documentation/x86/exception-tables.txt).

Let's get back to the `early_fixup_exception` function, the next step is:

```C
	if (fixup_bug(regs, trapnr))
		return;
```

The `fixup_bug` function is defined in [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/traps.c). Let's have a look at its implementation:

```C
int fixup_bug(struct pt_regs *regs, int trapnr)
{
	if (trapnr != X86_TRAP_UD)
		return 0;

	switch (report_bug(regs->ip, regs)) {
	case BUG_TRAP_TYPE_NONE:
	case BUG_TRAP_TYPE_BUG:
		break;

	case BUG_TRAP_TYPE_WARN:
		regs->ip += LEN_UD2;
		return 1;
	}

	return 0;
}
```

All what this function does is to return `1` if the exception is generated because `#UD` (or [Invalid Opcode](https://wiki.osdev.org/Exceptions#Invalid_Opcode) occurred and the `report_bug` function returns `BUG_TRAP_TYPE_WARN`), otherwise it returns `0`.

Conclusion
--------------------------------------------------------------------------------

This is the end of the second part about Linux kernel insides. If you have questions or suggestions, ping me on twitter [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com) or just create an [issue](https://github.com/0xAX/linux-insides/issues/new). In the next part we will see all the steps before kernel entry point - `start_kernel` function.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [GNU assembly .rept](https://sourceware.org/binutils/docs-2.23/as/Rept.html)
* [APIC](http://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller)
* [NMI](http://en.wikipedia.org/wiki/Non-maskable_interrupt)
* [Page table](https://en.wikipedia.org/wiki/Page_table)
* [Interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler)
* [Page Fault](https://en.wikipedia.org/wiki/Page_fault),
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/initialization/linux-initialization-1)
