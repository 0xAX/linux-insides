# Kernel booting process. Part 4.

In the previous [part](./linux-bootstrap-3.md), we saw the transition from the [real mode](https://en.wikipedia.org/wiki/Real_mode) into [protected mode](http://en.wikipedia.org/wiki/Protected_mode). At this point, the two crucial things were changed - the processor can address up to 4 gigabytes of memory and the privilege levels were set for the memory access. Despite this, the kernel is still in its early setup mode. There are many different things that has to be prepared and configured before we will reach the main kernel's entry point. Since we are learning the Linux kernel for `x86_64` processors, the protected mode is not the main mode where the processor should operate. The next crucial step is to switch to the native mode for `x86_64` - [long mode](https://en.wikipedia.org/wiki/Long_mode).

The main characteristic of this new mode, as with all the earlier modes - the way it defines the memory model. In real mode, the memory model was relatively simple and each memory location was formed based on the base address specified in a segment register and plus some offset. In protected mode, introduced Global and Local descriptor table with descriptors which describe memory areas. All the memory accesses in long mode are based on the new mechanism called [paging](https://en.wikipedia.org/wiki/Memory_paging). One of the crucial goal of the kernel before it can switch to the long mode is to setup paging. This and all other details needed to switch to long mode we will see in this chapter.

> [!NOTE]
> There will be lots of assembly code in this part, so if you are not familiar with that, you might want to consult a book about it or read another set of my [posts](https://github.com/0xAX/asm) about assembly programming.

## The 32-bit kernel entry point location

The last point where we stopped was the [jump](https://en.wikipedia.org/wiki/Branch_(computer_science)#Implementation) to the kernel's entry point in protected mode. This jump is defined in the [arch/x86/boot/pmjump.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/pmjump.S) and looks like this:

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

The `32-bit` entry point is defined in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) assembly source code file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L81-L82 -->
```assembly
	.code32
SYM_FUNC_START(startup_32)
```

First of all, it is worth to know is the directory named `compressed`? The answer to that is that the kernel is in the [`bzImage`](https://en.wikipedia.org/wiki/Vmlinux#bzImage) file. This file is a compressed package consisting of kernel image and the kernel setup code. In all previous chapters we were researching the kernel setup code. The next two big steps which remaining before we will see the entrypoint of the kernel are:

- switch to long mode
- decompress the kernel image and jump to its entrypoint

In this part we will focus at the first big step and the steps leading to the kernel decompression and the decompression itself we will see in the next chapters. Returning to the current kernel code, you may find the two following files in the [arch/x86/boot/compressed](https://github.com/torvalds/linux/tree/master/arch/x86/boot/compressed) directory:

- [head_32.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_32.S)
- [head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S)

In our case, we will consider only the `head_64.S` file. Yes, the file named with the `64` suffix despite the kernel is in the 32-bit protected mode for this moment. The explanation for this situation is simple. Let's look at [arch/x86/boot/compressed/Makefile](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/Makefile). We may see the following `make` goal here:

```Makefile
vmlinux-objs-y := $(obj)/vmlinux.lds $(obj)/kernel_info.o $(obj)/head_$(BITS).o \
	$(obj)/misc.o $(obj)/string.o $(obj)/cmdline.o $(obj)/error.o \
	$(obj)/piggy.o $(obj)/cpuflags.o
```

The first line contains this the following target - `$(obj)/head_$(BITS).o`. This means, that `make` will select the file during kernel build process based on the value of the `$(BITS)`. This `make` variable defined in the [arch/x86/Makefile](https://github.com/torvalds/linux/blob/master/arch/x86/Makefile) make file and its value depends on the kernel configuration:

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

As we already know, our start is in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) assembly source code file. The entry point is defined by the `startup_32` symbol.

In the beginning of the `startup_32`, we can see the `cld` instruction which clears the `DF` or [direction flag](https://en.wikipedia.org/wiki/Direction_flag) bit in the [flags](https://en.wikipedia.org/wiki/FLAGS_register) register:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L81-L89 -->
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
```

When the direction flag is clear, all string operations which usually used for copying data, like for example [stos](http://x86.renejeschke.de/html/file_module_x86_id_306.html), [scas](http://x86.renejeschke.de/html/file_module_x86_id_287.html) and others, will increment the index registers `esi` or `edi`. We need to clear the direction flag because later we will use strings operations to perform various operations such as clearing space for page tables or copying data.

The next instruction is to disable interrupts - `cli`. We already have seen it in previous chapter. The interrupts are disabled "twice" because modern bootloaders can load the kernel starting from this point but not only one that we have seen in the [first chapter](./linux-bootstrap-1.md).

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

We may see that and the linker script and the `objdump` utility tells us that the address of the `startup_32` function is `0` but it is not where the kernel was loaded. This is only the address that the code was compiled for, also called link-time address. Why it was done like that? The answer is for simplicity. By telling the linker to set the address of the very first symbol to zero, each next symbol becomes a simple offset from 0. As we already know, the kernel was loaded at the `0x100000` address. The difference between this address and zero called relocation delta. Once that delta is known, the code can reach any variable or function by adding this delta to their compile-time addresses.

We know these addresses and as the result the value of delta based on experiment we have seen above. Now let's take a look how the kernel calculates this difference:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L100-L104 -->
```assembly
	leal	(BP_scratch+4)(%esi), %esp
	call	1f
1:	popl	%ebp
	subl	$ rva(1b), %ebp
```

The `call` instruction is used to get the real address of the kernel. This trick works because after the `call` instruction is executed, the stack should have return address on its top. In the code above we setup a temporary mini stack to get the address of the kernel and execute the call to the nearest label `1`. Since the top of the stack contains the return address, we put it into the `ebp` register. Using the last instruction we subtract the difference between the address of the label `1` and `strtup_32` address from the return address that we got at the previous step:

![startup_32](./images/startup_32.svg)

Starting from this moment, the `ebp` register will contain the address of the beginning of the kernel image and using it we can calculate offset to any other symbols or structures in memory. And the first such structure that we will access is the Global Descriptor Table. To switch to long mode, we need to update the previously loaded Global Descriptor Table with `64-bit` segments:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L106-L109 -->
```assembly
	leal	rva(gdt)(%ebp), %eax
	movl	%eax, 2(%eax)
	lgdt	(%eax)
```

Where the new Global Descriptor Table is:

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

- `32-bit` kernel code segment
- `64-bit` kernel code segment
- `32-bit` kernel data segment
- Task state descriptor
- Second task state descriptor

We already saw the loading the Global Descriptor Table in the previous [part](./linux-bootstrap-3.md#set-up-global-descriptor-table), and now we're doing almost the same here, but we set descriptors to use `CS.L = 1` and `CS.D = 0` for execution in 64 bit mode.

After the new Global Descriptor Table is loaded, the kernel can setup the new stack:

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

At the previous step we loaded new Global Descriptor Table, but all the segment registers may have selectors from old table. If those selectors point to invalid entries in the new Global Descriptor Table, next memory access can cause [General Protection Fault](https://en.wikipedia.org/wiki/General_protection_fault). Setting them to the `__BOOT_DS` which is a known-good descriptor should fix this potential fault and allow us to set proper stack pointed by the `boot_stack_end`.

The last action after we loaded the new Global Descriptor Table is to reload `cs` descriptor:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L121-L125 -->
```assembly
	pushl	$__KERNEL32_CS
	leal	rva(1f)(%ebp), %eax
	pushl	%eax
	lretl
1:
```

Since we can not change segment registers using simple `mov` instruction, we need to apply a trick with the `lretl` instruction. This instruction fetches the two values from the top of the stack and put the first value into the `eip` register and the second value to the `cs` register. Since this moment we have proper kernel code selector and instruction pointer values.

Just a couple of steps separate us from the transition into the long mode. As it was mentioned in the beginning of this chapter, one of the most crucial is to setup `paging`. But before this task, the kernel needs to do last preparations which we will see in the next sections.

## Last steps before paging setup

As we mentioned in the previous section, there a couple of additional steps before we can setup paging and switch to long mode. These steps are:

- Verification of CPU
- Calculation of the relocation address
- Enabling `PAE` mode

In the next sections we will take a look at these steps.

### CPU verification

Before we the kernel can switch to long mode, it needs to check that it runs on the suitable `x86_64` processor. This is done by the next piece of code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L132-L136 -->
```assembly
	/* Make sure cpu supports long mode. */
	call	verify_cpu
	testl	%eax, %eax
	jnz	.Lno_longmode
```

The `verify_cpu` function defined in the [arch/x86/kernel/verify_cpu.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/verify_cpu.S) and executes the [cpuid](https://en.wikipedia.org/wiki/CPUID) instruction to check the details of the processors on which kernel is running on. In our case, the most crucial check is for `long mode` and [SSE](http://en.wikipedia.org/wiki/Streaming_SIMD_Extensions) support. and sets the `eax` register to `0` on success and `1` on failure. If the long mode is not supported by the current processor, the kernel jumps to the `no_longmode` label which just stops the CPU with the `hlt` instruction:

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

The next step is to calculate the address for the kernel decompression. The kernel consists of two parts:

- Relatively small decompressor code
- Chunk of compressed kernel code

Obviously, the final decompressed kernel code will be bigger than compressed image. The memory area where the decompressed kernel should locate may overlap with the area where the compressed image is located. In this case, the compressed image could be overwritten during decompression process. To avoid this, the the kernel will copy the compressed part for safe decompression. This is done by the following code:

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

The `ebp` register contains current address of the beginning of the kernel image. We put this address to the `ebx` register and aligned it by the `2MB` border. If the resulted address equal or bigger than `LOAD_PHYSICAL_ADDRESS` which is `0x1000000` we use it as is, otherwise we set it to `0x1000000`. Since we have the beginning of the address where to move the compressed kernel image, we add to it `BP_init_size` which is the size of decompressed kernel image. This will allow us to copy compressed kernel image behind the memory area where the kernel will be decompressed. In the end we just subtract the address of the `_end` from the value in the `ebx` to get the new base address of the decompressor kernel code.

### Enabling PAE mode

The next step is to setup so-called `PAE` mode:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L167-L170 -->
```assembly
	/* Enable PAE mode */
	movl	%cr4, %eax
	orl	$X86_CR4_PAE, %eax
	movl	%eax, %cr4
```

We doing it by setting the `X86_CR4_PAE` bit in the `cr4` [control register](https://en.wikipedia.org/wiki/Control_register). This tells to CPU that the page table entries that we will see soon will be enlarged from `32` to `64` bits.

## Setup paging

At this moment we are almost finished with the preparations needed to switch the processor into the 64-bit mode. One of the last step, is to build [page tables](https://en.wikipedia.org/wiki/Page_table). But before we will take a look at the process of page tables setup, let's try briefly understand what is it.

As we mentioned in the beginning of this chapter - on `x86_64`, the processor must have paging enabled to use long mode. Paging lets the processor translate [virtual addresses](https://en.wikipedia.org/wiki/Virtual_address_space) or addresses used by the code, into a [physical addresses](https://en.wikipedia.org/wiki/Physical_address). The translation of virtual addresses into physical done using the special structure - page tables. All the memory considered as array of sequential blocks called pages. Each page is described by the special descriptor in the page table called `PTE` or page table entry. The page table entries are stored in the special structure called page tables. The page table is a structure with predefined hierarchy:

- `PML4` - top level table, each entry points to `PDPT`
- `PDPT` - 3rd level table, each entry points to `PD`
- `PD` - 2nd level table, each entry points to `PT`
- `PT` - 1st level table, each entry points to a 4 killobyte physical page

The physical address of the top level table must be stored in the `cr3` register.

When the processor needs to translate a virtual address into the corresponding physical address, it splits the virtual address to the next parts:

![early-page-table.svg](./images/early-page-table.svg)

Knowing the index of the corresponding entry in each table, CPU obtains the physical address.

The next goal of the kernel is to build a structure similar to the description above to switch to long mode. Let's take a look how it is implemented in the kernel. First of all we need to fill the current page table structure specified by the [pgtable](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S#L533) with zeros for safeness:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L200-L203 -->
```assembly
	leal	rva(pgtable)(%ebx), %edi
	xorl	%eax, %eax
	movl	$(BOOT_INIT_PGT_SIZE/4), %ecx
	rep	stosl
```

After we cleaned the memory area for the page tables, we can start to fill it. First of all, we need to fill the top-level page entry:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L206-L209 -->
```assembly
	leal	rva(pgtable + 0)(%ebx), %edi
	leal	0x1007 (%edi), %eax
	movl	%eax, 0(%edi)
	addl	%edx, 4(%edi)
```

This adds the first entry to the top-level page table. This entry will contain a reference to the first entry of the lower-level table. The offset to it is `0x1000` bytes. The `0x7` are flags of the page table entry:

- Present
- Read/Write
- User

Each page entry is `64-bit` structure, no matter if it is a `PML4`, `PDPT`, `PD` or `PT` entry. The format is almost the same among all the levels. The difference is only in the address field which stores the physical address of the next page table by hierarchy. Besides the address field, a page table entry contains flags like:

- `P` - present bit
- `RW` - read/write bit
- `US` - user/supervisor bit
- `PWT` - Page-level Write-Through bit controlling caching of the page
- `PCD` - Page Cache Disable bit controlling caching of the page
- `A` - accessed page bit
- `D` - dirty page bit
- `PS` - page size bit
- `NX` - No-Execute bit

More information about the page tables and page table entries structure you can find in the [Intel® 64 and IA-32 Architectures Software Developer Manuals](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html).

In the next step we will build four `Page Directory` entries in the `Page Directory Pointer` table with the same `Present+Read/Write/User` flags:

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

In the code above, we may see filling of the first four entries of the 3rd level page table. The first entry is located at the offset `0x1000` from the beginning of the page table. The value of the `eax` register is similar to the 4th level page table entry. Next we just fill the four entries of this table in the "loop" while value of the `ecx` will not be zero. As soon as this table entries are filled, the next turn of the next level page table:

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

Here we already fill 4 page directories with 2048 entries. The first entry is located at the offset `0x2000` from the beginning of the page table. Each entry maps a 2 megabytes chunk of memory with the same `Present/Read/Write/Large Page` flags but in addition there is `Global` flag. This additional flag tells the processor to keep [TLB](https://en.wikipedia.org/wiki/Translation_lookaside_buffer) entry across reload of the value of the `cr3` register.

This was the last page table entries which kernel fills. There is no need for this moment to fill the 4th level `PT` tables because every at the 2nd level page table was filled with the `Large Page` bit, so each such entry directly maps a 2 megabytes region. During the address transition, the page-walk procedure stops at the `PD` level going through `PML4 → PDPT → PD`, and the lower `21` bits of the virtual address will be used as the offset inside that 2 megabytes page.

Now we can enable the paging by storing the address of the page table in the `cr3` register:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L234-L235 -->
```assembly
	leal	rva(pgtable)(%ebx), %eax
	movl	%eax, %cr3
```

The page tables is ready and paging is enabled starting from this moment. Now the kernel is prepared for transition into the long mode.

## The transition into 64-bit mode

Only the last steps are remaining before the Linux kernel can switch CPU into the long mode. The first one is setting the `EFER.LME` flag in the special [model specific register](http://en.wikipedia.org/wiki/Model-specific_register) to the predefined value `0xC0000080`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L238-L241 -->
```assembly
	movl	$MSR_EFER, %ecx
	rdmsr
	btsl	$_EFER_LME, %eax
	wrmsr
```

This is the `Long Mode Enable` bit and it is mandatory action to set this bit to enable `64-bit` mode.

In the next step, we may see the preparation of the jump on the long mode entrypoint. To do this jump, the kernel stores the base address of the kernel segment code along with the address of the long mode entrypoint on the stack:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L264-L266 -->
```assembly
	leal	rva(startup_64)(%ebp), %eax
	pushl	$__KERNEL_CS
	pushl	%eax
```

Everything is ready. Since our stack contains the base of the kernel code segment and the address of the entrypoint, kernel executes the last instruction in protected mode:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L273-L273 -->
```assembly
	lret
```

The CPU extracts the address of the `startup_64` from the stack and jumps there:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/compressed/head_64.S#L276-L278 -->
```assembly
	.code64
	.org 0x200
SYM_CODE_START(startup_64)
```

The Linux kernel now in 64-bit mode 🎉


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
