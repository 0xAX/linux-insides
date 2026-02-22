# Kernel booting process. Part 4

In the previous [part](./linux-bootstrap-3.md), we saw the transition from the [real mode](https://en.wikipedia.org/wiki/Real_mode) into [protected mode](http://en.wikipedia.org/wiki/Protected_mode). At this point, the two crucial things were changed: 

- The processor now can address up to four gigabytes of memory
- The privilege levels were set for the memory access 

Despite this, the kernel is still in its early setup mode. There are many different things that the early setup code should prepare before we reach the main kernel's entry point. Right now, the processor operates in protected mode. However, protected mode is not the main mode in which `x86_64` processors should operate – it exists only for backward compatibility. The next crucial step is to switch to the native mode for `x86_64` - [long mode](https://en.wikipedia.org/wiki/Long_mode).

The main characteristic of this new mode (as with all the earlier modes) is the way it defines the memory model. In real mode, the memory model was relatively simple, and each memory location was formed based on the base address specified in a segment register, plus some offset. In protected mode, the global and local descriptor tables contain descriptors that describe memory areas. All the memory accesses in long mode are based on the new mechanism called [paging](https://en.wikipedia.org/wiki/Memory_paging). One of the crucial goals of the kernel setup code before it can switch to the long mode is to set up paging.

In this chapter, we will see how the kernel switches to long mode in detail.

> [!NOTE]
> There will be lots of assembly code in this part, so if you are not familiar with that, read another set of my [posts about assembly programming](https://github.com/0xAX/asm).

## The 32-bit kernel entry point location

The last point where we stopped was the [jump](https://en.wikipedia.org/wiki/Branch_(computer_science)#Implementation) instruction to the kernel's entry point in protected mode. This jump was located in the [arch/x86/boot/pmjump.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/pmjump.S) and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pmjump.S#L74-L74 -->
```assembly
	jmpl	*%eax			# Jump to the 32-bit entrypoint
```

The value of the `eax` register contains the address of the `32-bit` entry point. What is this address? To answer on this question, we can read the [Linux kernel x86 boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt) document:

> When using bzImage, the protected-mode kernel was relocated to 0x100000

We can make make sure that this 32-bit entry point of the Linux kernel using the [GNU GDB](https://sourceware.org/gdb/) debugger and running the Linux kernel in the [QEMU](https://www.qemu.org/) virtual machine. To do this, you can run the following command in one terminal:

```bash
sudo qemu-system-x86_64 -kernel ./linux/arch/x86/boot/bzImage \ 
                        -nographic                            \
                        -append "console=ttyS0 nokaslr" -s -S \ 
                        -initrd /boot/initramfs-6.17.0-rc3-g1b237f190eb3.img
```

> [!NOTE]
> You need to pass your own kernel image and [initrd](https://en.wikipedia.org/wiki/Initial_ramdisk) image to the `-kernel` and `-initrd` command line options.

After this, run the GNU GDB debugger in another terminal and pass the following commands:

```
$ gdb
(gdb) target remote :1234
(gdb) hbreak *0x100000
(gdb) c
Continuing.

Breakpoint 1, 0x0000000000100000 in ?? ()
```

As soon as the debugger stopped at the [breakpoint](https://en.wikipedia.org/wiki/Breakpoint), we can inspect registers to be sure that the `eax` register contains the `0x100000` - address of the 32-bit kernel entry point:

```
eax            0x100000	1048576
ecx            0x0	    0
edx            0x0	    0
ebx            0x0	    0
esp            0x1ff5c	0x1ff5c
ebp            0x0	    0x0
esi            0x14470	83056
edi            0x0	    0
eip            0x100000	0x100000
eflags         0x46	    [ PF ZF ]
```

From the previous part, you may remember:

> First of all, we preserve the address of `boot_params` structure in the `esi` register.

So the `esi` register has the pointer to the `boot_params`. Let's inspect it to make sure that it is really it. For example we can take a look at the command line string that we passed to the virtual machine:

```
(gdb) x/s ((struct boot_params *)$rsi)->hdr.cmd_line_ptr
0x20000:	"console=ttyS0 nokaslr"
(gdb) ptype struct boot_params
type = struct boot_params {
    struct screen_info screen_info;
    struct apm_bios_info apm_bios_info;
    __u8 _pad2[4];
    __u64 tboot_addr;
    struct ist_info ist_info;
    __u64 acpi_rsdp_addr;
    __u8 _pad3[8];
    __u8 hd0_info[16];
    __u8 hd1_info[16];
    struct sys_desc_table sys_desc_table;
    struct olpc_ofw_header olpc_ofw_header;
    __u32 ext_ramdisk_image;
    __u32 ext_ramdisk_size;
    __u32 ext_cmd_line_ptr;
    __u8 _pad4[112];
    __u32 cc_blob_address;
    struct edid_info edid_info;
    struct efi_info efi_info;
    __u32 alt_mem_k;
    __u32 scratch;
    __u8 e820_entries;
    __u8 eddbuf_entries;
    __u8 edd_mbr_sig_buf_entries;
    __u8 kbd_status;
    __u8 secure_boot;
    __u8 _pad5[2];
    __u8 sentinel;
    __u8 _pad6[1];
    struct setup_header hdr;
    __u8 _pad7[36];
    __u32 edd_mbr_sig_buffer[16];
    struct boot_e820_entry e820_table[128];
    __u8 _pad8[48];
    struct edd_info eddbuf[6];
    __u8 _pad9[276];
}
(gdb) x/s ((struct boot_params *)$rsi)->hdr.cmd_line_ptr
0x20000:	"console=ttyS0 nokaslr"
```

We got it 🎉

Now we know where we are, so let's take a look at the code and proceed with learning of the Linux kernel.

## First steps in the protected mode

The `32-bit` entry point is defined in [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) assembly source code file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L81-L82 -->
```assembly
	.code32
SYM_FUNC_START(startup_32)
```

First of all, it is worth knowing why the directory is named `compressed`. It's because the kernel is in the [`bzImage`](https://en.wikipedia.org/wiki/Vmlinux#bzImage) file, which is a compressed package that contains the kernel image and kernel setup code. In all previous chapters, we were researching the kernel setup code. The next two big steps, which the kernel's setup code should do before we see the entry point of the kernel itself, are:

- Switch to long mode
- Decompress the kernel image and jump to its entry point

In this part, we will focus only on switching to long mode. The kernel image decompression will be covered in the next chapters. Returning to the current kernel code, you can find the following two files in the [arch/x86/boot/compressed](https://github.com/torvalds/linux/tree/master/arch/x86/boot/compressed) directory:

- [head_32.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_32.S)
- [head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S)

We will focus only on the `head_64.S` file. Yes, the file name contains the `64` suffix, despite the kernel being in the 32-bit protected mode at the moment. The explanation for this situation is simple. Let's look at [arch/x86/boot/compressed/Makefile](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/Makefile). We can see the following `make` goal here:

```Makefile
vmlinux-objs-y := $(obj)/vmlinux.lds $(obj)/kernel_info.o $(obj)/head_$(BITS).o \
	$(obj)/misc.o $(obj)/string.o $(obj)/cmdline.o $(obj)/error.o \
	$(obj)/piggy.o $(obj)/cpuflags.o
```

The first line contains the following target - `$(obj)/head_$(BITS).o`. This means that `make` will select the file during the kernel build process based on the `$(BITS)` value. This `make` variable is defined in the [arch/x86/Makefile](https://github.com/torvalds/linux/blob/master/arch/x86/Makefile) Makefile and its value depends on the kernel's configuration:

```Makefile
ifeq ($(CONFIG_X86_32),y)
        BITS := 32
        ...
        ...
else
        BITS := 64
        ...
        ...
endif
```

Since we are consider the kernel for `x86_64` architecture, we assume that the `CONFIG_X86_64` is set to `y`. As the result, the `head_64.S` file will be used during the kernel build process. Let's start to investigate this what the kernel does in this file.

### Reload the segments if needed

As we already know, our start is in [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) assembly source code file. The entry point is defined by the `startup_32` symbol.

At the beginning of the `startup_32`, we can see the `cld` instruction, which clears the `DF` or [direction flag](https://en.wikipedia.org/wiki/Direction_flag) bit in the [flags](https://en.wikipedia.org/wiki/FLAGS_register) register:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L81-L90 -->
```assembly
	.code32
SYM_FUNC_START(startup_32)
	/*
	 * 32bit entry is 0 and it is ABI so immutable!
	 * If we come here directly from a bootloader,
	 * kernel(text+data+bss+brk) ramdisk, zero_page, command line
	 * all need to be under the 4G limit.
	 */
	cld
	cli
```

When the direction flag is clear, all string or copy-like operations used for copying data, like for example [stos](http://x86.renejeschke.de/html/file_module_x86_id_306.html) or [scas](http://x86.renejeschke.de/html/file_module_x86_id_287.html), will increment the index registers `esi` or `edi`. We need to clear the direction flag because later we will use string operations for tasks such as clearing space for page tables or copying data.

The next instruction is to disable interrupts - `cli`. We have already seen it in the previous chapter. The interrupts are disabled "twice" because modern bootloaders can load the kernel starting from this point, but not only one that we have seen in the [first chapter](./linux-bootstrap-1.md).

After these two simple instructions, the next step is to calculate the difference between where the kernel is compiled to run, and where it actually was loaded. If we will take a look at the linker [script](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/vmlinux.lds.S), we will see the following definition:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/vmlinux.lds.S#L19-L24 -->
```linker-script
SECTIONS
{
	/* Be careful parts of head_64.S assume startup_32 is at
	 * address 0.
	 */
	. = 0;
```

This means that the code in this section is compiled to run at the address zero. We also can see this in the output of `objdump` utility:

```bash
$ objdump -D /home/alex/disk/dev/linux/arch/x86/boot/compressed/vmlinux | less

/home/alex/disk/dev/linux/arch/x86/boot/compressed/vmlinux:     file format elf64-x86-64


Disassembly of section .head.text:

0000000000000000 <startup_32>:
   0:   fc                      cld
   1:   fa                      cli
```

We can see that both the linker script and the `objdump` utility indicate that the address of the `startup_32` function is `0`, but this is not where the kernel was loaded. This is the address that the code was compiled for, also known as the link-time address. Why was it done like that? The answer is – for simplicity. By telling the linker to set the address of the very first symbol to zero, each next symbol becomes a simple offset from 0. As we already know, the kernel was loaded at the `0x100000` address. The difference between the address where the kernel was loaded and the address with which the kernel was compiled is called the relocation delta. Once the delta is known, the code can reach any variable or function by adding this delta to their compile-time addresses.

We know both these addresses based on the experiment above, and as a result, we know the value of the delta. Now let's take a look at how the kernel calculates this difference:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L100-L104 -->
```assembly
	leal	(BP_scratch+4)(%esi), %esp
	call	1f
1:	popl	%ebp
	subl	$ rva(1b), %ebp
```

The `call` instruction is used to get the physical address where the kernel is actually loaded. This trick works because after the `call` instruction is executed, the stack should have the return address on top. This return address will be exactly the address of the label `1`. 

In the code above, the kernel sets up a temporary mini stack where the return address will be stored after the `call` instruction. Right after the call, we pop this address from the stack and save it in the `ebp` register. Using the last instruction, we subtract the difference between the address of the label `1` and the `startup_32` physical address using the `rva` macro and `subl` instruction, and store the result in the `ebp` register.

The `rva` macro is defined in the same source code file and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L79-L79 -->
```assembly
#define rva(X) ((X) - startup_32)
```

Schematically, it can be represented like this:

![startup_32](./images/startup_32.svg)

Starting from this moment, the `ebp` register contains the physical address of the `startup_32` symbol. Next, it will be used to calculate the offset to any other symbols or structures in memory.

The very first such structure that we need to access is the Global Descriptor Table. To switch to long mode, we need to update the previously loaded Global Descriptor Table with `64-bit` segments:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L106-L109 -->
```assembly
	leal	rva(gdt)(%ebp), %eax
	movl	%eax, 2(%eax)
	lgdt	(%eax)
```

Knowing now that the `ebp` register contains the physical address of the beginning of the kernel in protected mode, we calculate the offset to the `gdt` structure using it at the first line of code shown above. In the last two lines, we write this address to the `gdt` structure with offset `2`, and load the new Global Descriptor Table with the `lgdt` instruction.

The new Global Descriptor Table looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L495-L504 -->
```assembly
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

The new Global Descriptor table contains five descriptors: 

- 32-bit kernel code segment
- 64-bit kernel code segment
- 32-bit kernel data segment
- Task state descriptor
- Second task state descriptor

We already saw loading the Global Descriptor Table in the previous [part](./linux-bootstrap-3.md#set-up-global-descriptor-table), and now we're doing almost the same, but we set descriptors to use `CS.L = 1` and `CS.D = 0` for execution in `64` bit mode.

After the new Global Descriptor Table is loaded, the next step is to set up the stack:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L111-L119 -->
```assembly
	movl	$__BOOT_DS, %eax
	movl	%eax, %ds
	movl	%eax, %es
	movl	%eax, %fs
	movl	%eax, %gs
	movl	%eax, %ss

	/* Setup a stack and load CS from current GDT */
	leal	rva(boot_stack_end)(%ebp), %esp
```

In the previous step, we loaded a new Global Descriptor Table; however, all the segment registers may still have selectors from the old table. If those selectors point to invalid entries in the new Global Descriptor Table, the next memory access can cause [General Protection Fault](https://en.wikipedia.org/wiki/General_protection_fault). Setting them to `__BOOT_DS`, which is a well-known descriptor, should fix this potential fault and allow us to set the proper stack pointed by `boot_stack_end`.

The last action after we loaded the new Global Descriptor Table is to reload the `cs` descriptor:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L121-L125 -->
```assembly
	pushl	$__KERNEL32_CS
	leal	rva(1f)(%ebp), %eax
	pushl	%eax
	lretl
1:
```

Since we can not change segment registers using the `mov` instruction, a trick with the `lretl` instruction is used to set the `cs` with the correct value. This instruction fetches two values from the top of the stack, then puts the first value into the `eip` register and the second value into the `cs` register. Since this moment, we have a proper kernel code selector and instruction pointer values.

Just a couple of steps separate us from transitioning into the long mode. As mentioned at the beginning of this chapter, one of the most crucial steps is to set up `paging`. But before that, the kernel needs to do the last preparations, which we will see in the next sections.

## Last steps before paging setup

As we mentioned in the previous section, there a couple of additional steps before we can setup paging and switch to long mode. These steps are:

- Verification of CPU
- Calculation of the relocation address
- Enabling `PAE` mode

In the next sections we will take a look at these steps.

### CPU verification

Before the kernel can switch to long mode, it checks that it runs on a suitable `x86_64` processor by running this piece of code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L132-L136 -->
```assembly
	/* Make sure cpu supports long mode. */
	call	verify_cpu
	testl	%eax, %eax
	jnz	.Lno_longmode
```

The `verify_cpu` function is defined in [arch/x86/kernel/verify_cpu.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/verify_cpu.S) and executes the [CPUID](https://en.wikipedia.org/wiki/CPUID) instruction to check the details of the processors on which the kernel is running. In our case, the most crucial check is for long mode and [SSE](http://en.wikipedia.org/wiki/Streaming_SIMD_Extensions) support. This function returns the result in the `eax` register. Its value is `0` on success and `1` on failure. If long mode is not supported by the current processor, the kernel jumps to the `no_longmode` label, which stops the CPU with the `hlt` instruction:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L478-L483 -->
```assembly
	.code32
SYM_FUNC_START_LOCAL_NOALIGN(.Lno_longmode)
	/* This isn't an x86-64 CPU, so hang intentionally, we cannot continue */
1:
	hlt
	jmp     1b
```

If everything is ok, the kernel proceeds its work.

### Calculation of the kernel relocation address

The next step is to calculate the address for the kernel decompression. The kernel image mainly consists of two parts:

- Kernel's setup and decompressor code
- Chunk of compressed kernel code

We can see it looking at the [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/vmlinux.lds.S) linker script:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/vmlinux.lds.S#L19-L39 -->
```linker-script
SECTIONS
{
	/* Be careful parts of head_64.S assume startup_32 is at
	 * address 0.
	 */
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
		*(.noinstr.text)
		_etext = . ;
	}
```

There are three sections at the beginning of the linker script above:

- `.head.text` - section where we are now
- `.rodaya..compressed` - section with the compressed kernel image
- `.text` - section with the decompressor code

The kernel decompression happens in-place, which is the same place where the compressed kernel is. This means that the parts of the decompressed kernel image will overwrite the parts of the compressed image during the decompression process. It may sound dangerous – if the decompressed part overwrites the decompressor code or the part of the compressed kernel image that is not decompressed yet, this will lead to code or image corruption.

One way to avoid this problem is to allocate a buffer for the decompressed kernel image and copy the compressed image outside of it. But this is not the most effective way in terms of memory consumption, and may not work on devices with not enough memory to hold both kernel images.

The second way to avoid this problem is to allocate a buffer for the decompressed kernel image, but copy the compressed image to the end of this buffer and leave some room at the beginning of this buffer for the parts of the decompressed kernel. Of course, the kernel decompressor must choose the right parameters, so the pointer to the end of the decompressed part does not move faster than the pointer to the part that is currently compressed.

Schematically, it can be represented like this:

![kernel-relocation](./images/kernel-relocation.svg)

The buffer for the decompressed kernel starts at the address specified by the `LOAD_PHYSICAL_ADDR` macro, which by default expands to the `0x1000000` address. Since we loaded this address below (at `0x100000`), the kernel setup code should copy itself, the compressed kernel image, and the decompressor code at this address. In addition, to have some room for the safe in-place decompression, it should calculate a special offset from the beginning of this buffer.

We can see this calculation in the following code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L146-L161 -->
```assembly
#ifdef CONFIG_RELOCATABLE
	movl	%ebp, %ebx
	movl	BP_kernel_alignment(%esi), %eax
	decl	%eax
	addl	%eax, %ebx
	notl	%eax
	andl	%eax, %ebx
	cmpl	$LOAD_PHYSICAL_ADDR, %ebx
	jae	1f
#endif
	movl	$LOAD_PHYSICAL_ADDR, %ebx
1:

	/* Target address to relocate to for decompression */
	addl	BP_init_size(%esi), %ebx
	subl	$ rva(_end), %ebx
```

Despite it may look scary, it is not as complex as it may seem. Let's take a closer look at it and try to understand what it does.

The `ebp` register contains the physical address where the protected kernel mode was loaded. We know that this address is `0x100000`. This address is aligned to the two-megabyte boundary, and the result value is compared with the `LOAD_PHYSICAL_ADDRESS`:

- If this value is equal to or greater than `LOAD_PHYSICAL_ADDRESS`, we leave it as is. 
- Otherwise, we put the value of the `LOAD_PHYSICAL_ADDRESS` (which is `0x1000000`) into the `ebx` register. 

At this moment, we have the pointer to the beginning of the buffer where the kernel image is relocated and decompressed in the `ebx` register.

The last two lines are the most interesting. Using them, the kernel calculates the offset where to move the compressed kernel image with the decompressor for safe in-place decompression. At first, we add the `BP_init_size` to the `ebx` register. The `BP_init_size` is the maximum value between the size of the uncompressed kernel image code (from `_text` to `_end`) and the size of the kernel setup code + compressed kernel image + decompressor code. At this moment, the `ebx` register points to the end of the decompression buffer. On the last line of the code, we move this pointer back to the new place of the `startup_32` symbol within the decompression buffer.

As a result, we get something like this:

![kernel-relocation](./images/kernel-relocation-2.svg)

The decompressor code decompresses the compressed kernel image starting from the beginning of the buffer and gradually overwrites the compressed kernel image. As mentioned above, the size of the gap between the beginning of the decompression buffer and `startup_32` must be safe enough not to overwrite still-compressed parts of the image with the decompressed ones. The calculation of this gap highly depends on the compression method the kernel uses and is encoded in `BP_init_size`. Here I will skip all the details about this calculation, but if you are interested, you can find more details in the comment located in the [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S) file.

### Enabling PAE mode

The next step before the kernel can switch the processor into the long mode is to set up the so-called [`PAE`](https://en.wikipedia.org/wiki/Physical_Address_Extension) mode:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L167-L170 -->
```assembly
	/* Enable PAE mode */
	movl	%cr4, %eax
	orl	$X86_CR4_PAE, %eax
	movl	%eax, %cr4
```

Kernel does it by setting the `X86_CR4_PAE` bit in the `cr4` [control register](https://en.wikipedia.org/wiki/Control_register). This tells the processor that the page table entries will be enlarged from `32` to `64` bits. We will see this process soon.

## Set up paging

At this moment, we almost finished the preparations needed to switch the processor into 64-bit long mode. The next crucial step is to build [page tables](https://en.wikipedia.org/wiki/Page_table). But before we take a look at the process of page table setup, let's try to briefly understand what it is.

In protected mode, each memory access is interpreted through a segment descriptor stored in the Global Descriptor Table. The situation changes significantly in long mode.

In 64-bit mode, segmentation is disabled. The base and limit fields of most segment descriptors are ignored, and the processor treats the address space as a flat linear range. Of course, code, data, and stack segments still exist, but only formally. The processor still requires valid segment selectors, but they no longer perform address translation in the traditional sense.

Instead, memory translation in long mode relies almost entirely on the mechanism called `paging`.

Each program operates now with addresses that are called `virtual`. When a program references a virtual address, the processor interprets the address as a 64-bit linear address and translates it through the multi-level structure called page tables.

> [!NOTE]
> Modern x86_64 processors support five-level paging, but we will skip it in this post and focus on four-level paging.

Let’s briefly see what happens when the processor needs to translate a virtual address into a physical one.

In four-level paging mode, a virtual address is 64 bits long. However, only the `48` bits are actually used for translation to a physical address. These `48` bits are divided into several parts:

![early-page-table.svg](./images/early-page-table.svg)

Each group of `9` bits selects an entry in one level of the page-table hierarchy. Since `9` bits can represent `512` values, each page table contains exactly `512` entries. Each entry of a page table occupies `8` bytes, so a single page table fits into one 4-kilobyte page.

When the processor translates a virtual address, it performs the following steps:

1. It reads the `cr3` control register to obtain the physical address of the top-level page table called `PML4`.
2. It extracts bits `47–39` of the virtual address and uses them as an index of the `PML4` page table.
3. The selected `PML4` entry contains the physical address of the next-level table called `PDPT`.
4. Bits `38–30` are selected to find an entry in the `PDPT`.
5. Bits `29–21` are selected to find an entry in the `PD`.
6. Bits `20–12` select an entry in the `PT`.
7. Bits `11–0` provide the offset inside the resulting physical page.

In addition to a physical address of the next-level table, each page table entry contains flags in first `12` bits. These flags are:

| Bit   | Name                     | Description                                                                                                                                        |
|-------|--------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| `P`   | Present                  | Indicates whether the page or page table entry is valid and exists in memory. If cleared, accessing the corresponding address causes a page fault. |
| `RW`  | Read/Write               | Determines whether write operations are permitted. If cleared, the page is read-only; if set, writes are allowed (subject to privilege rules).     |
| `US`  | User/Supervisor          | Controls privilege-level access. If cleared, the page is accessible only in supervisor mode. If set, it may also be accessed from user mode.       |
| `PWT` | Page-Level Write-Through | Controls the caching policy. If set, write-through caching is used; otherwise, write-back caching is typically applied.                            |
| `PCD` | Page Cache Disable       | Disables caching for the referenced page when set. Commonly used for memory-mapped I/O regions.                                                    |
| `A`   | Accessed                 | Set automatically by the processor when the page-table entry is used during address translation. Useful for page replacement decisions.            |
| `D`   | Dirty                    | Set automatically by the processor when a write operation occurs to a mapped page. Indicates that the page has been modified.                      |
| `PS`  | Page Size                | Determines whether the entry maps a large page (e.g., 2 MiB or 1 GiB) instead of pointing to a lower-level page table.                             |
| `NX`  | No-Execute               | Prevents instruction execution from the referenced page when set. Used to enforce executable/non-executable memory protections.                    |
       
You might wonder how an 8-byte entry can contain both a 64-bit physical address of the next-level page table and flags at the same time. The reason is that each page table is aligned on a four-kilobyte boundary. As a result, the lower 12 bits of its physical address are always zero. These 12 bits are therefore used to store the flags.

Now that we know how the processor translates a virtual address to a physical address using paging, it is time to take a look at the structure of page tables.

A page table in x86_64 is a four-kilobyte memory area that contains 512 entries. Each entry occupies `8` bytes. In four-level paging mode with four-kilobyte pages, four such tables participate in the translation of a virtual address:

| Level | Name   | Description                                                                                                                 |
|-------|--------|-----------------------------------------------------------------------------------------------------------------------------|
| 4     | `PML4` | The top-level page table. Each entry points to a Page Directory Pointer Table (`PDPT`).                                     |
| 3     | `PDPT` | The third-level table. Each entry points to a Page Directory (`PD`) or, if the `PS` bit is set, directly maps a 1 GiB page. |
| 2     | `PD`   | The second-level table. Each entry points to a Page Table (`PT`) or, if the `PS` bit is set, directly maps a 2 MiB page.    |
| 1     | `PT`   | The first-level table. Each entry points directly to a 4 KiB physical memory page.                                          |

Each table has the same internal structure. The only difference between them is how their entries are interpreted. As we already know, an entry in a page table is 64 bits wide. It contains two types of information:

- A physical address of either the next-level page table or a physical memory page
- A set of control flags that define access permissions and status information 

If you are interested in this topic, you can find more information about page tables and page table entries structure in the [Intel® 64 and IA-32 Architectures Software Developer Manuals](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html).

Now that we know a little about paging, we can return to the kernel and update our knowledge by looking at the real code. Now we will see how the kernel builds the early page table to switch to long mode. But before we jump directly to the code, we need to remember one important thing. The kernel will be relocated to the address stored in the `ebx` register, as seen above. So, all structures, including the page tables, should be aligned to this address.

The page table structure for boot is defined in the same source code file and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L531-L533 -->
```assembly
	.section ".pgtable","aw",@nobits
	.balign 4096
SYM_DATA_LOCAL(pgtable,		.fill BOOT_PGT_SIZE, 1, 0)
```

The kernel needs to fill this structure with the proper page table entries for early 64-bit code. First of all, it fills the whole memory area occupied by the page tables with zeros for safety:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L200-L203 -->
```assembly
	leal	rva(pgtable)(%ebx), %edi
	xorl	%eax, %eax
	movl	$(BOOT_INIT_PGT_SIZE/4), %ecx
	rep	stosl
```

At the beginning, we set the address of the top of the page table to the `edi` register. After this, the kernel fills with zeros the memory area that will be occupied by the page table. The boot page table will have the following structure:

- 1 level4 table
- 1 level3 table
- 4 level2 table that maps everything with 2M pages

After the kernel clears the memory region reserved for the page tables, it starts populating it with entries. At the start, it fills the first and single entry of the top-level page table. The following snippet shows this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L206-L209 -->
```assembly
	leal	rva(pgtable + 0)(%ebx), %edi
	leal	0x1007 (%edi), %eax
	movl	%eax, 0(%edi)
	addl	%edx, 4(%edi)
```

In the code above, the kernel fills the first entry of the top-level page table with the address of the next-level page table, which is located at the `pgtable + 0x1000` address and has `0x7` flags. In our case, the flags `0x7` are:

- Present
- Read/Write
- User

In the next step, the kernel builds four `Page Directory` entries in the `Page Directory Pointer` table with the same `Present+Read/Write/User` flags:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L212-L220 -->
```assembly
	leal	rva(pgtable + 0x1000)(%ebx), %edi
	leal	0x1007(%edi), %eax
	movl	$4, %ecx
1:	movl	%eax, 0x00(%edi)
	addl	%edx, 0x04(%edi)
	addl	$0x00001000, %eax
	addl	$8, %edi
	decl	%ecx
	jnz	1b
```

In the code above, we can see the filling of the first four entries of the 3rd-level page table. The first entry of the 3rd level page table is located at the offset `0x1000` from the beginning of the top-level page table. The value of the `eax` register is similar to the 4th-level page table entry, with the difference that now it points to the 2nd-level page table. Next, the kernel fills the four entries of the 3rd-level page table in the "loop" until the value of the `ecx` register is not zero. As soon as these page table entries are filled, the kernel proceeds to the next-level page table:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L223-L231 -->
```assembly
	leal	rva(pgtable + 0x2000)(%ebx), %edi
	movl	$0x00000183, %eax
	movl	$2048, %ecx
1:	movl	%eax, 0(%edi)
	addl	%edx, 4(%edi)
	addl	$0x00200000, %eax
	addl	$8, %edi
	decl	%ecx
	jnz	1b
```

Here we already fill four page directory tables with `2048` entries. The first entry is located at the offset `0x2000` from the beginning of the top-level page table. Each entry maps a two-megabyte chunk of memory with the following flags:

- Present
- Read/Write
- User
- Page Cache Disable
- Large Page 

The two additional flags tell the processor to keep [TLB](https://en.wikipedia.org/wiki/Translation_lookaside_buffer) entry across reload of the value of the `cr3` register and use two-megabyte pages.

There is no need to populate the lowest-level page tables yet. Every entry in the 2nd-level page directory has the `Large Page` bit set, which means each entry directly maps a two-megabyte region of physical memory. During the address translation, the page-walk procedure stops at the 2nd-level page table, and the lower `21` bits of the virtual address are used as the offset inside that two-megabyte page.

The page tables are now fully prepared. The last remaining step is to actually enable paging. To do this, the processor must know where the top-level page table resides. As we know, this is done by loading the physical address of the top-level page table into the `cr3` control register:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L234-L235 -->
```assembly
	leal	rva(pgtable)(%ebx), %eax
	movl	%eax, %cr3
```

From this moment, page tables that cover four gigabytes of memory are ready, and paging is enabled. The kernel is ready for transition into the long mode.

## The transition into 64-bit mode

Only the last steps remain before the Linux kernel can switch the processor into the long mode. The first one is setting the `EFER.LME` flag in the special [model-specific register](http://en.wikipedia.org/wiki/Model-specific_register) to the predefined value `0xC0000080`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L238-L241 -->
```assembly
	movl	$MSR_EFER, %ecx
	rdmsr
	btsl	$_EFER_LME, %eax
	wrmsr
```

This is the `Long Mode Enable` bit, and it is mandatory to set this bit to enable long mode.

In the next step, we can see the preparation for the jump on the long mode entrypoint. To do this jump, the kernel stores the base address of the kernel segment code along with the address of the long mode entrypoint on the stack:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L264-L266 -->
```assembly
	leal	rva(startup_64)(%ebp), %eax
	pushl	$__KERNEL_CS
	pushl	%eax
```

Since the stack contains the base of the kernel code segment and the address of the entrypoint, the kernel executes the last instruction in protected mode:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L273-L273 -->
```assembly
	lret
```

The CPU extracts the address of `startup_64`, which is the long mode entrypoint from the stack, and jumps there:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L276-L278 -->
```assembly
	.code64
	.org 0x200
SYM_CODE_START(startup_64)
```

The Linux kernel is now in 64-bit mode! 🎉

## Conclusion

This is the end of the third part about Linux kernel insides. If you have questions or suggestions, feel free ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).

## Links

Here is the list of the links that you may find useful during reading of this chapter:

- [Real mode](https://en.wikipedia.org/wiki/Real_mode)
- [Protected mode](http://en.wikipedia.org/wiki/Protected_mode)
- [Long mode](https://en.wikipedia.org/wiki/Long_mode)
- [Linux kernel x86 boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt)
- [Intel® 64 and IA-32 Architectures Software Developer Manuals](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)
- [Paging](http://en.wikipedia.org/wiki/Paging)
- [Virtual addresses](https://en.wikipedia.org/wiki/Virtual_address_space)
- [Physical addresses](https://en.wikipedia.org/wiki/Physical_address)
- [Model specific registers](http://en.wikipedia.org/wiki/Model-specific_register)
- [Control registers](https://en.wikipedia.org/wiki/Control_register)
- [Previous part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-3.md)
