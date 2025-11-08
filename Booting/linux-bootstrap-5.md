# Kernel booting process. Part 5.

In the previous [part](./linux-bootstrap-4.md), we saw the transition from the [protected mode](https://en.wikipedia.org/wiki/Protected_mode) into [long mode](https://en.wikipedia.org/wiki/Long_mode) but what we have in memory is not yet the full kernel image ready to run. We are still in the kernel setup code. The kernel itself is already loaded by the bootloader but it is in a compressed form. Before we can reach the real kernel entry point, this compressed blob must be unpacked into memory and prepared for execution. The next step before we will see the Linux kernel entrypoint is kernel decompression.

## Preparing to Decompress the Kernel

The point where we stopped in the previous chapter is the [jump](https://en.wikipedia.org/wiki/Branch_(computer_science)#Implementation) to the `64-bit` entry point which is located in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L276-L278 -->
```assembly
	.code64
	.org 0x200
SYM_CODE_START(startup_64)
```

The `64-bit` entrypoint starts with the same two instructions that `32-bit`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L290-L291 -->
```assembly
	cld
	cli
```

As you already may know from the previous part, the first instruction clears the [direction flag](https://en.wikipedia.org/wiki/Direction_flag) bit in the [flags](https://en.wikipedia.org/wiki/FLAGS_register) register and the second instruction disables [interrupts](https://en.wikipedia.org/wiki/Interrupt). The same as the bootloader can load the Linux kernel and jump to the `32-bit` entrypoint immediately after load, in the same way the bootloader can switch the processor into `64-bit` long mode and jump on this entrypoint right after the kernel is loaded. These two instructions have to be executed in a case if the bootloader didn't do it before jumping to the kernel. The `direction flag` allows us to use memory copying operations in a correct direction and disabled interrupts will not break or interrupt the kernel decompression process.

After these two instructions are executed for safeness, the next step is to unify data segments:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L294-L299 -->
```assembly
	xorl	%eax, %eax
	movl	%eax, %ds
	movl	%eax, %es
	movl	%eax, %ss
	movl	%eax, %fs
	movl	%eax, %gs
```

Since we have loaded a new `Global Descriptor Table` before we jumped into long mode all the data segment registers have to be unified and set to zero as Linux kernel uses [flat memory model](https://en.wikipedia.org/wiki/Flat_memory_model):

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

This operation is very similar to what we have already seen in the [Calculation of the kernel relocation address](./linux-bootstrap-4.md#calculation-of-the-kernel-relocation-address) section of the previous chapter. This piece of code is almost 1:1 copy to what we have seen in the protected mode. The only one difference that now kernel can use `rip` based addressing to get the address of the `startup_32` in memory. All other is just the same what we already have seen in the previous chapter and done only for the same reason - if bootloader is loaded kernel starting from the `64-bit` mode. As the result the `rbx` register will contain the physical address where the decompressor will be relocated.

After this address obtained, we can setup the stack for decompressor code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L334-L334 -->
```assembly
	leaq	rva(boot_stack_end)(%rbx), %rsp
```

The next step is to setup new `Global Descriptor Table`. Yes, one more time 😊 There are at least two reasons to do this. The first reason you already may guess is that bootloader may load the Linux kernel starting from the `64-bit` entrypoint and the kernel needs to setup own Global Descriptor Table in a case one from bootloader is not suitable. The second reason is that the kernel might be configured with support for the [5-level](https://en.wikipedia.org/wiki/Intel_5-level_paging) paging and in this case, kernel needs to jump to `32-bit` mode again to setup it safely. So the `gdt64` will have `32-bit` code segment:

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

The definition of `gdt64` you can find in the same [file](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S#L490) and basically contains the same fields what the Global Descriptor Table for `32-bit` mode, with the single difference is that `lgdt` in `64-bit` mode loads `GDTR` with size `10` bytes in comparison to `32-bit` where `GDTR` is `6` bytes:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L490-L504 -->
```assembly
SYM_DATA_START_LOCAL(gdt64)
	.word	gdt_end - gdt - 1
	.quad   gdt - gdt64
SYM_DATA_END(gdt64)
	.balign	8
SYM_DATA_START_LOCAL(gdt)
	.word	gdt_end - gdt - 1
	.long	0
	.word	0
	.quad	0x00cf9a000000ffff	/* __KERNEL32_CS */
	.quad	0x00af9a000000ffff	/* __KERNEL_CS */
	.quad	0x00cf92000000ffff	/* __KERNEL_DS */
	.quad	0x0080890000000000	/* TS descriptor */
	.quad   0x0000000000000000	/* TS continued */
SYM_DATA_END_LABEL(gdt, SYM_L_LOCAL, gdt_end)
```

After the new `Global Descriptor Table` was loaded, the next step is to load new `Interrupt Descriptor Table`:

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

The `load_stage1_idt` function is defined in the [arch/x86/boot/compressed/idt_64.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/idt_64.c) and uses the `lidt` instruction to load address of the new `Interrupt Descriptor Table` . For this moment, the `Interrupt Descriptor Table` has `NULL` entries to avoid interrupts. The valid interrupt handlers will be loaded after kernel relocation.

The next steps after this will be highly related to the setup of `5-level` paging if it is configured using the `CONFIG_PGTABLE_LEVELS=5` kernel configuration option. This feature extends the virtual address space beyond the traditional 4-level paging scheme, but it is still relatively uncommon in practice and not essential for understanding the mainline boot flow. For clarity and focus, we’ll set it aside and continue with the standard 4-level paging case.

Since the Linux kernel has now valid stack, the kernel setup code can copy the compressed kernel image to the address that we calculated above and stored in the `rbx` register.

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

Th set of assembly instructions above copies the compressed kernel over to where it will be decompressed. These instructions copies the decompressor image to the the safe place for the decompression to not overlap important regions of memory during decompression process. After the decompressor code moved, the kernel needs to re-load the previously loaded `Global Descriptor Table` in a case it was overwritten or corrupted during the copy procedure:

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

In the previous section we looked at how the kernel’s decompressor code relocates itself and then jumps to the new entry point at its final address. The very first task after this jump is to clear the `.bss` section.

This step is needed because the `.bss` section holds all uninitialized global and static variables. By definition, they must start out as zero in `C` code. Since the relocation code only copied the initialized part of the image, the `.bss` may contain random garbage values. Cleaning it, the kernel ensures that the decompressor begins with a predictable state before it proceeds further.

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

The assembly code above should be pretty easy to understand if you read the previous parts. It clears the value of the `eax` register and fills memory area with it which belongs to the `.bss` section between `_bss` and `_ebss` labels.

At the next step, kernel fills new `Interrupt Descriptor Table` with the call:

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

We can skip the part of the code wrapped with the `CONFIG_AMD_MEM_ENCRYPT` as it is not the main interest for us, but try to understand the rest of the function's body. It is similar to the first stage `Interrupt Descriptor Table`. It loads entries of this table using the `lidt` instruction which we have seen during the loading of the first step. The only single difference is that it sets up two interrupt handlers:

- `PF` - Page fault interrupt
- `NMI` - Non-maskable interrupt

The first interrupt handler is set because the `initialize_identity_maps` function which we will see very soon many need it. It can be used in a case [Address space layout randomization](https://en.wikipedia.org/wiki/Address_space_layout_randomization) is enabled and such random physical and virtual addresses were chosen for which mapping does not exist in the current page tables. The second interrupt handler needed to prevent triple-fault if such interrupt will appear during kernel decompression. So at least dummy NMI is needed.

After the `Interrupt Descriptor Table` is re-loaded, the `initialize_identity_maps` function is called:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L460-L461 -->
```assembly
	movq	%r15, %rdi
	call	initialize_identity_maps
```

This function defined in the [arch/x86/boot/compressed/ident_map_64.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/ident_map_64.c) and clears the memory area for the top level page table identified by the `top_level_pgt` pointer to initialize new page table. Yes. The kernel needs to initialize page tables one more time despite we have seen the initialization and setup of the early page tables in the [previous chapter](./linux-bootstrap-4.md##setup-paging). The reason for "one more" page table is that if kernel was booted using the `64-bit` entrypoint, it uses the page table built by the bootloader. To be sure that the kernel can make any changes in memory mapping when it is necessary, it loads own page table. 

The new page table will be built and used in which each [virtual address](https://en.wikipedia.org/wiki/Virtual_address_space) directly corresponds to the same [physical address](https://en.wikipedia.org/wiki/Physical_address). That is why it called - identity mapping. Now when we know a little bit of theory, let's return back to practice and take a look at the most crucial parts of this function.

This function starts by initializing an instance of the `x86_mapping_info` structure called `mapping_info`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L119-L122 -->
```C
	mapping_info.alloc_pgt_page = alloc_pgt_page;
	mapping_info.context = &pgt_data;
	mapping_info.page_flag = __PAGE_KERNEL_LARGE_EXEC | sme_me_mask;
	mapping_info.kernpg_flag = _KERNPG_TABLE;
```

This structure provides information about memory mappings and callback to allocate space for a page table entries. The `context` field is used for the tracking of the allocated page tables. The `page_flag` and `kernpg_flag` fields define various page attributes (such as present, writable, or executable), which is reflected in their names.

At the next step, the kernel reads the address of the top level page table from the `cr3` [control register](https://en.wikipedia.org/wiki/Control_register) and compares it with the `_pgtable`. If you read the previous chapter, you may remember that `_pgtable` pointer stores the address of the top level page table initialized by the early kernel setup code. If we came from the `startup_32` and it is exactly our case, the `cr3` register will contain the same address as `_pgtable`. In this case, this page table will be "re-used" by the kernel. Otherwise the new page table hierarchy will be built:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L142-L152 -->
```C
	top_level_pgt = read_cr3_pa();
	if (p4d_offset((pgd_t *)top_level_pgt, 0) == (p4d_t *)_pgtable) {
		pgt_data.pgt_buf = _pgtable + BOOT_INIT_PGT_SIZE;
		pgt_data.pgt_buf_size = BOOT_PGT_SIZE - BOOT_INIT_PGT_SIZE;
		memset(pgt_data.pgt_buf, 0, pgt_data.pgt_buf_size);
	} else {
		pgt_data.pgt_buf = _pgtable;
		pgt_data.pgt_buf_size = BOOT_PGT_SIZE;
		memset(pgt_data.pgt_buf, 0, pgt_data.pgt_buf_size);
		top_level_pgt = (unsigned long)alloc_pgt_page(&pgt_data);
	}
```

We saw that the kernel does not overwrite the existing bootstrap page tables. Instead, it reuses them and extends the mapping. At this stage, new identity mappings are added to cover the essential regions needed for the kernel to continue booting:

- the kernel image itself (from `_head` to `_end`)
- the boot parameters provided by the bootloader
- the kernel command line

All of the actual work is performed by the `kernel_add_identity_map` function defined in the same source code [file](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/ident_map_64.c):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L161-L166 -->
```C
	kernel_add_identity_map((unsigned long)_head, (unsigned long)_end);
	boot_params_ptr = rmode;
	kernel_add_identity_map((unsigned long)boot_params_ptr,
				(unsigned long)(boot_params_ptr + 1));
	cmdline = get_cmd_line_ptr();
	kernel_add_identity_map(cmdline, cmdline + COMMAND_LINE_SIZE);
```

This helper function walks the page table hierarchy and ensures that there is existing page table entries which provide 1:1 mapping into the virtual address space. If such entries not exist, the new entry is allocated with the flags that we have seen during the initialization of the `mapping_info`.

After all the identity mapping page table entries were initialized, the kernel updates the `cr3` control register with the address of the top page table:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/ident_map_64.c#L183-L183 -->
```C
	write_cr3(top_level_pgt);
```

At this point, all the preparations which were needed to decompress the kernel is done. Now kernel decompressor code is ready to decompress the kernel:

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

After kernel is decompressed, kernel jumps on the Linux kernel entrypoint - the place where finally we already behind the kernel setup code and where the Linux kernel starts its job 🎉

In the next section, let's see how kernel is decompressed.

## Kernel decompression

We are the last point before we will see the kernel entrypoint. After kernel will be decompressed we will see the jump on its entrypoint. The kernel decompression performed in the `extract_kernel` function which is defined in the [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c). This function starts with the video mode and console initialization that we already saw in the previous parts. We need to do this again because we don't know if the kernel was loaded in the [real mode](https://en.wikipedia.org/wiki/Real_mode) or whether the bootloader used the `32-bit` or `64-bit` boot protocol.

We will skip all these initialization steps as we already saw them in the previous chapters. After the first initialization steps, we store pointers to the start of the free heap memory and to the end of it:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L458-L459 -->
```C
	free_mem_ptr     = heap;	/* Heap */
	free_mem_end_ptr = heap + BOOT_HEAP_SIZE;
```

After the initialization of the heap pointers, the next step is the call of the `choose_random_location` function from the [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c). This function chooses the random location in memory to write the decompressed kernel to. This function performs a work only if the addresses randomization was enabled. At this point we will skip it and move to the next step as it is not the most crucial point in the kernel decompression. If you are interested what this function does, you can find more information in the [next chapter](./linux-bootstrap-6.md).

Now let's get back to the `extract_kernel` function. Since we assume that the kernel address randomization is disabled, the address where the kernel image will be decompressed is stored in the `output` variable without any change. The value from this variable is obtained from the `rbp` register since we calculated it in the previous steps. Before the kernel will be decompressed kernel does last sanitizing checks:

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

After all these checks we will see the familiar message:

```
Decompressing Linux...
```

and the kernel setup code starts decompression by the calling the `decompress_kernel` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L521-L521 -->
```C
	entry_offset = decompress_kernel(output, virt_addr, error);
```

This function performs 3 following actions:

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

The `parse_elf` function is responsible for reading ELF headers and extracting the information about segments and where they should live in memory.

In addition this `ELF` file contains relocation entries. Normally, the Linux kernel can be loaded to the fixed virtual address. But as we have seen before, the kernel address randomization can be enabled and in this case the entrypoint of the kernel will be located at random address. Relocation entries provides information which instructions or data references contain addresses that need to be patched with the actual load address. The `handle_relocations` function goes through the relocation table and applies the necessary adjustments so that all references point to the correct locations in memory.

After the kernel is relocated, we return from the `extract_kernel` function, the code jumps to the kernel entrypoint which address is stored in the `rax` register as we already have seen above.

Now we are in the kernel 🎉🎉🎉

## Conclusion

This is the end of the third part about Linux kernel insides. If you have questions or suggestions, feel free ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).

## Links

Here is the list of the links that you may find useful during reading of this chapter:

- [Real mode](https://en.wikipedia.org/wiki/Real_mode)
- [Protected mode](http://en.wikipedia.org/wiki/Protected_mode)
- [Long mode](https://en.wikipedia.org/wiki/Long_mode)
- [Flat memory model](https://en.wikipedia.org/wiki/Flat_memory_model)
- [Address space layout randomization](https://en.wikipedia.org/wiki/Address_space_layout_randomization)
- [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format)
- [Previous part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-4.md)
