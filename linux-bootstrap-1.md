GNU/Linux kernel internals
================================================================================

Linux kernel booting process. Part 1.
--------------------------------------------------------------------------------

If you read my previous [blog posts](http://0xax.blogspot.com/search/label/asm), you'll see that some time ago I started to get involved with low-level programming. I wrote some posts about x86_64 assembly programming for Linux. At the same time, I started to dive into the GNU/Linux kernel source code. It is very interesting for me to understand how low-level things work, how programs run on my computer, how they are located in memory, how the kernel manages processes and memory, how the network stack works on low-level and many many other things. I decided to write yet another series of posts about the GNU/Linux kernel for the **x86_64** processors.

Note that I'm not a professional kernel hacker, and I don't write code for the kernel at work. It's just a hobby. I just like low-level stuff, and it is interesting for me to see how these things work. So if you notice anything confusing, or if you have any questions/remarks, ping me on twitter [0xAX](https://twitter.com/0xAX), drop me an [email](anotherworldofworld@gmail.com) or just create an [issue](https://github.com/0xAX/linux-internals/issues/new). I appreciate it. All posts will also be accessible at[linux-internals](https://github.com/0xAX/linux-internals) and if you find something wrong with my English or post content, feel free to send pull request.


*Note that it isn't official documentation, just learning and knowledge sharing.*

**Required knowledge**

* Understanding C code
* Understanding assembly code (AT&T syntax)

Anyway if you just started to learn some tools, I will try to explain some parts during this and the following posts. Ok, enough with the introductions. Lets dive into kernel and low-level stuff.

All code is for kernel - 3.18, if there come about any changes, I will update the posts.

Magic power button, what's next?
--------------------------------------------------------------------------------

Despite that it is a series of posts about the Linux kernel, we will not start with kernel code (at least in this paragraph). Ok, so you pressed the magic power button on your laptop or desktop computer and it started up. After the motherboard sends signal to the [power supply](http://en.wikipedia.org/wiki/Power_supply), it provides the computer with the proper amount of electricity. Once the motherboard receives the [power good signal](http://en.wikipedia.org/wiki/Power_good_signal), it tries to run the CPU. The CPU then resets all of the leftover data in its register and sets up predefined values for every register.

[80386](http://en.wikipedia.org/wiki/Intel_80386) and later CPUs define the following predifined data in CPU registers after computer resets:

```
IP          0xfff0
CS selector 0xf000
CS base     0xffff0000
```

Processor begins working in the [real mode](http://en.wikipedia.org/wiki/Real_mode) now and we need to deviate a little to understand memory segmentation in this mode. Real mode is supported in all x86 compatible processors from the [8086](http://en.wikipedia.org/wiki/Intel_8086) to the modern Intel CPUs. 8086 processor had a 20-bit address bus; this means that it could work with the 0th address space all the way up to the 2^20th address space (1 MB). However, it has only 16-bit registers, and with 16-bit registers, the  maximum address is 2^16 or 0xffff (640 KB). To use all of the address space, it uses memory segmentation. All memory is divided into small fixed-size segments of 65535 bytes or 64 KB each. Since we cannot address memory behind 640 KB with a 16-bit register, a newer method was used to achieve this. The address consists of two parts: the beginning address of the segment and the offset from the beginning of this segment. For getting physical address of memory, we need to multiply segment part by 16 and add the offset, as shown below:

```
PhysicalAddress = Segment * 16 + Offset
```

For example `CS:IP` is `0x2000:0x0010`; its physical address will be:

```python
>>> hex((0x2000 << 4) + 0x0010)
'0x20010'
```

But if we take the biggest segment part and offset: `0xffff:0xffff`, it will be:

```python
>>> hex((0xffff << 4) + 0xffff)
'0x10ffef'
```

which is 65519 bytes over the first megabyte. Since only one megabyte accessible in real mode, `0x10ffef` becomes `0x00ffef` with disabled [A20](http://en.wikipedia.org/wiki/A20_line).

Ok, now we know about real mode and memory addressing, let's back to registers values after reset.

`CS` register has two parts: the visible segment selector and hidden base address. We know the predefined values of `CS` base and `IP`, so our logical address will be:

```
0xffff0000:0xfff0
```

which we can translate to the physical address:

```python
>>> hex((0xffff000 << 4) + 0xfff0)
'0xfffffff0'
```

We get `fffffff0` which is 4GB - 16 bytes. This point is a - [Reset vector](http://en.wikipedia.org/wiki/Reset_vector). TThe first instruction exists at this memory location, which the CPU inteprets after reset. It contains the [jump](http://en.wikipedia.org/wiki/JMP_%28x86_instruction%29) instruction which usually points to the BIOS entry point. For example if we look into the [coreboot](http://www.coreboot.org/) source code, we see:

```assembly
	.section ".reset"
	.code16
.globl	reset_vector
reset_vector:
	.byte  0xe9
	.int   _start - ( . + 2 )
	...
```

We can see here that the jump instruction [opcode](http://ref.x86asm.net/coder32.html#xE9) - 0xe9 to the address `_start - ( . + 2)`. And we can see that `reset` section is 16 bytes and starts at `0xfffffff0`:

```
SECTIONS {
	_ROMTOP = 0xfffffff0;
	. = _ROMTOP;
	.reset . : {
		*(.reset)
		. = 15 ;
		BYTE(0x00);
	}
}
```

Now the BIOS has begun its work, and, after all the required initializations and hardware checking, it loads the operating system. The BIOS tries to find bootable device, which contains the boot sector. Boot sector is a first sector on device (512 bytes) and contains sequence of `0x55` and `0xaa` at the **511**th and **512**th byte. For example:

```assembly
[BITS 16]
[ORG  0x7c00]

jmp boot

boot:
    mov ah, 0x0e
    mov bh, 0x00
    mov bl, 0x07
    mov al, !

	int 0x10
    jmp $

times 510-($-$$) db 0
db 0xaa
db 0x55
```

Build and run this code with using the following command:

```
nasm -f bin boot.nasm && qemu-system-x86_64 boot
```

We will see:

![Simple bootloader which prints only `!`](http://oi60.tinypic.com/2qbwup0.jpg)

In this example we can see that this code will be executed in 16-bit real mode and started at 0x7c00 in memory. After the start it calls [0x10](http://www.ctyme.com/intr/rb-0106.htm) interruption which just prints `!` symbol. It fills rest of the 510 bytes with zeros and ends it with two magic bytes 0xaa and 0x55.

In the real world, the bootloader starts at the same point, ends with `0xaa55` bytes, but reads kernel code from the device instead, loading it to memory, parsing it and passing the necessary boot parameters to the kernel, among other required tasks... intead printing one symbol :) Ok, so, from this moment, the BIOS has officially handed control to the operating system bootloader and we can go ahead.

**NOTE**: as you can read above, the CPU is in real mode. In real mode, for calculating physical address of memory, it uses the following form:

```
PhysicalAddress = Segment * 16 + Offset
```

As i wrote above. But we have only 16-bit general purpose registers. The maximum value of 16 bit register is: `0xffff`; So if we take the biggest values, it will be:

```python
>>> hex((0xffff * 16) + 0xffff)
'0x10ffef'
```

Where `0x10ffef` is equal to `1mb + 64KB - 16b`. But the [8086](http://en.wikipedia.org/wiki/Intel_8086) processor, which was first processor with real mode had 20 address lines, but `20^2 = 1048576.0` which is 1MB; this means that the amount of memory actually available was 1MB.

The general real mode memory map is:

```
0x00000000 - 0x000003FF - Real Mode Interrupt Vector Table
0x00000400 - 0x000004FF - BIOS Data Area
0x00000500 - 0x00007BFF - Unused
0x00007C00 - 0x00007DFF - Our Bootloader
0x00007E00 - 0x0009FFFF - Unused
0x000A0000 - 0x000BFFFF - Video RAM (VRAM) Memory
0x000B0000 - 0x000B7777 - Monochrome Video Memory
0x000B8000 - 0x000BFFFF - Color Video Memory
0x000C0000 - 0x000C7FFF - Video ROM BIOS
0x000C8000 - 0x000EFFFF - BIOS Shadow Area
0x000F0000 - 0x000FFFFF - System BIOS
```

But stop; at the beginning of this post, I had written that the first instruction executed by the CPU is located by `0xfffffff0` address; however, it's much bigger than `0xffff` (1MB). How can the CPU access *this* in real mode? As I write and you can read about in [coreboot](http://www.coreboot.org/Developer_Manual/Memory_map) documentation:

```
0xFFFE_0000 - 0xFFFF_FFFF: 128 kilobyte ROM mapped into address space
```

At the start, the BIOS is not located in RAM, but in ROM.

Bootloader
--------------------------------------------------------------------------------

Now, the BIOS has transferred control to the operating system's bootloader and it needs to load the operating system into memory. There are a couple of bootloaders which can boot linux like: [Grub2](http://www.gnu.org/software/grub/), [syslinux](http://www.syslinux.org/wiki/index.php/The_Syslinux_Project) etc... Linux kernel has a [Boot protocol](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt) which describes how to load the linux kernel into memory.

Let us briefly consider how grub loads linux: GRUB2 execution starts from `grub-core/boot/i386/pc/boot.S`. It starts to load from the device, its own kernel (**not to be confused with the linux kernel**) and executes `grub_main` after successfully loading.

`grub_main` initializes the console, gets the base address for the modules, sets the root device, loads/parses the grub configuration file etc... In the end of execution `grub_main` moves grub to normal mode. `grub_normal_execute` (from `grub-core/normal/main.c`) completes the final preparation steps and shows the menu for selecting the operating system. When we pressed on one of grub's menu entry, `grub_menu_execute_entry` begins to be executed, which executes grub's `boot` command. Finally, it starts to boot into the operating system.

As we can read in the kernel boot protocol, the bootloader must read and fill some fields of the kernel setup header which starts at `0x01f1` offset from the kernel setup code. Kernel header [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S) starts from:

```assembly
	.globl hdr
hdr:
	setup_sects: .byte 0
	root_flags:  .word ROOT_RDONLY
	syssize:     .long 0
	ram_size:    .word 0
	vid_mode:    .word SVGA_MODE
	root_dev:    .word 0
	boot_flag:   .word 0xAA55
```

The bootloader must fill this and the rest of the headers (only marked as `write` in the linux boot protocol, for example [this](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt#L354)) with information gotten from the command line or calculated values. We will delve into the description and explanation of all the fields of the kernel setup header, and instead will get back to it when kernel will use it. However, you can find the descriptions of any field in the [boot protocol](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt#L156).

As we can see in kernel boot protocol, memory map will be following after the kernel loads:

```shell
         | Protected-mode kernel  |
100000   +------------------------+
         | I/O memory hole        |
0A0000   +------------------------+
         | Reserved for BIOS      | Leave as much as possible unused
         ~                        ~
         | Command line           | (Can also be below the X+10000 mark)
X+10000  +------------------------+
         | Stack/heap             | For use by the kernel real-mode code.
X+08000  +------------------------+
         | Kernel setup           | The kernel real-mode code.
         | Kernel boot sector     | The kernel legacy boot sector.
       X +------------------------+
         | Boot loader            | <- Boot sector entry point 0x7C00
001000   +------------------------+
         | Reserved for MBR/BIOS  |
000800   +------------------------+
         | Typically used by MBR  |
000600   +------------------------+
         | BIOS use only          |
000000   +------------------------+

```

So after the bootloader has transferred control to the kernel, it starts somewhere at:

```
0x1000 + X + sizeof(KernelBootSector) + 1
```

where `X` is the address the kernel's bootsector loaded. In my case `X` is `0x10000` (), which we can see in the memory dump:

![kernel first address](http://oi57.tinypic.com/16bkco2.jpg)

Ok, the bootloader has successfully loaded the linux kernel into memory, filled the required header fields and jumped to it. Now we can move directly to the kernel setup code.

Start of kernel setup
--------------------------------------------------------------------------------

Finally we are in the kernel. Technically the kernel hasn't run yet; first of all we need to setup the kernel, memory manager, process manager etc... Kernel setup execution starts from [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S) at [_start](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L293). It is little strange when initially looked at, but there are many instructions before it. Actually....

A long time ago, linux had its own bootloader, but now if you will run for example:

```
qemu-system-x86_64 vmlinuz-3.18-generic
```

You will see:

![Try vmlinuz in qemu](http://oi60.tinypic.com/r02xkz.jpg)

Actually `header.S` starts from [MZ](http://en.wikipedia.org/wiki/DOS_MZ_executable) (see image above), error message printing and following [PE](http://en.wikipedia.org/wiki/Portable_Executable) header:

```assembly
#ifdef CONFIG_EFI_STUB
# "MZ", MS-DOS header
.byte 0x4d
.byte 0x5a
#endif
...
...
...
pe_header:
	.ascii "PE"
	.word 0
```

It needs for loading operating system with [UEFI](http://en.wikipedia.org/wiki/Unified_Extensible_Firmware_Interface). Here we will not see how it works (will look on it in the next parts).

So actual kernel setup entry point is:

```
// header.S line 292
.globl _start
_start:
```

Bootloader (grub2 and others) knows this point (`0x200` offset from `MZ`) and makes a jump directly to it, despite the fact that `header.S` starts from the `.bstext` section which prints error message:

```
//
// arch/x86/boot/setup.ld
//
. = 0;                    // current position
.bstext : { *(.bstext) }  // put .bstext section to position 0
.bsdata : { *(.bsdata) }
```

So the kernel setup entry point is:

```assembly
	.globl _start
_start:
	.byte 0xeb
	.byte start_of_setup-1f
1:
	//
	// rest of the header
	//
```

Here we can see the `jmp` instruction jump from opcode - `0xeb` to the `start_of_setup-1f` point. `Nf` notation means following: `2f` refers to the next local `2:` label. In our case it is label `1` which goes right after the jump. It contains the rest of the setup [header](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt#L156), and right after the setup header we can see the `.entrytext` section which starts at the `start_of_setup` label.

Actually it's the first code which executes beside previous jump instruction. After the kernel setup got control from bootloader, the first `jmp` instruction is located at `0x200` (first 512 bytes) offset from the start of the kernel's real mode. This we can read in linux kernel's boot protocol and also see in the grub2 source code:

```C
  state.gs = state.fs = state.es = state.ds = state.ss = segment;
  state.cs = segment + 0x20;
```

It means that segment registers will have the following values after the kernel setup starts to work:

```
fs = es = ds = ss = 0x1000
cs = 0x1020
```

for my case when the kernel is loaded at `0x10000`.

After the jump to `start_of_setup`, it needs to do following things:

* Be sure that all values of all segment registers are equal
* Setup correct stack if need be
* Setup [bss](http://en.wikipedia.org/wiki/.bss)
* Jump to C code at [main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c)

Let's look at the implementation.

Segement registers align
--------------------------------------------------------------------------------

First of all it ensures that `ds` and `es` segment registers points to the same address and enables interruptions with the `sti` instruction:

```assembly
	movw	%ds, %ax
	movw	%ax, %es
	sti
```

As i wrote above, grub2 loads the kernel setup code at `0x10000` address and `cs` at `0x0x1020` because execution doesn't start from the start of the file, but rather from:

```
_start:
	.byte 0xeb
	.byte start_of_setup-1f
```

jump, which is 512 bytes offset from the [4d 5a](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L47). Also, it needs to align `cs` from 0x10200 to 0x10000 as do all other segement registers. After we setup stack:

```assembly
	pushw	%ds
	pushw	$6f
	lretw
```

push `ds` value to stack, and the address of the [6](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L494) label and execute the `lretw` instruction. When we call `lretw`, it loads the address of `6` label to the [instruction pointer](http://en.wikipedia.org/wiki/Program_counter) register and `cs` with value of `ds`. After this, we see that `ds` and `cs` have the same values.

Stack setup
--------------------------------------------------------------------------------

Actually almost all of the setup code is preparation for the C language environment in the real mode. The next [step](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L467) is checking the `ss` register's value and making the correct stack if `ss` is wrong:

```assembly
	movw	%ss, %dx
	cmpw	%ax, %dx
	movw	%sp, %dx
	je	2f
```

Generally, it can be 3 different cases:

* `ss` has valid value 0x10000 (as do all another segment registers besides `cs`)
* `ss` is invalid and `CAN_USE_HEAP` flag is set     (see below)
* `ss` is invalid and `CAN_USE_HEAP` flag is not set (see below)

Let's look on all of these cases:

1. `ss` has a correct address (0x10000). If this is the case, we go to the [2](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L481) label:

```
2: 	andw	$~3, %dx
	jnz	3f
	movw	$0xfffc, %dx
3:  movw	%ax, %ss
	movzwl %dx, %esp
	sti
```

Here we can see aligning of `dx` (contains `sp` given by bootloader) to 4 bytes and checking that it is not zero. If it is zero we put `0xfffc` (4 byte aligned address before maximum segment size - 64 KB) to `dx`. If it is zero we continue to use the value of `sp` given by the bootloader (0xf7f4 in my case). After this we put the `ax` value to `ss` which stores the correct segment address `0x10000` and sets up the correct `sp` value. After it we have the corrected stack:

![stack](http://oi58.tinypic.com/16iwcis.jpg)

2. In the second case (`ss` != `ds`), first of all put [_end](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld#L52) (address of end of setup code) value at the `dx`. And check the `loadflags` header field with `testb` instruction to determine whether we can use the heap or not. [loadflags](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L321) is a bitmask header which is defined as:

```C
#define LOADED_HIGH	    (1<<0)
#define QUIET_FLAG	    (1<<5)
#define KEEP_SEGMENTS	(1<<6)
#define CAN_USE_HEAP	(1<<7)
```

And as we read in the boot protocol:

```
Field name:	loadflags

  This field is a bitmask.

  Bit 7 (write): CAN_USE_HEAP
	Set this bit to 1 to indicate that the value entered in the
	heap_end_ptr is valid.  If this field is clear, some setup code
	functionality will be disabled.
```

If `CAN_USE_HEAP` bit is set, put `heap_end_ptr` to `dx` which points to `_end` and add `STACK_SIZE` (minimal stack size - 512 bytes) to it. After this if `dx` is not equal, carry jump to the `2` (it will be not carry, dx = _end + 512) label as is in the previous case and make a correct stack.

![stack](http://oi62.tinypic.com/dr7b5w.jpg)

3. The last case, when `CAN_USE_HEAP` is not set, we just use a minimal stack from `_end` to `_end + STACK_SIZE`:

![minimal stack](http://oi60.tinypic.com/28w051y.jpg)

Bss setup
--------------------------------------------------------------------------------

Last two steps before we can jump to see code is the need to setup [bss](http://en.wikipedia.org/wiki/.bss) and check magic signature. Signature checking:

```assembly
cmpl	$0x5a5aaa55, setup_sig
jne	setup_bad
```

just consists of the comparing of [setup_sig](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld#L39) and `0x5a5aaa55` number, and if they are not equal, jump to error printing.

Ok now we have the correct segment registers, stack, and we need only to setup BSS and jump to C code. The BSS section used is for storing statically allocated uninitialized data. Here is the code:

```assembly
	movw	$__bss_start, %di
	movw	$_end+3, %cx
	xorl	%eax, %eax
	subw	%di, %cx
	shrw	$2, %cx
	rep; stosl
```

First of all we put [__bss_start](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld#L47) address to `di` and `_end + 3` (+3 - align to 4 bytes) to `cx`. Clear the `eax` register with the `xor` instruction and calculate the size of BSS section (put to `cx`). Divide `cx` by 4 and repeat `cx` times, the `stosl` instruction which stores the value of `eax` (it is zero) and increase `di` by the size of `eax`. In this way, we write zeros from `__bss_start` to `_end`:

![bss](http://oi59.tinypic.com/29m2eyr.jpg)

Jump to main
--------------------------------------------------------------------------------

That's all! We have our stack and BSS set up. Now we can jump to the `main` C function:

```assembly
	call main
```

which is in [arch/x86/boot/main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c). What will be there? We will see it in the next part.

Conclusion
--------------------------------------------------------------------------------

It is the end of the first part about the Linux kernel internals. If you have any questions or suggestions, ping me on twitter [0xAX](https://twitter.com/0xAX), drop me an [email](anotherworldofworld@gmail.com) or just create an [issue](https://github.com/0xAX/linux-internals/issues/new). In next part we will see our first C code which executes during the linux kernel setup, implementation of memory routines as memset, memcpy, `earlyprintk` implementation and early console initialization and much more. Stay tuned!

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you will find any mistakes please send me PR to [linux-internals](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

  * [Intel 80386 programmer's reference manual 1986](http://css.csail.mit.edu/6.858/2014/readings/i386.pdf)
  * [Minimal Boot Loader for Intel® Architecture](https://www.cs.cmu.edu/~410/doc/minimal_boot.pdf)
  * [8086](http://en.wikipedia.org/wiki/Intel_8086)
  * [80386](http://en.wikipedia.org/wiki/Intel_80386)
  * [Reset vector](http://en.wikipedia.org/wiki/Reset_vector)
  * [Real mode](http://en.wikipedia.org/wiki/Real_mode)
  * [Linux kernel boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt)
  * [CoreBoot developer manual](http://www.coreboot.org/Developer_Manual)
  * [Ralf Brown's Interrupt List](http://www.ctyme.com/intr/int.htm)
  * [Power supply](http://en.wikipedia.org/wiki/Power_supply)
  * [Power good signal](http://en.wikipedia.org/wiki/Power_good_signal)
