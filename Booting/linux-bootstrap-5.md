Kernel booting process. Part 5.
================================================================================

Kernel decompression
--------------------------------------------------------------------------------

This is the fifth part of the `Kernel booting process` series. We saw transition to the 64-bit mode in the previous [part](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-4.md#transition-to-the-long-mode) and we will continue from this point in this part. We will see the last steps before we jump to the kernel code as preparation for kernel decompression, relocation and directly kernel decompression. So... let's start to dive in the kernel code again.

Preparation before kernel decompression
--------------------------------------------------------------------------------

We stoped right before jump on 64-bit entry point - `startup_64` which located in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) source code file. As we saw a jump to the `startup_64` in the `startup_32`:

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

in the previous part, `startup_64` starts to work. Since we loaded the new Global Descriptor Table and there was CPU transition in other mode (64-bit mode in our case), we can see setup of the data segments:

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

in the start of `startup_64`. All segment registers besides `cs` points now to the `ds` which is `0x18` (if you don't understand why it is `0x18`, read the previous part).

The next step is computation of difference between where kernel was compiled and where it was loaded:

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

`rbp` contains decompressed kernel start address and after this code executed `rbx` register will contain address where to relocate the kernel code for decompression. We already saw code like this in the `startup_32` ( you can read about it in the previous part - [Calculate relocation address](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-4.md#calculate-relocation-address)), but we need to do this calculation again because bootloader can use 64-bit boot protocol and `startup_32` just will not be executed in this case.

In the next step we can see setup of the stack and reset of flags register:

```assembly
	leaq	boot_stack_end(%rbx), %rsp

 	pushq	$0
	popfq
```

As you can see above `rbx` register contains the start address of the decompressing kernel code and we just put this address with `boot_stack_end` offset to the `rsp` register. After this stack will be correct. You can find definition of the `boot_stack_end` in the end of `compressed/head_64.S` file:

```assembly
	.bss
	.balign 4
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
boot_stack:
	.fill BOOT_STACK_SIZE, 1, 0
boot_stack_end:

```

It located in the `.bss` section right before `.pgtable`. You can look at [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/vmlinux.lds.S) to find it.

As we set the stack, now we can copy the compressed kernel to the address that we got above, when we calculated the relocation address of the decompressed kernel. Let's look on this code:

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

First of all we push `rsi` to the stack. We need save value of `rsi`, because this register now stores pointer to the `boot_params` real mode structure (you must remember this structure, we filled it in the start of kernel setup). In the end of this code we'll restore pointer to the `boot_params` into `rsi` again. 

The next two `leaq` instructions calculates effective address of the `rip` and `rbx` with `_bss - 8` offset and put it to the `rsi` and `rdi`. Why we calculate this addresses? Actually compressed kernel image located between this copying code (from `startup_32` to the current code) and the decompression code. You can verify this by looking on the linker script - [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/vmlinux.lds.S):

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

Note that `.head.text` section contains `startup_32`. You can remember it from the previous part:

```assembly
	__HEAD
	.code32
ENTRY(startup_32)
...
...
...
```

`.text` section contains decompression code:

assembly
```
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

And `.rodata..compressed` contains compressed kernel image. 

So `rsi` will contain `rip` relative address of the `_bss - 8` and `rdi` will contain relocation relative address of the ``_bss - 8`. As we store these addresses in register, we put the address of `_bss` to the `rcx` register. As you can see in the `vmlinux.lds.S`, it located in the end of all sections with the setup/kernel code. Now we can start to copy data from `rsi` to `rdi` by 8 bytes with `movsq` instruction. 

Note that there is `std` instruction before data copying, it sets `DF` flag and it means that `rsi` and `rdi` will be decremeted or in other words, we will crbxopy bytes in backwards. 

In the end we clear `DF` flag with `cld` instruction and restore `boot_params` structure to the `rsi`.

After it we get `.text` section address address and jump to it:

```assembly
	leaq	relocated(%rbx), %rax
	jmp	*%rax
```

Last preparation before kernel decompression
--------------------------------------------------------------------------------

`.text` sections starts with the `relocated` label. For the start there is clearing of the `bss` section with:

```assembly
	xorl	%eax, %eax
	leaq    _bss(%rip), %rdi
	leaq    _ebss(%rip), %rcx
	subq	%rdi, %rcx
	shrq	$3, %rcx
	rep	stosq
```

Here we just clear `eax`, put RIP relative address of the `_bss` to the `rdi` and `_ebss` to `rcx` and fill it with zeros with `rep stosq` instructions.

In the end we can see the call of the `decompress_kernel` routine:

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

Again we save `rsi` with pointer to `boot_params` structure and call `decompress_kernel` from the [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c) with seven arguments. All arguments will be passed through the registers. We finished all preparation and now can look on the kernel decompression.

Kernel decompression
--------------------------------------------------------------------------------

As i wrote above, `decompress_kernel` function is in the [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c) source code file. This function starts with the video/console initialization that we saw in the previous parts. This calls need if bootloaded used 32 or 64-bit protocols. After this we store pointers to the start of the free memory and to the end of it:

```C
	free_mem_ptr     = heap;
	free_mem_end_ptr = heap + BOOT_HEAP_SIZE;
```

where `heap` is the second parameter of the `decompress_kernel` function which we got with:

```assembly
leaq	boot_heap(%rip), %rsi
```

As you saw about `boot_heap` defined as:

```assembly
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
```

where `BOOT_HEAP_SIZE` is `0x400000` if the kernel compressed with `bzip2` or `0x8000` if not.

In the next step we call `choose_kernel_location` function from the [arch/x86/boot/compressed/aslr.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/aslr.c#L298). As we can understand from the function name it chooses memory location where to decompress the kernel image. Let's look on this function.

At the start `choose_kernel_location` tries to find `kaslr` option in the command line if `CONFIG_HIBERNATION` is set and `nokaslr` option if this configuration option `CONFIG_HIBERNATION` is not set:

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

If there is no `kaslr` or `nokaslr` in the command line it jumps to `out` label:

```C
out:
	return (unsigned char *)choice;
```

which just returns the `output` parameter which we passed to the `choose_kernel_location` without any changes. Let's try to understand what is it `kaslr`. We can find information about it in the [documentation](https://github.com/torvalds/linux/blob/master/Documentation/kernel-parameters.txt):

```
kaslr/nokaslr [X86]

Enable/disable kernel and module base offset ASLR
(Address Space Layout Randomization) if built into
the kernel. When CONFIG_HIBERNATION is selected,
kASLR is disabled by default. When kASLR is enabled,
hibernation will be disabled.
```

It means that we can pass `kaslr` option to the kernel's command line and get random address for the decompressed kernel (more about aslr you can read [here](https://en.wikipedia.org/wiki/Address_space_layout_randomization)). 

Let's consider the case when kernel's command line contains `kaslr` option.

There is the call of the `mem_avoid_init` function from the same `aslr.c` source code file. This function gets the unsafe memory regions (initrd, kernel command line and etc...). We need to know about this memory regions to not overlap them with the kernel after decompression. For example:

```C
	initrd_start  = (u64)real_mode->ext_ramdisk_image << 32;
	initrd_start |= real_mode->hdr.ramdisk_image;
	initrd_size  = (u64)real_mode->ext_ramdisk_size << 32;
	initrd_size |= real_mode->hdr.ramdisk_size;
	mem_avoid[1].start = initrd_start;
	mem_avoid[1].size = initrd_size;
```

Here we can see calculation of the [initrd](http://en.wikipedia.org/wiki/Initrd) start address and size. `ext_ramdisk_image` is high 32-bits of the `ramdisk_image` field from boot header and `ext_ramdisk_size` is high 32-bits of the `ramdisk_size` field from [boot protocol](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt):

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

And `ext_ramdisk_image` and `ext_ramdisk_size` you can find in the [Documentation/x86/zero-page.txt](https://github.com/torvalds/linux/blob/master/Documentation/x86/zero-page.txt):

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

So we're taking `ext_ramdisk_image` and `ext_ramdisk_size`, shifting they left on 32 (now they will contain low 32-bits in the high 32-bit bits) and getting start address of the `initrd` and size of it. After this we store these values in the `mem_avoid` array which defined as:

```C
#define MEM_AVOID_MAX 5
static struct mem_vector mem_avoid[MEM_AVOID_MAX];
```

where `mem_vector` structure is:

```C
struct mem_vector {
	unsigned long start;
	unsigned long size;
};
```

The next step after we collected all unsafe memory regions in the `mem_avoid` array will be search of the random address which does not overlap with the unsafe regions with the `find_random_addr` function.

First of all we can see allign of the output address in the `find_random_addr` function:

```C
minimum = ALIGN(minimum, CONFIG_PHYSICAL_ALIGN);
```

you can remember `CONFIG_PHYSICAL_ALIGN` configuration option from the previous part. This option provides the value to which kernel should be aligned and it is `0x200000` by default. After that we got aligned output address, we go through the memory and collect regions which are good for decompressed kernel image:

```C
for (i = 0; i < real_mode->e820_entries; i++) {
	process_e820_entry(&real_mode->e820_map[i], minimum, size);
}
```

You can remember that we collected `e820_entries` in the second part of the [Kernel booting process part 2](https://github.com/0xAX/linux-insides/blob/master/Booting/linux-bootstrap-2.md#memory-detection).

First of all `process_e820_entry` function does some checks that e820 memory region is not non-RAM, that the start address of the memory region  is not bigger than Maximum allowed `aslr` offset and that memory region is not less than value of kernel alignment:

```C
struct mem_vector region, img;

if (entry->type != E820_RAM)
	return;

if (entry->addr >= CONFIG_RANDOMIZE_BASE_MAX_OFFSET)
	return;

if (entry->addr + entry->size < minimum)
	return;
```

After this, we store e820 memory region start address and the size in the `mem_vector` structure (we saw definition of this structure above):

```C
region.start = entry->addr;
region.size = entry->size;
```

As we store these values, we align the `region.start` as we did it in the `find_random_addr` function and check that we didn't get address that bigger than original memory region:

```C
region.start = ALIGN(region.start, CONFIG_PHYSICAL_ALIGN);

if (region.start > entry->addr + entry->size)
	return;
```

Next we get difference between the original address and aligned and check that if the last address in the memory region is bigger than `CONFIG_RANDOMIZE_BASE_MAX_OFFSET`, we reduce the memory region size that end of kernel image will be less than maximum `aslr` offset:

```C
region.size -= region.start - entry->addr;

if (region.start + region.size > CONFIG_RANDOMIZE_BASE_MAX_OFFSET)
		region.size = CONFIG_RANDOMIZE_BASE_MAX_OFFSET - region.start;
```

In the end we go through the all unsafe memory regions and check that this region does not overlap unsafe ares with kernel command line, initrd and etc...:

```C
for (img.start = region.start, img.size = image_size ;
	     mem_contains(&region, &img) ;
	     img.start += CONFIG_PHYSICAL_ALIGN) {
		if (mem_avoid_overlap(&img))
			continue;
		slots_append(img.start);
	}
```

If memory region does not overlap unsafe regions we call `slots_append` function with the start address of the region. `slots_append` function just collects start addresses of memory regions to the `slots` array:

```C
	slots[slot_max++] = addr;
```

which defined as:

```C
static unsigned long slots[CONFIG_RANDOMIZE_BASE_MAX_OFFSET /
			   CONFIG_PHYSICAL_ALIGN];
static unsigned long slot_max;
```

After `process_e820_entry` will be executed, we will have array of the addressess which are safe for the decompressed kernel. Next we call `slots_fetch_random` function for getting random item from this array:

```C
if (slot_max == 0)
	return 0;

return slots[get_random_long() % slot_max];
```

where `get_random_long` function checks different CPU flags as `X86_FEATURE_RDRAND` or `X86_FEATURE_TSC` and chooses method for getting random number (it can be obtain with RDRAND instruction, Time stamp counter, programmable interval timer and etc...). After that we got random address execution of the `choose_kernel_location` is finished.

Now let's back to the [misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c#L404). After we got address for the kernel image, there need to do some checks to be sure that gotten random address is correctly aligned and address is not wrong. 

After all these checks will see the familiar message:

```
Decompressing Linux... 
```

and call `decompress` function which will decompress the kernel. `decompress` function depends on what decompression algorithm was choosen during kernel compilartion:

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

After kernel will be decompressed, the last function `handle_relocations` will relocate the kernel to the address that we got from `choose_kernel_location`. After that kernel relocated we return from the `decompress_kernel` to the `head_64.S`. The address of the kernel will be in the `rax` register and we jump on it:

```assembly
jmp	*%rax
```

That's all. Now we are in the kernel!

Conclusion
--------------------------------------------------------------------------------

This is the end of the fifth and the last part about linux kernel booting process. We will not see posts about kernel booting anymore (maybe only updates in this and previous posts), but there will be many posts about other kernel internals. 

Next chapter will be about kernel initialization and we will see the first steps in the linux kernel initialization code.

If you will have any questions or suggestions write me a comment or ping me in [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you will find any mistakes please send me PR to [linux-internals](https://github.com/0xAX/linux-internals).**

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
