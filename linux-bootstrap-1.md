GNU/Linux kernel internals
================================================================================

Linux kernel booting process. Part 1.
--------------------------------------------------------------------------------

If you have read my previous [blog posts](http://0xax.blogspot.com/search/label/asm), you can see that some time ago I started to get involved with low-level programming. I wrote some posts about x86_64 assembly programming for Linux. At the same time, I started to dive into the GNU/Linux kernel source code. It is very interesting for me to understand how low-level things work, how programs run on my computer, how they are located in memory, how the kernel manages processes and memory, how the network stack works on low-level and many many other things. I decided to write yet another series of posts about the GNU/Linux kernel for **x86_64**.

Note that I'm not a professional kernel hacker, and I don't write code for the kernel at work. It's just a hobby. I just like low-level stuff, and it is interesting for me to see how these things work. So if you notice anything confusing, or if you have any questions/remarks, ping me on twitter [0xAX](https://twitter.com/0xAX), drop me an [email](anotherworldofworld@gmail.com) or just create an [issue](https://github.com/0xAX/linux-internals/issues/new). I appreciate it. All posts will also be accessible at[linux-internals](https://github.com/0xAX/linux-internals) and if you find something wrong with my English or post content, feel free to send pull request.


*Note that it isn't official documentation, just learning and knowledge sharing.*

**Required knowledge**

* Understanding C code
* Understanding assembly code (AT&T syntax)

Anyway, if you just started to learn some tools, I will try to explain some parts during this and following posts. Ok, little introduction finished and now we can start to dive into kernel and low-level stuff.

All code is actual for kernel - 3.18, if there will be changes, I will update posts.

Magic power button, what's next?
--------------------------------------------------------------------------------

Despite that it is series of posts about linux kernel, we will not start from kernel code (at least in this paragraph). Ok, you pressed magic power button on your laptop or desktop computer and it started to work. After this mother board sends signal to the [power supply](http://en.wikipedia.org/wiki/Power_supply) which provides computer with the proper amount of electricity. Once motherboard receives [power good signal](http://en.wikipedia.org/wiki/Power_good_signal), it tries to run CPU. CPU resets all leftover data in its registers and sets up predefined values for every register.


[80386](http://en.wikipedia.org/wiki/Intel_80386) and later CPUs defines following predefined data in CPU registers after computer resets:

```
IP          0xfff0
CS selector 0xf000
CS base     0xffff0000
```

Processor works in the [real mode](http://en.wikipedia.org/wiki/Real_mode) now and we need to make a little retreat for understanding memory segmentation in this mode. Real mode is supported in all x86 compatible processors, from [8086](http://en.wikipedia.org/wiki/Intel_8086) to modern Intel 64bit CPUs. 8086 processor had 20 bit address bus, which means that it could work with 0-2^20 bytes address space (1 megabyte). But it had only 16 bit registers, and with 16 bit registers maximum address is 2^16 or 0xffff (640 KB). Memory segmentation was used to make use of all of the address space. All memory was divided into small fixed-size segments of 65535 bytes, or 64 KB. Since we can not address memory behind 640 KB with 16 bit register, another method to do it has been devised. Address consists of two parts: beginning address of segment and offset from the beginning of this segment. To get physical address in memory, we need to multiply segment part by 16 and add offset part:

```
PhysicalAddress = Segment * 16 + Offset
```

For example `CS:IP` is `0x2000:0x0010`, physical address will be:

```python
>>> hex((0x2000 << 4) + 0x0010)
'0x20010'
```

But if we take the biggest segment part and offset: `0xffff:0xffff`, it will be:

```python
>>> hex((0xffff << 4) + 0xffff)
'0x10ffef'
```

which is 65519 bytes over first megabyte. Since only one megabyte is accessible in real mode, `0x10ffef` becomes `0x00ffef` with disabled [A20](http://en.wikipedia.org/wiki/A20_line).

Ok, now we know about real mode and memory addressing, let's get back to register values after reset.

`CS` register has two parts: the visible segment selector and hidden base address. We know predefined `CS` base and `IP` value, so our logical address will be:

```
0xffff0000:0xfff0
```

which we can translate to the physical address::

```python
>>> hex((0xffff000 << 4) + 0xfff0)
'0xfffffff0'
```

We get `0xfffffff0` which is 4GB - 16 bytes. This point is the [Reset vector](http://en.wikipedia.org/wiki/Reset_vector). This is the memory location at which CPU expects to find the first instruction to execute after reset. It contains [jump](http://en.wikipedia.org/wiki/JMP_%28x86_instruction%29) instruction which usually points to the BIOS entry point. For example if we look in [coreboot](http://www.coreboot.org/) source code, we will see it:

```assembly
	.section ".reset"
	.code16
.globl	reset_vector
reset_vector:
	.byte  0xe9
	.int   _start - ( . + 2 )
	...
```

We can see here jump instruction [opcode](http://ref.x86asm.net/coder32.html#xE9) - 0xe9 to the address `_start - ( . + 2)`. And we can see that `reset` section is 16 bytes and starts at `0xfffffff0`:

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

Now BIOS started to work, after all initializations, hardware checking, it needs to load operating system. BIOS tries to find bootable device which contains boot sector. Boot sector is the first sector on device (512 bytes) and contains sequence of `0x55` and `0xaa` at 511 and 512 byte. For example:

```assembly
[BITS 16]
[ORG  0x7c00]

jmp boot

boot:
    mov al, '!'
    mov ah, 0x0e
    mov bh, 0x00
    mov bl, 0x07

    int 0x10
    jmp $

times 510-($-$$) db 0

db 0x55
db 0xaa
```

Build and run it with:

```
nasm -f bin boot.nasm && qemu-system-x86_64 boot
```

We will see:

![Simple bootloader which prints only `!`](http://oi60.tinypic.com/2qbwup0.jpg)

In this example we can see that this code will be executed in 16 bit real mode and will start at 0x7c00 in memory. After the start it calls [0x10](http://www.ctyme.com/intr/rb-0106.htm) interrupt which just prints `!` symbol. It fills rest of 510 bytes with zeros and finish with two magic bytes 0xaa and 0x55.

Real world boot loader starts at the same point, ends with `0xaa55` bytes, but reads kernel code from device, loads it to memory, parses and passes boot parameters to kernel and etc... instead of printing one symbol :) Ok, so, from this moment bios handed control to the operating system bootloader and we can go ahead.

**NOTE**: as you can read above CPU is still in real mode. In real mode for calculating physical address in memory uses following form:

```
PhysicalAddress = Segment * 16 + Offset
```

as I wrote above. But we have only 16 bit general purpose registers. The maximum value of 16 bit register is: `0xffff`; So if we take the biggest values, it will be:

```python
>>> hex((0xffff * 16) + 0xffff)
'0x10ffef'
```

Where `0x10ffef` is equal to `1mb + 64KB - 16b`. But [8086](http://en.wikipedia.org/wiki/Intel_8086) processor, which was first processor with real mode, had 20 bit address line, and `2^20 = 1048576.0` which is 1MB, so it means that actually available memory amount is 1MB.

General real mode memory map is:

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

But stop, at the beginning of post I wrote that first instruction executed by CPU located by `0xfffffff0` address, which is much bigger than `0xffff` (1MB). How can CPU access it in real mode? As I write about and you can read in [coreboot](http://www.coreboot.org/Developer_Manual/Memory_map) documentation:

```
0xFFFE_0000 - 0xFFFF_FFFF: 128 kilobyte ROM mapped into address space
```

At the start of execution BIOS is not in RAM, it is located in ROM.

Bootloader
--------------------------------------------------------------------------------

Now bios transfered control to the operating system bootlader and it needs to load operating system into the memory. There are a couple of bootloaders which can boot linux, like: [Grub2](http://www.gnu.org/software/grub/), [syslinux](http://www.syslinux.org/wiki/index.php/The_Syslinux_Project) and etc... Linux kernel has [Boot protocol](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt) which describes how to load linux kernel.

Let us briefly consider how grub loads linux. GRUB2 execution starts from `grub-core/boot/i386/pc/boot.S`. It starts to load from device its own kernel (not to be confused with linux kernel) and executes `grub_main` after successfully loading.

`grub_main` initializes console, gets base address for modules, sets root device, loads/parses grub configuration file, loads modules etc... At the end of execution `grub_main` moves grub to normal mode. `grub_normal_execute` (from `grub-core/normal/main.c`) completes last preparation and shows menu for selecting operating system. When we select one of grub menu entries, `grub_menu_execute_entry` begins to be executed, which executes grub `boot` command. It starts to boot operating system.

As we can read in the kernel boot protocol, bootloader must read and fill some fields of kernel setup header which starts at `0x01f1` offset from the kernel setup code. Kernel header [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S) starts from:

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

Bootloader must fill this and the rest of headers (only marked as `write` in the linux boot protocol, for example [this](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt#L354)) with values which it either got from command line or calculated. We will not see description and explanation of all fields of kernel setup header, we will get back to it when kernel uses it. Anyway, you can find description of any field in the [boot protocol](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt#L156).

As we can see in kernel boot protocol, memory map will be following after kernel loading:

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

So after bootloader transferred control to the kernel, it starts somewhere at:

```
0x1000 + X + sizeof(KernelBootSector) + 1
```

where `X` is the address kernel bootsector loaded. In my case `X` is `0x10000` (), we can see it in memory dump:

![kernel first address](http://oi57.tinypic.com/16bkco2.jpg)

Ok, bootloader loaded linux kernel into memory, filled header fields and jumped to it. Now we can move directly to the kernel setup code.

Start of kernel setup
--------------------------------------------------------------------------------

Finally we are in the kernel. Technically kernel didn't run yet, first of all we need to setup kernel, memory manager, process manager and etc... Kernel setup execution starts from [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S) at the [_start](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L293). It is little strange at the first look, there are many instructions before it. Actually....

Long time ago linux had its own bootloader, but now if you run for example:

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

It needs this for loading operating system with [UEFI](http://en.wikipedia.org/wiki/Unified_Extensible_Firmware_Interface). Here we will not see how it works (will look into it in the next parts).

So actual kernel setup entry point is:

```
// header.S line 292
.globl _start
_start:
```

Bootloader (grub2 and others) knows about this point (`0x200` offset from `MZ`) and makes a jump directly to this point, despite the fact that `header.S` starts from `.bstext` section which prints error message:

```
//
// arch/x86/boot/setup.ld
//
. = 0;                    // current position
.bstext : { *(.bstext) }  // put .bstext section to position 0
.bsdata : { *(.bsdata) }
```

So kernel setup entry point is:

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

Here we can see `jmp` instruction opcode - `0xeb` to the `start_of_setup-1f` point. `Nf` notation means following: `2f` refers to the next local `2:` label. In our case it is label `1` which goes right after jump. It contains rest of setup [header](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt#L156) and right after setup header we can see `.entrytext` section which starts at `start_of_setup` label.

Actually it's first code which starts to execute besides previous jump instruction. After kernel setup got the control from bootloader, first `jmp` instruction is located at `0x200` (first 512 bytes) offset from the start of kernel real mode. This we can read in linux kernel boot protocol and also see in grub2 source code:

```C
  state.gs = state.fs = state.es = state.ds = state.ss = segment;
  state.cs = segment + 0x20;
```

It means that segment registers will have following values after kernel setup starts to work:

```
fs = es = ds = ss = 0x1000
cs = 0x1020
```

for my case when kernel loaded at `0x10000`.

After jump to `start_of_setup`, needs to do following things:

* Be sure that all values of all segement registers are equal
* Setup correct stack if need
* Setup [bss](http://en.wikipedia.org/wiki/.bss)
* Jump to C code at [main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c)

Let's look at implementation.

Segement registers align
--------------------------------------------------------------------------------

First of all it ensures that `ds` and `es` segment registers point to the same address and enables interrupts with `sti` instruction:

```assembly
	movw	%ds, %ax
	movw	%ax, %es
	sti
```

As i wrote above, grub2 loads kernel setup code at `0x10000` address and `cs` at `0x0x1020` because execution doesn't start from the start of file, but from:

```
_start:
	.byte 0xeb
	.byte start_of_setup-1f
```

jump, which is 512 bytes offset from the [4d 5a](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L47). Also need to align `cs` from 0x10200 to 0x10000 as all other segment registers. After that we setup stack:

```assembly
	pushw	%ds
	pushw	$6f
	lretw
```

push `ds` value to stack, and address of [6](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L494) label and execute `lretw` instruction. When we call `lretw`, it loads address of `6` label to [instruction pointer](http://en.wikipedia.org/wiki/Program_counter) register and `cs` with value of `ds`. After it we will have `ds` and `cs` with the same values.

Stack setup
--------------------------------------------------------------------------------

Actually, almost all of the setup code is preparation for C language environment in the real mode. Next [step](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L467) is checking of `ss` register value and making of correct stack if `ss` is wrong:

```assembly
	movw	%ss, %dx
	cmpw	%ax, %dx
	movw	%sp, %dx
	je	2f
```

Generally, it can be 3 different cases:

* `ss` has valid value 0x10000 (as all other segment registers beside `cs`)
* `ss` is invalid and `CAN_USE_HEAP` flag is set     (see below)
* `ss` is invalid and `CAN_USE_HEAP` flag is not set (see below)

Let's look at all of these cases:

1. `ss` has a correct address (0x10000). In this case we go to [2](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L481) label:

```
2: 	andw	$~3, %dx
	jnz	3f
	movw	$0xfffc, %dx
3:  movw	%ax, %ss
	movzwl %dx, %esp
	sti
```

Here we can see aligning of `dx` (contains `sp` given by bootloader) to 4 bytes and checking that it is not zero. If it is zero we put `0xfffc` (4 byte aligned address before maximum segment size - 64 KB) to `dx`. If it is not zero we continue to use `sp` given by bootloader (0xf7f4 in my case). After this we put `ax` value to `ss` which stores correct segment address `0x10000` and set up correct `sp`. After it we have correct stack:

![stack](http://oi58.tinypic.com/16iwcis.jpg)

2. In the second case (`ss` != `ds`), first of all put [_end](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld#L52) (address of end of setup code) value in `dx`. And check `loadflags` header field with `testb` instruction too see if we can use heap or not. [loadflags](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L321) is a bitmask header which is defined as:

```C
#define LOADED_HIGH	    (1<<0)
#define QUIET_FLAG	    (1<<5)
#define KEEP_SEGMENTS	(1<<6)
#define CAN_USE_HEAP	(1<<7)
```

And as we can read in the boot protocol:

```
Field name:	loadflags

  This field is a bitmask.

  Bit 7 (write): CAN_USE_HEAP
	Set this bit to 1 to indicate that the value entered in the
	heap_end_ptr is valid.  If this field is clear, some setup code
	functionality will be disabled.
```

If `CAN_USE_HEAP` bit is set, put `heap_end_ptr` to `dx` which points to `_end` and add `STACK_SIZE` (minimal stack size - 512 bytes) to it. After this if `dx` is not carry, jump to `2` (it will be not carry, dx = _end + 512) label as in previous case and make correct stack.

![stack](http://oi62.tinypic.com/dr7b5w.jpg)

3. The last case when `CAN_USE_HEAP` is not set, we just use minimal stack from `_end` to `_end + STACK_SIZE`:

![minimal stack](http://oi60.tinypic.com/28w051y.jpg)

Bss setup
--------------------------------------------------------------------------------

Last two steps before we can jump to see code need to setup [bss](http://en.wikipedia.org/wiki/.bss) and check magic signature. Signature checking:

```assembly
cmpl	$0x5a5aaa55, setup_sig
jne	setup_bad
```

just consists of comparing of [setup_sig](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld#L39) and `0x5a5aaa55` number, and if they are not equal jump to error printing.

Ok now we have correct segment registers, stack, need only setup bss and jump to C code. Bss section used for storing statically allocated uninitialized data. Here is the code:

```assembly
	movw	$__bss_start, %di
	movw	$_end+3, %cx
	xorl	%eax, %eax
	subw	%di, %cx
	shrw	$2, %cx
	rep; stosl
```

First of all we put [__bss_start](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld#L47) address in `di` and `_end + 3` (+3 - align to 4 bytes) in `cx`. Clear `eax` register with `xor` instruction and calculate size of BSS section (put in `cx`). Divide `cx` by 4 and repeat `cx` times `stosl` instruction which stores value of `eax` (it is zero) and increase `di`by the size of `eax`. In this way, we write zeros from `__bss_start` to `_end`:

![bss](http://oi59.tinypic.com/29m2eyr.jpg)

Jump to main
--------------------------------------------------------------------------------

That's all, we have stack, bss and now we can jump to `main` C function:

```assembly
	call main
```

which is in [arch/x86/boot/main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c). What will be there? We will see it in the next part.

Conclusion
--------------------------------------------------------------------------------

It is the end of the first part about linux kernel internals. If you have questions or suggestions, ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-internals/issues/new). In next part we will see first C code which executes in linux kernel setup, implementation of memory routines as memset, memcpy, `earlyprintk` implementation and early console initialization and many more.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you will find any mistakes please send me PR to [linux-internals](https://github.com/0xAX/linux-internals).**

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
