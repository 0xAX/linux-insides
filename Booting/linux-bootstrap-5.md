Kernel booting process. Part 5.
================================================================================

Kernel decompression
--------------------------------------------------------------------------------

This is the fifth part of the `Kernel booting process` series. We saw transition to the 64-bit mode in the previous [part](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-4.md#transition-to-the-long-mode) and we will continue from this point in this part. We will see the last steps before we jump to the kernel code as preparation for kernel decompression, relocation and directly kernel decompression. So... let's start to dive in the kernel code again.

Preparation before kernel decompression
--------------------------------------------------------------------------------

We stopped right before the jump on the 64-bit entry point - `startup_64` which is located in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) source code file. We already saw the jump to the `startup_64` in the `startup_32`:

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

in the previous part, `startup_64` starts to work. Since we loaded the new Global Descriptor Table and there was CPU transition in other mode (64-bit mode in our case), we can see the setup of the data segments:

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

in the beginning of the `startup_64`. All segment registers besides `cs` now point to the `ds` which is `0x18` (if you don't understand why it is `0x18`, read the previous part).

The next step is computation of difference between where the kernel was compiled and where it was loaded:

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
	leaq	z_extract_offset(%rbp), %rbx
```

`rbp` contains the decompressed kernel start address and after this code executes `rbx` register will contain address to relocate the kernel code for decompression. We already saw code like this in the `startup_32` ( you can read about it in the previous part - [Calculate relocation address](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-4.md#calculate-relocation-address)), but we need to do this calculation again because the bootloader can use 64-bit boot protocol and `startup_32` just will not be executed in this case.

In the next step we can see setup of the stack pointer and resetting of the flags register:

```assembly
	leaq	boot_stack_end(%rbx), %rsp

	pushq	$0
	popfq
```

As you can see above, the `rbx` register contains the start address of the kernel decompressor code and we just put this address with `boot_stack_end` offset to the `rsp` register which represents pointer to the top of the stack. After this step, the stack will be correct. You can find definition of the `boot_stack_end` in the end of [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) assembly source code file:

```assembly
	.bss
	.balign 4
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
boot_stack:
	.fill BOOT_STACK_SIZE, 1, 0
boot_stack_end:
```

It located in the end of the `.bss` section, right before the `.pgtable`. If you will look into [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/vmlinux.lds.S) linker script, you will find  Definition of the `.bss` and `.pgtable` there.

As we set the stack, now we can copy the compressed kernel to the address that we got above, when we calculated the relocation address of the decompressed kernel. Before details, let's look at this assembly code:

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

First of all we push `rsi` to the stack. We need preserve the value of `rsi`, because this register now stores a pointer to the `boot_params` which is real mode structure that contains booting related data (you must remember this structure, we filled it in the start of kernel setup). In the end of this code we'll restore the pointer to the `boot_params` into `rsi` again. 

The next two `leaq` instructions calculates effective addresses of the `rip` and `rbx` with `_bss - 8` offset and put it to the `rsi` and `rdi`. Why do we calculate these addresses? Actually the compressed kernel image is located between this copying code (from `startup_32` to the current code) and the decompression code. You can verify this by looking at the linker script - [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/vmlinux.lds.S):

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

Note that `.head.text` section contains `startup_32`. You may remember it from the previous part:

```assembly
	__HEAD
	.code32
ENTRY(startup_32)
...
...
...
```

The `.text` section contains decompression code:

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

And `.rodata..compressed` contains the compressed kernel image. So `rsi` will contain the absolute address of `_bss - 8`, and `rdi` will contain the relocation relative address of `_bss - 8`. As we store these addresses in registers, we put the address of `_bss` in the `rcx` register. As you can see in the `vmlinux.lds.S` linker script, it's located at the end of all sections with the setup/kernel code. Now we can start to copy data from `rsi` to `rdi`, `8` bytes at the time, with the `movsq` instruction. 

Note that there is an `std` instruction before data copying: it sets the `DF` flag, which means that `rsi` and `rdi` will be decremented. In other words, we will copy the bytes backwards. At the end, we clear the `DF` flag with the `cld` instruction, and restore `boot_params` structure to `rsi`.

Now we have the address of the `.text` section address after relocation, and we can jump to it:

```assembly
	leaq	relocated(%rbx), %rax
	jmp	*%rax
```

Last preparation before kernel decompression
--------------------------------------------------------------------------------

In the previous paragraph we saw that the `.text` section starts with the `relocated` label. The first thing it does is clearing the `bss` section with:

```assembly
	xorl	%eax, %eax
	leaq    _bss(%rip), %rdi
	leaq    _ebss(%rip), %rcx
	subq	%rdi, %rcx
	shrq	$3, %rcx
	rep	stosq
```

We need to initialize the `.bss` section, because we'll soon jump to [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) code. Here we just clear `eax`, put the address of `_bss` in `rdi` and `_ebss` in `rcx`, and fill it with zeros with the `rep stosq` instruction.

At the end, we can see the call to the `decompress_kernel` function:

```assembly
	pushq	%rsi
	movq	$z_run_size, %r9
	pushq	%r9
	movq	%rsi, %rdi
	leaq	boot_heap(%rip), %rsi
	leaq	input_data(%rip), %rdx
	movl	$z_input_len, %ecx
	movq	%rbp, %r8
	movq	$z_output_len, %r9
	call	decompress_kernel
	popq	%r9
	popq	%rsi
```

Again we set `rdi` to a pointer to the `boot_params` structure and call `decompress_kernel` from [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c) with seven arguments:

* `rmode` - pointer to the [boot_params](https://github.com/torvalds/linux/blob/master//arch/x86/include/uapi/asm/bootparam.h#L114) structure which is filled by bootloader or during early kernel initialization;
* `heap` - pointer to the `boot_heap` which represents start address of the early boot heap;
* `input_data` - pointer to the start of the compressed kernel or in other words pointer to the `arch/x86/boot/compressed/vmlinux.bin.bz2`;
* `input_len` - size of the compressed kernel;
* `output` - start address of the future decompressed kernel;
* `output_len` - size of decompressed kernel;
* `run_size` - amount of space needed to run the kernel including `.bss` and `.brk` sections.

All arguments will be passed through the registers according to [System V Application Binary Interface](http://www.x86-64.org/documentation/abi.pdf). We've finished all preparation and can now look at the kernel decompression.

Kernel decompression
--------------------------------------------------------------------------------

As we saw in previous paragraph, the `decompress_kernel` function is defined in the [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c) source code file and takes seven arguments. This function starts with the video/console initialization that we already saw in the previous parts. We need to do this again because we don't know if we started in [real mode](https://en.wikipedia.org/wiki/Real_mode) or a bootloader was used, or whether the bootloader used the 32 or 64-bit boot protocol.

After the first initialization steps, we store pointers to the start of the free memory and to the end of it:

```C
free_mem_ptr     = heap;
free_mem_end_ptr = heap + BOOT_HEAP_SIZE;
```

where the `heap` is the second parameter of the `decompress_kernel` function which we got in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

```assembly
leaq	boot_heap(%rip), %rsi
```

As you saw above, the `boot_heap` is defined as:

```assembly
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
```

where the `BOOT_HEAP_SIZE` is macro which expands to `0x8000` (`0x400000` in a case of `bzip2` kernel) and represents the size of the heap.

After heap pointers initialization, the next step is the call of the `choose_random_location` function from [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c#L425) source code file. As we can guess from the function name, it chooses the memory location where the kernel image will be decompressed. It may look weird that we need to find or even `choose` location where to decompress the compressed kernel image, but the Linux kernel supports [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization) which allows decompression of the kernel into a random address, for security reasons. Let's open the [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c#L425) source code file and look at `choose_random_location`.

First, `choose_random_location` tries to find the `kaslr` option in the Linux kernel command line if `CONFIG_HIBERNATION` is set, and `nokaslr` otherwise:

```C
#ifdef CONFIG_HIBERNATION
	if (!cmdline_find_option_bool("kaslr")) {
		debug_putstr("KASLR disabled by default...\n");
		goto out;
	}
#else
	if (cmdline_find_option_bool("nokaslr")) {
		debug_putstr("KASLR disabled by cmdline...\n");
		goto out;
	}
#endif
```

If the `CONFIG_HIBERNATION` kernel configuration option is enabled during kernel configuration and there is no `kaslr` option in the Linux kernel command line, it prints `KASLR disabled by default...` and jumps to the `out` label:

```C
out:
	return (unsigned char *)choice;
```

which just returns the `output` parameter which we passed to the `choose_random_location`, unchanged. If the `CONFIG_HIBERNATION` kernel configuration option is disabled and the `nokaslr` option is in the kernel command line, we jump to `out` again.

For now, let's assume the kernel was configured with randomization enabled and try to understand what `kASLR` is. We can find information about it in the [documentation](https://github.com/torvalds/linux/blob/master/Documentation/kernel-parameters.txt):

```
kaslr/nokaslr [X86]

Enable/disable kernel and module base offset ASLR
(Address Space Layout Randomization) if built into
the kernel. When CONFIG_HIBERNATION is selected,
kASLR is disabled by default. When kASLR is enabled,
hibernation will be disabled.
```

It means that we can pass the `kaslr` option to the kernel's command line and get a random address for the decompressed kernel (you can read more about ASLR [here](https://en.wikipedia.org/wiki/Address_space_layout_randomization)). So, our current goal is to find random address where we can `safely` to decompress the Linux kernel. I repeat: `safely`. What does it mean in this context? You may remember that besides the code of decompressor and directly the kernel image, there are some unsafe places in memory. For example, the [initrd](https://en.wikipedia.org/wiki/Initrd) image is in memory too, and we must not overlap it with the decompressed kernel.

The next function will help us to find a safe place where we can decompress kernel. This function is `mem_avoid_init`. It defined in the same source code [file](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c), and takes four arguments that we already saw in the `decompress_kernel` function:

* `input_data` - pointer to the start of the compressed kernel, or in other words, the pointer to `arch/x86/boot/compressed/vmlinux.bin.bz2`;
* `input_len` - the size of the compressed kernel;
* `output` - the start address of the future decompressed kernel;
* `output_len` - the size of decompressed kernel.

The main point of this function is to fill array of the `mem_vector` structures:

```C
#define MEM_AVOID_MAX 5

static struct mem_vector mem_avoid[MEM_AVOID_MAX];
```

where the `mem_vector` structure contains information about unsafe memory regions:

```C
struct mem_vector {
	unsigned long start;
	unsigned long size;
};
```

The implementation of the `mem_avoid_init` is pretty simple. Let's look on the part of this function:

```C
	...
	...
	...
	initrd_start  = (u64)real_mode->ext_ramdisk_image << 32;
	initrd_start |= real_mode->hdr.ramdisk_image;
	initrd_size  = (u64)real_mode->ext_ramdisk_size << 32;
	initrd_size |= real_mode->hdr.ramdisk_size;
	mem_avoid[1].start = initrd_start;
	mem_avoid[1].size = initrd_size;
	...
	...
	...
```

Here we can see calculation of the [initrd](http://en.wikipedia.org/wiki/Initrd) start address and size. The `ext_ramdisk_image` is the high `32-bits` of the `ramdisk_image` field from the setup header, and `ext_ramdisk_size` is the high 32-bits of the `ramdisk_size` field from the [boot protocol](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt):

```
Offset	Proto	Name		Meaning
/Size
...
...
...
0218/4	2.00+	ramdisk_image	initrd load address (set by boot loader)
021C/4	2.00+	ramdisk_size	initrd size (set by boot loader)
...
```

And `ext_ramdisk_image` and `ext_ramdisk_size` can be found in the [Documentation/x86/zero-page.txt](https://github.com/torvalds/linux/blob/master/Documentation/x86/zero-page.txt):

```
Offset	Proto	Name		Meaning
/Size
...
...
...
0C0/004	ALL	ext_ramdisk_image ramdisk_image high 32bits
0C4/004	ALL	ext_ramdisk_size  ramdisk_size high 32bits
...
```

So we're taking `ext_ramdisk_image` and `ext_ramdisk_size`, shifting them left on `32` (now they will contain low 32-bits in the high 32-bit bits) and getting start address of the `initrd` and size of it. After this we store these values in the `mem_avoid` array.

The next step after we've collected all unsafe memory regions in the `mem_avoid` array will be searching for a random address that does not overlap with the unsafe regions, using the `find_random_addr` function. First of all we can see the alignment of the output address in the `find_random_addr` function:

```C
minimum = ALIGN(minimum, CONFIG_PHYSICAL_ALIGN);
```

You can remember `CONFIG_PHYSICAL_ALIGN` configuration option from the previous part. This option provides the value to which kernel should be aligned and it is `0x200000` by default. Once we have the aligned output address, we go through the memory regions which we got with the help of the BIOS [e820](https://en.wikipedia.org/wiki/E820) service and collect regions suitable for the decompressed kernel image:

```C
for (i = 0; i < real_mode->e820_entries; i++) {
	process_e820_entry(&real_mode->e820_map[i], minimum, size);
}
```

Recall that we collected `e820_entries` in the second part of the [Kernel booting process part 2](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-2.md#memory-detection). The `process_e820_entry` function does some checks that an `e820` memory region is not `non-RAM`, that the start address of the memory region is not bigger than maximum allowed `aslr` offset, and that the memory region is above the minimum load location:

```C
struct mem_vector region, img;

if (entry->type != E820_RAM)
	return;

if (entry->addr >= CONFIG_RANDOMIZE_BASE_MAX_OFFSET)
	return;

if (entry->addr + entry->size < minimum)
	return;
```

After this, we store an `e820` memory region start address and the size in the `mem_vector` structure (we saw definition of this structure above):

```C
region.start = entry->addr;
region.size = entry->size;
```

As we store these values, we align the `region.start` as we did it in the `find_random_addr` function and check that we didn't get an address that is outside the original memory region:

```C
region.start = ALIGN(region.start, CONFIG_PHYSICAL_ALIGN);

if (region.start > entry->addr + entry->size)
	return;
```

In the next step, we reduce the size of the memory region to not include rejected regions at the start, and ensure that the last address in the memory region is smaller than `CONFIG_RANDOMIZE_BASE_MAX_OFFSET`, so that the end of the kernel image will be less than the maximum `aslr` offset:

```C
region.size -= region.start - entry->addr;

if (region.start + region.size > CONFIG_RANDOMIZE_BASE_MAX_OFFSET)
		region.size = CONFIG_RANDOMIZE_BASE_MAX_OFFSET - region.start;
```

Finally, we go through all unsafe memory regions and check that the region does not overlap unsafe areas, such as kernel command line, initrd, etc...:

```C
for (img.start = region.start, img.size = image_size ;
	     mem_contains(&region, &img) ;
	     img.start += CONFIG_PHYSICAL_ALIGN) {
		if (mem_avoid_overlap(&img))
			continue;
		slots_append(img.start);
	}
```

If the memory region does not overlap unsafe regions we call the `slots_append` function with the start address of the region. `slots_append` function just collects start addresses of memory regions to the `slots` array:

```C
slots[slot_max++] = addr;
```

which is defined as:

```C
static unsigned long slots[CONFIG_RANDOMIZE_BASE_MAX_OFFSET /
			   CONFIG_PHYSICAL_ALIGN];
static unsigned long slot_max;
```

After `process_e820_entry` is done, we will have an array of addresses that are safe for the decompressed kernel. Then we call `slots_fetch_random` function to get a random item from this array:

```C
if (slot_max == 0)
	return 0;

return slots[get_random_long() % slot_max];
```

where `get_random_long` function checks different CPU flags as `X86_FEATURE_RDRAND` or `X86_FEATURE_TSC` and chooses a method for getting random number (it can be the RDRAND instruction, the time stamp counter, the programmable interval timer, etc...). After retrieving the random address, execution of the `choose_random_location` is finished.

Now let's back to [misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c#L404). After getting the address for the kernel image, there need to be some checks to be sure that the retrieved random address is correctly aligned and address is not wrong. 

After all these checks we will see the familiar message:

```
Decompressing Linux... 
```

and call the `__decompress` function which will decompress the kernel. The `__decompress` function depends on what decompression algorithm was chosen during kernel compilation:

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

After kernel is decompressed, the last two functions are `parse_elf` and `handle_relocations`. The main point of these functions is to move the uncompressed kernel image to the correct memory place. The fact is that the decompression will decompress [in-place](https://en.wikipedia.org/wiki/In-place_algorithm), and we still need to move kernel to the correct address. As we already know, the kernel image is an [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) executable, so the main goal of the `parse_elf` function is to move loadable segments to the correct address. We can see loadable segments in the output of the `readelf` program:

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

The goal of the `parse_elf` function is to load these segments to the `output` address we got from the `choose_random_location` function. This function starts with checking the [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) signature:

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

and if it's not valid, it prints an error message and halts. If we got a valid `ELF` file, we go through all program headers from the given `ELF` file and copy all loadable segments with correct address to the output buffer:

```C
	for (i = 0; i < ehdr.e_phnum; i++) {
		phdr = &phdrs[i];

		switch (phdr->p_type) {
		case PT_LOAD:
#ifdef CONFIG_RELOCATABLE
			dest = output;
			dest += (phdr->p_paddr - LOAD_PHYSICAL_ADDR);
#else
			dest = (void *)(phdr->p_paddr);
#endif
			memcpy(dest,
			       output + phdr->p_offset,
			       phdr->p_filesz);
			break;
		default: /* Ignore other PT_* */ break;
		}
	}
```

That's all. From now on, all loadable segments are in the correct place. The last `handle_relocations` function adjusts addresses in the kernel image, and is called only if the `kASLR` was enabled during kernel configuration.

After the kernel is relocated, we return back from the `decompress_kernel` to [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S). The address of the kernel will be in the `rax` register and we jump to it:

```assembly
jmp	*%rax
```

That's all. Now we are in the kernel!

Conclusion
--------------------------------------------------------------------------------

This is the end of the fifth and the last part about linux kernel booting process. We will not see posts about kernel booting anymore (maybe updates to this and previous posts), but there will be many posts about other kernel internals. 

Next chapter will be about kernel initialization and we will see the first steps in the Linux kernel initialization code.

If you have any questions or suggestions write me a comment or ping me in [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

* [address space layout randomization](https://en.wikipedia.org/wiki/Address_space_layout_randomization)
* [initrd](http://en.wikipedia.org/wiki/Initrd)
* [long mode](http://en.wikipedia.org/wiki/Long_mode)
* [bzip2](http://www.bzip.org/)
* [RDdRand instruction](http://en.wikipedia.org/wiki/RdRand)
* [Time Stamp Counter](http://en.wikipedia.org/wiki/Time_Stamp_Counter)
* [Programmable Interval Timers](http://en.wikipedia.org/wiki/Intel_8253)
* [Previous part](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-4.md)
