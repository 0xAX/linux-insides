Kernel booting process. Part 4.
================================================================================

The Transition to 64-bit mode
--------------------------------------------------------------------------------

This is the fourth part of the `Kernel booting process`. Here, we will learn about the first steps taken in [protected mode](http://en.wikipedia.org/wiki/Protected_mode), like checking if the CPU supports [long mode](http://en.wikipedia.org/wiki/Long_mode) and [SSE](http://en.wikipedia.org/wiki/Streaming_SIMD_Extensions). We will initialize the page tables with [paging](http://en.wikipedia.org/wiki/Paging) and, at the end, transition the CPU to [long mode](https://en.wikipedia.org/wiki/Long_mode).

**NOTE: there will be lots of assembly code in this part, so if you are not familiar with that, you might want to consult a book about it**

In the previous [part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-3.md) we stopped at the jump to the `32-bit` entry point in [arch/x86/boot/pmjump.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/pmjump.S):

```assembly
jmpl	*%eax
```

You will recall that the `eax` register contains the address of the 32-bit entry point. We can read about this in the [linux kernel x86 boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt):

```
When using bzImage, the protected-mode kernel was relocated to 0x100000
```

Let's make sure that this is so by looking at the register values at the 32-bit entry point:

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
cs             0x10	16
ss             0x18	24
ds             0x18	24
es             0x18	24
fs             0x18	24
gs             0x18	24
```

We can see here that the `cs` register contains a value of `0x10` (as you might recall from the [previous part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-3.md), this is the second index in the `Global Descriptor Table`), the `eip` register contains the value `0x100000` and the base address of all segments including the code segment are zero.

So, the physical address where the kernel is loaded would be `0:0x100000` or just `0x100000`, as specified by the boot protocol. Now let's start with the `32-bit` entry point.

The 32-bit entry point
--------------------------------------------------------------------------------

The `32-bit` entry point is defined in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S) assembly source code file:

```assembly
	__HEAD
	.code32
ENTRY(startup_32)
....
....
....
ENDPROC(startup_32)
```

First, why is the directory named `compressed`? The answer to that is that `bzimage` is a gzipped package consisting of `vmlinux`,   `header` and ` kernel setup code`. We looked at kernel setup code in all of the previous parts. The main goal of the code in `head_64.S` is to prepare to enter long mode, enter it and then decompress the kernel. We will look at all of the steps leading to kernel decompression in this part.

You will find two files in the `arch/x86/boot/compressed` directory:

* [head_32.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_32.S)
* [head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S)

but we will consider only the `head_64.S` source code file because, as you may remember, this book is only `x86_64` related; Let's look at [arch/x86/boot/compressed/Makefile](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/Makefile). We can find the following `make` target here:

```Makefile
vmlinux-objs-y := $(obj)/vmlinux.lds $(obj)/head_$(BITS).o $(obj)/misc.o \
	$(obj)/string.o $(obj)/cmdline.o \
	$(obj)/piggy.o $(obj)/cpuflags.o
```

The first line contains this- `$(obj)/head_$(BITS).o`.

This means that we will select which file to link based on what `$(BITS)` is set to, either `head_32.o` or `head_64.o`. The `$(BITS)` variable is defined elsewhere in [arch/x86/Makefile](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/Makefile) based on the kernel configuration:

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

Now that we know where to start, let's get to it.

Reload the segments if needed
--------------------------------------------------------------------------------

As indicated above, we start in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/compressed/head_64.S) assembly source code file. We first see the definition of a special section attribute before the definition of the `startup_32` function:

```assembly
    __HEAD
    .code32
ENTRY(startup_32)
```

`__HEAD` is a macro defined in the [include/linux/init.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/init.h) header file and expands to the definition of the following section:

```C
#define __HEAD		.section	".head.text","ax"
```

Here, `.head.text` is the name of the section and `ax` is a set of flags. In our case, these flags show us that this section is [executable](https://en.wikipedia.org/wiki/Executable) or in other words contains code. We can find the definition of this section in the [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/compressed/vmlinux.lds.S) linker script:

```
SECTIONS
{
	. = 0;
	.head.text : {
		_head = . ;
		HEAD_TEXT
		_ehead = . ;
     }
     ...
     ...
     ...
}
```

If you are not familiar with the syntax of the `GNU LD` linker scripting language, you can find more information in its [documentation](https://sourceware.org/binutils/docs/ld/Scripts.html#Scripts). In short, the `.` symbol is a special linker variable, the location counter. The value assigned to it is an offset relative to the segment. In our case, we set the location counter to zero. This means that our code is linked to run from an offset of `0` in memory. This is also stated in the comments:

```
Be careful parts of head_64.S assume startup_32 is at address 0.
```

Now that we have our bearings, let's look at the contents of the `startup_32` function.

In the beginning of the `startup_32` function, we can see the `cld` instruction which clears the `DF` bit in the [flags](https://en.wikipedia.org/wiki/FLAGS_register) register. When the direction flag is clear, all string operations like [stos](http://x86.renejeschke.de/html/file_module_x86_id_306.html), [scas](http://x86.renejeschke.de/html/file_module_x86_id_287.html) and others will increment the index registers `esi` or `edi`. We need to clear the direction flag because later we will use strings operations to perform various operations such as clearing space for page tables.

After we have cleared the `DF` bit, the next step is to check the `KEEP_SEGMENTS` flag in the `loadflags` kernel setup header field. If you remember, we already talked about `loadflags` in the very first [part](https://0xax.gitbook.io/linux-insides/summary/booting/linux-bootstrap-1) of this book. There we checked the `CAN_USE_HEAP` flag to query the ability to use the heap. Now we need to check the `KEEP_SEGMENTS` flag. This flag is described in the Linux [boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt) documentation:

```
Bit 6 (write): KEEP_SEGMENTS
  Protocol: 2.07+
  - If 0, reload the segment registers in the 32bit entry point.
  - If 1, do not reload the segment registers in the 32bit entry point.
    Assume that %cs %ds %ss %es are all set to flat segments with
		a base of 0 (or the equivalent for their environment).
```

So, if the `KEEP_SEGMENTS` bit is not set in `loadflags`, we need to set the `ds`, `ss` and `es` segment registers to the index of the data segment with a base of `0`. That we do:

```C
	testb $KEEP_SEGMENTS, BP_loadflags(%esi)
	jnz 1f

	cli
	movl	$(__BOOT_DS), %eax
	movl	%eax, %ds
	movl	%eax, %es
	movl	%eax, %ss
```

Remember that `__BOOT_DS` is `0x18` (the index of the data segment in the [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table)). If `KEEP_SEGMENTS` is set, we jump to the nearest `1f` label or update segment registers with `__BOOT_DS` if they are not set. This is all pretty easy, but here's something to consider. If you've read the previous [part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-3.md), you may remember that we already updated these segment registers right after we switched to [protected mode](https://en.wikipedia.org/wiki/Protected_mode) in [arch/x86/boot/pmjump.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/pmjump.S). So why do we need to care about the values in the segment registers again? The answer is easy. The Linux kernel also has a 32-bit boot protocol and if a bootloader uses *that* to load the Linux kernel, all the code before the `startup_32` function will be missed. In this case, the `startup_32` function would be the first entry point to the Linux kernel right after the bootloader and there are no guarantees that the segment registers will be in a known state.

After we have checked the `KEEP_SEGMENTS` flag and set the segment registers to a correct value, the next step is to calculate the difference between where the kernel is compiled to run, and where we loaded it. Remember that `setup.ld.S` contains the following definition: `. = 0` at the start of the `.head.text` section. This means that the code in this section is compiled to run at the address `0`. We can see this in the output of `objdump`:

```
arch/x86/boot/compressed/vmlinux:     file format elf64-x86-64


Disassembly of section .head.text:

0000000000000000 <startup_32>:
   0:   fc                      cld
   1:   f6 86 11 02 00 00 40    testb  $0x40,0x211(%rsi)
```

The `objdump` util tells us that the address of the `startup_32` function is `0` but that isn't so. We now need to know where we actually are. This is pretty simple to do in [long mode](https://en.wikipedia.org/wiki/Long_mode) because it supports `rip` relative addressing, but currently we are in [protected mode](https://en.wikipedia.org/wiki/Protected_mode). We will use a common pattern to find the address of the `startup_32` function. We need to define a label, make a call to it and pop the top of the stack to a register:

```assembly
call label
label: pop %reg
```

After this, the register indicated by `%reg` will contain the address of `label`. Let's look at the code which uses this pattern to search for the `startup_32` function in the Linux kernel:

```assembly
        leal	(BP_scratch+4)(%esi), %esp
        call	1f
1:      popl	%ebp
        subl	$1b, %ebp
```

As you remember from the previous part, the `esi` register contains the address of the [boot_params](https://github.com/torvalds/linux/blob/v4.16/arch/x86/include/uapi/asm/bootparam.h#L113) structure which was filled before we moved to the protected mode. The `boot_params` structure contains a special field `scratch` with an offset of `0x1e4`. This four byte field is a temporary stack for the `call` instruction. We set `esp` to the address four bytes after the `BP_scratch` field of the `boot_params` structure. We add `4` bytes to the base of the `BP_scratch` field because, as just described, it will be a temporary stack and the stack grows from the top to bottom in the `x86_64` architecture. So our stack pointer will point to the top of the temporary stack. Next, we can see the pattern that I've described above. We make a call to the `1f` label and pop the top of the stack onto `ebp`. This works because `call` stores the return address of the current function on the top of the stack. We now have the address of the `1f` label and can now easily get the address of the `startup_32` function. We just need to subtract the address of the label from the address we got from the stack:

```
startup_32 (0x0)     +-----------------------+
                     |                       |
                     |                       |
                     |                       |
                     |                       |
                     |                       |
                     |                       |
                     |                       |
                     |                       |
1f (0x0 + 1f offset) +-----------------------+ %ebp - real physical address
                     |                       |
                     |                       |
                     +-----------------------+
```

The `startup_32` function is linked to run at the address `0x0` and this means that `1f` has the address `0x0 + offset to 1f`, which is approximately `0x21` bytes. The `ebp` register contains the real physical address of the `1f` label. So, if we subtract `1f` from the `ebp` register, we will get the real physical address of the `startup_32` function. The Linux kernel [boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt) says the base of the protected mode kernel is `0x100000`. We can verify this with [gdb](https://en.wikipedia.org/wiki/GNU_Debugger). Let's start the debugger and add a breakpoint at the address of `1f`, which is `0x100021`. If this is correct we will see the value `0x100021` in the `ebp` register:

```
$ gdb
(gdb)$ target remote :1234
Remote debugging using :1234
0x0000fff0 in ?? ()
(gdb)$ br *0x100022
Breakpoint 1 at 0x100022
(gdb)$ c
Continuing.

Breakpoint 1, 0x00100022 in ?? ()
(gdb)$ i r
eax            0x18	0x18
ecx            0x0	0x0
edx            0x0	0x0
ebx            0x0	0x0
esp            0x144a8	0x144a8
ebp            0x100021	0x100021
esi            0x142c0	0x142c0
edi            0x0	0x0
eip            0x100022	0x100022
eflags         0x46	[ PF ZF ]
cs             0x10	0x10
ss             0x18	0x18
ds             0x18	0x18
es             0x18	0x18
fs             0x18	0x18
gs             0x18	0x18
```

If we execute the next instruction, `subl $1b, %ebp`, we will see:

```
(gdb) nexti
...
...
...
ebp            0x100000	0x100000
...
...
...
```

Ok, we've verified that the address of the `startup_32` function is `0x100000`. After we know the address of the `startup_32` label, we can prepare for the transition to [long mode](https://en.wikipedia.org/wiki/Long_mode). Our next goal is to setup the stack and verify that the CPU supports long mode and [SSE](http://en.wikipedia.org/wiki/Streaming_SIMD_Extensions).

Stack setup and CPU verification
--------------------------------------------------------------------------------

We can't set up the stack until we know where in memory the `startup_32` label is. If we imagine the stack as an array, the stack pointer register `esp` must point to the end of it. Of course, we can define an array in our code, but we need to know its actual address to configure the stack pointer correctly. Let's look at the code:

```assembly
	movl	$boot_stack_end, %eax
	addl	%ebp, %eax
	movl	%eax, %esp
```

The `boot_stack_end` label is also defined in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S) assembly source code file  and is located in the [.bss](https://en.wikipedia.org/wiki/.bss) section:

```assembly
	.bss
	.balign 4
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
boot_stack:
	.fill BOOT_STACK_SIZE, 1, 0
boot_stack_end:
```

First of all, we put the address of `boot_stack_end` into the `eax` register, so the `eax` register contains the address of `boot_stack_end` as it was linked, which is `0x0 + boot_stack_end`. To get the real address of `boot_stack_end`, we need to add the real address of the `startup_32` function. We've already found this address and put it into the `ebp` register. In the end, the  `eax` register will contain the real address of `boot_stack_end` and we just need to set the stack pointer to it.

After we have set up the stack, the next step is CPU verification. Since we are transitioning to `long mode`, we need to check that the CPU supports `long mode` and `SSE`. We will do this with a call to the `verify_cpu` function:

```assembly
	call	verify_cpu
	testl	%eax, %eax
	jnz	no_longmode
```

This function is defined in the [arch/x86/kernel/verify_cpu.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/kernel/verify_cpu.S) assembly file and just contains a couple of calls to the [cpuid](https://en.wikipedia.org/wiki/CPUID) instruction. This instruction is used to get information about the processor. In our case, it checks for `long mode` and `SSE` support and sets the `eax` register to `0` on success and `1` on failure.

If the value of `eax` is not zero, we jump to the `no_longmode` label which just stops the CPU with the `hlt` instruction while no hardware interrupt can happen:

```assembly
no_longmode:
1:
	hlt
	jmp     1b
```

If the value of the `eax` register is zero, everything is ok and we can continue.

Calculate the relocation address
--------------------------------------------------------------------------------

The next step is to calculate the relocation address for decompression if needed. First, we need to know what it means for a kernel to be `relocatable`. We already know that the base address of the 32-bit entry point of the Linux kernel is `0x100000`, but that is a 32-bit entry point. The default base address of the Linux kernel is determined by the value of the `CONFIG_PHYSICAL_START` kernel configuration option. Its default value is `0x1000000` or `16 MB`. The main problem here is that if the Linux kernel crashes, a kernel developer must have a `rescue kernel` for [kdump](https://www.kernel.org/doc/Documentation/kdump/kdump.txt) which is configured to load from a different address. The Linux kernel provides a special configuration option to solve this problem: `CONFIG_RELOCATABLE`. As we can read in the documentation of the Linux kernel:

```
This builds a kernel image that retains relocation information
so it can be loaded someplace besides the default 1MB.

Note: If CONFIG_RELOCATABLE=y, then the kernel runs from the address
it has been loaded at and the compile time physical address
(CONFIG_PHYSICAL_START) is used as the minimum location.
```

Now that we know where to start, let's get to it.

Reload the segments if needed
--------------------------------------------------------------------------------

As indicated above, we start in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/compressed/head_64.S) assembly source code file. We first see the definition of a special section attribute before the definition of the `startup_32` function:

```assembly
    __HEAD
    .code32
ENTRY(startup_32)
```

`__HEAD` is a macro defined in the [include/linux/init.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/init.h) header file and expands to the definition of the following section:

```C
#define __HEAD		.section	".head.text","ax"
```

Here, `.head.text` is the name of the section and `ax` is a set of flags. In our case, these flags show us that this section is [executable](https://en.wikipedia.org/wiki/Executable). In simple terms, this means that a Linux kernel with this option set can be booted from different addresses. Technically, this is done by compiling the decompressor as [position independent code](https://en.wikipedia.org/wiki/Position-independent_code). If we look at [arch/x86/boot/compressed/Makefile](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/Makefile), we can see that the decompressor is indeed compiled with the `-fPIC` flag:

```Makefile
KBUILD_CFLAGS += -fno-strict-aliasing -fPIC
```

When we are using position-independent code an address is obtained by adding the address field of the instruction to the value of the program counter. We can load code which uses such addressing from any address. That's why we had to get the real physical address of `startup_32`. Now let's get back to the Linux kernel code. Our current goal is to calculate an address where we can relocate the kernel for decompression. The calculation of this address depends on the `CONFIG_RELOCATABLE` kernel configuration option. Let's look at the code:

```assembly
#ifdef CONFIG_RELOCATABLE
	movl	%ebp, %ebx
	movl	BP_kernel_alignment(%esi), %eax
	decl	%eax
	addl	%eax, %ebx
	notl	%eax
	andl	%eax, %ebx
	cmpl	$LOAD_PHYSICAL_ADDR, %ebx
	jge	1f
#endif
	movl	$LOAD_PHYSICAL_ADDR, %ebx
```

Remember that the value of the `ebp` register is the physical address of the `startup_32` label. If the `CONFIG_RELOCATABLE` kernel configuration option is enabled during kernel configuration, we put this address in the `ebx` register, align it to a multiple of `2MB` and compare it with the result of the `LOAD_PHYSICAL_ADDR` macro. `LOAD_PHYSICAL_ADDR` is defined in the [arch/x86/include/asm/boot.h](https://github.com/torvalds/linux/blob/v4.16/arch/x86/include/asm/boot.h) header file and it looks like this:

```C
#define LOAD_PHYSICAL_ADDR ((CONFIG_PHYSICAL_START \
				+ (CONFIG_PHYSICAL_ALIGN - 1)) \
				& ~(CONFIG_PHYSICAL_ALIGN - 1))
```

As we can see it just expands to the aligned `CONFIG_PHYSICAL_ALIGN` value which represents the physical address where the kernel will be loaded. After comparing `LOAD_PHYSICAL_ADDR` and the value of the `ebx` register, we add the offset from `startup_32` where we will decompress the compressed kernel image. If the `CONFIG_RELOCATABLE` option is not enabled during kernel configuration, we just add `z_extract_offset` to the default address where the kernel is loaded.

After all of these calculations, `ebp` will contain the address where we loaded the kernel and `ebx` will contain the address where the decompressed kernel will be relocated. But that is not the end. The compressed kernel image should be moved to the end of the decompression buffer to simplify calculations regarding where the kernel will be located later. For this:

```assembly
1:
    movl	BP_init_size(%esi), %eax
    subl	$_end, %eax
    addl	%eax, %ebx
```

we put the value from the `boot_params.BP_init_size` field (or the kernel setup header value from `hdr.init_size`) in the `eax` register. The `BP_init_size` field contains the larger of the compressed and uncompressed [vmlinux](https://en.wikipedia.org/wiki/Vmlinux) sizes. Next we subtract the address of the `_end` symbol from this value and add the result of the subtraction to the `ebx` register which will store the base address for kernel decompression.

Preparation before entering long mode
--------------------------------------------------------------------------------

After we get the address to relocate the compressed kernel image to, we need to do one last step before we can transition to 64-bit mode. First, we need to update the [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table) with 64-bit segments because a relocatable kernel is runnable at any address below 512GB:

```assembly
	addl	%ebp, gdt+2(%ebp)
	lgdt	gdt(%ebp)
```

Here we adjust the base address of the Global Descriptor table to the address where we actually loaded the kernel and load the `Global Descriptor Table` with the `lgdt` instruction.

To understand the magic with `gdt` offsets we need to look at the definition of the `Global Descriptor Table`. We can find its definition in the same source code [file](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S):

```assembly
	.data
gdt64:
	.word	gdt_end - gdt
	.long	0
	.word	0
	.quad   0
gdt:
	.word	gdt_end - gdt
	.long	gdt
	.word	0
	.quad	0x00cf9a000000ffff	/* __KERNEL32_CS */
	.quad	0x00af9a000000ffff	/* __KERNEL_CS */
	.quad	0x00cf92000000ffff	/* __KERNEL_DS */
	.quad	0x0080890000000000	/* TS descriptor */
	.quad   0x0000000000000000	/* TS continued */
gdt_end:
```

We can see that it is located in the `.data` section and contains five descriptors: the first is a `32-bit` descriptor for the kernel code segment, a `64-bit` kernel segment, a kernel data segment and two task descriptors.

We already loaded the `Global Descriptor Table` in the previous [part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-3.md), and now we're doing almost the same here, but we set descriptors to use `CS.L = 1` and `CS.D = 0` for execution in `64` bit mode. As we can see, the definition of the `gdt` starts with a two byte value: `gdt_end - gdt` which represents the address of the last byte in the `gdt` table or the table limit. The next four bytes contain the base address of the `gdt`.

After we have loaded the `Global Descriptor Table` with the `lgdt` instruction, we must enable [PAE](http://en.wikipedia.org/wiki/Physical_Address_Extension) by putting the value of the `cr4` register into `eax`, setting the 5th bit and loading it back into `cr4`:

```assembly
	movl	%cr4, %eax
	orl	$X86_CR4_PAE, %eax
	movl	%eax, %cr4
```

Now we are almost finished with the preparations needed to move into 64-bit mode. The last step is to build page tables, but before that, here is some information about long mode.

Long mode
--------------------------------------------------------------------------------

[Long mode](https://en.wikipedia.org/wiki/Long_mode) is the native mode for [x86_64](https://en.wikipedia.org/wiki/X86-64) processors. First, let's look at some differences between `x86_64` and `x86`.

`64-bit` mode provides the following features:

* 8 new general purpose registers from `r8` to `r15`
* All general purpose registers are 64-bit now
* A 64-bit instruction pointer - `RIP`
* A new operating mode - Long mode;
* 64-Bit Addresses and Operands;
* RIP Relative Addressing (we will see an example of this in the coming parts).

Long mode is an extension of the legacy protected mode. It consists of two sub-modes:

* 64-bit mode;
* compatibility mode.

To switch into `64-bit` mode we need to do the following things:

* Enable [PAE](https://en.wikipedia.org/wiki/Physical_Address_Extension);
* Build page tables and load the address of the top level page table into the `cr3` register;
* Enable `EFER.LME`;
* Enable paging.

We already enabled `PAE` by setting the `PAE` bit in the `cr4` control register. Our next goal is to build the structure for [paging](https://en.wikipedia.org/wiki/Paging). We will discuss this in the next paragraph.

Early page table initialization
--------------------------------------------------------------------------------

We already know that before we can move into `64-bit` mode, we need to build page tables. Let's look at how the early `4G` boot page tables are built.

**NOTE: I will not describe the theory of virtual memory here. If you want to know more about virtual memory, check out the links at the end of this part.**

The Linux kernel uses `4-level` paging, and we generally build 6 page tables:

* One `PML4` or `Page Map Level 4` table with one entry;
* One `PDP` or `Page Directory Pointer` table with four entries;
* Four Page Directory tables with a total of `2048` entries.

Let's look at how this is implemented. First, we clear the buffer for the page tables in memory. Every table is `4096` bytes, so we need clear a `24` kilobyte buffer:

```assembly
	leal	pgtable(%ebx), %edi
	xorl	%eax, %eax
	movl	$(BOOT_INIT_PGT_SIZE/4), %ecx
	rep	stosl
```

We put the address of `pgtable` with an offset of `ebx` (remember that `ebx` points to the location in memory where the kernel will be decompressed later) into the `edi` register, clear the `eax` register and set the `ecx` register to `6144`.

The `rep stosl` instruction will write the value of `eax` to the memory location where `edi` points to, increment `edi` by `4`, and decrement `ecx` by `1`. This operation will be repeated while the value of the `ecx` register is greater than zero. That's why we put `6144` or `BOOT_INIT_PGT_SIZE/4` in `ecx`.

`pgtable` is defined at the end of the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S) assembly file:

```assembly
	.section ".pgtable","a",@nobits
	.balign 4096
pgtable:
	.fill BOOT_PGT_SIZE, 1, 0
```

As we can see, it is located in the `.pgtable` section and its size depends on the `CONFIG_X86_VERBOSE_BOOTUP` kernel configuration option:

```C
#  ifdef CONFIG_X86_VERBOSE_BOOTUP
#   define BOOT_PGT_SIZE	(19*4096)
#  else /* !CONFIG_X86_VERBOSE_BOOTUP */
#   define BOOT_PGT_SIZE	(17*4096)
#  endif
# else /* !CONFIG_RANDOMIZE_BASE */
#  define BOOT_PGT_SIZE		BOOT_INIT_PGT_SIZE
# endif
```

After we have a buffer for the `pgtable` structure, we can start to build the top level page table - `PML4` - with:

```assembly
	leal	pgtable + 0(%ebx), %edi
	leal	0x1007 (%edi), %eax
	movl	%eax, 0(%edi)
```

Here again, we put the address of `pgtable` relative to `ebx` or in other words relative to address of `startup_32` in the `edi` register. Next, we put this address with an offset of `0x1007` into the `eax` register. `0x1007` is the result of adding the size of the `PML4` table which is `4096` or `0x1000` bytes with `7`. The `7` here represents the flags associated with the `PML4` entry. In our case, these flags are `PRESENT+RW+USER`. In the end, we just write the address of the first `PDP` entry to the `PML4` table.

In the next step we will build four `Page Directory` entries in the `Page Directory Pointer` table with the same `PRESENT+RW+USE` flags:

```assembly
	leal	pgtable + 0x1000(%ebx), %edi
	leal	0x1007(%edi), %eax
	movl	$4, %ecx
1:  movl	%eax, 0x00(%edi)
	addl	$0x00001000, %eax
	addl	$8, %edi
	decl	%ecx
	jnz	1b
```

We set `edi` to the base address of the page directory pointer which is at an offset of `4096` or `0x1000` bytes from the `pgtable` table and `eax` to the address of the first page directory pointer entry. We also set `ecx` to `4` to act as a counter in the following loop and write the address of the first page directory pointer table entry to the `edi` register. After this, `edi` will contain the address of the first page directory pointer entry with flags `0x7`. Next we calculate the address of the following page directory pointer entries — each entry is `8` bytes — and write their addresses to `eax`. The last step in building the paging structure is to build the `2048` page table entries with `2-MByte` pages:

```assembly
	leal	pgtable + 0x2000(%ebx), %edi
	movl	$0x00000183, %eax
	movl	$2048, %ecx
1:  movl	%eax, 0(%edi)
	addl	$0x00200000, %eax
	addl	$8, %edi
	decl	%ecx
	jnz	1b
```

Here we do almost the same things that we did in the previous example, all entries are associated with these flags - `$0x00000183` - `PRESENT + WRITE + MBZ`. In the end, we will have a page table with `2048` `2-MByte` pages, which represents a 4 Gigabyte block of memory:

```python
>>> 2048 * 0x00200000
4294967296
```

Since we've just finished building our early page table structure which maps `4` gigabytes of memory, we can put the address of the high-level page table - `PML4` - into the `cr3` control register:

```assembly
	leal	pgtable(%ebx), %eax
	movl	%eax, %cr3
```

That's all. We are now prepared to transition to long mode.

The transition to 64-bit mode
--------------------------------------------------------------------------------

First of all we need to set the `EFER.LME` flag in the [MSR](http://en.wikipedia.org/wiki/Model-specific_register) to `0xC0000080`:

```assembly
	movl	$MSR_EFER, %ecx
	rdmsr
	btsl	$_EFER_LME, %eax
	wrmsr
```

Here we put the `MSR_EFER` flag (which is defined in [arch/x86/include/asm/msr-index.h](https://github.com/torvalds/linux/blob/v4.16/arch/x86/include/asm/msr-index.h)) in the `ecx` register and execute the `rdmsr` instruction which reads the [MSR](http://en.wikipedia.org/wiki/Model-specific_register) register. After `rdmsr` executes, the resulting data is stored in `edx:eax` according to the `MSR` register specified in `ecx`. We check the current `EFER_LME` bit, transfer it into the carry flag and update the bit, all with the `btsl` instruction. Then we write data from `edx:eax` back to the `MSR` register with the `wrmsr` instruction.

In the next step, we push the address of the kernel segment code to the stack (we defined it in the GDT) and put the address of the `startup_64` routine in `eax`.

```assembly
	pushl	$__KERNEL_CS
	leal	startup_64(%ebp), %eax
```

After this we push `eax` to the stack and enable paging by setting the `PG` and `PE` bits in the `cr0` register:

```assembly
	pushl	%eax
    movl	$(X86_CR0_PG | X86_CR0_PE), %eax
	movl	%eax, %cr0
```

We then execute the `lret` instruction:

```assembly
lret
```

Remember that we pushed the address of the `startup_64` function to the stack in the previous step. The CPU extracts `startup_64`'s address from the stack and jumps there.

After all of these steps we're finally in 64-bit mode:

```assembly
	.code64
	.org 0x200
ENTRY(startup_64)
....
....
....
```

That's all!

Conclusion
--------------------------------------------------------------------------------

This is the end of the fourth part of the Linux kernel booting process. If you have any questions or suggestions, ping me on twitter [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com) or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).

In the next part, we will learn about many things, including how kernel decompression works.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you find any mistakes please send a PR to [linux-insides](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

* [Protected mode](http://en.wikipedia.org/wiki/Protected_mode)
* [Intel® 64 and IA-32 Architectures Software Developer’s Manual 3A](http://www.intel.com/content/www/us/en/processors/architectures-software-developer-manuals.html)
* [GNU linker](http://www.eecs.umich.edu/courses/eecs373/readings/Linker.pdf)
* [SSE](http://en.wikipedia.org/wiki/Streaming_SIMD_Extensions)
* [Paging](http://en.wikipedia.org/wiki/Paging)
* [Model specific register](http://en.wikipedia.org/wiki/Model-specific_register)
* [.fill instruction](http://www.chemie.fu-berlin.de/chemnet/use/info/gas/gas_7.html)
* [Previous part](https://github.com/0xAX/linux-insides/blob/v4.16/Booting/linux-bootstrap-3.md)
* [Paging on osdev.org](http://wiki.osdev.org/Paging)
* [Paging Systems](https://www.cs.rutgers.edu/~pxk/416/notes/09a-paging.html)
* [x86 Paging Tutorial](http://www.cirosantilli.com/x86-paging/)
