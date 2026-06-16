# Kernel booting process. Part 6

In the [previous part](./linux-bootstrap-5.md), we finally left the setup code and reached the Linux kernel itself. We explored the last steps of the early boot process - from the kernel decompression to the hand-off to the Linux kernel entrypoint (the `startup_64` function). You may think this is the end of the set of posts about the Linux kernel booting process, but I'd like to come back one more time to the early setup code and look at one more important part of it - `KASLR` or Kernel Address Space Layout Randomization.

As you can remember from the previous parts, the entry point of the Linux kernel is the `startup_64` function defined in [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S). In normal cases, the kernel is loaded at the fixed, well-known address defined by the value of the `CONFIG_PHYSICAL_START` configuration option. The description and the default value of this option are defined in [arch/x86/Kconfig](https://github.com/torvalds/linux/blob/master/arch/x86/Kconfig):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/Kconfig#L2021-L2025 -->
```
config PHYSICAL_START
	hex "Physical address where the kernel is loaded" if (EXPERT || CRASH_DUMP)
	default "0x1000000"
	help
	  This gives the physical address where the kernel is loaded.
```

However, modern systems rarely stick to predictable memory layouts for security reasons. Knowing the fixed address where the kernel was loaded can make it easier for attackers to guess the location of the kernel structures which can be exploited in various ways. To make such attacks harder, the Linux kernel provides support for [address space layout randomization](https://en.wikipedia.org/wiki/Address_space_layout_randomization) mechanism. 

To enable this mechanism, the `CONFIG_RANDOMIZE_BASE` kernel configuration option should be enabled. If this mechanism is enabled, the kernel will not be decompressed and loaded at the given fixed address. Instead, each boot the kernel image will be placed at a different physical address. 

In this part, we will look at how this mechanism works.

## Choose random location for kernel image

Before we will start to investigate kernel's code, let's remember where we were and what we have seen. 

In the [previous part](linux-bootstrap-5.md), we followed the kernel decompression code and transition to [long mode](https://en.wikipedia.org/wiki/Long_mode). The kernel's decompressor entrypoint is the `extract_kernel` function defined in [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c). At this point, the kernel image is about to be decompressed into the specific location in memory.

Before the kernel's decompressor actually begins to decompress the kernel image, it needs to decide where that image should be placed in memory. While we were going through the kernel's decompression code in the `extract_kernel`, we skipped the next function call:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L490-L493 -->
```C
	choose_random_location((unsigned long)input_data, input_len,
				(unsigned long *)&output,
				needed_size,
				&virt_addr);
```

This function is defined in [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c) and does nothing if the `kaslr` option is not passed to the kernel command line:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L862-L873 -->
```C
void choose_random_location(unsigned long input,
			    unsigned long input_size,
			    unsigned long *output,
			    unsigned long output_size,
			    unsigned long *virt_addr)
{
	unsigned long random_addr, min_addr;

	if (cmdline_find_option_bool("nokaslr")) {
		warn("KASLR disabled: 'nokaslr' on cmdline.");
		return;
	}
```

Otherwise, it selects a randomized address where the kernel image should be decompressed.

As we can see, this function takes five parameters:

- `input` - beginning address of the compressed kernel image
- `input_size` - size of the compressed kernel image
- `output` - physical address where the kernel should be decompressed
- `output_size` - size of the decompressed kernel image
- `virt_addr` - virtual address where the kernel should be decompressed

The `extract_kernel` function receives the `output` parameter from the code that prepares the decompressor:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L467-L469 -->
```
	movq	%r15, %rdi
	movq	%rbp, %rsi
	call	extract_kernel		/* returns kernel entry point in %rax */
```

If you read the previous chapters, you can remember that the starting address where the kernel image should be decompressed was calculated and stored in the `rbp` register.

The source of the values for the `input`, `input_size`, and `output_size` parameters is quite interesting. These values come from a little program called [mkpiggy](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/mkpiggy.c).

If you've ever tried compiling the Linux kernel yourself, you can find the output generated by this program in the `arch/x86/boot/compressed/piggy.S` assembly file, which contains all the parameters needed for decompression. In my case, this file looks like this:

```assembly
.section ".rodata..compressed","a",@progbits
.globl z_input_len
z_input_len = 14213122
.globl z_output_len
z_output_len = 36564556
.globl input_data, input_data_end
input_data:
.incbin "arch/x86/boot/compressed/vmlinux.bin.lz4"
input_data_end:
.section ".rodata","a",@progbits
.globl input_len
input_len:
	.long 14213122
.globl output_len
output_len:
	.long 36564556
```

At build time, the kernel's `vmlinux` image is compressed into `vmlinux.bin.{ALGO}` file. A small `mkpiggy` program gets the information about the compressed kernel image and generates this assembly file using the following code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/mkpiggy.c#L52-L67 -->
```C
	printf(".section \".rodata..compressed\",\"a\",@progbits\n");
	printf(".globl z_input_len\n");
	printf("z_input_len = %lu\n", ilen);
	printf(".globl z_output_len\n");
	printf("z_output_len = %lu\n", (unsigned long)olen);

	printf(".globl input_data, input_data_end\n");
	printf("input_data:\n");
	printf(".incbin \"%s\"\n", argv[1]);
	printf("input_data_end:\n");

	printf(".section \".rodata\",\"a\",@progbits\n");
	printf(".globl input_len\n");
	printf("input_len:\n\t.long %lu\n", ilen);
	printf(".globl output_len\n");
	printf("output_len:\n\t.long %lu\n", (unsigned long)olen);
```

That is where the kernel setup code obtains the values of these parameters.

The last parameter of the `choose_random_location` function is the virtual base address for the decompressed kernel image. At this point during early boot it is set to the physical load address:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.c#L409-L409 -->
```C
	unsigned long virt_addr = LOAD_PHYSICAL_ADDR;
```

Why is a virtual address initialized with the value of the physical address? The answer is simple and can be found in the previous chapters. During decompression, the early boot-time page tables are set up as an identity map. In other words, for this early stage, we have each virtual address equal to a physical address.

The value of `LOAD_PHYISICAL_ADDR` is the aligned value of the `CONFIG_PHYSICAL_START` configuration option, which we already saw at the beginning of this chapter:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/page_types.h#L32-L32 -->
```C
#define LOAD_PHYSICAL_ADDR	__ALIGN_KERNEL_MASK(CONFIG_PHYSICAL_START, CONFIG_PHYSICAL_ALIGN - 1)
```

At this point, we have examined all the parameters passed to the `choose_random_location` function. Now it is time to look inside the function. 

As it was mentioned above, the first thing that this function does is check whether ASLR disabled using the `nokaslr` option in the kernel's command line:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L870-L873 -->
```C
	if (cmdline_find_option_bool("nokaslr")) {
		warn("KASLR disabled: 'nokaslr' on cmdline.");
		return;
	}
```

If this option is specified in the kernel command line, the function does nothing, and the kernel is decompressed at the fixed address. In this chapter, however, we focus on the case where this option is not provided, as that is the main topic under discussion. If the `nokaslr` option is not present, the function proceeds to find a random location in memory to decompress the kernel.

The very first step is to set a mark in the boot parameters that ASLR is enabled. This is done by setting a specific flag in the kernel’s boot header:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L875-L875 -->
```C
	boot_params_ptr->hdr.loadflags |= KASLR_FLAG;
```

After marking that ASLR is enabled, the next task is to determine the upper memory limit which system can use:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L877-L880 -->
```C
	if (IS_ENABLED(CONFIG_X86_32))
		mem_limit = KERNEL_IMAGE_SIZE;
	else
		mem_limit = MAXMEM;
```

Since we consider only `x86_64` systems, the memory limit is `MAXMEM`, which is a macro defined in [arch/x86/include/asm/pgtable_64_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/pgtable_64_types.h):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/pgtable_64_types.h#L96-L96
```C
#define MAXMEM			(1UL << MAX_PHYSMEM_BITS)
```

where `MAX_PHYSMEM_BITS` depends on is [5-level paging](https://en.wikipedia.org/wiki/Intel_5-level_paging) is enabled or not. We will consider only 4-level paging, so in our case `MAXMEM` will be expand to `1 << 46` bytes.

With the `mem_limit` value set, the decompressor and kernel code responsible for the address randomization will know how far they can safely go during calculating an address for the kernel image. But before a random address for the kernel image can be chosen, the kernel needs to make sure it does not overwrite something important.

### Avoiding reserved memory ranges

The next step in the randomization process is to build a map of forbidden memory regions to prevent the kernel image from overwriting memory areas that are already in use. These may include, for example, the [initial ramdisk](https://en.wikipedia.org/wiki/Initial_ramdisk) or the kernel command line. To gather this information, we use this function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L883-L883 -->
```C
	mem_avoid_init(input, input_size, *output);
```

It collects the forbidden memory regions into the `mem_avoid` array, which has `mem_vector` type:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/misc.h#L97-L100 -->
```C
struct mem_vector {
	u64 start;
	u64 size;
};
```

For this moment, the randomization code tries to avoid the memory regions specified by the `mem_avoid_index`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L86-L94 -->
```C
enum mem_avoid_index {
	MEM_AVOID_ZO_RANGE = 0,
	MEM_AVOID_INITRD,
	MEM_AVOID_CMDLINE,
	MEM_AVOID_BOOTPARAMS,
	MEM_AVOID_MEMMAP_BEGIN,
	MEM_AVOID_MEMMAP_END = MEM_AVOID_MEMMAP_BEGIN + MAX_MEMMAP_REGIONS - 1,
	MEM_AVOID_MAX,
};
```

Let's look at the implementation of the `mem_avoid_init` function. As we know, the main goal of this function is to store information about reserved memory regions to avoid them when choosing a random address for the kernel image. There are no complex calculations in this function, and most of the reserved memory areas are known, as they are set by the bootloader or were already calculated at the previous steps during kernel setup. A typical example of the process of gathering information about the memory reserved regions looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L370-L375 -->
```C
	initrd_start  = (u64)boot_params_ptr->ext_ramdisk_image << 32;
	initrd_start |= boot_params_ptr->hdr.ramdisk_image;
	initrd_size  = (u64)boot_params_ptr->ext_ramdisk_size << 32;
	initrd_size |= boot_params_ptr->hdr.ramdisk_size;
	mem_avoid[MEM_AVOID_INITRD].start = initrd_start;
	mem_avoid[MEM_AVOID_INITRD].size = initrd_size;
```

In the code above, the start address of the initial ramdisk and its size are stored in the `mem_avoid` array. The same pattern repeats for other important memory areas, for example:

- the setup header 
- the decompressor itself
- the compressed kernel image

After the `mem_avoid_init` function is executed, the decompressor code has a complete picture of the system’s reserved memory zones and avoids them during selecting a random address to load the kernel image.

Now we can return to the `choose_random_location` function and finally see the process of the address randomization.

### Physical address randomization

The whole process of finding a suitable random address to load the kernel image consists of two parts:

- Find a random physical address
- Find a random virtual address

You can remember that at this point, the kernel uses identity-mapped page tables. Having this in mind, you can ask why two different addresses are calculated if there is a `1:1` mapping anyway. The answer is that these two random addresses have different purposes. Physical address determines where the kernel image is loaded in memory. Virtual address determines the kernel's address in the virtual address space. Despite the decompressor code now running with identity mapping, all the symbol references in the kernel image are patched during the relocation process with a random virtual address and offset. If it turns out that there is no mapping between the newly chosen physical and virtual addresses in the current page tables, the [page fault](https://en.wikipedia.org/wiki/Page_fault) interrupt handler builds a new identity mapping. You can find more information in the [previous chapter](./linux-bootstrap-5.md#the-last-actions-before-the-kernel-decompression).

Before generating any random offset, the decompressor determines the lowest possible base address that the kernel can use:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L890-L892 -->
```C
	min_addr = min(*output, 512UL << 20);
	/* Make sure minimum is aligned. */
	min_addr = ALIGN(min_addr, CONFIG_PHYSICAL_ALIGN);
```

This address is the minimal aligned value between `512` megabytes and the starting address of the output buffer passed to the `extract_kernel` function. After obtaining this value, the kernel calls the next function, which returns a random physical address:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L895-L902 -->
```C
	random_addr = find_random_phys_addr(min_addr, output_size);
	if (!random_addr) {
		warn("Physical KASLR disabled: no suitable memory region!");
	} else {
		/* Update the new physical address location. */
		if (*output != random_addr)
			*output = random_addr;
	}
```

The `find_random_phys_addr` function is defined in the same [arch/x86/boot/compressed/kaslr.c](https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c) source code file as the `choose_random_location` function. This function starts from the sanity checks. The first check is that the kernel image will not get behind the memory limit:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L813-L814 -->
```C
	if (minimum + image_size > mem_limit)
		return 0;
```

The next check is to verify that the number of memory regions specified via `memmap` kernel command line option is not excessive:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L817-L820 -->
```C
	if (memmap_too_large) {
		debug_putstr("Aborted memory entries scan (more than 4 memmap= args)!\n");
		return 0;
	}
```

After these sanity checks, the decompressor code begins scanning the system's available memory regions to find suitable candidates for the randomized address to decompress the kernel image. This is done with the help of the following functions:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L826-L829 -->
```C
	if (!process_kho_entries(minimum, image_size) &&
	    !process_efi_entries(minimum, image_size))
		process_e820_entries(minimum, image_size);
```

The scanning consists of three potential stages:

1. Scan the memory regions that are not preserved by the [KHO](https://docs.kernel.org/next/kho/concepts.html).
2. Scan the memory regions presented by the [EFI](https://en.wikipedia.org/wiki/Uefi) memory map.
3. Fallback to scanning the memory regions reported by the [e820](https://en.wikipedia.org/wiki/E820) BIOS service.

All the memory regions that were found and accepted as suitable will be stored in the `slot_areas` array represented by the following structure:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L453-L456 -->
```C
struct slot_area {
	u64 addr;
	unsigned long num;
};
```

The kernel will select a random index from this array to decompress kernel to. The selection of the random index happens in the `slots_fetch_random` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L528-L550 -->
```C
static u64 slots_fetch_random(void)
{
	unsigned long slot;
	unsigned int i;

	/* Handle case of no slots stored. */
	if (slot_max == 0)
		return 0;

	slot = kaslr_get_random_long("Physical") % slot_max;

	for (i = 0; i < slot_area_index; i++) {
		if (slot >= slot_areas[i].num) {
			slot -= slot_areas[i].num;
			continue;
		}
		return slot_areas[i].addr + ((u64)slot * CONFIG_PHYSICAL_ALIGN);
	}

	if (i == slot_area_index)
		debug_putstr("slots_fetch_random() failed!?\n");
	return 0;
}
```

The main goal of the `slots_fetch_random` function is to select a random memory slot from the list of possible locations that were gathered into the `slot_areas` array. Each entry of this array represents a contiguous free region of memory and the number of possible aligned kernel placements that fit in it.

To select a random address, this function generates a random number which is limited to the total number of the available slots. The random value is produced by the `kaslr_get_random_long` function which is defined in the same file. As its name suggests, this function returns a random `unsigned long` value, obtained using whatever entropy sources are available on the system. Depending on the hardware and the kernel configuration it can be:

- the CPU’s [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter)
- the [rdrand](https://en.wikipedia.org/wiki/RdRand) instruction
- The [i8254 programmable interval timer](https://en.wikipedia.org/wiki/Intel_8253)

After obtaining the random value, the code goes through the `slot_areas` array to find a memory region with enough available slots. If such a memory region is found, its starting address is used as a random physical address for decompressing the kernel image.

The kernel checks the result of the `find_random_phys_addr` function and prints a warning message if this operation was not successful, otherwise it assigned the obtained address to the `output`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L896-L902 -->
```C
	if (!random_addr) {
		warn("Physical KASLR disabled: no suitable memory region!");
	} else {
		/* Update the new physical address location. */
		if (*output != random_addr)
			*output = random_addr;
	}
```

At this point, the kernel has successfully picked a random physical address. The final step is to obtain a random virtual address.

### Virtual address randomization

With the physical address chosen, the decompressor now knows where to decompress the kernel image. Once the decompressed kernel starts running, it switches from the early-boot page tables to the full paging setup. The next and last step is to randomize the virtual base address:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L906-L908 -->
```C
	if (IS_ENABLED(CONFIG_X86_64))
		random_addr = find_random_virt_addr(LOAD_PHYSICAL_ADDR, output_size);
	*virt_addr = random_addr;
```

The function `find_random_virt_addr` is located in the same source code file and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/kaslr.c#L841-L856 -->
```C
static unsigned long find_random_virt_addr(unsigned long minimum,
					   unsigned long image_size)
{
	unsigned long slots, random_addr;

	/*
	 * There are how many CONFIG_PHYSICAL_ALIGN-sized slots
	 * that can hold image_size within the range of minimum to
	 * KERNEL_IMAGE_SIZE?
	 */
	slots = 1 + (KERNEL_IMAGE_SIZE - minimum - image_size) / CONFIG_PHYSICAL_ALIGN;

	random_addr = kaslr_get_random_long("Virtual") % slots;

	return random_addr * CONFIG_PHYSICAL_ALIGN + minimum;
}
```

As we can see, this function uses the same `kaslr_get_random_long` call to get a random memory slot.

At this point, both the physical and virtual base addresses are determined — randomized, aligned, and guaranteed to fit in available memory.

## Conclusion

This is the end of the sixth part about Linux kernel insides. If you have questions or suggestions, feel free ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).

The next chapter will be about kernel initialization and we will study the first steps take in the Linux kernel initialization code.

## Links

- [Address Space Layout Randomization](https://en.wikipedia.org/wiki/Address_space_layout_randomization)
- [Linux kernel boot protocol](https://github.com/torvalds/linux/blob/v4.16/Documentation/x86/boot.txt)
- [Long mode](https://en.wikipedia.org/wiki/Long_mode)
- [Initial ramdisk](https://en.wikipedia.org/wiki/Initial_ramdisk)
- [Four-level page tables](https://lwn.net/Articles/117749/)
- [Five-level page tables](https://lwn.net/Articles/717293/)
- [EFI](https://en.wikipedia.org/wiki/Unified_Extensible_Firmware_Interface)
- [e820](https://en.wikipedia.org/wiki/E820)
- [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter)
- [rdrand instruction](https://en.wikipedia.org/wiki/RdRand)
- [Previous part](linux-bootstrap-5.md)
