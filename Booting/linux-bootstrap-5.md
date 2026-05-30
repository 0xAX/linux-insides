# Kernel booting process. Part 5

In the previous [part](./linux-bootstrap-4.md), we saw the transition from the [protected mode](https://en.wikipedia.org/wiki/Protected_mode) into [long mode](https://en.wikipedia.org/wiki/Long_mode), but what we have in memory is not yet the kernel image ready to run. We are still in the kernel setup code, which should decompress the kernel and pass control to it. The next step before we see the Linux kernel entrypoint is kernel decompression.

## First steps in the long mode

The point where we stopped in the previous chapter is the [lret](https://www.felixcloutier.com/x86/ret) instruction, which performed "jump" to the `64-bit` entry point located in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L276-L278 -->
```assembly
	.code64
	.org 0x200
SYM_CODE_START(startup_64)
```

This is the first 64-bit code that we see. Before decompression, the kernel must complete a few final steps. These steps are:

- Disabling the interrupts
- Unification of the segment registers
- Calculation of the kernel relocation address
- Reload of the Global Descriptor Table
- Load of the Interrupt Descriptor Table

All of this we will see in the next sections.

### Disabling the interrupts

The `64-bit` entrypoint starts with the same two instructions that `32-bit`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L290-L291 -->
```assembly
	cld
	cli
```

As we already know from the previous part, the first instruction clears the [direction flag](https://en.wikipedia.org/wiki/Direction_flag) bit in the [flags](https://en.wikipedia.org/wiki/FLAGS_register) register, and the second instruction disables [interrupts](https://en.wikipedia.org/wiki/Interrupt).

The same as the bootloader can load the Linux kernel at the `32-bit` entrypoint instead of [16-bit entry point](linux-bootstrap-1.md#the-beginning-of-the-kernel-setup-stage), in the same way the bootloader can switch the processor into `64-bit` long mode by itself and load the kernel starting from the `64-bit` entry point. 

The kernel executes these two instructions if the bootloader didn't perform them before transfering the control to the kernel. The `direction flag` ensures that memory copying operations proceed in the correct direction, and disabling interrupts prevents them from disrupting the kernel decompression process.

### Unification of the segment registers

After these two instructions are executed, the next step is to unify segment registers:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L294-L299 -->
```assembly
	xorl	%eax, %eax
	movl	%eax, %ds
	movl	%eax, %es
	movl	%eax, %ss
	movl	%eax, %fs
	movl	%eax, %gs
```

Segment registers are not used in long mode, so the kernel resets them to zero.

### Calculation of the kernel relocation address

The next step is to compute the difference between the location the kernel was compiled to be loaded at and the location where it is actually loaded:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L315-L331 -->
```assembly
#ifdef CONFIG_RELOCATABLE
	leaq	startup_32(%rip) /* - $startup_32 */, %rbp
	movl	BP_kernel_alignment(%rsi), %eax
	decl	%eax
	addq	%rax, %rbp
	notq	%rax
	andq	%rax, %rbp
	cmpq	$LOAD_PHYSICAL_ADDR, %rbp
	jae	1f
#endif
	movq	$LOAD_PHYSICAL_ADDR, %rbp
1:

	/* Target address to relocate to for decompression */
	movl	BP_init_size(%rsi), %ebx
	subl	$ rva(_end), %ebx
	addq	%rbp, %rbx
```

This operation is very similar to what we have seen already in the [Calculation of the kernel relocation address](./linux-bootstrap-4.md#calculation-of-the-kernel-relocation-address) section of the previous chapter.

> [!TIP]
> It is highly recommended to read carefully [Calculation of the kernel relocation address](./linux-bootstrap-4.md#calculation-of-the-kernel-relocation-address) before trying to understand this code.

This piece of code is almost a 1:1 copy of what we have seen in protected mode. If you understood it back then, you shouldn't have any problems understanding it now. The main purpose of this code is to set up the `rbp` and `ebx` registers with the base addresses where the kernel will be decompressed, and the address where the kernel image with decompressor code should be relocated for safe decompression.

The only difference with the code from protected mode is that now, the kernel can use `rip` based addressing to get the address of the `startup_32`. So it does not need to do magic tricks with `call` and `popl` instructions like in protected mode. All the rest is just the same as what we already have seen in the previous chapter and done only for the same reason - if the bootloader is loaded, the kernel starts from the `64-bit` mode, and the protected mode code is skipped.

After these addresses are obtained, the kernel sets up the stack for the decompressor code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L334-L334 -->
```assembly
	leaq	rva(boot_stack_end)(%rbx), %rsp
```

### Reload of the Global Descriptor Table

The next step is to set up a new Global Descriptor Table. Yes, one more time 😊 There are at least two reasons to do this:

1. The bootloader can load the Linux kernel starting from the `64-bit` entrypoint, and the kernel needs to set up its own Global Descriptor Table in case the one from the bootloader is not suitable.
2. The kernel might be configured with support for the [5-level](https://en.wikipedia.org/wiki/Intel_5-level_paging) paging, and in this case, the kernel needs to jump to `32-bit` mode again to set it safely.

The "new" Global Descriptor Table has the same entries but is pointed by the `gdt64` symbol:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L489-L493 -->
```assembly
	.data
SYM_DATA_START_LOCAL(gdt64)
	.word	gdt_end - gdt - 1
	.quad   gdt - gdt64
SYM_DATA_END(gdt64)
```

The single difference is that `lgdt` in `64-bit` mode loads `GDTR` register with size `10` bytes. In comparison, in `32-bit`, the size of `GDTR` is `6` bytes. To load the new Global Descriptor Table, the kernel writes its address to the `GDTR` register using the `lgdt` instruction:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L357-L368 -->
```assembly
	/* Make sure we have GDT with 32-bit code segment */
	leaq	gdt64(%rip), %rax
	addq	%rax, 2(%rax)
	lgdt	(%rax)

	/* Reload CS so IRET returns to a CS actually in the GDT */
	pushq	$__KERNEL_CS
	leaq	.Lon_kernel_cs(%rip), %rax
	pushq	%rax
	lretq

.Lon_kernel_cs:
```

### Load of the Interrupt Descriptor Table

After the new Global Descriptor Table is loaded, the next step is to load the new `Interrupt Descriptor Table`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L369-L376 -->
```assembly
	/*
	 * RSI holds a pointer to a boot_params structure provided by the
	 * loader, and this needs to be preserved across C function calls. So
	 * move it into a callee saved register.
	 */
	movq	%rsi, %r15

	call	load_stage1_idt
```

The `load_stage1_idt` function is defined in [arch/x86/boot/compressed/idt_64.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/idt_64.c) and uses the `lidt` instruction to load the address of the new `Interrupt Descriptor Table`. For this moment, the `Interrupt Descriptor Table` has `NULL` entries to avoid handling the interrupts. As you can remember, the interrupts are disabled at this moment anyway. The valid interrupt handlers will be loaded after kernel relocation.

The next steps after this are highly related to the setup of `5-level` paging, if it is configured using the `CONFIG_PGTABLE_LEVELS=5` kernel configuration option. This feature extends the virtual address space beyond the traditional 4-level paging scheme, but it is still relatively uncommon in practice and not essential for understanding the mainline boot flow. As mentioned in the [previous chapter](./linux-bootstrap-5.md), for clarity and focus, we’ll set it aside and continue with the standard 4-level paging case.

### Kernel relocation

Since the calculation of the base address for the kernel relocation is done, the kernel setup code can copy the compressed kernel image and the decompressor code to the memory area pointed by this address:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L419-L425 -->
```assembly
	leaq	(_bss-8)(%rip), %rsi
	leaq	rva(_bss-8)(%rbx), %rdi
	movl	$(_bss - startup_32), %ecx
	shrl	$3, %ecx
	std
	rep	movsq
	cld
```

The set of assembly instructions above copies the compressed kernel image and decompressor code to the memory area, which starts at the address pointed by the `rbx` register. The code above copies the memory contents starting from the `_bss-8` up to the `_startup_32` symbol, which includes:

- `32-bit` kernel setup code
- compressed kernel image 
- decompressor code

Because of the `std` instruction, the copying is performed in the backward order, from higher memory addresses to the lower.

After the copying is performed, the kernel needs to reload the previously loaded `Global Descriptor Table` in case it was overwritten or corrupted during the copy procedure:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L432-L435 -->
```assembly
	leaq	rva(gdt64)(%rbx), %rax
	leaq	rva(gdt)(%rbx), %rdx
	movq	%rdx, 2(%rax)
	lgdt	(%rax)
```

And finally jump on the relocated code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L440-L441 -->
```assembly
	leaq	rva(.Lrelocated)(%rbx), %rax
	jmp	*%rax
```

## The last actions before the kernel decompression

In the previous section, we saw the kernel relocation. The very first task after this jump is to clear the `.bss` section. This step is needed because the `.bss` section holds all uninitialized global and static variables. By definition, they must be initialized with zeros in `C` code. Cleaning it, the kernel ensures that all the following code, including the decompressor, begins with a proper `.bss` memory area without any possible garbage in it.

The following code does that:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L450-L455 -->
```assembly
	xorl	%eax, %eax
	leaq    _bss(%rip), %rdi
	leaq    _ebss(%rip), %rcx
	subq	%rdi, %rcx
	shrq	$3, %rcx
	rep	stosq
```

The assembly code above should be pretty easy to understand if you read the previous parts. It clears the value of the `eax` register and uses its value to fill the memory region of the `.bss` section between the `_bss` and `_ebss` symbols.

In the next step, the kernel fills the new `Interrupt Descriptor Table` with the call:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L457-L457 -->
```
	call	load_stage2_idt
```

This function defined in the [arch/x86/boot/compressed/idt_64.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/idt_64.c) and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/idt_64.c#L59-L78 -->
```C
void load_stage2_idt(void)
{
	boot_idt_desc.address = (unsigned long)boot_idt;

	set_idt_entry(X86_TRAP_PF, boot_page_fault);
	set_idt_entry(X86_TRAP_NMI, boot_nmi_trap);

#ifdef CONFIG_AMD_MEM_ENCRYPT
	/*
	 * Clear the second stage #VC handler in case guest types
	 * needing #VC have not been detected.
	 */
	if (sev_status & BIT(1))
		set_idt_entry(X86_TRAP_VC, boot_stage2_vc);
	else
		set_idt_entry(X86_TRAP_VC, NULL);
#endif

	load_boot_idt(&boot_idt_desc);
}
```

We can skip the part of the code wrapped with `CONFIG_AMD_MEM_ENCRYPT` as it is not of main interest for us right now, but try to understand the rest of the function's body. It is similar to the first stage of the `Interrupt Descriptor Table`. It loads the entries of this table using the `lidt` instruction, which we already have seen before. The only single difference is that it sets up two interrupt handlers:

- `PF` - Page fault interrupt handler
- `NMI` - Non-maskable interrupt handler

The first interrupt handler is set because the `initialize_identity_maps` function (which we will see very soon) may trigger page fault exception. This exception can be triggered for example, when [Address space layout randomization](https://en.wikipedia.org/wiki/Address_space_layout_randomization) is enabled and such random physical and virtual addresses were used for which the page tables do have an entry.

The second interrupt handler is needed to "handle" a triple-fault if such an interrupt appears during kernel decompression. So at least dummy NMI handler is needed.

After the `Interrupt Descriptor Table` is re-loaded, the `initialize_identity_maps` function is called:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L460-L461 -->
```assembly
	movq	%r15, %rdi
	call	initialize_identity_maps
```

This function is defined in [arch/x86/boot/compressed/ident_map_64.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/ident_map_64.c) and clears the memory area for the top-level page table identified by the `top_level_pgt` pointer to initialize a new page table. Yes, the kernel needs to initialize page tables one more time, despite we have seen the initialization and setup of the early page tables in the [previous chapter](./linux-bootstrap-4.md#set-up-paging). The reason for "one more" page table is that if the kernel was loaded at the `64-bit` entrypoint, it uses the page table built by the bootloader. Since the kernel was relocated to a new place, the decompressor code can overwrite these page tables during decompression.

The new page table is built in a very similar way to the [previous page table](./linux-bootstrap-4.md#set-up-paging). Each [virtual address](https://en.wikipedia.org/wiki/Virtual_address_space) directly corresponds to the same [physical address](https://en.wikipedia.org/wiki/Physical_address). That is why it is called the identity mapping.

Now let's take a look at the implementation of this function. It starts by initializing an instance of the `x86_mapping_info` structure called `mapping_info`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L119-L122 -->
```C
	mapping_info.alloc_pgt_page = alloc_pgt_page;
	mapping_info.context = &pgt_data;
	mapping_info.page_flag = __PAGE_KERNEL_LARGE_EXEC | sme_me_mask;
	mapping_info.kernpg_flag = _KERNPG_TABLE;
```

This structure provides information about memory mappings and a callback to allocate space for page table entries. The `context` field is used for tracking the allocated page tables. The `page_flag` and `kernpg_flag` fields define various page attributes (such as `present`, `writable`, or `executable`), which are reflected in their names.

In the next step, the kernel reads the address of the top-level page table from the `cr3` [control register](https://en.wikipedia.org/wiki/Control_register) and compares it with the `_pgtable`. If you read the previous chapter, you remember that `_pgtable` is the page table initialized by the early kernel setup code before switching to long mode. If we came from the `startup_32`, and it is exactly our case, the `cr3` register contains the same address as `_pgtable`. In this case, the kernel reuses and extends this page table:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L142-L146 -->
```C
	top_level_pgt = read_cr3_pa();
	if (p4d_offset((pgd_t *)top_level_pgt, 0) == (p4d_t *)_pgtable) {
		pgt_data.pgt_buf = _pgtable + BOOT_INIT_PGT_SIZE;
		pgt_data.pgt_buf_size = BOOT_PGT_SIZE - BOOT_INIT_PGT_SIZE;
		memset(pgt_data.pgt_buf, 0, pgt_data.pgt_buf_size);
```

Otherwise, the new page table is built:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L147-L152 -->
```C
	} else {
		pgt_data.pgt_buf = _pgtable;
		pgt_data.pgt_buf_size = BOOT_PGT_SIZE;
		memset(pgt_data.pgt_buf, 0, pgt_data.pgt_buf_size);
		top_level_pgt = (unsigned long)alloc_pgt_page(&pgt_data);
	}
```

At this stage, new identity mappings are added to cover the essential regions needed for the kernel to continue the boot process:

- the kernel image itself (from `_head` to `_end`)
- the boot parameters provided by the bootloader
- the kernel command line

All of the actual work is performed by the `kernel_add_identity_map` function defined in the same [file](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/ident_map_64.c):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L161-L166 -->
```C
	kernel_add_identity_map((unsigned long)_head, (unsigned long)_end);
	boot_params_ptr = rmode;
	kernel_add_identity_map((unsigned long)boot_params_ptr,
				(unsigned long)(boot_params_ptr + 1));
	cmdline = get_cmd_line_ptr();
	kernel_add_identity_map(cmdline, cmdline + COMMAND_LINE_SIZE);
```

The `kernel_add_itntity_map` function walks the page table hierarchy and ensures that there is existing page table entries which provide 1:1 mapping into the virtual address space. If such entries does not exist, the new entry is allocated with the flags that we have seen during the initialization of the `mapping_info`.

After all the identity mapping page table entries were initialized, the kernel updates the `cr3` control register with the address of the top page table:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L183-L183 -->
```C
	write_cr3(top_level_pgt);
```

At this point, all the preparations needed to decompress the kernel image are done. Now the kernel decompressor code is ready to decompress the kernel:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L466-L475 -->
```assembly
	/* pass struct boot_params pointer and output target address */
	movq	%r15, %rdi
	movq	%rbp, %rsi
	call	extract_kernel		/* returns kernel entry point in %rax */

/*
 * Jump to the decompressed kernel.
 */
	movq	%r15, %rsi
	jmp	*%rax
```

After the kernel is decompressed. The last instructions of the decompressor code transfers control to the Linux kernel entrypoint jumping on the address of the kernel's entrypoint. The early setup phase is complete, and the Linux kernel starts its job 🎉

In the next section, let's see how the kernel decompression works.

## Kernel decompression

Right now, we are finally at the last point before we see the kernel entrypoint. The last remaining step is only to decompress the kernel and switch control to it.

The kernel decompression is performed by the `extract_kernel` function defined in [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c). This function starts with the video mode and console initialization that we already saw in the previous parts. The kernel needs to do this again because it does not know if the kernel was loaded in the [real mode](https://en.wikipedia.org/wiki/Real_mode) or whether the bootloader used the `32-bit` or `64-bit` boot protocol.

We will skip all these initialization steps as we already saw them in the previous chapters. After the first initialization steps are done, the decompressor code stores the pointers to the start of the free heap memory and to the end of it:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L458-L459 -->
```C
	free_mem_ptr     = heap;	/* Heap */
	free_mem_end_ptr = heap + BOOT_HEAP_SIZE;
```

The main reason to set up the heap borders is that the kernel decompressor code uses the heap intensively during decompression.

After the initialization of the heap, the kernel calls the `choose_random_location` function from [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c). This function chooses the random location in memory to write the decompressed kernel to. This function performs work only if the address randomization is enabled. At this point, we will skip it and move to the next step, as it is not the most crucial point in the kernel decompression. If you are interested in what this function does, you can find more information in the [next chapter](./linux-bootstrap-6.md).

Now let's get back to the `extract_kernel` function. Since we assume that the kernel address randomization is disabled, the address where the kernel image will be decompressed is stored in the `output` parameter without any change. The value from this variable is obtained from the `rbp` register as calculated in the previous steps.

The next action before the kernel is decompressed is to perform the sanitising checks:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L496-L512 -->
```C
	if ((unsigned long)output & (MIN_KERNEL_ALIGN - 1))
		error("Destination physical address inappropriately aligned");
	if (virt_addr & (MIN_KERNEL_ALIGN - 1))
		error("Destination virtual address inappropriately aligned");
#ifdef CONFIG_X86_64
	if (heap > 0x3fffffffffffUL)
		error("Destination address too large");
	if (virt_addr + needed_size > KERNEL_IMAGE_SIZE)
		error("Destination virtual address is beyond the kernel mapping area");
#else
	if (heap > ((-__PAGE_OFFSET-(128<<20)-1) & 0x7fffffff))
		error("Destination address too large");
#endif
#ifndef CONFIG_RELOCATABLE
	if (virt_addr != LOAD_PHYSICAL_ADDR)
		error("Destination virtual address changed when not relocatable");
#endif
```

After all these checks, we can see the familiar message on the screen of our computers:

```
Decompressing Linux...
```

The kernel setup code starts decompression by calling the `decompress_kernel` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L521-L521 -->
```C
	entry_offset = decompress_kernel(output, virt_addr, error);
```

This function performs the following actions:

1. Decompress the kernel
2. Parse kernel ELF binary
3. Handle relocations

The kernel decompression performed by the helper function `__decompress`. The implementation of this function depends on what compression algorithm was used to compress the kernel and located in one of the following files:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L63-L89 -->
```C
#ifdef CONFIG_KERNEL_GZIP
#include "../../../../lib/decompress_inflate.c"
#endif

#ifdef CONFIG_KERNEL_BZIP2
#include "../../../../lib/decompress_bunzip2.c"
#endif

#ifdef CONFIG_KERNEL_LZMA
#include "../../../../lib/decompress_unlzma.c"
#endif

#ifdef CONFIG_KERNEL_XZ
#include "../../../../lib/decompress_unxz.c"
#endif

#ifdef CONFIG_KERNEL_LZO
#include "../../../../lib/decompress_unlzo.c"
#endif

#ifdef CONFIG_KERNEL_LZ4
#include "../../../../lib/decompress_unlz4.c"
#endif

#ifdef CONFIG_KERNEL_ZSTD
#include "../../../../lib/decompress_unzstd.c"
#endif
```

I will not describe here each implementation as this information is rather about compression algorithms rather than something specific to the Linux kernel.

After the kernel is decompressed, two more functions are called: `parse_elf` and `handle_relocations`. Let's take a short look at them.

The kernel binary, which is called `vmlinux` is an [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) executable file. As a result, after decompression we have not just a "piece" of code on which we can jump but an ELF file with headers, program segments, debug symbols and other information. We can easily make sure in it inspecting the `vmlinux` with `readelf` utility:

```bash
readelf -l vmlinux

Elf file type is EXEC (Executable file)
Entry point 0x1000000
There are 5 program headers, starting at offset 64

Program Headers:
  Type           Offset             VirtAddr           PhysAddr
                 FileSiz            MemSiz              Flags  Align
  LOAD           0x0000000000200000 0xffffffff81000000 0x0000000001000000
                 0x0000000000893000 0x0000000000893000  R E    200000
  LOAD           0x0000000000a93000 0xffffffff81893000 0x0000000001893000
                 0x000000000016d000 0x000000000016d000  RW     200000
  LOAD           0x0000000000c00000 0x0000000000000000 0x0000000001a00000
                 0x00000000000152d8 0x00000000000152d8  RW     200000
  LOAD           0x0000000000c16000 0xffffffff81a16000 0x0000000001a16000
                 0x0000000000138000 0x000000000029b000  RWE    200000
  ...
  ...
  ...
```

The `parse_elf` function acts as a minimal [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) loader. It reads the ELF program headers of the decompressed kernel image and uses them to determine which segments must be loaded and where each segment should be placed in physical memory.

At this point, the `parse_elf` function has completed loading the decompressed kernel image into memory. Each `PT_LOAD` segment has been copied from the ELF file into its proper location. The kernel’s code, data, and other segments are now present at the chosen load address. However, it might not be sufficient to make the kernel fully runnable.

The kernel was originally linked assuming a specific base address. If the address space layout randomization is enabled, the kernel can instead be loaded at a different physical and virtual address. As a result, any absolute addresses embedded within the kernel image will still reflect the original link-time address rather than the actual load address. To resolve this, the kernel image includes a relocation table that identifies all locations containing such absolute references. 

The `handle_relocations` function processes this table and adjusts each affected value by applying the relocation delta, which is the difference between the actual load address and the link-time base address. 

Once the relocations are applied, the decompressor code jumps to the kernel entrypoint. Its address is stored in the `rax` register, as we already have seen above.

Now we are in the kernel 🎉🎉🎉

The kernel entrypoint is the `startup_64` function from [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S). This is our next stop, but it will be in the next set of chapters - [Kernel initialization process](https://github.com/0xAX/linux-insides/tree/master/Initialization).

## Conclusion

This is the end of the third part about Linux kernel insides. If you have questions or suggestions, feel free ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).

## Links

Here is the list of the links that you can find useful when reading this chapter:

- [Real mode](https://en.wikipedia.org/wiki/Real_mode)
- [Protected mode](http://en.wikipedia.org/wiki/Protected_mode)
- [Long mode](https://en.wikipedia.org/wiki/Long_mode)
- [Flat memory model](https://en.wikipedia.org/wiki/Flat_memory_model)
- [Address space layout randomization](https://en.wikipedia.org/wiki/Address_space_layout_randomization)
- [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format)
- [Previous part](linux-bootstrap-4.md)
