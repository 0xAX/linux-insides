Kernel booting process. Part 2.
================================================================================

First steps in the kernel setup
--------------------------------------------------------------------------------

We started to dive into linux kernel internals in the previous [part](linux-bootstrap-1.md) and saw the initial part of the kernel setup code. We stopped at the first call of the `main` function (which is the first function written in C) from [arch/x86/boot/main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c). Here we will continue to research the kernel setup code and see what is `protected mode`, some preparation for the transition into it, the heap and console initialization, memory detection and much much more. So... Let's go ahead.

Protected mode
--------------------------------------------------------------------------------

Before we can move to the native Intel64 [Long mode](http://en.wikipedia.org/wiki/Long_mode), the kernel must switch the CPU into protected mode. What is the protected mode? The Protected mode was first added to the x86 architecture in 1982 and was the main mode of Intel processors from [80286](http://en.wikipedia.org/wiki/Intel_80286) processor until Intel 64 and long mode. The Main reason to move away from the real mode that there is very limited access to the RAM. As you can remember from the previous part, there is only 2^20 bytes or 1 megabyte, sometimes even only 640 kilobytes.

Protected mode brought many changes, but the main is a different memory management.The 24-bit address bus was replaced with a 32-bit address bus. It allows to access to 4 gigabytes of physical adress space. Also [paging](http://en.wikipedia.org/wiki/Paging) support was added which we will see in the next parts.

Memory management in the protected mode is divided into two, almost independent parts:

* Segmentation
* Paging

Here we can only see segmentation. As you can read in the previous part, addresses consist of two parts in the real mode:

* Base address of segment
* Offset from the segment base

And we can get the physical address if we know these two parts by:

```
PhysicalAddress = Segment * 16 + Offset
```

Memory segmentation was completely redone in the protected mode. There are no 64 kilobytes fixed-size segments. All memory segments are described by the `Global Descriptor Table` (GDT) instead of segment registers.The GDT is a structure which resides in memory. There is no fixed place for it in memory, but its address is stored in the special `GDTR` register. Later we will see the GDT loading in the linux kernel code. There will be an operation for loading it into memory, something like:

```assembly
lgdt gdt
```

where the `lgdt` instruction loads the base address and limit of global descriptor table to the `GDTR` register. `GDTR` is a 48-bit register and consists of two parts:

 * size - 16 bit of global descriptor table;
 * address  - 32-bit of the global descriptor table.

The global descriptor table contains `descriptors` which describe memory segments.  Every descriptor is 64-bit. General scheme of a descriptor is:

```
31          24        19      16              7            0
------------------------------------------------------------
|             | |B| |A|       | |   | |0|E|W|A|            |
| BASE 31..24 |G|/|L|V| LIMIT |P|DPL|S|  TYPE | BASE 23:16 | 4
|             | |D| |L| 19..16| |   | |1|C|R|A|            |
------------------------------------------------------------
|                             |                            |
|        BASE 15..0           |       LIMIT 15..0          | 0
|                             |                            |
------------------------------------------------------------
```

Don't worry, i know that it looks a little scary after real mode, but it's easy. Let's look on it closer:

1. Limit (0 - 15 bits) defines a `length_of_segment - 1`. It depends on `G` bit.

  * if `G` (55-bit) is 0 and segment limit is 0 - size of segment - 1 byte
  * if `G` is 1 and segment limit is 0 - size of segment 4096 bytes
  * if `G` is 0 and segment limit is 0xfffff - size of segment 1 megabyte
  * if `G` is 1 and segment limit is 0xfffff - size of segment 4 gigabytes

2. Base (0-15, 32-39 and 56-63 bits) defines the physical address of the segment's start address.

3. Type (40-47 bits) defines the type of segment and kinds of access to it. Next `S` flag specifies descriptor type. if `S` is 0 - this segment is a system segment, if `S` is 1 - code or data segment (Stack segments are data segments which must be read/write segments). If the segment is a code or data segment, it can be one of the following access types:

```
|           Type Field        | Descriptor Type | Description
|-----------------------------|-----------------|------------------
| Decimal                     |                 |
|             0    E    W   A |                 |
| 0           0    0    0   0 | Data            | Read-Only
| 1           0    0    0   1 | Data            | Read-Only, accessed
| 2           0    0    1   0 | Data            | Read/Write
| 3           0    0    1   1 | Data            | Read/Write, accessed
| 4           0    1    0   0 | Data            | Read-Only, expand-down
| 5           0    1    0   1 | Data            | Read-Only, expand-down, accessed
| 6           0    1    1   0 | Data            | Read/Write, expand-down
| 7           0    1    1   1 | Data            | Read/Write, expand-down, accessed
|                  C    R   A |                 |
| 8           1    0    0   0 | Code            | Execute-Only
| 9           1    0    0   1 | Code            | Execute-Only, accessed
| 10          1    0    1   0 | Code            | Execute/Read
| 11          1    0    1   1 | Code            | Execute/Read, accessed
| 12          1    1    0   0 | Code            | Execute-Only, conforming
| 14          1    1    0   1 | Code            | Execute-Only, conforming, accessed
| 13          1    1    1   0 | Code            | Execute/Read, conforming
| 15          1    1    1   1 | Code            | Execute/Read, conforming, accessed
```

As we can see the first bit is 0 for data segment and 1 for code segment. Next three bits `EWA` are expansion direction (expand-down segment will grow down, you can read more about it  [here](http://www.sudleyplace.com/dpmione/expanddown.html)), write enable and accessed for data segments. `CRA` bits are conforming (A transfer of execution into a more-privileged conforming segment allows execution to continue at the current privilege level), read enable and accessed.

4. DPL (descriptor privilege level) defines the privilege level of the segment. It can be 0-3 where 0 is the most privileged.

5. P flag - indicates if segment is present in memory or not.

6. AVL flag - Available and reserved bits.

7. L flag - indicates whether a code segment contains native 64-bit code. If 1 then the code segment executes in 64 bit mode.

8. B/D flag - default operation size/default stack pointer size and/or upper bound.

Segment registers don't contain the base address of the segment as in the real mode. Instead they contain a special structure - `segment selector`. `Selector` is a 16-bit structure:

```
-----------------------------
|       Index    | TI | RPL |
-----------------------------
```

Where `Index` shows the index number of the descriptor in descriptor table. `TI` shows where to search for the descriptor: in the global descriptor table or local. And `RPL` is the privilege level.

Every segment register has a visible and hidden part. When a selector is loaded into one of the segment registers, it will be stored into the visible part. The hidden part contains the base address, limit and access information of the descriptor which pointed to the selector. The following steps are nneded to get the physical address in the protected mode:

* Segment selector must be loaded in one of the segment registers;
* CPU tries to find (by GDT address + Index from selector) and load the descriptor into the hidden part of segment register;
* Base address (from segment descriptor) + offset will be the linear address of the segment which is the physical address (if paging is disabled).

Schematically it will look like this:

![linear address](http://oi62.tinypic.com/2yo369v.jpg)

THe algorithm for the transition from the real mode into protected mode is:

* Disable interrupts;
* Describe and load GDT with `lgdt` instruction;
* Set PE (Protection Enable) bit in CR0 (Control Register 0);
* Jump to protected mode code;

We will see the transition to the protected mode in the linux kernel in the next part, but before we can move to protected mode, we need to do some preparations.

Let's look on [arch/x86/boot/main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c). We can see some routines there which make keyboard initialization, heap initialization, etc... Let's look into it.

Copying boot parameters into the "zeropage"
--------------------------------------------------------------------------------

We will start from the `main` routine in "main.c". First function which is called in `main` is [copy_boot_params](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c#L30). It copies the kernel setup header into the field of the `boot_params` structure which is defined in the [arch/x86/include/uapi/asm/bootparam.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/uapi/asm/bootparam.h#L113).

The `boot_params` structure contains the `struct setup_header hdr` field. This structure contains the same fields as defined in [linux boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt) and is filled by the boot loader and also at kernel compile/build time. `copy_boot_params` does two things: copies `hdr` from [header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S#L281) to the `boot_params` structure in `setup_header` field and updates pointer to the kernel command line if the kernel was loaded with old command line protocol.

Note that it copies `hdr` with `memcpy` function which is defined in the [copy.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/copy.S) source file. Let's have a look inside:

```assembly
GLOBAL(memcpy)
	pushw	%si
	pushw	%di
	movw	%ax, %di
	movw	%dx, %si
	pushw	%cx
	shrw	$2, %cx
	rep; movsl
	popw	%cx
	andw	$3, %cx
	rep; movsb
	popw	%di
	popw	%si
	retl
ENDPROC(memcpy)
```

Yeah, we just moved to C code and now assembly again :) First of all we can see that `memcpy` and other routines which are defined here, start and end with the two macros: `GLOBAL` and `ENDPROC`. GLOBAL is described in [arch/x86/include/asm/linkage.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/linkage.h) which defines `globl` directive and the label for it. ENDPROC is described in [include/linux/linkage.h](https://github.com/torvalds/linux/blob/master/include/linux/linkage.h) which marks `name` symbol as function name and ends with the size of the `name` symbol.

Implementation of the `memcpy` is easy. At first, it pushes values from `si` and `di` registers to the stack because their values will change in the `memcpy`, so push it on the stack to preserve their values. `memcpy` (and other functions in copy.S) use `fastcall` calling conventions. So it gets incoming parameters from the `ax`, `dx` and `cx` registers.  Calling `memcpy` looks like this:

```C
memcpy(&boot_params.hdr, &hdr, sizeof hdr);
```

So `ax` will contain the address of the `boot_params.hdr`, `dx` will contain the address of `hdr` and `cx` will contain the size of `hdr` (all in bytes). memcpy puts the address of `boot_params.hdr` to the `di` register and address of `hdr` to `si` and saves the size on the stack. After this it shifts to the right on 2 size (or divide on 4) and copies from `si` to `di` by 4 bytes. After it we restore the size of `hdr` again, align it by 4 bytes and copy the rest of bytes from `si` to `di` byte by byte (if there is rest). Restore `si` and `di` values from the stack in the end and after this copying is finished.

Console initialization
--------------------------------------------------------------------------------

After the `hdr` is copied into `boot_params.hdr`, the next step is console initialization by calling the `console_init` function which is defined in [arch/x86/boot/early_serial_console.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/early_serial_console.c).

It tries to find the `earlyprintk` option in the command line and if the search was successful, it parses the port address and baud rate of the serial port and initializes the serial port. Value of `earlyprintk` command line option can be one of the:

	* serial,0x3f8,115200
	* serial,ttyS0,115200
	* ttyS0,115200

After serial port initialization we can see the first output:

```C
if (cmdline_find_option_bool("debug"))
		puts("early console in setup code\n");
```

`puts` definition is in [tty.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/tty.c). As we can see it prints character by character in the loop by calling The `putchar` function. Let's look into the `putchar` implementation:

```C
void __attribute__((section(".inittext"))) putchar(int ch)
{
	if (ch == '\n')
		putchar('\r');

	bios_putchar(ch);

	if (early_serial_base != 0)
		serial_putchar(ch);
}
```

`__attribute__((section(".inittext")))` means that this code will be in the .inittext section. We can find it in the linker file [setup.ld](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld#L19).

First of all, `put_char` checks for the `\n` symbol and if it is found, prints `\r` before. After that it outputs the character on the VGA screen by calling the BIOS with the `0x10` interrupt call:

```C
static void __attribute__((section(".inittext"))) bios_putchar(int ch)
{
	struct biosregs ireg;

	initregs(&ireg);
	ireg.bx = 0x0007;
	ireg.cx = 0x0001;
	ireg.ah = 0x0e;
	ireg.al = ch;
	intcall(0x10, &ireg, NULL);
}
```

Here `initregs` takes the `biosregs` structure and first fills `biosregs` with zeros using the `memset` function and then fills it with register values.

```C
	memset(reg, 0, sizeof *reg);
	reg->eflags |= X86_EFLAGS_CF;
	reg->ds = ds();
	reg->es = ds();
	reg->fs = fs();
	reg->gs = gs();
```

Let's look on the [memset](https://github.com/torvalds/linux/blob/master/arch/x86/boot/copy.S#L36) implementation:

```assembly
GLOBAL(memset)
	pushw	%di
	movw	%ax, %di
	movzbl	%dl, %eax
	imull	$0x01010101,%eax
	pushw	%cx
	shrw	$2, %cx
	rep; stosl
	popw	%cx
	andw	$3, %cx
	rep; stosb
	popw	%di
	retl
ENDPROC(memset)
```

As you can read above, it uses `fastcall` calling conventions like the `memcpy` function, which means that the function gets parameters from `ax`, `dx` and `cx` registers.

Generally `memset` is like a memcpy implementation. It saves the value of the `di` register on the stack and puts the `ax` value into `di` which is the address of the `biosregs` structure. Next is the `movzbl` instruction, which copies the `dl` value to the low 2 bytes of the `eax` register. The remaining 2 high bytes  of `eax` will be filled with zeros.

The next instruction multiplies `eax` with `0x01010101`. It needs to because `memset` will copy 4 bytes at the same time. For example we need to fill a structure with `0x7` with memset. `eax` will contain `0x00000007` value in this case. So if we multiply `eax` with `0x01010101`, we will get `0x07070707` and now we can copy these 4 bytes into the structure. `memset` uses `rep; stosl` instructions for copying `eax` into `es:di`.

The rest of the `memset` function does almost the same as `memcpy`.

After that `biosregs` structure is filled with `memset`, `bios_putchar` calls the [0x10](http://www.ctyme.com/intr/rb-0106.htm) interrupt which prints a character. Afterwards it checks if the serial port was initialized or not and writes a character there with [serial_putchar](https://github.com/torvalds/linux/blob/master/arch/x86/boot/tty.c#L30) and `inb/outb` instructions if it was set.

Heap initialization
--------------------------------------------------------------------------------

After the stack and bss section were prepared in [header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S) (see previous [part](linux-bootstrap-1.md)), the kernel needs to initialize the [heap](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c#L116) with the [init_heap](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c#L116) function.

First of all `init_heap` checks the `CAN_USE_HEAP` flag from the `loadflags` kernel setup header and calculates the end of the stack if this flag was set:

```C
	char *stack_end;

	if (boot_params.hdr.loadflags & CAN_USE_HEAP) {
		asm("leal %P1(%%esp),%0"
		    : "=r" (stack_end) : "i" (-STACK_SIZE));
```

or in other words `stack_end = esp - STACK_SIZE`.

Then there is the `heap_end` calculation which is `heap_end_ptr` or `_end` + 512 and a check if `heap_end` is greater than `stack_end` makes it equal.

From this moment we can use the heap in the kernel setup code. We will see how to use it and how the API for it is implemented in next posts.

CPU validation
--------------------------------------------------------------------------------

The next step as we can see is cpu validation by `validate_cpu` from [arch/x86/boot/cpu.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/cpu.c).

It calls the `check_cpu` function and passes cpu level and required cpu level to it and checks that kernel launched at the right cpu. It checks the cpu's flags, presence of [long mode](http://en.wikipedia.org/wiki/Long_mode) (which we will see more details on in the next parts) for x86_64, checks the processor's vendor and makes preparation for certain vendors like turning off SSE+SSE2 for AMD if they are missing and etc...

Memory detection
--------------------------------------------------------------------------------

The next step is memory detection by the `detect_memory` function. It uses different programming interfaces for memory detection like `0xe820`, `0xe801` and `0x88`. We will see only the implementation of 0xE820 here. Let's look into the `detect_memory_e820` implementation from the [arch/x86/boot/memory.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/memory.c) source file. First of all, `detect_memory_e820` function initializes `biosregs` structure as we saw above and fills registers with special values for the `0xe820` call:

```assembly
	initregs(&ireg);
	ireg.ax  = 0xe820;
	ireg.cx  = sizeof buf;
	ireg.edx = SMAP;
	ireg.di  = (size_t)&buf;
```

The `ax` register must contain the number of the function (0xe820 in our case), `cx` register contains size of the buffer which will contain data about memory, `edx` must contain the `SMAP` magic number, `es:di` must contain the address of the buffer which will contain memory data and `ebx` has to be zero.

Next is a loop where data about the memory will be collected. It starts from the call of the 0x15 bios interrupt, which writes one line from the address allocation table. For getting the next line we need to call this interrupt again (which we do in the loop). Before the next call `ebx` must contain the value returned previously:

```C
	intcall(0x15, &ireg, &oreg);
	ireg.ebx = oreg.ebx;
```

Ultimately, it does iterations in the loop to collect data from the address allocation table and writes this data into the `e820entry` array:

* start of memory segment
* size  of memory segment
* type of memory segment (which can be reserved, usable and etc...).

You can see the result of this in the `dmesg` output, something like:

```
[    0.000000] e820: BIOS-provided physical RAM map:
[    0.000000] BIOS-e820: [mem 0x0000000000000000-0x000000000009fbff] usable
[    0.000000] BIOS-e820: [mem 0x000000000009fc00-0x000000000009ffff] reserved
[    0.000000] BIOS-e820: [mem 0x00000000000f0000-0x00000000000fffff] reserved
[    0.000000] BIOS-e820: [mem 0x0000000000100000-0x000000003ffdffff] usable
[    0.000000] BIOS-e820: [mem 0x000000003ffe0000-0x000000003fffffff] reserved
[    0.000000] BIOS-e820: [mem 0x00000000fffc0000-0x00000000ffffffff] reserved
```

Keyboard initialization
--------------------------------------------------------------------------------

The next step is the initialization of the keyboard with the call of the `keyboard_init` function. At first `keyboard_init` initializes registers using the `initregs` function and calling the [0x16](http://www.ctyme.com/intr/rb-1756.htm) interrupt for getting the keyboard status. After this it calls [0x16](http://www.ctyme.com/intr/rb-1757.htm) again to set repeat rate and delay.

Querying
--------------------------------------------------------------------------------

The next couple of steps are queries for different parameters. We will not dive into details about these queries, but will be back to the all of it in the next parts. Let's make a short look on this functions:

The [query_mca](https://github.com/torvalds/linux/blob/master/arch/x86/boot/mca.c#L18) routine calls the [0x15](http://www.ctyme.com/intr/rb-1594.htm) BIOS interrupt to get the machine model number, sub-model number, BIOS revision level, and other hardware-specific attributes:

```C
int query_mca(void)
{
	struct biosregs ireg, oreg;
	u16 len;

	initregs(&ireg);
	ireg.ah = 0xc0;
	intcall(0x15, &ireg, &oreg);

	if (oreg.eflags & X86_EFLAGS_CF)
		return -1;	/* No MCA present */

	set_fs(oreg.es);
	len = rdfs16(oreg.bx);

	if (len > sizeof(boot_params.sys_desc_table))
		len = sizeof(boot_params.sys_desc_table);

	copy_from_fs(&boot_params.sys_desc_table, oreg.bx, len);
	return 0;
}
```

It fills  the `ah` register with `0xc0` and calls the `0x15` BIOS interruption. After the interrupt execution it checks  the [carry flag](http://en.wikipedia.org/wiki/Carry_flag) and if it is set to 1, BIOS doesn't support `MCA`. If carry flag is set to 0, `ES:BX` will contain a pointer to the system information table, which looks like this:

```
Offset	Size	Description	)
 00h	WORD	number of bytes following
 02h	BYTE	model (see #00515)
 03h	BYTE	submodel (see #00515)
 04h	BYTE	BIOS revision: 0 for first release, 1 for 2nd, etc.
 05h	BYTE	feature byte 1 (see #00510)
 06h	BYTE	feature byte 2 (see #00511)
 07h	BYTE	feature byte 3 (see #00512)
 08h	BYTE	feature byte 4 (see #00513)
 09h	BYTE	feature byte 5 (see #00514)
---AWARD BIOS---
 0Ah  N BYTEs	AWARD copyright notice
---Phoenix BIOS---
 0Ah	BYTE	??? (00h)
 0Bh	BYTE	major version
 0Ch	BYTE	minor version (BCD)
 0Dh  4 BYTEs	ASCIZ string "PTL" (Phoenix Technologies Ltd)
---Quadram Quad386---
 0Ah 17 BYTEs	ASCII signature string "Quadram Quad386XT"
---Toshiba (Satellite Pro 435CDS at least)---
 0Ah  7 BYTEs	signature "TOSHIBA"
 11h	BYTE	??? (8h)
 12h	BYTE	??? (E7h) product ID??? (guess)
 13h  3 BYTEs	"JPN"
 ```

Next we call the `set_fs` routine and pass the value of the `es` register to it. Implementation of `set_fs` is pretty simple:

```C
static inline void set_fs(u16 seg)
{
	asm volatile("movw %0,%%fs" : : "rm" (seg));
}
```

There is inline assembly which gets the value of the `seg` parameter and puts it into the `fs` register. There are many functions in [boot.h](https://github.com/torvalds/linux/blob/master/arch/x86/boot/boot.h) like `set_fs`, for example `set_gs`, `fs`, `gs` for reading a value in it and etc...

In the end of `query_mca` it just copies the table which pointed to by `es:bx` to the `boot_params.sys_desc_table`.

The next is getting [Intel SpeedStep](http://en.wikipedia.org/wiki/SpeedStep) information with the call of `query_ist` function. First of all it checks CPU level and if it is correct, calls `0x15` for getting info and saves the result to `boot_params`.

The following [query_apm_bios](https://github.com/torvalds/linux/blob/master/arch/x86/boot/apm.c#L21) function gets [Advanced Power Management](http://en.wikipedia.org/wiki/Advanced_Power_Management) information from the BIOS. `query_apm_bios` calls the `0x15` BIOS interruption too, but with `ah` - `0x53` to check `APM` installation. After the `0x15` execution, `query_apm_bios` functions checks `PM` signature (it must be `0x504d`), carry flag (it must be 0 if `APM` supported) and value of the `cx` register (if it's 0x02, protected mode interface is supported).

Next it calls the `0x15` again, but with `ax = 0x5304` for disconnecting the `APM` interface and connect the 32bit protected mode interface. In the end it fills `boot_params.apm_bios_info` with values obtained from the BIOS.

Note that `query_apm_bios` will be executed only if `CONFIG_APM` or `CONFIG_APM_MODULE` was set in configuration file:

```C
#if defined(CONFIG_APM) || defined(CONFIG_APM_MODULE)
	query_apm_bios();
#endif
```

The last is the [query_edd](https://github.com/torvalds/linux/blob/master/arch/x86/boot/edd.c#L122) function, which asks `Enhanced Disk Drive` information from the BIOS. Let's look into the `query_edd` implementation.

First of all it reads the [edd](https://github.com/torvalds/linux/blob/master/Documentation/kernel-parameters.txt#L1023) option from kernel's command line and if it was set to `off` then `query_edd` just returns.

If EDD is enabled, `query_edd` goes over BIOS-supported hard disks and queries EDD information in the following loop:

```C
	for (devno = 0x80; devno < 0x80+EDD_MBR_SIG_MAX; devno++) {
		if (!get_edd_info(devno, &ei) && boot_params.eddbuf_entries < EDDMAXNR) {
			memcpy(edp, &ei, sizeof ei);
			edp++;
			boot_params.eddbuf_entries++;
		}
		...
		...
		...
```

where the `0x80` is the first hard drive and the `EDD_MBR_SIG_MAX` macro is 16. It collects data into the array of [edd_info](https://github.com/torvalds/linux/blob/master/include/uapi/linux/edd.h#L172) structures. `get_edd_info` checks that EDD is present by invoking the `0x13` interrupt with `ah` as `0x41` and if EDD is present, `get_edd_info` again calls the `0x13` interrupt, but with `ah` as `0x48` and `si` contianing the address of the buffer where EDD informantion will be stored.

Conclusion
--------------------------------------------------------------------------------

This is the end of the second part about linux kernel internals. In the next part we will see video mode setting and the rest of preparations before transition to protected mode and directly transitioning into it.

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-internals](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

* [Protected mode](http://en.wikipedia.org/wiki/Protected_mode)
* [Long mode](http://en.wikipedia.org/wiki/Long_mode)
* [How to Use Expand Down Segments on Intel 386 and Later CPUs](http://www.sudleyplace.com/dpmione/expanddown.html)
* [earlyprintk documentation](http://lxr.free-electrons.com/source/Documentation/x86/earlyprintk.txt)
* [Kernel Parameters](https://github.com/torvalds/linux/blob/master/Documentation/kernel-parameters.txt)
* [Serial console](https://github.com/torvalds/linux/blob/master/Documentation/serial-console.txt)
* [Intel SpeedStep](http://en.wikipedia.org/wiki/SpeedStep)
* [APM](https://en.wikipedia.org/wiki/Advanced_Power_Management)
* [EDD specification](http://www.t13.org/documents/UploadedDocuments/docs2004/d1572r3-EDD3.pdf)
* [Previous part](linux-bootstrap-1.md)
