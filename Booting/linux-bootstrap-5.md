Kernel booting process. Part 5.
================================================================================

Kernel Decompression
--------------------------------------------------------------------------------

This is the fifth part of the `Kernel booting process` series. We went over the transition to 64-bit mode in the previous [part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-4.md#transition-to-the-long-mode) and we will continue where we left off in this part. We will study the steps taken to prepare for kernel decompression, relocation and the process of  kernel decompression itself. So... let's dive into the kernel code again.

Preparing to Decompress the Kernel
--------------------------------------------------------------------------------

We stopped right before the jump to the `64-bit` entry point - `startup_64` which is located in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S) source code file. We already covered the jump to `startup_64` from `startup_32` in the previous part:

```assembly
	pushl	$__KERNEL_CS
	leal	startup_64(%ebp), %eax
	...
	...
	...
	pushl	%eax
	...
	...
	...
	lret
```

Since we have loaded a new `Global Descriptor Table` and the CPU has transitioned to a new mode (`64-bit` mode in our case), we set up the segment registers again at the beginning of the `startup_64` function:

```assembly
	.code64
	.org 0x200
ENTRY(startup_64)
	xorl	%eax, %eax
	movl	%eax, %ds
	movl	%eax, %es
	movl	%eax, %ss
	movl	%eax, %fs
	movl	%eax, %gs
```

All segment registers besides the `cs` register are now reset in `long mode`.

The next step is to compute the difference between the location the kernel was compiled to be loaded at and the location where it is actually loaded:

```assembly
#ifdef CONFIG_RELOCATABLE
	leaq	startup_32(%rip), %rbp
	movl	BP_kernel_alignment(%rsi), %eax
	decl	%eax
	addq	%rax, %rbp
	notq	%rax
	andq	%rax, %rbp
	cmpq	$LOAD_PHYSICAL_ADDR, %rbp
	jge	1f
#endif
	movq	$LOAD_PHYSICAL_ADDR, %rbp
1:
	movl	BP_init_size(%rsi), %ebx
	subl	$_end, %ebx
	addq	%rbp, %rbx
```

The `rbp` register contains the decompressed kernel's start address. After this code executes, the `rbx` register will contain the address where the kernel code will be relocated to for decompression. We've already done this before in the `startup_32` function ( you can read about this in the previous part - [Calculate relocation address](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-4.md#calculate-relocation-address)), but we need to do this calculation again because the bootloader can use the 64-bit boot protocol now and `startup_32` is no longer being executed.

In the next step we set up the stack pointer, reset the flags register and set up the `GDT` again to overwrite the `32-bit` specific values with those from the `64-bit` protocol:

```assembly
    leaq	boot_stack_end(%rbx), %rsp

    leaq	gdt(%rip), %rax
    movq	%rax, gdt64+2(%rip)
    lgdt	gdt64(%rip)

    pushq	$0
    popfq
```

If you take a look at the code after the `lgdt gdt64(%rip)` instruction, you will see that there is some additional code. This code builds the trampoline to enable [5-level paging](https://lwn.net/Articles/708526/) if needed. We will only consider 4-level paging in this book, so this code will be omitted.

As you can see above, the `rbx` register contains the start address of the kernel decompressor code and we just put this address with an offset of `boot_stack_end` in the `rsp` register which points to the top of the stack. After this step, the stack will be correct. You can find the definition of the `boot_stack_end` constant in the end of the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S) assembly source code file:

```assembly
	.bss
	.balign 4
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
boot_stack:
	.fill BOOT_STACK_SIZE, 1, 0
boot_stack_end:
```

It located in the end of the `.bss` section, right before `.pgtable`. If you peek inside the [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/vmlinux.lds.S) linker script, you will find the definitions of `.bss` and `.pgtable` there.

Since the stack is now correct, we can copy the compressed kernel to the address that we got above, when we calculated the relocation address of the decompressed kernel. Before we get into the details, let's take a look at this assembly code:

```assembly
	pushq	%rsi
	leaq	(_bss-8)(%rip), %rsi
	leaq	(_bss-8)(%rbx), %rdi
	movq	$_bss, %rcx
	shrq	$3, %rcx
	std
	rep	movsq
	cld
	popq	%rsi
```

This set of instructions copies the compressed kernel over to where it will be decompressed.

First of all we push `rsi` to the stack. We need preserve the value of `rsi`, because this register now stores a pointer to `boot_params`  which is a real mode structure that contains booting related data (remember,  this structure was populated at the start of the kernel setup). We pop the pointer to `boot_params` back to `rsi` after we execute this code.

The next two `leaq` instructions calculate the effective addresses of the `rip` and `rbx` registers with an offset of `_bss - 8` and assign the results to `rsi` and `rdi` respectively. Why do we calculate these addresses? The compressed kernel image is located between this code (from `startup_32` to the current code) and the decompression code. You can verify this by looking at this linker script - [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/vmlinux.lds.S):

```
	. = 0;
	.head.text : {
		_head = . ;
		HEAD_TEXT
		_ehead = . ;
	}
	.rodata..compressed : {
		*(.rodata..compressed)
	}
	.text :	{
		_text = .; 	/* Text */
		*(.text)
		*(.text.*)
		_etext = . ;
	}
```

Note that the `.head.text` section contains `startup_32`. You may remember it from the previous part:

```assembly
	__HEAD
	.code32
ENTRY(startup_32)
...
...
...
```

The `.text` section contains the decompression code:

```assembly
	.text
relocated:
...
...
...
/*
 * Do the decompression, and jump to the new kernel..
 */
...
```

And `.rodata..compressed` contains the compressed kernel image. So `rsi` will contain the absolute address of `_bss - 8`, and `rdi` will contain the relocation relative address of `_bss - 8`. In the same way we store these addresses in registers, we put the address of `_bss` in the `rcx` register. As you can see in the `vmlinux.lds.S` linker script, it's located at the end of all sections with the setup/kernel code. Now we can start copying data from `rsi` to `rdi`, `8` bytes at a time, with the `movsq` instruction.

Note that we execute an `std` instruction before copying the data. This sets the `DF` flag, which means that `rsi` and `rdi` will be decremented. In other words, we will copy the bytes backwards. At the end, we clear the `DF` flag with the `cld` instruction, and restore the `boot_params` structure to `rsi`.

Now we have a pointer to the `.text` section's address after relocation, and we can jump to it:

```assembly
	leaq	relocated(%rbx), %rax
	jmp	*%rax
```

The final touches before kernel decompression
--------------------------------------------------------------------------------

In the previous paragraph we saw that the `.text` section starts with the `relocated` label. The first thing we do is to clear the `bss` section with:

```assembly
	xorl	%eax, %eax
	leaq    _bss(%rip), %rdi
	leaq    _ebss(%rip), %rcx
	subq	%rdi, %rcx
	shrq	$3, %rcx
	rep	stosq
```

We need to initialize the `.bss` section, because we'll soon jump to [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) code. Here we just clear `eax`, put the addresses of `_bss` in `rdi` and `_ebss` in `rcx`, and fill `.bss` with zeros with the `rep stosq` instruction.

At the end, we can see a call to the `extract_kernel` function:

```assembly
	pushq	%rsi
	movq	%rsi, %rdi
	leaq	boot_heap(%rip), %rsi
	leaq	input_data(%rip), %rdx
	movl	$z_input_len, %ecx
	movq	%rbp, %r8
	movq	$z_output_len, %r9
	call	extract_kernel
	popq	%rsi
```

Like before, we push `rsi` onto the stack to preserve the pointer to `boot_params`. We also copy the contents of `rsi` to `rdi`. Then, we set `rsi` to point to the area where the kernel will be decompressed. The last step is to prepare the parameters for the  `extract_kernel` function and call it to decompress the kernel. The `extract_kernel` function is defined in the  [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/misc.c) source code file and takes six arguments:

* `rmode` - a pointer to the [boot_params](https://github.com/torvalds/linux/blob/v4.16/arch/x86/include/uapi/asm/bootparam.h) structure which is filled by either the bootloader or during early kernel initialization;
* `heap` - a pointer to `boot_heap` which represents the start address of the early boot heap;
* `input_data` - a pointer to the start of the compressed kernel or in other words, a pointer to the `arch/x86/boot/compressed/vmlinux.bin.bz2` file;
* `input_len` - the size of the compressed kernel;
* `output` - the start address of the decompressed kernel;
* `output_len` - the size of the decompressed kernel;

All arguments will be passed through registers as per the [System V Application Binary Interface](https://github.com/hjl-tools/x86-psABI/wiki/x86-64-psABI-1.0.pdf). We've finished all the preparations and can now decompress the kernel.

Kernel decompression
--------------------------------------------------------------------------------

As we saw in the previous paragraph, the `extract_kernel` function is defined in the [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/misc.c) source code file and takes six arguments. This function starts with the video/console initialization that we already saw in the previous parts. We need to do this again because we don't know if we started in [real mode](https://en.wikipedia.org/wiki/Real_mode) or if a bootloader was used, or whether the bootloader used the `32` or `64-bit` boot protocol.

After the first initialization steps, we store pointers to the start of the free memory and to the end of it:

```C
free_mem_ptr     = heap;
free_mem_end_ptr = heap + BOOT_HEAP_SIZE;
```

Here, `heap` is the second parameter of the `extract_kernel` function as passed to it in [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S):

```assembly
leaq	boot_heap(%rip), %rsi
```

As you saw above, `boot_heap` is defined as:

```assembly
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
```

where `BOOT_HEAP_SIZE` is a macro which expands to `0x10000` (`0x400000` in the case of a `bzip2` kernel) and represents the size of the heap.

After we initialize the heap pointers, the next step is to call the `choose_random_location` function from the [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/kaslr.c) source code file. As we can guess from the function name, it chooses a memory location to write the decompressed kernel to. It may look weird that we need to find or even `choose` where to decompress the compressed kernel image, but the Linux kernel supports [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization) which allows decompression of the kernel into a random address, for security reasons.

We'll take a look at how the kernel's load address is randomized in the next part.

Now let's get back to [misc.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/misc.c). After getting the address for the kernel image, we need to check that the random address we got is correctly aligned, and in general, not wrong:

```C
if ((unsigned long)output & (MIN_KERNEL_ALIGN - 1))
	error("Destination physical address inappropriately aligned");

if (virt_addr & (MIN_KERNEL_ALIGN - 1))
	error("Destination virtual address inappropriately aligned");

if (heap > 0x3fffffffffffUL)
	error("Destination address too large");

if (virt_addr + max(output_len, kernel_total_size) > KERNEL_IMAGE_SIZE)
	error("Destination virtual address is beyond the kernel mapping area");

if ((unsigned long)output != LOAD_PHYSICAL_ADDR)
    error("Destination address does not match LOAD_PHYSICAL_ADDR");

if (virt_addr != LOAD_PHYSICAL_ADDR)
	error("Destination virtual address changed when not relocatable");
```

After all these checks we will see the familiar message:

```
Decompressing Linux...
```

Now, we call the `__decompress` function to decompress the kernel:

```C
__decompress(input_data, input_len, NULL, NULL, output, output_len, NULL, error);
```

The implementation of the `__decompress` function depends on what decompression algorithm was chosen during kernel compilation:

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
```

After the kernel is decompressed, two more functions are called: `parse_elf` and `handle_relocations`. The main point of these functions is to move the decompressed kernel image to its correct place in memory. This is because the decompression is done [in-place](https://en.wikipedia.org/wiki/In-place_algorithm), and we still need to move the kernel to the correct address. As we already know, the kernel image is an [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) executable. The main goal of the `parse_elf` function is to move loadable segments to the correct address. We can see the kernel's loadable segments in the output of the `readelf` program:

```
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
```

The goal of the `parse_elf` function is to load these segments to the `output` address we got from the `choose_random_location` function. This function starts by checking the [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) signature:

```C
Elf64_Ehdr ehdr;
Elf64_Phdr *phdrs, *phdr;

memcpy(&ehdr, output, sizeof(ehdr));

if (ehdr.e_ident[EI_MAG0] != ELFMAG0 ||
    ehdr.e_ident[EI_MAG1] != ELFMAG1 ||
    ehdr.e_ident[EI_MAG2] != ELFMAG2 ||
    ehdr.e_ident[EI_MAG3] != ELFMAG3) {
        error("Kernel is not a valid ELF file");
        return;
}
```

If the ELF header is not valid, it prints an error message and halts. If we have a valid `ELF` file, we go through all the program headers from the given `ELF` file and copy all loadable segments with correct 2 megabyte aligned addresses to the output buffer:

```C
	for (i = 0; i < ehdr.e_phnum; i++) {
		phdr = &phdrs[i];

		switch (phdr->p_type) {
		case PT_LOAD:
#ifdef CONFIG_X86_64
			if ((phdr->p_align % 0x200000) != 0)
				error("Alignment of LOAD segment isn't multiple of 2MB");
#endif
#ifdef CONFIG_RELOCATABLE
			dest = output;
			dest += (phdr->p_paddr - LOAD_PHYSICAL_ADDR);
#else
			dest = (void *)(phdr->p_paddr);
#endif
			memmove(dest, output + phdr->p_offset, phdr->p_filesz);
			break;
		default:
			break;
		}
	}
```

That's all.

From this moment, all loadable segments are in the correct place.

The next step after the `parse_elf` function is to call the `handle_relocations` function. The implementation of this function depends on the `CONFIG_X86_NEED_RELOCS` kernel configuration option and if it is enabled, this function adjusts addresses in the kernel image. This function is also only called if the `CONFIG_RANDOMIZE_BASE` configuration option was enabled during kernel configuration. The implementation of the `handle_relocations` function is easy enough. This function subtracts the value of `LOAD_PHYSICAL_ADDR` from the value of the base load address of the kernel and thus we obtain the difference between where the kernel was linked to load and where it was actually loaded. After this we can relocate the kernel since we know the actual address where the kernel was loaded, the address where it was linked to run and the relocation table which is at the end of the kernel image.

After the kernel is relocated, we return from the `extract_kernel` function to [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S).

The address of the kernel will be in the `rax` register and we jump to it:

```assembly
jmp	*%rax
```

That's all. Now we are in the kernel!

Conclusion
--------------------------------------------------------------------------------

This is the end of the fifth part about the Linux kernel booting process. We will not see any more posts about the kernel booting process (there may be updates to this and previous posts though), but there will be many posts about other kernel internals.

The Next chapter will describe more advanced details about Linux kernel booting process, like load address randomization and etc.

If you have any questions or suggestions write me a comment or ping me in [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [address space layout randomization](https://en.wikipedia.org/wiki/Address_space_layout_randomization)
* [initrd](https://en.wikipedia.org/wiki/Initrd)
* [long mode](https://en.wikipedia.org/wiki/Long_mode)
* [bzip2](http://www.bzip.org/)
* [RdRand instruction](https://en.wikipedia.org/wiki/RdRand)
* [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter)
* [Programmable Interval Timers](https://en.wikipedia.org/wiki/Intel_8253)
* [Previous part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-4.md)
