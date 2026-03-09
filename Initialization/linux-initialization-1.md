# Kernel Initialization — Part 1

The previous [post](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-6.md) was the final part of the chapter describing the Linux kernel [booting process](https://github.com/0xAX/linux-insides/tree/master/Booting). In that chapter, we looked at the kernel boot process path step by step, starting from the very first instructions executed after the system powers on, through the bootloader, and finally into the Linux kernel setup code.

Now we are entering the next stage of the journey - the initialization of the Linux kernel.

Everything we have seen so far happened before the kernel really started running. The setup code prepared the environment:

- switched CPU modes: from [real mode](https://en.wikipedia.org/wiki/Real_mode) to [protected mode](https://en.wikipedia.org/wiki/Protected_mode), and to [long mode](https://en.wikipedia.org/wiki/Long_mode) from there
- temporary page tables were built
- the kernel was relocated and decompressed

Only after all of these steps are complete, we are finally inside the Linux kernel!

By the time we reach this point, the compressed kernel image has already been decompressed and placed at the correct location in memory. The decompressor code has finished its job, and the temporary environment created during early boot is no longer needed. For now, the control was transferred to the kernel code.

All upcoming parts of this chapter will be dedicated to exploring how the kernel initializes itself before launching the very first userspace process with [PID](https://en.wikipedia.org/wiki/Process_identifier) `1`. It can be hard to believe, but even after so much code we already have seen, there is really still a lot to do. The kernel must initialize all core subsystems, finish setting up memory management, detect hardware and load drivers for it, and perform many other tasks before userspace code will be able to run.

Our journey begins at the kernel entry point located in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S). From there we will move step by step through the early initialization code, looking at the first actions performed by the kernel:

- preparing the execution environment
- setting up early page tables
- switching to the proper kernel descriptors

And many others actions before we will see the famous `start_kernel` function from [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c), which begins the main initialization sequence of the Linux kernel.

## First steps in the kernel

At the end of the previous chapter, we reached the moment when the kernel decompressor finished its job. The `decompress_kernel` function from [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c) returned the address of the decompressed kernel image, this address was placed in the `rax` register, and execution flow switched directly to it:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L475-L475 -->
```assembly
jmp	*%rax
```

In other words, control has now been transferred from the temporary decompressor environment to the actual Linux kernel code.

The entry point of the decompressed kernel image is defined in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) assembly source file. This file contains the very first instructions executed by the 64-bit Linux kernel:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L36-L38 -->
```assembly
	__INIT
	.code64
SYM_CODE_START_NOALIGN(startup_64)
```

The `startup_64` symbol represents the entry point of the kernel image. Its definition is preceded by the `__INIT` macro, which says that this code into a special section in the kernel image. The `__INIT` macro expands to the definition of the `.init.text` section:

```C
#define __INIT		.section	".init.text","ax"
```

The `.init.text` section contains code that is executed only during the early stages of kernel startup. Once initialization is complete, this memory can be reclaimed because the code in this section is no longer needed. The layout of this section is described in the kernel linker script which is used during the compilation and linking of the kernel. We can find the corresponding definition in the [arch/x86/kernel/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S) linker script:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/vmlinux.lds.S#L217-L217 -->
```linker-script
	INIT_TEXT_SECTION(PAGE_SIZE)
```

The `INIT_TEXT_SECTION` macro defined in [include/asm-generic/vmlinux.lds.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/vmlinux.lds.h) and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/asm-generic/vmlinux.lds.h#L1154-L1160 -->
```C
#define INIT_TEXT_SECTION(inittext_align)				\
	. = ALIGN(inittext_align);					\
	.init.text : AT(ADDR(.init.text) - LOAD_OFFSET) {		\
		_sinittext = .;						\
		INIT_TEXT						\
		_einittext = .;						\
	}
```

This macro defines the `.init.text` section and its memory location. The linker first aligns the section to the page size boundary (4096 bytes) and then places all initialization code between the `_sinittext` and `_einittext` symbols. Each section can have at least two addresses associated with it:

- `VMA` or virtual memory address - an address of a section in runtime
- `LMA` or load memory address - where a section must be placed in a binary

The `ADDR` directive in the linker script above, returns `VMA` or virtual memory address of the `.init.text` section assigned to this section during linking. We can see it using the following command:

```bash
objdump -h vmlinux | grep -E "(Idx Name|init\.text)"
Idx Name          Size      VMA               LMA               File off  Algn
 19 .init.text    000af4c4  ffffffff83ce7000  0000000003ce7000  02ee7000  2**5
```

The `AT` directive tells the linker where the section should be placed in the kernel image. The `LOAD_OFFSET` represents the base of the kernel virtual address space and equal to `0xffffffff80000000`. In other words, the section is linked to execute at a high kernel virtual address, but the loader places it in memory at a lower physical address. Subtracting the `LOAD_OFFSET` converts the virtual address assigned by the linker into the correct load address used during early boot.

If you are interested to know more details about the linker script syntax and keywords, you can take a look at the [official GNU linker](https://ftp.gnu.org/old-gnu/Manuals/ld-2.9.1/html_node/ld_21.html) documentation.

At this point, we know where the kernel's entry point is located. But how do we know that the entry point of the kernel is `startup_64` and not something else? From the previous chapter we already know that the kernel image was decompressed at the `0x1000000` adddress, at least if the address randomization was disabled. Although the kernels' entry point is not in the beginning of the kernel image, but has some offset from it. We can check it using the `readelf` utility:

```bash
readelf -h vmlinux | grep "Entry point address"
  Entry point address:               0x2e9f1b0
```

This is the offset of the kernel's entry point and where the kernel jumps after the decompression. You can remember that this offset was returned from the `parse_elf` function in [arc/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L331-L331 -->
```C
	return ehdr.e_entry - LOAD_PHYSICAL_ADDR;
```

It was added to the base address of the decompression buffer after the kernel was decompressed in the `extract_kernel` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L536-L536 -->
```C
	return output + entry_offset;
```

Now let's  check the address of the `startup_64` symbol to be sure that it is the entry point:

```bash
printf "0x%x\n" $(( $(nm vmlinux | grep -w "startup_64" | cut -d' ' -f1 | sed 's/^/0x/') - 0xffffffff80000000 ))
0x2e9f1b0
```

The `startup_64` has the same address which we have seen above in the output of the `readelf`. Now when we are sure that we are really found the correct entry point of the Linux kernel, let's take a look at the first instructions executed there.

The very first instruction that we can see is:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L59-L59 -->
```assembly
	mov	%rsi, %r15
```

This instruction stores the pointer to the `boot_params` structure in the `r15` register to preserve it for later use.

After the `boot_params` pointer is handled, the next step is the stack setup:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L62-L62 -->
```assembly
	leaq	__top_init_kernel_stack(%rip), %rsp
```

This instruction loads the address of `__top_init_kernel_stack` into the `rsp` register, which is the stack pointer in 64-bit mode. We can find the definition of the `__top_init_kernel_stack` in the same [linker script]() that we already saw above:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/vmlinux.lds.S#L183-L183 -->
```linker-script
		__top_init_kernel_stack = __end_init_stack - TOP_OF_KERNEL_STACK_PADDING - PTREGS_SIZE;
```

The top of the stack is located at the address specified by the symbol `__end_init_stack` which is defined in the `.data` section of the kernel:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/vmlinux.lds.S#L183-L183 -->
```C
#define INIT_TASK_DATA(align)						\
	. = ALIGN(align);						\
	__start_init_stack = .;						\
	init_thread_union = .;						\
	init_stack = .;							\
	KEEP(*(.data..init_thread_info))				\
	. = __start_init_stack + THREAD_SIZE;				\
	__end_init_stack = .;
```

The top of the stack is at the `__end_init_stack` address minus:

- The padding defined by the `TOP_OF_KERNEL_STACK_PADDING` which for this moment is reserved for [Intel FRED](https://www.intel.com/content/www/us/en/content-details/779982/flexible-return-and-event-delivery-fred-specification.html)
- The registers which pushed on the top of the stack during interrupt handling

The size of the init stack is `16384` bytes.

After this instruction executes, the early kernel code has a valid stack and can continue with further initialization:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L69-L72 -->
```assembly
	movl	$MSR_GS_BASE, %ecx
	xorl	%eax, %eax
	xorl	%edx, %edx
	wrmsr
```

This code writes a value to a [model-specific register](https://en.wikipedia.org/wiki/Model-specific_register). These registers are special CPU registers used to control various processor features and are accessed with the `rdmsr` (to read a value from a register) and wrmsr (to write a value to a register) instructions. In our case, the `wrmsr` instruction writes a 64-bit value to an MSR specified in the `ecx` register. The value itself is taken from the `edx:eax` register pair. As a result of the code above, the `gs` base register is initialized to zero.

This register plays a very important role. The `gs` segment is used for accessing [per-CPU data structures](../Concepts/linux-cpu-1.md). Clearing it here ensures that the register starts in a known state before the kernel sets up the proper per-CPU base during initialization.

## Setup of the kernel GDT

The next step is the setup of the kernel [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table). Yes, yes. I can imagine how you'll exclaim - how, again? Yes, again. The Global Descriptor Table (specified by the `gdt64` symbol) that we saw in the part about the [Linux kernel boot process](../Booting/linux-bootstrap-5.md) is a temporary table used only during decompression. At this moment, the kernel will load per-CPU Global Descriptor Table defined in the [arch/x86/kernel/cpu/common.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/cpu/common.c), which contains the full set of the segments needed by the kernel.

According to the [Intel® 64 and IA-32 Architectures Software Developer’s Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html):

> In 64-bit mode, segmentation is generally (but not completely) disabled, creating a flat 64-bit linear-address space. The processor treats the segment base of CS, DS, ES, SS as zero, creating a linear address that is equal to the effective address.

Despite this, the kernel loads the following segment descriptors:

- `GDT_ENTRY_KERNEL_CS` - The kernel code segment.
- `GDT_ENTRY_KERNEL_DS` - The kernel data segment, mainly used for stack access.
- `GDT_ENTRY_KERNEL32_CS` - The 32-bit kernel segment used when switching to protected mode, for example during reboot, switching between four-level and five-level page tables, or booting secondary CPUs.
- `GDT_ENTRY_DEFAULT_USER_CS` - The userspace code segment.
- `GDT_ENTRY_DEFAULT_USER_DS` - The userspace data segment, used for stack and data segment access.
- `GDT_ENTRY_DEFAULT_USER32_CS` - The 32-bit userspace segment used for running 32-bit userspace programs.

The main reason to load these descriptors is how they are used in the long mode. Despite the base and limit values of the code segment are ignored and in general are not used any more for address calculations, the other fields functions normally, for example the checks of the privileges are still executed.

The other two reasons to reload the Global Descriptor Table are:

- Each CPU needs its own GDT because each CPU requires its own TSS descriptor, and the TSS contains per-CPU data such as the kernel stack pointer and Interrupt Stack Table entries
- The current GDT resides at low identity-mapped addresses, which will soon be unmapped and become userspace memory

The loading of the new Global Descriptor table performed by the:

<!-- https://github.com/torvalds/linux/raw/refs/heads/master/arch/x86/kernel/head_64.S#L62-L62 -->
```assembly
	call	__pi_startup_64_setup_gdt_idt
```

The one interesting moment about this function is that you will not find the definition of this function if you will try "to grep" the Linux kernel source code:

```bash
rg __pi_startup_64_setup_gdt_idt
arch/x86/kernel/head_64.S
74:	call	__pi_startup_64_setup_gdt_idt
```

The actual definition of this function we can find in [arch/x86/boot/startup/gdt_idt.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/startup/gdt_idt.c), but it will be without the `__pi_` prefix:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/gdt_idt.c#L49-L49 -->
```C
void __init startup_64_setup_gdt_idt(void)
```

All symbols from this directory prefixed with the `__pi_` prefix using `objcopy`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/startup/Makefile#L42-L49 -->
```make
# Confine the startup code by prefixing all symbols with __pi_ (for position
# independent). This ensures that startup code can only call other startup
# code, or code that has explicitly been made accessible to it via a symbol
# alias.
#
$(obj)/%.pi.o: OBJCOPYFLAGS := --prefix-symbols=__pi_
$(obj)/%.pi.o: $(obj)/%.o FORCE
	$(call if_changed,objcopy)
```

This is done to prevent compiler to generate any absolute address references. As you can remember from the last parts of the previous chapter, the kernel uses identity-mapping page tables for this moment. This page tables map 1:1 the first four gigabytes of memory. From other side, the kernel is linked to the high memory virtual addresses strting from the `0xffffffff80000000` address. In this case, any absolute address reference would fail.

Now let's take a closer look at the `startup_64_setup_gdt_idt` function:

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

This function loads the new Global Descriptor Table using the `lgdt` instruction which we already saw in the previous chapter. The Global Descriptor Table is specified with the `gdt_page` which provides the memory descritpors that we mentioned above:

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

After the new Global Descriptor Table is loaded, the kernel traditionally reload the segment registers and load the new Interrupt Descriptor Table. For this moment, we will not pay too much attention on this table, since it is empty if the support for [AMD Secure Memory Encryption](https://www.amd.com/en/developer/sev.html) is not enabled.

Since the kernel loaded the new Global Descriptor Table, the next action is to reload the code segment register to use the __KERNEL_CS selector from the new GDT:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L77-L80 -->
```assembly
	pushq	$__KERNEL_CS
	leaq	.Lon_kernel_cs(%rip), %rax
	pushq	%rax
	lretq
```

The `lretq` instruction pops two values from the stack:

- The first into `rip` register
- The second into `cs` register

After execution, the CPU continues at `.Lon_kernel_cs` symbol, ensuring the kernel is running with the correct code segment from its own GDT.

TODO

Besides the definition of the `.text` section, we can understand default virtual and physical addresses from the linker script. Note that address of the `_text` is location counter which is defined as:

```
. = __START_KERNEL;
```

for [x86_64](https://en.wikipedia.org/wiki/X86-64). The definition of the `__START_KERNEL` macro is located in the [arch/x86/include/asm/page_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/page_types.h) header file and represented by the sum of the base virtual address of the kernel mapping and physical start:

```C
#define __START_KERNEL	(__START_KERNEL_map + __PHYSICAL_START)

#define __PHYSICAL_START  ALIGN(CONFIG_PHYSICAL_START, CONFIG_PHYSICAL_ALIGN)
```

Or in other words:

* Base physical address of the Linux kernel - `0x1000000`;
* Base virtual address of the Linux kernel - `0xffffffff81000000`.

After we sanitized CPU configuration, we call `__startup_64` function which is defined in [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head64.c):

```assembly
	leaq	_text(%rip), %rdi
	pushq	%rsi
	call	__startup_64
	popq	%rsi
```

```C
unsigned long __head __startup_64(unsigned long physaddr,
				 struct boot_params *bp)
{
	unsigned long load_delta, *p;
	unsigned long pgtable_flags;
	pgdval_t *pgd;
	p4dval_t *p4d;
	pudval_t *pud;
	pmdval_t *pmd, pmd_entry;
	pteval_t *mask_ptr;
	bool la57;
	int i;
	unsigned int *next_pgt_ptr;
	...
	...
	...
}
```

Since [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization#Linux) is enabled, the address `startup_64` routine was loaded may be different from the address compiled to run at, so we need to calculate the delta with the following code:

```C
	load_delta = physaddr - (unsigned long)(_text - __START_KERNEL_map);
```

As a result, `load_delta` contains the delta between the address compiled to run at and the address actually loaded.

After we got the delta, we check if `_text` address is correctly aligned for `2` megabytes. We will do it with the following code:

```C
	if (load_delta & ~PMD_PAGE_MASK)
		for (;;);
```

If `_text` address is not aligned for `2` megabytes, we enter infinite loop. The `PMD_PAGE_MASK` indicates the mask for `Page middle directory` (read [Paging](https://0xax.gitbook.io/linux-insides/summary/theory/linux-theory-1) about it) and is defined as:

```C
#define PMD_PAGE_MASK           (~(PMD_PAGE_SIZE-1))
```

where `PMD_PAGE_SIZE` macro is defined as:

```C
#define PMD_PAGE_SIZE           (_AC(1, UL) << PMD_SHIFT)
#define PMD_SHIFT		21
```

As we can easily calculate, `PMD_PAGE_SIZE` is `2` megabytes.

If [SME](https://en.wikipedia.org/wiki/Zen_%28microarchitecture%29#Enhanced_security_and_virtualization_support) is supported and enabled, we activate it and include the SME encryption mask in `load_delta`:

```C
	sme_enable(bp);
	load_delta += sme_get_me_mask();
```

Okay, we did some early checks and now we can move on.

Fix base addresses of page tables
--------------------------------------------------------------------------------

In the next step we fixup the physical addresses in the page table:

```C
	pgd = fixup_pointer(&early_top_pgt, physaddr);
	pud = fixup_pointer(&level3_kernel_pgt, physaddr);
	pmd = fixup_pointer(level2_fixmap_pgt, physaddr);
```

So, let's look at the definition of `fixup_pointer` function which returns physical address of the passed argument:

```C
static void __head *fixup_pointer(void *ptr, unsigned long physaddr)
{
	return ptr - (void *)_text + (void *)physaddr;
}
```

Next we'll focus on `early_top_pgt` and the other page table symbols which we saw above. Let's try to understand what these symbols mean. First of all let's look at their definition:

```assembly
NEXT_PAGE(early_top_pgt)
	.fill	512,8,0
	.fill	PTI_USER_PGD_FILL,8,0

NEXT_PAGE(level3_kernel_pgt)
	.fill	L3_START_KERNEL,8,0
	.quad	level2_kernel_pgt - __START_KERNEL_map + _KERNPG_TABLE_NOENC
	.quad	level2_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC

NEXT_PAGE(level2_kernel_pgt)
	PMDS(0, __PAGE_KERNEL_LARGE_EXEC,
		KERNEL_IMAGE_SIZE/PMD_SIZE)

NEXT_PAGE(level2_fixmap_pgt)
	.fill	506,8,0
	.quad	level1_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC
	.fill	5,8,0

NEXT_PAGE(level1_fixmap_pgt)
	.fill	512,8,0
```

Looks hard, but it isn't. First of all let's look at the `early_top_pgt`. It starts with the `4096` bytes of zeros (or `8192` bytes if `CONFIG_PAGE_TABLE_ISOLATION` is enabled), it means that we don't use the first `512` entries. And after this we can see `level3_kernel_pgt` entry. At the start of its definition, we can see that it is filled with the `4080` bytes of zeros (`L3_START_KERNEL` equals `510`). Subsequently, it stores two entries which map kernel space. Note that we subtract `__START_KERNEL_map` from `level2_kernel_pgt` and `level2_fixmap_pgt`. As we know `__START_KERNEL_map` is a base virtual address of the kernel text, so if we subtract `__START_KERNEL_map`, we will get physical addresses of the `level2_kernel_pgt` and `level2_fixmap_pgt`.

Next let's look at `_KERNPG_TABLE_NOENC` and `_PAGE_TABLE_NOENC`, these are just page entry access rights:

```C
#define _KERNPG_TABLE_NOENC   (_PAGE_PRESENT | _PAGE_RW | _PAGE_ACCESSED | \
			       _PAGE_DIRTY)
#define _PAGE_TABLE_NOENC     (_PAGE_PRESENT | _PAGE_RW | _PAGE_USER | \
			       _PAGE_ACCESSED | _PAGE_DIRTY)
```

The `level2_kernel_pgt` is page table entry which contains pointer to the page middle directory which maps kernel space. It calls the `PDMS` macro which creates `512` megabytes from the `__START_KERNEL_map` for kernel `.text` (after these `512` megabytes will be module memory space).

The `level2_fixmap_pgt` is a virtual addresses which can refer to any physical addresses even under kernel space. They are represented by the `4048` bytes of zeros, the `level1_fixmap_pgt` entry, `8` megabytes reserved for [vsyscalls](https://lwn.net/Articles/446528/) mapping and `2` megabytes of hole.

You can read more about it in the [Paging](https://0xax.gitbook.io/linux-insides/summary/theory/linux-theory-1) part.

Now, after we saw the definitions of these symbols, let's get back to the code. Next we initialize last entry of `pgd` with `level3_kernel_pgt`:

```C
	pgd[pgd_index(__START_KERNEL_map)] = level3_kernel_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC;
```

All of `p*d` addresses may be wrong if the `startup_64` is not equal to default `0x1000000` address. Remember that the `load_delta` contains delta between the address of the `startup_64` symbol which was got during kernel [linking](https://en.wikipedia.org/wiki/Linker_%28computing%29) and the actual address. So we add the delta to the certain entries of the `p*d`.

```C
	pgd[pgd_index(__START_KERNEL_map)] += load_delta;
	pud[510] += load_delta;
	pud[511] += load_delta;
	pmd[506] += load_delta;
```

After all of this we will have:

```
early_top_pgt[511] -> level3_kernel_pgt[0]
level3_kernel_pgt[510] -> level2_kernel_pgt[0]
level3_kernel_pgt[511] -> level2_fixmap_pgt[0]
level2_kernel_pgt[0]   -> 512 MB kernel mapping
level2_fixmap_pgt[506] -> level1_fixmap_pgt
```

Note that we didn't fixup base address of the `early_top_pgt` and some of other page table directories, because we will see this when building/filling structures of these page tables. As we corrected base addresses of the page tables, we can start to build it.

Identity mapping setup
--------------------------------------------------------------------------------

Now we can see the set up of identity mapping of early page tables. In Identity Mapped Paging, virtual addresses are mapped to physical addresses identically. Let's look at it in detail. First of all we replace `pud` and `pmd` with the pointer to first and second entry of `early_dynamic_pgts`:

```C
	next_pgt_ptr = fixup_pointer(&next_early_pgt, physaddr);
	pud = fixup_pointer(early_dynamic_pgts[(*next_pgt_ptr)++], physaddr);
	pmd = fixup_pointer(early_dynamic_pgts[(*next_pgt_ptr)++], physaddr);
```

Let's look at the `early_dynamic_pgts` definition:

```assembly
NEXT_PAGE(early_dynamic_pgts)
	.fill	512*EARLY_DYNAMIC_PAGE_TABLES,8,0
```

which will store temporary page tables for early kernel.

Next we initialize `pgtable_flags` which will be used when initializing `p*d` entries later:

```C
	pgtable_flags = _KERNPG_TABLE_NOENC + sme_get_me_mask();
```

`sme_get_me_mask` function returns `sme_me_mask` which was initialized in `sme_enable` function.

Next we fill two entries of `pgd` with `pud` plus `pgtable_flags` which we initialized above:

```C
	i = (physaddr >> PGDIR_SHIFT) % PTRS_PER_PGD;
	pgd[i + 0] = (pgdval_t)pud + pgtable_flags;
	pgd[i + 1] = (pgdval_t)pud + pgtable_flags;
```

`PGDIR_SHFT` indicates the mask for page global directory bits in a virtual address. Here we calculate modulo with `PTRS_PER_PGD` (which expands to `512`) so as not to access the index greater than `512`. There are macro for all types of page directories:

```C
#define PGDIR_SHIFT     39
#define PTRS_PER_PGD	512
#define PUD_SHIFT       30
#define PTRS_PER_PUD	512
#define PMD_SHIFT       21
#define PTRS_PER_PMD	512
```

We do the almost same thing above:

```C
	i = (physaddr >> PUD_SHIFT) % PTRS_PER_PUD;
	pud[i + 0] = (pudval_t)pmd + pgtable_flags;
	pud[i + 1] = (pudval_t)pmd + pgtable_flags;
```

Next we initialize `pmd_entry` and filter out unsupported `__PAGE_KERNEL_*` bits:

```C
	pmd_entry = __PAGE_KERNEL_LARGE_EXEC & ~_PAGE_GLOBAL;
	mask_ptr = fixup_pointer(&__supported_pte_mask, physaddr);
	pmd_entry &= *mask_ptr;
	pmd_entry += sme_get_me_mask();
	pmd_entry += physaddr;
```

Next we fill all `pmd` entries to cover full size of the kernel:

```C
	for (i = 0; i < DIV_ROUND_UP(_end - _text, PMD_SIZE); i++) {
		int idx = i + (physaddr >> PMD_SHIFT) % PTRS_PER_PMD;
		pmd[idx] = pmd_entry + i * PMD_SIZE;
	}
```

Next we fixup the kernel text+data virtual addresses. Note that we might write invalid pmds, when the kernel is relocated (`cleanup_highmap` function fixes this up along with the mappings beyond `_end`).

```C
	pmd = fixup_pointer(level2_kernel_pgt, physaddr);
	for (i = 0; i < PTRS_PER_PMD; i++) {
		if (pmd[i] & _PAGE_PRESENT)
			pmd[i] += load_delta;
	}
```

Next we remove the memory encryption mask to obtain the true physical address (remember that `load_delta` includes the mask):

```C
	*fixup_long(&phys_base, physaddr) += load_delta - sme_get_me_mask();
```

`phys_base` must match the first entry in `level2_kernel_pgt`.

As final step of `__startup_64` function, we encrypt the kernel (if SME is active) and return the SME encryption mask to be used as a modifier for the initial page directory entry programmed into `cr3` register:

```C
	sme_encrypt_kernel(bp);
	return sme_get_me_mask();
```

Now let's get back to assembly code. We prepare for next paragraph with following code:

```assembly
	addq	$(early_top_pgt - __START_KERNEL_map), %rax
	jmp 1f
```

which adds physical address of `early_top_pgt` to `rax` register so that `rax` register contains sum of the address and the SME encryption mask.

That's all for now. Our early paging is prepared and we just need to finish last preparation before we will jump into kernel entry point.

Last preparation before jump at the kernel entry point
--------------------------------------------------------------------------------

After that we jump to the label `1` we enable `PAE`, `PGE` (Paging Global Extension) and put the content of the `phys_base` (see above) to the `rax` register and fill `cr3` register with it:

```assembly
1:
	movl	$(X86_CR4_PAE | X86_CR4_PGE), %ecx
	movq	%rcx, %cr4

	addq	phys_base(%rip), %rax
	movq	%rax, %cr3
```

In the next step we check that CPU supports [NX](http://en.wikipedia.org/wiki/NX_bit) bit with:

```assembly
	movl	$0x80000001, %eax
	cpuid
	movl	%edx,%edi
```

We put `0x80000001` value to the `eax` and execute `cpuid` instruction for getting the extended processor info and feature bits. The result will be in the `edx` register which we put to the `edi`.

Now we put `0xc0000080` or `MSR_EFER` to the `ecx` and execute `rdmsr` instruction for the reading model specific register.

```assembly
	movl	$MSR_EFER, %ecx
	rdmsr
```

The result will be in the `edx:eax`. General view of the `EFER` is following:

```
63                                                                              32
 --------------------------------------------------------------------------------
|                                                                               |
|                                Reserved MBZ                                   |
|                                                                               |
 --------------------------------------------------------------------------------
31                            16  15      14      13   12  11   10  9  8 7  1   0
 --------------------------------------------------------------------------------
|                              | T |       |       |    |   |   |   |   |   |   |
| Reserved MBZ                 | C | FFXSR | LMSLE |SVME|NXE|LMA|MBZ|LME|RAZ|SCE|
|                              | E |       |       |    |   |   |   |   |   |   |
 --------------------------------------------------------------------------------
```

We will not see all fields in details here, but we will learn about this and other `MSRs` in a special part about it. As we read `EFER` to the `edx:eax`, we check `_EFER_SCE` or zero bit which is `System Call Extensions` with `btsl` instruction and set it to one. By the setting `SCE` bit we enable `SYSCALL` and `SYSRET` instructions. In the next step we check 20th bit in the `edi`, remember that this register stores result of the `cpuid` (see above). If `20` bit is set (`NX` bit) we just write `EFER_SCE` to the model specific register.

```assembly
	btsl	$_EFER_SCE, %eax
	btl	$20,%edi
	jnc     1f
	btsl	$_EFER_NX, %eax
	btsq	$_PAGE_BIT_NX,early_pmd_flags(%rip)
1:	wrmsr
```

If the [NX](https://en.wikipedia.org/wiki/NX_bit) bit is supported we enable `_EFER_NX`  and write it too, with the `wrmsr` instruction. After the [NX](https://en.wikipedia.org/wiki/NX_bit) bit is set, we set some bits in the `cr0` [control register](https://en.wikipedia.org/wiki/Control_register) with following assembly code:

```assembly
	movl	$CR0_STATE, %eax
	movq	%rax, %cr0
```

specifically the following bits:

* `X86_CR0_PE` - system is in protected mode;
* `X86_CR0_MP` - controls interaction of WAIT/FWAIT instructions with TS flag in CR0;
* `X86_CR0_ET` - on the 386, it allowed to specify whether the external math coprocessor was an 80287 or 80387;
* `X86_CR0_NE` - enable internal x87 floating point error reporting when set, else enables PC style x87 error detection;
* `X86_CR0_WP` - when set, the CPU can't write to read-only pages when privilege level is 0;
* `X86_CR0_AM` - alignment check enabled if AM set, AC flag (in EFLAGS register) set, and privilege level is 3;
* `X86_CR0_PG` - enable paging.

We already know that to run any code, and even more [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) code from assembly, we need to setup a stack. As always, we are doing it by the setting of [stack pointer](https://en.wikipedia.org/wiki/Stack_register) to a correct place in memory and resetting [flags](https://en.wikipedia.org/wiki/FLAGS_register) register after this:

```assembly
	movq initial_stack(%rip), %rsp
	pushq $0
	popfq
```

The most interesting thing here is the `initial_stack`. This symbol is defined in the [source](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) code file and looks like:

```assembly
GLOBAL(initial_stack)
    .quad  init_thread_union + THREAD_SIZE - SIZEOF_PTREGS
```

The `THREAD_SIZE` macro is defined in the [arch/x86/include/asm/page_64_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/page_64_types.h) header file and depends on value of the `KASAN_STACK_ORDER` macro:

```C
#ifdef CONFIG_KASAN
#define KASAN_STACK_ORDER 1
#else
#define KASAN_STACK_ORDER 0
#endif

#define THREAD_SIZE_ORDER       (2 + KASAN_STACK_ORDER)
#define THREAD_SIZE  (PAGE_SIZE << THREAD_SIZE_ORDER)
```

We consider when the [kasan](https://github.com/torvalds/linux/blob/master/Documentation/dev-tools/kasan.rst) is disabled and the `PAGE_SIZE` is `4096` bytes. So the `THREAD_SIZE` will expands to `16` kilobytes and represents size of the stack of a thread. Why is `thread`? You may already know that each [process](https://en.wikipedia.org/wiki/Process_%28computing%29) may have [parent processes](https://en.wikipedia.org/wiki/Parent_process) and [child processes](https://en.wikipedia.org/wiki/Child_process). Actually, a parent process and child process differ in stack. A new kernel stack is allocated for a new process. In the Linux kernel this stack is represented by the [union](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B) with the `thread_info` structure.

The `init_thread_union` is represented by the `thread_union`. And the `thread_union` is defined in the [include/linux/sched.h](https://github.com/torvalds/linux/blob/master/include/linux/sched.h) file like the following:

```C
union thread_union {
#ifndef CONFIG_ARCH_TASK_STRUCT_ON_STACK
	struct task_struct task;
#endif
#ifndef CONFIG_THREAD_INFO_IN_TASK
	struct thread_info thread_info;
#endif
	unsigned long stack[THREAD_SIZE/sizeof(long)];
};
```

The `CONFIG_ARCH_TASK_STRUCT_ON_STACK` kernel configuration option is only enabled for `ia64` architecture, and the `CONFIG_THREAD_INFO_IN_TASK` kernel configuration option is enabled for `x86_64` architecture. Thus the `thread_info` structure will be placed in `task_struct` structure instead of the `thread_union` union.

The `init_thread_union` is placed in the [include/asm-generic/vmlinux.lds.h](https://github.com/torvalds/blob/master/include/asm-generic/vmlinux.lds.h) file as part of the `INIT_TASK_DATA` macro like the following:

```C
#define INIT_TASK_DATA(align)  \
	. = ALIGN(align);      \
	...                    \
	init_thread_union = .; \
	...
```

This macro is used in the [arch/x86/kernel/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S) file like the following:

```
.data : AT(ADDR(.data) - LOAD_OFFSET) {
	...
	INIT_TASK_DATA(THREAD_SIZE)
	...
} :data
```

That is, `init_thread_union` is initialized with the address which is aligned to `THREAD_SIZE` which is `16` kilobytes.

Now we may understand this expression:

```assembly
GLOBAL(initial_stack)
    .quad  init_thread_union + THREAD_SIZE - SIZEOF_PTREGS
```

that `initial_stack` symbol points to the start of the `thread_union.stack` array + `THREAD_SIZE` which is 16 killobytes and - `SIZEOF_PTREGS` which is convention which helps the in-kernel unwinder reliably detect the end of the stack.

After the early boot stack is set, to update the [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table) with the `lgdt` instruction:

```assembly
lgdt	early_gdt_descr(%rip)
```

where the `early_gdt_descr` is defined as:

```assembly
early_gdt_descr:
	.word	GDT_ENTRIES*8-1
early_gdt_descr_base:
	.quad	INIT_PER_CPU_VAR(gdt_page)
```

We need to reload `Global Descriptor Table` because now kernel works in the low userspace addresses, but soon kernel will work in its own space.

Now let's look at the definition of `early_gdt_descr`. `GDT_ENTRIES` expands to `32` so that Global Descriptor Table contains `32` entries for kernel code, data, thread local storage segments and etc...

Now let's look at the definition of `early_gdt_descr_base`. The `gdt_page` structure is defined in the [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/desc.h) as:

```C
struct gdt_page {
	struct desc_struct gdt[GDT_ENTRIES];
} __attribute__((aligned(PAGE_SIZE)));
```

It contains one field `gdt` which is array of the `desc_struct` structure which is defined as:

```C
struct desc_struct {
         union {
                 struct {
                         unsigned int a;
                         unsigned int b;
                 };
                 struct {
                         u16 limit0;
                         u16 base0;
                         unsigned base1: 8, type: 4, s: 1, dpl: 2, p: 1;
                         unsigned limit: 4, avl: 1, l: 1, d: 1, g: 1, base2: 8;
                 };
         };
 } __attribute__((packed));
```

which looks familiar `GDT` descriptor. Note that `gdt_page` structure is aligned to `PAGE_SIZE` which is `4096` bytes. Which means that `gdt` will occupy one page.

Now let's try to understand what `INIT_PER_CPU_VAR` is. `INIT_PER_CPU_VAR` is a macro which is defined in the [arch/x86/include/asm/percpu.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/percpu.h) and just concatenates `init_per_cpu__` with the given parameter:

```C
#define INIT_PER_CPU_VAR(var) init_per_cpu__##var
```

After the `INIT_PER_CPU_VAR` macro will be expanded, we will have `init_per_cpu__gdt_page`. We can see the initialization of `init_per_cpu__gdt_page` in the [linker script](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S):

```
#define INIT_PER_CPU(x) init_per_cpu__##x = x + __per_cpu_load
INIT_PER_CPU(gdt_page);
```

As we got `init_per_cpu__gdt_page` in `INIT_PER_CPU_VAR` and `INIT_PER_CPU` macro from linker script will be expanded we will get offset from the `__per_cpu_load`. After this calculations, we will have correct base address of the new GDT.

Generally per-CPU variables is a 2.6 kernel feature. You can understand what it is from its name. When we create `per-CPU` variable, each CPU will have its own copy of this variable. Here we are creating `gdt_page` per-CPU variable. There are many advantages for variables of this type, like there are no locks, because each CPU works with its own copy of variable and etc... So every core on multiprocessor will have its own `GDT` table and every entry in the table will represent a memory segment which can be accessed from the thread which ran on the core. You can read in details about `per-CPU` variables in the [Concepts/per-cpu](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1) post.

As we loaded new Global Descriptor Table, we reload segments as we did it every time:

```assembly
	xorl %eax,%eax
	movl %eax,%ds
	movl %eax,%ss
	movl %eax,%es
	movl %eax,%fs
	movl %eax,%gs
```

After all of these steps we set up `gs` register that it post to the `irqstack` which represents special stack where [interrupts](https://en.wikipedia.org/wiki/Interrupt) will be handled on:

```assembly
	movl	$MSR_GS_BASE,%ecx
	movl	initial_gs(%rip),%eax
	movl	initial_gs+4(%rip),%edx
	wrmsr
```

where `MSR_GS_BASE` is:

```C
#define MSR_GS_BASE             0xc0000101
```

We need to put `MSR_GS_BASE` to the `ecx` register and load data from the `eax` and `edx` (which point to the `initial_gs`) with `wrmsr` instruction. We don't use `cs`, `fs`, `ds` and `ss` segment registers for addressing in the 64-bit mode, but `fs` and `gs` registers can be used. `fs` and `gs` have a hidden part (as we saw it in the real mode for `cs`) and this part contains a descriptor which is mapped to [Model Specific Registers](https://en.wikipedia.org/wiki/Model-specific_register). So we can see above `0xc0000101` is a `gs.base` MSR address. When a [system call](https://en.wikipedia.org/wiki/System_call) or [interrupt](https://en.wikipedia.org/wiki/Interrupt) occurs, there is no kernel stack at the entry point, so the value of the `MSR_GS_BASE` will store address of the interrupt stack.

In the next step we put the address of the real mode bootparam structure to the `rdi` (remember `rsi` holds pointer to this structure from the start) and jump to the C code with:

```assembly
	pushq	$.Lafter_lret	# put return address on stack for unwinder
	xorq	%rbp, %rbp	# clear frame pointer
	movq	initial_code(%rip), %rax
	pushq	$__KERNEL_CS	# set correct cs
	pushq	%rax		# target address in negative space
	lretq
.Lafter_lret:
```

Here we put the address of the `initial_code` to the `rax` and push the return address, `__KERNEL_CS` and the address of the `initial_code` to the stack. After this we can see `lretq` instruction which means that after it return address will be extracted from stack (now there is address of the `initial_code`) and jump there. `initial_code` is defined in the same source code file and looks:

```assembly
	.balign	8
	GLOBAL(initial_code)
	.quad	x86_64_start_kernel
	...
	...
	...
```

As we can see `initial_code` contains address of the `x86_64_start_kernel`, which is defined in the [arch/x86/kerne/head64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head64.c) and looks like this:

```C
asmlinkage __visible void __init x86_64_start_kernel(char * real_mode_data)
{
	...
	...
	...
}
```

It has one argument is a `real_mode_data` (remember that we passed address of the real mode data to the `rdi` register previously).

Next to start_kernel
--------------------------------------------------------------------------------

We need to see last preparations before we can see "kernel entry point" - start_kernel function from the [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c).

First of all we can see some checks in the `x86_64_start_kernel` function:

```C
BUILD_BUG_ON(MODULES_VADDR < __START_KERNEL_map);
BUILD_BUG_ON(MODULES_VADDR - __START_KERNEL_map < KERNEL_IMAGE_SIZE);
BUILD_BUG_ON(MODULES_LEN + KERNEL_IMAGE_SIZE > 2*PUD_SIZE);
BUILD_BUG_ON((__START_KERNEL_map & ~PMD_MASK) != 0);
BUILD_BUG_ON((MODULES_VADDR & ~PMD_MASK) != 0);
BUILD_BUG_ON(!(MODULES_VADDR > __START_KERNEL));
MAYBE_BUILD_BUG_ON(!(((MODULES_END - 1) & PGDIR_MASK) == (__START_KERNEL & PGDIR_MASK)));
BUILD_BUG_ON(__fix_to_virt(__end_of_fixed_addresses) <= MODULES_END);
```

There are checks for different things like virtual address of module space is not fewer than base address of the kernel text - `__STAT_KERNEL_map`, that kernel text with modules is not less than image of the kernel and etc... `BUILD_BUG_ON` is a macro which looks as:

```C
#define BUILD_BUG_ON(condition) ((void)sizeof(char[1 - 2*!!(condition)]))
```

Let's try to understand how this trick works. Let's take for example first condition: `MODULES_VADDR < __START_KERNEL_map`. `!!conditions` is the same that `condition != 0`. So it means if `MODULES_VADDR < __START_KERNEL_map` is true, we will get `1` in the `!!(condition)` or zero if not. After `2*!!(condition)` we will get or `2` or `0`. In the end of calculations we can get two different behaviors:

* We will have compilation error, because try to get size of the char array with negative index (as can be in our case, because `MODULES_VADDR` can't be less than `__START_KERNEL_map` will be in our case);
* No compilation errors.

That's all. So interesting C trick for getting compile error which depends on some constants.

In the next step we can see call of the `cr4_init_shadow` function which stores shadow copy of the `cr4` per cpu. Context switches can change bits in the `cr4` so we need to store `cr4` for each CPU. And after this we can see call of the `reset_early_page_tables` function where we resets all page global directory entries and write new pointer to the PGT in `cr3`:

```C
	memset(early_top_pgt, 0, sizeof(pgd_t)*(PTRS_PER_PGD-1));
	next_early_pgt = 0;
	write_cr3(__sme_pa_nodebug(early_top_pgt));
```

Soon we will build new page tables. Here we can see that we zero all Page Global Directory entries. After this we set `next_early_pgt` to zero (we will see details about it in the next post) and write physical address of the `early_top_pgt` to the `cr3`.

After this we clear `_bss` from the `__bss_stop` to `__bss_start` and also clear `init_top_pgt`. `init_top_pgt` is defined in the [arch/x86/kerne/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) like the following:

```assembly
NEXT_PGD_PAGE(init_top_pgt)
	.fill	512,8,0
	.fill	PTI_USER_PGD_FILL,8,0
``` 

This is exactly the same definition as `early_top_pgt`.

The next step will be setup of the early `IDT` handlers, but it's big concept so we will see it in the next post.

Conclusion
--------------------------------------------------------------------------------

This is the end of the first part about Linux kernel initialization.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](mailto:anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

In the next part we will see initialization of the early interruption handlers, kernel space memory mapping and a lot more.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Model Specific Register](http://en.wikipedia.org/wiki/Model-specific_register)
* [Paging](https://0xax.gitbook.io/linux-insides/summary/theory/linux-theory-1)
* [Previous part - kernel load address randomization](https://0xax.gitbook.io/linux-insides/summary/booting/linux-bootstrap-6)
* [NX](http://en.wikipedia.org/wiki/NX_bit)
* [ASLR](http://en.wikipedia.org/wiki/Address_space_layout_randomization)
