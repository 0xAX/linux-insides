# Linux kernel initialization - Part 1

The previous [post](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-6.md) was the final part of the chapter describing the [Linux kernel boot process](https://github.com/0xAX/linux-insides/tree/master/Booting). In that chapter, we looked at the kernel boot process step by step, starting from the very first actions and instructions executed after the system powers on, through the bootloader, and finally into the Linux kernel setup code.

Now we are entering the next stage of the journey - the initialization of the Linux kernel. The CPU has switched modes, the temporary page tables have been built, the kernel image has been decompressed, placed at its final location in memory, and control has been passed to it. For now, the kernel is in a very early state. It is running on simple identity-mapped page tables and a temporary GDT inherited from the early setup code. It must rebuild all of these structures before it can continue.

We will start at the kernel's entry point in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) and focus on the first steps:

- preparing the execution environment
- setting up kernel page tables
- switching to the proper kernel descriptors

But, of course, that is only the beginning. There is still a lot to do - the kernel must initialize all core subsystems, finish setting up memory management, detect hardware, and load drivers before userspace code can run. All upcoming parts of this chapter will be dedicated to exploring how the kernel initializes itself before launching the very first userspace process with [PID 1](https://en.wikipedia.org/wiki/Process_identifier).

Let's get started.

## Linux kernel entry point

At the end of the previous chapter, we reached the moment when the kernel decompressor finished its job. The kernel image was decompressed and the `extract_kernel` function from [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c) returned the address of the kernel's entry point. This address was put in the `rax` register, and execution flow switched directly to it in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L469-L475 -->
```assembly
	call	extract_kernel		/* returns kernel entry point in %rax */

/*
 * Jump to the decompressed kernel.
 */
	movq	%r15, %rsi
	jmp	*%rax
```

In other words, we have finally arrived at the actual kernel code.

The x86_64 Linux kernel entry point is `startup_64` defined in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S):

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L36-L38 -->
```assembly
	__INIT
	.code64
SYM_CODE_START_NOALIGN(startup_64)
```

How do we know that `startup_64` is really the entry point? We can verify it by checking the [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) header of `vmlinux` with `readelf`:

```bash
readelf -h vmlinux | grep "Entry point address"
  Entry point address:               0x2e9f1b0
```

Knowing the entry point address from the kernel image, we can compare it against the `startup_64` symbol address. Since kernel symbols are located at high virtual addresses (we will see more details about this soon), we subtract the text mapping base to get a physical address:

```bash
printf "0x%x\n" $(( $(nm vmlinux | grep -w "startup_64" | cut -d' ' -f1 | sed 's/^/0x/') - 0xffffffff80000000 ))
0x2e9f1b0
```

The addresses match, so `startup_64` is indeed the entry point.

## First steps in the kernel

Now that we know where the kernel entry point is, let's follow its very first instructions. First, the kernel saves the pointer to the `boot_params` structure for later use:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L59-L59 -->
```assembly
	mov	%rsi, %r15
```

The decompressor passed this pointer in the `rsi` register because the kernel will need information collected by the bootloader and during early kernel setup many times during initialization. But the `rsi` register is [caller-saved](https://en.wikipedia.org/wiki/X86_calling_conventions). This means that any function call could overwrite it. To avoid losing this data during function calls, the kernel copies it into the `r15` register, which is a safer place.

But before the kernel can call any function, it needs a valid stack. Without it, `push`, `pop`, and `call` instructions would read and write unpredictable memory, making any function call impossible. So the kernel sets up the stack:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L62-L62 -->
```assembly
	leaq	__top_init_kernel_stack(%rip), %rsp
```

The stack pointer is set to `__top_init_kernel_stack`. This is the stack of the init task which will eventually become the idle process with PID 0. The stack is `16384` bytes in size, and its top is defined in the kernel image by the [linker script](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/vmlinux.lds.S#L183-L183 -->
```linker-script
		__top_init_kernel_stack = __end_init_stack - TOP_OF_KERNEL_STACK_PADDING - PTREGS_SIZE;
```

Two subtractions reserve the top of the stack for specific purposes:

- `TOP_OF_KERNEL_STACK_PADDING` - currently reserved for [Intel FRED](https://www.intel.com/content/www/us/en/content-details/779982/flexible-return-and-event-delivery-fred-specification.html)
- `PTREGS_SIZE` - leaves room for the register frame that gets pushed during interrupt handling

With the stack ready, the kernel can now safely use stack operations and call functions.

The next few instructions deal with the `gs` register. The kernel uses it to access [per-CPU data structures](../Concepts/linux-cpu-1.md), but right now it may still hold whatever value the early kernel setup code left. If that garbage value is used as a base for a per-CPU access, the kernel would read from or write to the wrong memory location. So the kernel zeroes it out:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L69-L72 -->
```assembly
	movl	$MSR_GS_BASE, %ecx
	xorl	%eax, %eax
	xorl	%edx, %edx
	wrmsr
```

This is done using a [model-specific register](https://en.wikipedia.org/wiki/Model-specific_register) write. Model-specific registers are a special class of CPU registers for controlling processor features. They are accessed with two instructions:

- `rdmsr` - to read a value from an MSR
- `wrmsr` - to write a value to an MSR

In the code snippet above, the `wrmsr` instruction writes a 64-bit value to the MSR specified in `ecx`. The value comes from the `edx:eax` register pair. Since both are zeroed in the code snippet above, the `gs` base is set to zero.

You might wonder why the kernel doesn't just load `gs` with a regular `mov` instruction. According to the [Intel® 64 and IA-32 Architectures Software Developer’s Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html), in long mode, the CPU manages the `gs` base using the MSR rather than using a GDT descriptor:

> The hidden descriptor register fields for FS.base and GS.base are physically mapped to MSRs in order to load all address bits supported by a 64-bit implementation. Software with CPL = 0 (privileged software) can load all supported linear-address bits into FS.base or GS.base using WRMSR.

With the `gs` register zeroed out, the kernel can now turn its attention to another piece inherited from the previous stages - the Global Descriptor Table.

## Setup of the kernel GDT

The next step is the setup of the kernel [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table). Yes, yes. I can imagine how you will exclaim - how, again? Yes, again, and it is not even the last time.

The Global Descriptor Table (specified by the `gdt64` symbol) that we saw in the part about the [Linux kernel boot process](../Booting/linux-bootstrap-5.md) is a temporary table used only during decompression. The kernel cannot keep using it for two reasons. First, the decompressor's GDT is located in the decompressor's memory, which will not be mapped after the kernel switches to its own page tables. Second, each CPU needs its own GDT. The reason is that each CPU uses its own task-state segment, and the GDT entry for that segment must point to CPU-local data. The task-state segment holds the stack information that the processor uses when entering the kernel from user mode and when handling exceptions. For these reasons, the kernel loads a per-CPU Global Descriptor Table defined in [arch/x86/kernel/cpu/common.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/cpu/common.c), which contains the full set of segments needed by the kernel.

According to the [Intel® 64 and IA-32 Architectures Software Developer’s Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html):

> In 64-bit mode, segmentation is generally (but not completely) disabled, creating a flat 64-bit linear-address space. The processor treats the segment base of CS, DS, ES, SS as zero, creating a linear address that is equal to the effective address.

Despite this, the kernel still loads the following segment descriptors:

- `GDT_ENTRY_KERNEL_CS` - The kernel code segment.
- `GDT_ENTRY_KERNEL_DS` - The kernel data segment, mainly used for stack access.
- `GDT_ENTRY_KERNEL32_CS` - The 32-bit kernel segment used when switching to protected mode, for example during reboot, switching between four-level and five-level page tables, or booting secondary CPUs.
- `GDT_ENTRY_DEFAULT_USER_CS` - The userspace code segment.
- `GDT_ENTRY_DEFAULT_USER_DS` - The userspace data segment, used for stack and data segment access.
- `GDT_ENTRY_DEFAULT_USER32_CS` - The 32-bit userspace segment used for running 32-bit userspace programs.

The main reason to load these descriptors is how they are used in long mode. Although the base and limit values of the code segment are ignored and no longer used for address calculations, the other fields still function normally. For example, privilege checks are still performed.

The following call loads the new Global Descriptor Table:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L74-L74 -->
```assembly
	call	__pi_startup_64_setup_gdt_idt
```

Before we look at this function, there is an interesting detail about how it is called. You will not find its definition if you try to grep the Linux kernel source code:

```bash
rg __pi_startup_64_setup_gdt_idt
arch/x86/kernel/head_64.S
74:	call	__pi_startup_64_setup_gdt_idt
```

We can find the actual definition of this function in [arch/x86/boot/startup/gdt_idt.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/startup/gdt_idt.c), but it will be without the `__pi_` prefix:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/gdt_idt.c#L49-L49 -->
```C
void __init startup_64_setup_gdt_idt(void)
```

All symbols from the [arch/x86/boot/startup](https://github.com/torvalds/linux/tree/master/arch/x86/boot/startup) directory are prefixed with `__pi_` using `objcopy`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/Makefile#L39-L49 -->
```make
$(pi-objs): objtool-args	= $(if $(delay-objtool),--dry-run,$(objtool-args-y)) --noabs

#
# Confine the startup code by prefixing all symbols with __pi_ (for position
# independent). This ensures that startup code can only call other startup
# code, or code that has explicitly been made accessible to it via a symbol
# alias.
#
$(obj)/%.pi.o: OBJCOPYFLAGS := --prefix-symbols=__pi_
$(obj)/%.pi.o: $(obj)/%.o FORCE
	$(call if_changed,objcopy)
```

As the comment says, this prefixing is used to **confine** early startup code. By rewriting the symbols in this directory with the `__pi_` prefix, the build system restricts startup code to referencing only other startup routines or symbols that were explicitly exposed for it. Additionally, `objtool` checks that no absolute addresses were generated.

You may ask why all of these tricks are needed. The answer is to prevent any absolute address references from appearing in startup code. As you may remember from the previous chapter, the kernel uses identity-mapping page tables at this point, which map the first four gigabytes of memory 1:1 to low physical addresses. On the other hand, the kernel is linked to run at high virtual addresses starting from `0xffffffff80000000`. Any absolute address reference would point to a high virtual address that is not covered by the current identity mappings, resulting in a [page fault](https://en.wikipedia.org/wiki/Page_fault) that the kernel is not yet ready to handle. That is why early startup code must use only position-independent, RIP-relative addressing.

Now that we know where and why the new GDT should be loaded, let's take a look at the `startup_64_setup_gdt_idt` function. It does the following things:

- Loads the new GDT using the `lgdt` instruction, which should be familiar from the previous chapter
- Reloads the data segment registers with the `__KERNEL_DS` selector
- Loads an early IDT, although it is empty unless [AMD Secure Memory Encryption](https://www.amd.com/en/developer/sev.html) is enabled

Notice how `rip_rel_ptr` is used to get the runtime address of `gdt_page`. This is the position-independent technique in action. Since the kernel is still running at low identity-mapped addresses, it cannot use the link-time virtual address of `gdt_page` directly:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/gdt_idt.c#L49-L71 -->
```C
void __init startup_64_setup_gdt_idt(void)
{
	struct gdt_page *gp = rip_rel_ptr((void *)(__force unsigned long)&gdt_page);
	void *handler = NULL;

	struct desc_ptr startup_gdt_descr = {
		.address = (unsigned long)gp->gdt,
		.size    = GDT_SIZE - 1,
	};

	/* Load GDT */
	native_load_gdt(&startup_gdt_descr);

	/* New GDT is live - reload data segment registers */
	asm volatile("movl %%eax, %%ds\n"
		     "movl %%eax, %%ss\n"
		     "movl %%eax, %%es\n" : : "a"(__KERNEL_DS) : "memory");

	if (IS_ENABLED(CONFIG_AMD_MEM_ENCRYPT))
		handler = rip_rel_ptr(vc_no_ghcb);

	startup_64_load_idt(handler);
}
```

The `gdt_page` itself is defined in [arch/x86/kernel/cpu/common.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/cpu/common.c) and contains the segment descriptors we mentioned above:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/cpu/common.c#L210-L225 -->
```C
DEFINE_PER_CPU_PAGE_ALIGNED(struct gdt_page, gdt_page) = { .gdt = {
#ifdef CONFIG_X86_64
	/*
	 * We need valid kernel segments for data and code in long mode too
	 * IRET will check the segment types  kkeil 2000/10/28
	 * Also sysret mandates a special GDT layout
	 *
	 * TLS descriptors are currently at a different place compared to i386.
	 * Hopefully nobody expects them at a fixed place (Wine?)
	 */
	[GDT_ENTRY_KERNEL32_CS]		= GDT_ENTRY_INIT(DESC_CODE32, 0, 0xfffff),
	[GDT_ENTRY_KERNEL_CS]		= GDT_ENTRY_INIT(DESC_CODE64, 0, 0xfffff),
	[GDT_ENTRY_KERNEL_DS]		= GDT_ENTRY_INIT(DESC_DATA64, 0, 0xfffff),
	[GDT_ENTRY_DEFAULT_USER32_CS]	= GDT_ENTRY_INIT(DESC_CODE32 | DESC_USER, 0, 0xfffff),
	[GDT_ENTRY_DEFAULT_USER_DS]	= GDT_ENTRY_INIT(DESC_DATA64 | DESC_USER, 0, 0xfffff),
	[GDT_ENTRY_DEFAULT_USER_CS]	= GDT_ENTRY_INIT(DESC_CODE64 | DESC_USER, 0, 0xfffff),
```

With the new Global Descriptor Table in place, the kernel reloads the code segment register to use the `__KERNEL_CS` selector from the new GDT:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L77-L80 -->
```assembly
	pushq	$__KERNEL_CS
	leaq	.Lon_kernel_cs(%rip), %rax
	pushq	%rax
	lretq
```

This code is easier to read from the end. The `lretq` instruction pops two values from the stack:

- The first into the `rip` register
- The second into the `cs` register

After execution, the CPU continues at `.Lon_kernel_cs` symbol, which is located right after the `lretq` instruction, ensuring the kernel is running with the correct code segment from its own GDT. The next structure to update is the page tables.

## Switching to the kernel page tables

> [!NOTE]
> The code in this section also handles [5-level paging](https://en.wikipedia.org/wiki/Intel_5-level_paging) and [AMD Secure Memory Encryption](https://developer.amd.com/sev/). We will not cover these topics here to keep things focused on the core page table setup.

The next big step after the GDT setup is to adjust the page tables. This is one of the most critical parts of the early initialization, where the kernel needs to:

- Build page tables that map it at its high virtual address
- Create a temporary identity mapping so that switching to the new page tables does not cause a page fault
- Perform the switch to the new page tables

But before we look at the code, let's refresh our memory on how page tables work on x86_64 and where the kernel is supposed to be mapped in the virtual address space.

### Page tables on x86_64

To translate a virtual address to the corresponding physical address, the CPU goes through up to four levels of page tables:

- PGD - Page Global Directory
- PUD - Page Upper Directory
- PMD - Page Middle Directory
- PTE - Page Table Entry

The modern Linux kernel actually defines a fifth level called P4D (Page Level 4 Directory), adding a new layer between the PGD and the PUD. This level is used when 5-level paging is enabled, extending the virtual address space from `2^48` to `2^57` bytes. But most systems today still use 4-level paging. The CPU may simply not support 5-level paging, or it can be disabled with the `no5lvl` kernel command line option. So what happens to this extra level?

The answer is a trick called **page table folding**. When 5-level paging is disabled, the P4D level is folded into the PGD. The kernel defines `p4d_t` as a wrapper around `pgd_t`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/asm-generic/pgtable-nop4d.h#L9-L9 -->
```C
typedef struct { pgd_t pgd; } p4d_t;
```

One more thing about the page table hierarchy - not all levels have to be used. For example, the lower levels like PTE or even PMD can be omitted when larger page sizes are used. The early kernel page tables use this approach with 2 MB large pages, where the PMD entry maps a physical page. We will see this in the section below. The following three levels of page tables will be built:

- `early_top_pgt` - PGD
- `level3_kernel_pgt` - PUD
- `level2_kernel_pgt` - PMD

After this short reminder, let's get back to why the kernel needs to rebuild its page tables and how it builds them. To understand this, we need to know where the kernel is right now and where it should be.

### Kernel address space

At this point, the kernel is running with the page tables that were set up by the decompressor code. These are simple identity-mapped page tables, meaning that a virtual address maps directly to the same physical address. The first four gigabytes of physical memory are mapped to the first four gigabytes of virtual memory. Since the kernel is usually loaded somewhere in low memory, these page tables were enough to get the kernel through decompression. Of course, the bootloader can load the kernel relatively high, or KASLR can affect its physical location. But whatever load address was chosen, it is still much lower than the special location in virtual address space where the kernel is supposed to be mapped.

On x86_64, the virtual address space is huge - `2^48` bytes with 4-level paging. The virtual address space is split into two halves of `2^47` bytes each:

- The lower half, which covers addresses starting from `0x0`, belongs to userspace processes
- The upper half is the kernel's address space

The kernel text is mapped starting at the `0xffffffff81000000` address. This is where the linker places all kernel symbols when `vmlinux` is built. We can verify this with `readelf`:

```bash
readelf -S vmlinux | grep "  \[ 1\] \.text"
  [ 1] .text             PROGBITS         ffffffff81000000  00200000
```

We can find the whole virtual memory map of the Linux kernel for x86_64 in the [Documentation/arch/x86/x86_64/mm.rst](https://github.com/torvalds/linux/blob/master/Documentation/arch/x86/x86_64/mm.rst) document. I know. This table can look intimidating at first glance, but do not worry. We will refer back to specific regions of memory as they become relevant. For now, we are interested only in the last few entries at the very bottom of the table, which describe the kernel code mapping areas:

| Start addr       | Offset   | End addr         | Size    | Description                                            |
|------------------|----------|------------------|---------|--------------------------------------------------------|
| ffffffff80000000 | -2 GB    | ffffffff9fffffff | 512 MB  | kernel text mapping, mapped to physical address 0      |
| ffffffffa0000000 | -1536 MB | fffffffffeffffff | 1520 MB | module mapping space                                   |
| FIXADDR_START    | ~-11 MB  | ffffffffff5fffff | ~0.5 MB | kernel-internal fixmap range, variable size and offset |

Every function and every global variable in the kernel was linked to run at these high addresses. But the kernel's current page tables know nothing about this memory region since they cover only the low memory range. If the kernel tried to jump to its linked address right now, the CPU would trigger a page fault because there is no page table entry for it.

This is the main reason the kernel must build new page tables. Right now it is still running with the decompressor's identity-mapped tables, but soon it must switch to tables that also map the kernel at its linked high virtual addresses. Before we follow the code, it helps to picture that change.

Right now the page tables have the following structure:

![early-page-tables](./images/early-page-tables.svg)

After the new page tables are built, the structure looks like this:

![early-page-tables-on-init](./images/early-page-tables-after-init.svg)

### Building the page tables

Now that we have a picture of what will happen, we can take a look at the code. The new page tables are built in the `__startup_64` function defined in [arch/x86/boot/startup/map_kernel.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/startup/map_kernel.c). Let's look at the definition of this function. It takes two arguments:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L87-L88 -->
```C
unsigned long __init __startup_64(unsigned long p2v_offset,
				  struct boot_params *bp)
```

The second argument is well known to us from the previous chapter. It is a pointer to the data structure which contains information that the bootloader and early kernel code collected during boot. The first parameter is more interesting. Its value is computed right before the call to `__startup_64` in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L104-L105 -->
```assembly
	leaq	common_startup_64(%rip), %rdi
	subq	.Lcommon_startup_64(%rip), %rdi
```

These two instructions calculate the so-called `physical-to-virtual` offset. Since the kernel was loaded at some low address like `0x1000000` but linked to high addresses like `0xffffffff81000000`, every reference can have two interpretations:

- The runtime address - the address where the code is actually running
- The link-time address - the address assigned by the linker when the kernel was built

For example, the `_text` symbol might be located at the `0x1000000` address in memory when the kernel is loaded, but the `0xffffffff81000000` address is assigned during linking.

To switch safely to the kernel address space, the kernel must understand how these two address spaces relate to each other. This relation is usually called an offset between the runtime and link-time addresses in the kernel. The two instructions in the code snippet above calculate this offset.

The first instruction puts the runtime address of the `common_startup_64` symbol in the `rdi` register. The second instruction subtracts the link-time address of the same symbol from `rdi`, producing `runtime_address − linktime_address`. This may look tricky because `0x1000000 - 0xffffffff81000000` appears to be a negative value, but pay attention to the type of the `p2v_offset` argument. It is `unsigned long`, so `p2v_offset` will contain a wrapped-around value.

Knowing this offset, the kernel can convert from virtual address to physical and vice versa:

- `physical = virtual + p2v_offset`
- `virtual  = physical - p2v_offset`

It may not be obvious why this "trick" even works, so let's look at it more carefully. The offset is computed as:

```
offset = runtime_address - linktime_address
```

Since at this point the kernel uses identity-mapped pages, the runtime address equals the corresponding physical address. On the other hand, the virtual address assigned during linking is the address the kernel wants to map to. So the formula above can be rewritten as:

```
offset = physical_address - virtual_address
```

From here we have:

```
physical_address = virtual_address + offset

virtual_address = physical_address - offset
```

For example, `common_startup_64` might be located at `0x0000000001000dc0` when the kernel is loaded, and assigned `0xffffffff81000dc0` during linking. The physical-to-virtual offset is:

```python
# Offset
>>> hex((0x0000000001000dc0 - 0xffffffff81000dc0) & 0xffffffffffffffff)
'0x80000000'
```

The conversion between physical and virtual addresses of this symbol using the offset is:

```python
# Physical address
>>> hex((0xffffffff81000dc0 + 0x80000000) & 0xffffffffffffffff)
'0x1000dc0'

# Virtual address
>>> hex((0x0000000001000dc0 - 0x80000000) & 0xffffffffffffffff)
'0xffffffff81000dc0'
```

This is exactly the technique used at the beginning of the `__startup_64` function. `__START_KERNEL_map` is the base of the kernel text mapping, so adding `p2v_offset` converts it to the corresponding physical address:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L112-L112 -->
```C
	phys_base = load_delta = __START_KERNEL_map + p2v_offset;
```

Both `phys_base` and `load_delta` have the same value, but later they will serve two different purposes:

- `phys_base` is used as the physical base of the kernel text mapping
- `load_delta` is used to fix up page table entries

The same technique gives the virtual addresses of the kernel image boundaries. `physaddr` is the runtime address of `_text`, obtained earlier via `rip_rel_ptr`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L118-L119 -->
```C
	va_text = physaddr - p2v_offset;
	va_end  = (unsigned long)rip_rel_ptr(_end) - p2v_offset;
```

Now that we understand what `load_delta` means, we can see how the kernel builds the new page tables. The page table entries were computed at link time from virtual addresses, so they need to be adjusted to reflect where the kernel actually loaded. The key operation is adding `load_delta` to those entries.

The base of the new page table is `early_top_pgt`. This structure is defined in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L603-L608 -->
```assembly
SYM_DATA_START_PTI_ALIGNED(early_top_pgt)
	.fill	511,8,0
	.quad	level3_kernel_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC
	.fill	PTI_USER_PGD_FILL,8,0
SYM_DATA_END(early_top_pgt)
SYM_PIC_ALIAS(early_top_pgt)
```

The first `511` entries of the top level page table are empty, and only the last one points to `level3_kernel_pgt`. At first glance, you may think that the single entry is not enough, but this makes perfect sense. Each PGD entry covers 512 GB of memory, and the kernel is mapped in the very last 2 GB of the virtual address space. Entry `511` is the one that covers that memory region. The remaining entries are empty for now, but will be filled in the `__startup_64` function with the identity mapping pages needed for the `cr3` register switch. We will see that a little later, but first comes the adjusting of the top-level page entry:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L126-L127 -->
```C
	pgd = rip_rel_ptr(early_top_pgt);
	pgd[pgd_index(__START_KERNEL_map)] += load_delta;
```

The first line uses `rip_rel_ptr` to obtain the physical address of the top-level page table using RIP-relative addressing. The second line looks up the PGD entry that covers `__START_KERNEL_map`, or `0xffffffff80000000`. This is entry `511`, and the kernel adds `load_delta` to it to fix up the stored address.

To understand this better, let's take one more look at how entry `511` is defined:

```assembly
	.quad	level3_kernel_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC
```

`level3_kernel_pgt` has a link-time virtual address. Subtracting `__START_KERNEL_map` removes the virtual base and leaves an offset. That offset would be the correct physical address only if `__START_KERNEL_map` mapped to physical address `0`.

At the default load address this is true, so `load_delta` is zero. But if [KASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization#Linux) or another mechanism places the kernel elsewhere, the offset no longer matches the real physical address. So adding `load_delta` corrects it. Since `load_delta` is the sum of `__START_KERNEL_map` and the physical-to-virtual offset, the 511th entry of the top-level page table becomes:

```
level3_kernel_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC + __START_KERNEL_map + p2v_offset
```

Or just:

```
level3_kernel_pgt + p2v_offset + _PAGE_TABLE_NOENC
```

This is the physical address of `level3_kernel_pgt` together with its flags. It is exactly what a page table entry must contain.

Now the kernel moves on to the next level - `level3_kernel_pgt`, defined in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L630-L635 -->
```assembly
SYM_DATA_START_PAGE_ALIGNED(level3_kernel_pgt)
	.fill	L3_START_KERNEL,8,0
	/* (2^48-(2*1024*1024*1024)-((2^39)*511))/(2^30) = 510 */
	.quad	level2_kernel_pgt - __START_KERNEL_map + _KERNPG_TABLE_NOENC
	.quad	level2_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC
SYM_DATA_END(level3_kernel_pgt)
```

The first 510 entries of this page table are empty and the last two are special:

- `510` - maps the kernel image itself
- `511` - maps the fixmap region, used for special mappings like APIC and other fixed kernel mappings

Both entries use the same `symbol - __START_KERNEL_map` pattern we already saw, so they need the same adjustment with `load_delta`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L136-L137 -->
```C
	level3_kernel_pgt[PTRS_PER_PUD - 2].pud += load_delta;
	level3_kernel_pgt[PTRS_PER_PUD - 1].pud += load_delta;
```

We reached the bottom level of the current page table hierarchy. Here the kernel only adjusts entries that actually cover the kernel image and invalidates everything else:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L201-L214 -->
```C
	pmd = rip_rel_ptr(level2_kernel_pgt);

	/* invalidate pages before the kernel image */
	for (i = 0; i < pmd_index(va_text); i++)
		pmd[i] &= ~_PAGE_PRESENT;

	/* fixup pages that are part of the kernel image */
	for (; i <= pmd_index(va_end); i++)
		if (pmd[i] & _PAGE_PRESENT)
			pmd[i] += load_delta;

	/* invalidate pages after the kernel image */
	for (; i < PTRS_PER_PMD; i++)
		pmd[i] &= ~_PAGE_PRESENT;
```

The kernel image mappings are not the only entries that need fixing. As we have seen above, the early page tables also contain the fixmap region. So the entries related to it must be adjusted by `load_delta` as well:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L139-L140 -->
```C
	for (i = FIXMAP_PMD_TOP; i > FIXMAP_PMD_TOP - FIXMAP_PMD_NUM; i--)
		level2_fixmap_pgt[i].pmd += load_delta;
```

At this point, the kernel mapping at its high virtual addresses is complete. But if the kernel would try to switch to these page tables right now, execution would immediately go wrong. The kernel is still executing at low addresses while it has just built page tables with high virtual addresses. Without a temporary identity mapping, updating the `cr3` register would immediately lead to a [page fault](https://en.wikipedia.org/wiki/Page_fault).

To avoid this problem, the kernel needs to build temporary identity-mapping page tables. By also mapping the low physical address range where the CPU is currently running, the kernel makes sure that both the current physical address (where execution is right now) and the new high address (where the kernel should be mapped) are valid at the moment of the switch. Once the kernel jumps to its high virtual address, this identity mapping will have served its purpose and can be discarded.

To build the temporary identity mapping page tables, the kernel uses the `early_dynamic_pgts` array defined in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L610-L612 -->
```assembly
SYM_DATA_START_PAGE_ALIGNED(early_dynamic_pgts)
	.fill	512*EARLY_DYNAMIC_PAGE_TABLES,8,0
SYM_DATA_END(early_dynamic_pgts)
```

The kernel fills two top-level page table entries, both pointing to the same PUD page from the `early_dynamic_pgts` array:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L166-L168 -->
```C
		i = (physaddr >> PGDIR_SHIFT) % PTRS_PER_PGD;
		pgd[i + 0] = (pgdval_t)pud + pgtable_flags;
		pgd[i + 1] = (pgdval_t)pud + pgtable_flags;
```

Two adjacent entries are filled with the same pointer. Each PGD entry covers 512 GB, so if the kernel is loaded near a region boundary, both entries need to be valid. The kernel uses the same approach at the PUD level. At the bottom, it fills PMD entries with 2 MB large pages covering the physical range of the kernel image:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/map_kernel.c#L171-L183 -->
```C
	i = physaddr >> PUD_SHIFT;
	pud[(i + 0) % PTRS_PER_PUD] = (pudval_t)pmd + pgtable_flags;
	pud[(i + 1) % PTRS_PER_PUD] = (pudval_t)pmd + pgtable_flags;

	pmd_entry = __PAGE_KERNEL_LARGE_EXEC & ~_PAGE_GLOBAL;
	pmd_entry += sme_get_me_mask();
	pmd_entry +=  physaddr;

	for (i = 0; i < DIV_ROUND_UP(va_end - va_text, PMD_SIZE); i++) {
		int idx = i + (physaddr >> PMD_SHIFT);

		pmd[idx % PTRS_PER_PMD] = pmd_entry + i * PMD_SIZE;
	}
```

With the identity mapping page tables built, the kernel has page tables that map the kernel image at both its physical load address and its link-time virtual address. The identity mapping allows the kernel to safely switch `cr3` to the new page tables pointed to by `early_top_pgt`, and then jump from the low identity-mapped addresses into the high kernel virtual address space where it will continue the rest of initialization. These are still minimal early page tables. They only cover the kernel image itself and the fixmap region. We will see how the full page tables are built much later.

## Completing the transition to kernel address space

With the new kernel page tables ready, the `__startup_64` function returns and we arrive at [`common_startup_64`](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S). Now the kernel loads `cr3` with the address of `early_top_pgt`, activating the new page tables. The moment this write happens, every memory access, including the fetch of the next instruction, goes through the new page tables. This is why the kernel still needs the identity mapping. Without it, a page fault exception would be triggered on the very next instruction fetch.

After switching to the new page tables, some old [TLB](https://en.wikipedia.org/wiki/Translation_lookaside_buffer) entries may still survive. According to the [Intel® 64 and IA-32 Architectures Software Developer’s Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html), reloading the `cr3` register flushes most TLB entries, but global entries survive: 

> Global pages are not flushed from the translation-lookaside buffer (TLB) on a task switch or a write to register CR3.

So the kernel still needs an additional TLB flush. To flush those entries, the kernel clears the `PGE` ([Page Global Enable](https://en.wikipedia.org/wiki/Control_register)) bit in the `cr4` register. Changing this bit invalidates all global TLB entries, and setting it back re-enables global translations with fresh entries from the new page tables. But `cr4` contains many other important bits, so the kernel cannot just zero the whole register. It first builds a mask of the bits that must survive the flush. These bits are:

- [`PAE`](https://en.wikipedia.org/wiki/Physical_Address_Extension) 
- [`LA57`](https://en.wikipedia.org/wiki/Intel_5-level_paging)
- [`MCE`](https://en.wikipedia.org/wiki/Machine-check_exception)

The code below does this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L211-L221 -->
```assembly
	movl	$(X86_CR4_PAE | X86_CR4_LA57), %edx
#ifdef CONFIG_X86_MCE
	/*
	 * Preserve CR4.MCE if the kernel will enable #MC support.
	 * Clearing MCE may fault in some environments (that also force #MC
	 * support). Any machine check that occurs before #MC support is fully
	 * configured will crash the system regardless of the CR4.MCE value set
	 * here.
	 */
	orl	$X86_CR4_MCE, %edx
#endif
```

Then, the kernel performs the actual flush. It reads `cr4`, masks it to keep only the preserved bits, adds [`PSE`](https://en.wikipedia.org/wiki/Page_Size_Extension), and writes it back. This first write clears `PGE`, which flushes the global TLB entries that survived the `cr3` reload. Then a second write sets `PGE` again, re-enabling global pages with fresh TLB entries:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L222-L233 -->
```assembly
	movq	%cr4, %rcx
	andl	%edx, %ecx

	/* Even if ignored in long mode, set PSE uniformly on all logical CPUs. */
	btsl	$X86_CR4_PSE_BIT, %ecx
	movq	%rcx, %cr4

	/*
	 * Set CR4.PGE to re-enable global translations.
	 */
	btsl	$X86_CR4_PGE_BIT, %ecx
	movq	%rcx, %cr4
```

With `cr4` configured and the TLB flushed, the kernel is almost ready to leave assembly behind and enter C code. But first, there is a familiar pattern here. Just as it had to load the GDT and stack earlier while running on identity-mapped pages, it must reload them again now that the kernel runs at its high virtual addresses.

The stack pointer is updated to a proper kernel stack. On the current boot CPU, this is the init task's stack. On secondary CPUs it will be the current task's per-CPU stack. The Global Descriptor Table is loaded again... yes, again. The first load used the identity-mapped address of `gdt_page`, but now the GDTR must point to the proper virtual address of the GDT. The Interrupt Descriptor Table is reloaded too for the same reason. But since it is empty, for now we will skip it.

With all of that done, the kernel is ready to make the jump:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L418-L418 -->
```assembly
	callq	*initial_code(%rip)
```

The `initial_code` is defined like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/head_64.S#L479-L479 -->
```assembly
SYM_DATA(initial_code,	.quad x86_64_start_kernel)
```

Through `initial_code`, the kernel calls the `x86_64_start_kernel` function from [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head64.c). This is a milestone worth noting! For the first time since the kernel started executing, the instruction pointer holds an address the linker intended. From now on, every function call and global variable reference resolves to its compiled virtual address. The time for position-independent code and manual address fixups is over. There is still a long way to go before the first userspace process runs, but this is a nice checkpoint to end the first part about initialization.

## Conclusion

This is the end of the first part about the initialization process of the Linux kernel. If you have questions or suggestions, feel free to ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).

In the next part, we will continue to dive into this interesting process and see the continuation of the x86_64 architecture-specific initialization before the kernel jumps to the "generic" entry point - `start_kernel`.

## Links

Here is the list of the links that you may find useful when reading this chapter:

- [Linux kernel boot process](https://github.com/0xAX/linux-insides/tree/master/Booting)
- [Real mode](https://en.wikipedia.org/wiki/Real_mode)
- [Protected mode](https://en.wikipedia.org/wiki/Protected_mode)
- [Long mode](https://en.wikipedia.org/wiki/Long_mode)
- [GNU linker documentation](https://ftp.gnu.org/old-gnu/Manuals/ld-2.9.1/html_node/ld_21.html)
- [Paging](https://en.wikipedia.org/wiki/Memory_paging)
- [Model-specific register](https://en.wikipedia.org/wiki/Model-specific_register)
- [Control register](https://en.wikipedia.org/wiki/Control_register)
