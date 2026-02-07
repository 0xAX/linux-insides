# Kernel booting process - Part 2

We have already started our journey into the Linux kernel in the previous [part](./linux-bootstrap-1.md), where we walked through the very early stages of the booting process and first assembly instructions of the Linux kernel code. Aside from different mechanisms, this code was responsible for preparing the environment for the [C](https://en.wikipedia.org/wiki/C_(programming_language)) programming language. At the end of the chapter, we reached a symbolic milestone - the very first call of a C function. This function has a classical name - `main` - and is defined in the [arch/x86/boot/main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c) source code file.

From here on, we will still see some assembly code on our way, but it will be more and more rare 🤓 Now it is time for more "high-level" logic!

From the previous part, we know that the kernel setup code is still running in [real mode](https://en.wikipedia.org/wiki/Real_mode). Its primary task is to move the processor first into [protected mode](https://en.wikipedia.org/wiki/Protected_mode), and then into [long mode](https://en.wikipedia.org/wiki/Long_mode). Almost all of the C code we will see in the next chapters exists for this purpose - to prepare and complete these transitions.

In this part, we’ll keep digging through the kernel’s setup code and cover:

- What protected mode is on x86 processors
- Setup of early [heap](https://en.wikipedia.org/wiki/Memory_management#HEAP) and console
- Detection of available memory
- Validation of a CPU 
- Initialization of a keyboard 

Time to explore these steps in detail!

## Protected mode

The Linux kernel for x86_64 operates in a special mode called - [long mode](http://en.wikipedia.org/wiki/Long_mode). One of the main goal of all the setup kernel code is to switch to this mode. But before we can move to this mode, the kernel must switch the CPU into [protected mode](https://en.wikipedia.org/wiki/Protected_mode).

What is [protected mode](https://en.wikipedia.org/wiki/Protected_mode)? From the previous chapter we already know that currently CPU operates in [real mode](https://en.wikipedia.org/wiki/Real_mode). For us it is mostly means - memory segmentation. As a short reminder - to access a memory location, the combination of two CPU [registers](https://en.wikipedia.org/wiki/Processor_register) is used:

- A segment register - `cs`, `ds`, `ss` and `es` which defines segment selector.
- A general purpose register which specifies offset within the segment.

The main motivation for switching from real mode is its memory addressing limitation. As we saw in the previous part, real mode can address only 2<sup>20</sup> bytes. This is just 1 MB of RAM. Obviously, modern software, including an operating system kernel, needs more. To break these constraints, the new processor mode was introduced - `protected mode`.

Protected mode was introduced to the x86 architecture in 1982 and became the primary operating mode of Intel processors, starting with the [80286](http://en.wikipedia.org/wiki/Intel_80286) until the introduction of x86_64 and long mode. This mode brought many changes and improvements, but one of the most crucial was the memory management. The 20-bit address bus was replaced with a 32-bit address bus. It allowed access to 4 Gigabytes of memory in comparison to the 1 Megabyte in real mode.

Memory management in protected mode is divided into two, mostly independent mechanisms:

- `Segmentation`
- `Paging`

For now, our attention stays on segmentation. We’ll return to paging later, once we enter 64-bit long mode.

### Memory segmentation in protected mode

In protected mode, memory segmentation is completely redesigned. Fixed 64 KB real mode segments are gone. Instead, each segment is now defined by a special data structure called a `Segment Descriptor` which specifies the properties of a memory segment. The segment descriptors are stored in a special structure called the `Global Descriptor Table` or `GDT`. Whenever a CPU needs to find an actual physical memory address, it consults this table. The GDT itself is just a block of memory. Its address is stored in the special CPU register called `gdtr`.  This is a 48-bit register and consists of two parts:

- The size of the Global Descriptor Table
- The address of the Global Descriptor Table

Later, we will see exactly how the Linux kernel builds and loads its GDT. For now, it’s enough to know that the CPU provides a dedicated instruction to load the table’s address into the GDTR register:

```assembly
lgdt gdt
```

As mentioned above, the GDT contains `segment descriptors` which describe memory segments. Now let's see how segment descriptors look like. Each descriptor is 64-bits in size. The general scheme of a descriptor is:

![segment-descriptor](./images/segment-descriptor.svg)

Do not worry! I know it may look a little bit intimidating at the first glance, especially in comparison to the relatively simple addressing in real mode, but we will go through it in details. We will start from the bottom, from right to left. 

The first field is `LIMIT 15:0`. It represents the first 16 bits of the segment limit. The second part is located at the bits `51:48`. This field provides information about the size of a segment. Having 20-bit size of the limit field, it may seem that the max size of a memory segment can be 1 MB, but it is not like that. In addition, the max size of a segment depends on the 55th `G` bit:

- If `G=0` - the value of the `LIMIT` field is interpreted in bytes.
- if `G=1` - the value of the `LIMIT` field is interpreted in 4 KB units called pages.

Based on this, we can easily calculate that the max size of a segment is 4 GB.

The next field is `BASE`. We can see that it is split into three parts. The first part occupies bits from `16` to `31`, the second part occupies bits from `32` to `39`, and the last third part occupies bits from `56` to `63`. The main goal of this field is to store the base address of a segment.

The remaining fields in a segment descriptor represent flags that control different aspects of a segment, such as the type of memory. Let's take a look at the description of these flags:

- `Type` - describes the type of a memory segment.
- `S` - distinguishes system segments from code and data segments.
- `DPL` - provides information about the privilege level of a segment. It can be a value from `0` to `3`, where `0` is the level with the highest privileges.
- `P` - tells the CPU whether a segment presented in memory.
- `AVL` - available and reserved bits. It is ignored by the Linux kernel.
- `L` - indicates whether a code segment contains 64-bit code.
- `D / B` - provides different meaning depends on the type of a segment.
  - For a code segment: Controls the default operand and address size. If the bit is clear, it is a 16-bit code segment. Otherwise it is a 32-bit code segment.
  - For a stack segment or in other words a data segment pointed by the `ss` register: Controls the default stack pointer size. If the bit is clear, it is a 16-bit stack segment and stack operations use `sp` register. Otherwise it is a 32-bit stack segment and stack operations use `esp` register.
  - For a expand-down data segment: Specifies the upper bound of the segment. If the bit is clear, the upper bound is `0xFFFF` or 64 KB. Otherwise, it is `0xFFFFFFFF` or 4 GB.

If the `S` flag of a segment descriptor is set, the descriptor describes either a code or a data segment, otherwise it is a system segment. If the highest order bit of the `Type` flags is clear - this descriptor describes a data segment, otherwise a code segment. Rest of the three bits of a data segment descriptor interpreted as:

- `Accessed` - indicates whether a segment has been accessed since the last time the kernel cleared this bit.
- `Write-Enable` - determines whether a segment is writable or read-only.
- `Expansion-Direction` - determines whether addresses decreasing from the base address or not.

For a code segment, these three bits interpreted as:

- `Accessed` - indicates whether a segment has been accessed since the last time the kernel cleared this bit.
- `Read-Enable` - determines whether a segment is execute-only or execute-read.
- `Confirming` - determines how privilege level changes are handled when transferring execution to that segment.

In the tables below you can find full information about possible states of the flags for a code and a data segments.

A data segment `Type` field:

| E (Expand-Down) | W (Writable) | A (Accessed) | Description                       |
| --------------- | ------------ | ------------ | --------------------------------- |
| 0               | 0            | 0            | Read-Only                         |
| 0               | 0            | 1            | Read-Only, accessed               |
| 0               | 1            | 0            | Read/Write                        |
| 0               | 1            | 1            | Read/Write, accessed              |
| 1               | 0            | 0            | Read-Only, expand-down            |
| 1               | 0            | 1            | Read-Only, expand-down, accessed  |
| 1               | 1            | 0            | Read/Write, expand-down           |
| 1               | 1            | 1            | Read/Write, expand-down, accessed |

A code segment `Type` field:

| C (Conforming) | R (Readable) | A (Accessed) | Description                        |
| -------------- | ------------ | ------------ | ---------------------------------- |
| 0              | 0            | 0            | Execute-Only                       |
| 0              | 0            | 1            | Execute-Only, accessed             |
| 0              | 1            | 0            | Execute/Read                       |
| 0              | 1            | 1            | Execute/Read, accessed             |
| 1              | 0            | 0            | Execute-Only, conforming           |
| 1              | 1            | 0            | Execute/Read, conforming           |
| 1              | 0            | 1            | Execute-Only, conforming, accessed |
| 1              | 1            | 1            | Execute/Read, conforming, accessed |

So far, we’ve looked at how a segment descriptor defines the properties of a memory segment — its base, limit, type, and different flags. But how does the CPU actually refer to one of these descriptors during execution? Just like in real mode - using segment registers. In protected mode they contain segment selectors. However, in protected mode, a segment selector is handled differently. Each segment descriptor has an associated segment selector which is a 16-bit structure:

![segment-selector](./images/segment-selector.svg)

The meaning of the fields is:

- `Index` - the entry number of the descriptor in the descriptor table.
- `TI` - indicates where to search for the descriptor
  - If the value of the bit is `0`, a descriptor will be searched in the Global Descriptor Table.
  - If the value of this bit is `1`, a descriptor will be searched in the Local Descriptor Table.
- `RPL` - the privilege level requested by the selector.

When a program running in protected mode references a memory, the CPU need to calculate a proper physical address. The following steps are needed to get a physical address in protected mode:

1. A segment selector is loaded into one of the segment registers.
2. The CPU tries to find a associated segment descriptor in the Global Descriptor Table based on the `Index` value from the segment selector. If the descriptor was found, it is loaded into a special hidden part of this segment register.
3. The physical address will be the base address from the segment descriptor plus offset from the instruction pointer or memory location referenced within an executed instruction.

In the next part, we will see the transition into protected mode. But before the kernel can be switched to protected mode, we need to do some more preparations.

Let's continue from the point where we have stopped in the previous chapter.

## Back to the Kernel: Entering main.c

As we already have mentioned in the beginning of this chapter, one of the kernel's first main goals is to switch the processor into protected mode. But before this can happen, the kernel need to do some preparations.

If we look at the very beginning of the `main` function from the [arch/x86/boot/main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c), the very first thing we will see is a call of the `init_default_io_ops` function.

This function defined in the [arch/x86/boot/io.h](https://github.com/torvalds/linux/blob/master/arch/x86/boot/io.h) and looks like:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/io.h#L26-L31 -->
```C
static inline void init_default_io_ops(void)
{
	pio_ops.f_inb  = __inb;
	pio_ops.f_outb = __outb;
	pio_ops.f_outw = __outw;
}
```

This function initializes function pointers for:

- reading a byte from an I/O port
- writing a byte to an I/O port
- writing a word (16-bit) to an I/O port

These callbacks will be used to write data to the serial console which will be initialized at the one of the next steps. All the operations will be executed with the help of the `inb`, `outb`, and `outw` macros which defined in the same file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/io.h#L37-L39 -->
```C
#define inb  pio_ops.f_inb
#define outb pio_ops.f_outb
#define outw pio_ops.f_outw
```

The `__inb`, `__outb`, and `__outw` themselves are inline functions from the [arch/x86/include/asm/shared/io.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/shared/io.h):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/shared/io.h#L7-L24 -->
```C
#define BUILDIO(bwl, bw, type)						\
static __always_inline void __out##bwl(type value, u16 port)		\
{									\
	asm volatile("out" #bwl " %" #bw "0, %w1"			\
		     : : "a"(value), "Nd"(port));			\
}									\
									\
static __always_inline type __in##bwl(u16 port)				\
{									\
	type value;							\
	asm volatile("in" #bwl " %w1, %" #bw "0"			\
		     : "=a"(value) : "Nd"(port));			\
	return value;							\
}

BUILDIO(b, b, u8)
BUILDIO(w, w, u16)
BUILDIO(l,  , u32)
```

All of these functions use `in` and `out` assembly instructions which send the given value to the given port or read the value from the given port. If the syntax is not familiar to you, you can read the chapter about [inline assembly](https://github.com/0xAX/linux-insides/blob/master/Theory/linux-theory-3.md).

After initialization of callbacks for writing to a serial port, the next step is copying of the kernel setup header filled by a bootloader into the corresponding field of the C `boot_params` structure. This will make the fields from the kernel setup header more easily accessible. All the job by copying handled by the `copy_boot_params` function with the help of `memcpy`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/main.c#L39-L39 -->
```C
	memcpy(&boot_params.hdr, &hdr, sizeof(hdr));
```

Do not mix this `memcpy` with the function from the C standard library - [memcpy](https://man7.org/linux/man-pages/man3/memcpy.3.html). During the time when the kernel is in the early initialization phase, there is no way to load any library. For this reason, an operating system kernel provides own implementation of such functions. The kernel's `memcpy` defined in the [copy.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/copy.S). If you already started to miss an assembly code, this is the high time to bring some back:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/copy.S#L18-L32 -->
```assembly
SYM_FUNC_START_NOALIGN(memcpy)
	pushw	%si
	pushw	%di
	movw	%ax, %di
	movw	%dx, %si
	pushw	%cx
	shrw	$2, %cx
	rep movsl
	popw	%cx
	andw	$3, %cx
	rep movsb
	popw	%di
	popw	%si
	retl
SYM_FUNC_END(memcpy)
```

First of all, we can see that `memcpy` and other routines which are defined there, start and end with the two macros - `SYM_FUNC_START_NOALIGN` and `SYM_FUNC_END`. The `SYM_FUNC_START_NOALIGN` just specifies the given symbol name as [.globl](https://sourceware.org/binutils/docs/as.html#Global) to make it visible for other functions. The `SYM_FUNC_END` just expands to an empty string in our case.

Despite the implementation of this function is written in assembly language, the implementation of `memcpy` is relatively simple. At first, it pushes values from the `si` and `di` registers to the stack to preserve their values because they will change during the `memcpy` execution. At the next step we may see handling of the function's parameters. The parameters of this function are passed through the `ax`, `dx`, and `cx` registers. This is because the kernel setup code is built with `-mregparm=3` option. So:

- `ax` will contain the address of `boot_params.hdr`
- `dx` will contain the address of `hdr`
- `cx` will contain the size of `hdr` in bytes

The `rep movsl` instruction copies bytes from the memory pointed by the `si` register to the memory location pointed by the `di` register. At each iteration 4 bytes copied. For this reason we divided the size of the setup header by 4 using `shrw` instruction. After this step we just copy rest of bytes that is not divided by 4.

From this point, the setup header is copied into a proper place and we can move forward.

### Console initialization

As soon as the kernel setup header is copied into the `boot_params.hdr`, the next step is to initialize the serial console by calling the `console_init` function. Very soon we will be able to print something from within the kernel code!

The `console_init` defined in [arch/x86/boot/early_serial_console.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/early_serial_console.c). At the very first step it tries to find the `earlyprintk` option in the kernel's command line. If the search was successful, it parses the port address and [baud rate](https://en.wikipedia.org/wiki/Baud) and executes the initialization of the serial port.

> [!NOTE]
> If you want to know what else options you can pass in the kernel command line, you can find more information in the [The kernel's command-line parameters](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/kernel-parameters.rst) document.

Let's take a look at these two steps in details.

The possible values of the `earlyprintk` command line option are:

- `serial,0x3f8,115200`
- `serial,ttyS0,115200`
- `ttyS0,115200`

These parameters define the name of a serial port, the port number, and the [baud](https://en.wikipedia.org/wiki/Baud) rate.

The pointer to the kernel command line is stored in the kernel setup header that was copied in the previous section. The kernel setup code accesses it using `boot_params.hdr.cmd_line_ptr`. The `parse_earlyprintk` function tries to find the `earlyprintk` option in the kernel command line, parse it, and initialize the serial console with the given parameters. If the `earlyprintk` option is given and contains valid values, the initialization of the serial console takes place in the `early_serial_init` function. There is nothing specific to the Linux kernel in the initialization of a serial console, so we will skip this part. If you want to dive deeper, you can find more information [here](https://wiki.osdev.org/Serial_Ports#Port_Addresses) and learn [arch/x86/boot/early_serial_console.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/early_serial_console.c) step by step.

After the serial port initialization we can see the first output:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/main.c#L142-L143 -->
```C
	if (cmdline_find_option_bool("debug"))
		puts("early console in setup code\n");
```

The `puts` function uses the `inb` function that we have seen above during initialization of I/O callbacks.

From this point we can print messages from the kernel setup code 🎉. Time to move to the next step.

### Heap initialization

We have seen the initialization of the `stack` and `bss` memory areas in the previous chapter. The next step is to initialize the [heap](https://en.wikipedia.org/wiki/Memory_management#HEAP) memory area. The heap initialization takes place in the `init_heap` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/main.c#L118-131 -->
```C
static void init_heap(void)
{
	char *stack_end;

	if (boot_params.hdr.loadflags & CAN_USE_HEAP) {
		stack_end = (char *) (current_stack_pointer - STACK_SIZE);
		heap_end = (char *) ((size_t)boot_params.hdr.heap_end_ptr + 0x200);
		if (heap_end > stack_end)
			heap_end = stack_end;
	} else {
		/* Boot protocol 2.00 only, no heap available */
		puts("WARNING: Ancient bootloader, some functionality may be limited!\n");
	}
}
```

First of all, `init_heap` checks the `CAN_USE_HEAP` flag from the kernel setup header. We can find information about this flag in the kernel boot protocol:

>   Bit 7 (write): CAN_USE_HEAP
>
>	Set this bit to 1 to indicate that the value entered in the
>	heap_end_ptr is valid.  If this field is clear, some setup code
>	functionality will be disabled.

If this bit is not set, we'll see the warning message. Otherwise, the heap memory area is initialized. The beginning of the heap is defined by the `HEAP` pointer, which points to the end of the kernel setup image:

```C
char *HEAP = _end;
```

Now we need to initialize the size of the heap. There is another small hint in the Linux kernel boot protocol:

> ============	==================
> Field name:	heap_end_ptr
> Type:		write (obligatory)
> Offset/size:	0x224/2
> Protocol:	2.01+
> ============	==================
>
>  Set this field to the offset (from the beginning of the real-mode
>  code) of the end of the setup stack/heap, minus 0x0200.

The GRUB bootloader sets this value to:

```C
#define GRUB_LINUX_HEAP_END_OFFSET	(0x9000 - 0x200)
```

Based on these values, the end of the heap pointed by the `heap_end` will be at the `0x9000` offset from the end of the kernel setup image. To avoid the case when the heap and stack overlap, there is an additional check. It sets the end of the heap equal to the end of the stack if the first one is greater than the second. Having this, the heap memory area will be located above the `bss` area till the stack. So, the memory map will look like:

![early-heap](./images/early-heap.svg)

Now the heap is initialized, although we will see the usage of it in the next chapters.

### CPU validation

The next step is the validation of CPU on which the kernel is running. The kernel has to do it to make sure that the all required functionalities will work correctly on the given CPU.

The `validate_cpu` function from [arch/x86/boot/cpu.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/cpu.c) validates the CPU. This function calls the [`check_cpu`](https://github.com/torvalds/linux/blob/master/arch/x86/boot/cpucheck.c) which check the CPU model and its flags using the [cpuid](https://en.wikipedia.org/wiki/CPUID) instruction. The CPU's flags are checked like the presence of [long mode](http://en.wikipedia.org/wiki/Long_mode), checks the processor's vendor and makes preparations for certain vendors like turning on extensions like [SSE+SSE2](https://en.wikipedia.org/wiki/Single_instruction,_multiple_data):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/cpu.c#L60-L73 -->
```C
int validate_cpu(void)
{
	u32 *err_flags;
	int cpu_level, req_level;

	check_cpu(&cpu_level, &req_level, &err_flags);

	if (cpu_level < req_level) {
		printf("This kernel requires an %s CPU, ",
		       cpu_name(req_level));
		printf("but only detected an %s CPU.\n",
		       cpu_name(cpu_level));
		return -1;
	}
```

If the level of CPU is less than the required level specified by the `CONFIG_X86_MINIMUM_CPU_FAMILY` kernel configuration option, the function returns the error and the kernel setup process is aborted.

### Memory detection

After the kernel became sure that the CPU which it is running on is suitable, the next stage is to detect available memory in the system. This task is handled by the `detect_memory` function, which queries the system firmware to obtain a map of physical memory regions. To do this, the kernel uses the special BIOS service - `0xE820`, but kernel can fallback to legacy BIOS services like `0xE801` or `0x88`. In this chapter, we will see only the implementation of the `0xE820` interface.

The `detect_memory` function defined in the [arch/x86/boot/memory.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/memory.c) and as just mentioned, tries to get the information about available memory:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/memory.c#L116-L123 -->
```C
void detect_memory(void)
{
	detect_memory_e820();

	detect_memory_e801();

	detect_memory_88();
}
```

Let's look at the crucial part of the implementation of the `detect_memory_e820` function. First of all, the `detect_memory_e820` function initializes the `biosregs` structure with the special values related to the `0xE820` BIOS interface:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/memory.c#L25-L29 -->
```C
	initregs(&ireg);
	ireg.ax  = 0xe820;
	ireg.cx  = sizeof(buf);
	ireg.edx = SMAP;
	ireg.di  = (size_t)&buf;
```

- `ax` register contains the number of the BIOS service
- `cx` register contains the size of the buffer which will contain the data about available memory
- `di` register contain the address of the buffer which will contain memory data
- `edx` register contains the `SMAP` magic number

After registers are filled with the needed values, the kernel can ask the `0xE820` BIOS interface about the available memory. To do so, the kernel invokes `0x15` [BIOS interrupt](https://en.wikipedia.org/wiki/BIOS_interrupt_call), which returns information about one memory region. The kernel repeats this operation in a loop until it collects information about all available memory regions into the array of `boot_e820_entry` structures. This structure contains information about:

- beginning address of the memory region
- size of the memory region
- type of the memory region

The structure is defined in [arch/x86/include/uapi/asm/setup_data.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/uapi/asm/setup_data.h):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/uapi/asm/setup_data.h#L45-L49 -->
```C
struct boot_e820_entry {
	__u64 addr;
	__u64 size;
	__u32 type;
} __attribute__((packed));
```

After the information is called, the kernel prints a message about the available memory regions. You can find it in the [dmesg](https://en.wikipedia.org/wiki/Dmesg) output:

```
[    0.000000] e820: BIOS-provided physical RAM map:
[    0.000000] BIOS-e820: [mem 0x0000000000000000-0x000000000009fbff] usable
[    0.000000] BIOS-e820: [mem 0x000000000009fc00-0x000000000009ffff] reserved
[    0.000000] BIOS-e820: [mem 0x00000000000f0000-0x00000000000fffff] reserved
[    0.000000] BIOS-e820: [mem 0x0000000000100000-0x000000003ffdffff] usable
[    0.000000] BIOS-e820: [mem 0x000000003ffe0000-0x000000003fffffff] reserved
[    0.000000] BIOS-e820: [mem 0x00000000fffc0000-0x00000000ffffffff] reserved
```

### Keyboard initialization

Once memory detection is complete, the kernel proceeds with initializing the keyboard using the `keyboard_init`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/main.c#L64-L76 -->
```C
static void keyboard_init(void)
{
	struct biosregs ireg, oreg;

	initregs(&ireg);

	ireg.ah = 0x02;		/* Get keyboard status */
	intcall(0x16, &ireg, &oreg);
	boot_params.kbd_status = oreg.al;

	ireg.ax = 0x0305;	/* Set keyboard repeat rate */
	intcall(0x16, &ireg, NULL);
}
```

This function performs two tasks using [BIOS interrupt](https://en.wikipedia.org/wiki/BIOS_interrupt_call) `0x16`:

1. Gets the state of a keyboard which contains information about state of certain modifier keys, like for example Caps Lock active or not.
2. Sets the keyboard repeat rate which determines how long a key must hold down before it begins repeating

After the BIOS interrupt was executed, the keyboard should be initialized. If you are wondering why we need a working keyboard at such an early stage, the answer is - it can be used during the selection of the video mode. We will see more details in the [next chapter](linux-bootstrap-3.md).

### Gathering system information

After we went though the most essential hardware interfaces like CPU, I/O, memory map, keyboard, the next a couple of steps are to query the BIOS for additional information about the system. The information which kernel is going to gather is not strictly required for entering protected mode, but it provides useful details that later parts of the kernel may rely on. 

The following information is going to be collected:

- Information about [Intel SpeedStep](http://en.wikipedia.org/wiki/SpeedStep)
- Information about [Advanced Power Management](http://en.wikipedia.org/wiki/Advanced_Power_Management)
- Information about [Enhanced Disk Drive](https://en.wikipedia.org/wiki/INT_13H)

At this moment we will not dive into details about each of this query, but will get back to them in the next parts when we will use this information. For now, just let's take a short look at these functions:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/main.c#L163-L174 -->
```C
	/* Query Intel SpeedStep (IST) information */
	query_ist();

	/* Query APM information */
#if defined(CONFIG_APM) || defined(CONFIG_APM_MODULE)
	query_apm_bios();
#endif

	/* Query EDD information */
#if defined(CONFIG_EDD) || defined(CONFIG_EDD_MODULE)
	query_edd();
#endif
```

The first one is getting information about the [Intel SpeedStep](http://en.wikipedia.org/wiki/SpeedStep). This information is obtained by the calling the `0x15` BIOS interrupt and store the result in the `boot_params` structure. The returned information describes the support of the Intel SpeedStep and settings around it. If it is supported, this information will be passed later by the kernel to the power management subsystems.

The next one is getting information about the [Advanced Power Management](http://en.wikipedia.org/wiki/Advanced_Power_Management). The logic of this function is pretty similar to the one described above. It uses the same `0x15` BIOS interrupt to obtain information and store it in the `boot_params` structure. The returned information describes the support of the `APM` which was power management sub-system before [ACPI](https://en.wikipedia.org/wiki/ACPI) started to be a standard.

The last one function gets information about the `Enhanced Disk Drive` from the BIOS. The same `0x13` BIOS interrupt is used to obtain this information. The returned information describes the disks and their characteristics like geometry and mapping information.

## Conclusion

This is the end of the second part about Linux kernel insides. If you have questions or suggestions, feel free ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new). In the next part, we will continue to deal with the preparations before transitioning into protected mode and the transitioning itself.

## Links

Here is the list of the links that you may find useful during reading of this chapter:

- [Protected mode](http://en.wikipedia.org/wiki/Protected_mode)
- [Long mode](http://en.wikipedia.org/wiki/Long_mode)
- [The kernel's command-line parameters](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/kernel-parameters.rst)
- [Linux serial console](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/serial-console.rst)
- [BIOS interrupt](https://en.wikipedia.org/wiki/BIOS_interrupt_call)
- [Intel SpeedStep](http://en.wikipedia.org/wiki/SpeedStep)
- [APM](https://en.wikipedia.org/wiki/Advanced_Power_Management)
- [EDD specification](http://www.t13.org/documents/UploadedDocuments/docs2004/d1572r3-EDD3.pdf)
