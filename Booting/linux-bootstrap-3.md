# Kernel booting process. Part 3.

In the previous [part](./linux-bootstrap-2.md), we have seen first pieces of C code that run in the Linux kernel. One of the main goal of this stage is to switch into the [protected mode](https://en.wikipedia.org/wiki/Protected_mode), but before this, we have seen some early setup code which executes early initialization procedures, such as:

- Setup of console to be able to print messages from the kernel's setup code
- Validation of CPU
- Detection of available memory
- Initialization of keyboard

In this part we will continue to explore the next steps before we will see the transition into the protected mode.

## Video mode setup

Previously, we stopped right at the point where the kernel setup code was about to initialize the video mode. 

The setup code is located in the [arch/x86/boot/video.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/video.c) and implemented by the `set_video` function. Now let's take a look at the implementation of the `set_video` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/video.c#L317-L343 -->
```C
void set_video(void)
{
	u16 mode = boot_params.hdr.vid_mode;

	RESET_HEAP();

	store_mode_params();
	save_screen();
	probe_cards(0);

	for (;;) {
		if (mode == ASK_VGA)
			mode = mode_menu();

		if (!set_mode(mode))
			break;

		printf("Undefined video mode number: %x\n", mode);
		mode = ASK_VGA;
	}
	boot_params.hdr.vid_mode = mode;
	vesa_store_edid();
	store_mode_params();

	if (do_restore)
		restore_screen();
}
```

Let's try to understand what this function does in the next sections.

### Video modes

The implementation of the `set_video` function starts by getting the video mode from the `boot_params.hdr` structure:

```C
u16 mode = boot_params.hdr.vid_mode;
```

> [!NOTE] 
> Instead of old good standard C data types like `int`, `short`, `unsigned short`, Linux kernel provides own data types for numeric values. Here is the table that will help you to remember them:
>
> | Type | char | short | int | long | u8 | u16 | u32 | u64 |
> |------|------|-------|-----|------|----|-----|-----|-----|
> | Size |  1   |   2   |  4  |   8  |  1 |  2  |  4  |  8  |

The initial value of the video mode can be filled by the bootloader. This header field defined in the Linux kernel boot protocol:

```
Offset	Proto	Name		Meaning
/Size
01FA/2	ALL	    vid_mode	Video mode control
```

Information about potential values for this field can be also found in the Linux kernel boot protocol document:

```
vga=<mode>
	<mode> here is either an integer (in C notation, either
	decimal, octal, or hexadecimal) or one of the strings
	"normal" (meaning 0xFFFF), "ext" (meaning 0xFFFE) or "ask"
	(meaning 0xFFFD). This value should be entered into the
	vid_mode field, as it is used by the kernel before the command
	line is parsed.
```

This tells us that we can add the `vga` option to the GRUB (or another bootloader's) configuration file and it will pass this option to the kernel command line. This option can have different values as mentioned in the description above. For example, it can be an integer number `0xFFFD` or `ask`. If you pass `ask` to `vga`, you will see a menu with the possible video modes. We can test it using [QEMU](https://www.qemu.org/) virtual machine:

```bash
sudo qemu-system-x86_64 -kernel ./linux/arch/x86/boot/bzImage                \
                        -nographic                                           \
                        -append "console=ttyS0 nokaslr vga=ask"              \
                        -initrd /boot/initramfs-6.17.0-rc3-g1b237f190eb3.img 
```

If you did everything correctly, after the kernel is loaded it will ask you to press the `ENTER`. By pressing on it you should see something like this:

```
Booting from ROM...
Probing EDD (edd=off to disable)... ok
Press <ENTER> to see video modes available, <SPACE> to continue, or wait 30 sec
Mode: Resolution:  Type: Mode: Resolution:  Type: Mode: Resolution:  Type: 
0 F00   80x25      VGA   1 F01   80x50      VGA   2 F02   80x43      VGA   
3 F03   80x28      VGA   4 F05   80x30      VGA   5 F06   80x34      VGA   
6 F07   80x60      VGA   7 340  320x200x32  VESA  8 341  640x400x32  VESA  
9 342  640x480x32  VESA  a 343  800x600x32  VESA  b 344 1024x768x32  VESA  
c 345 1280x1024x32 VESA  d 347 1600x1200x32 VESA  e 34C 1152x864x32  VESA  
f 377 1280x768x32  VESA  g 37A 1280x800x32  VESA  h 37D 1280x960x32  VESA  
i 380 1440x900x32  VESA  j 383 1400x1050x32 VESA  k 386 1680x1050x32 VESA  
l 389 1920x1200x32 VESA  m 38C 2560x1600x32 VESA  n 38F 1280x720x32  VESA  
o 392 1920x1080x32 VESA  p 300  640x400x8   VESA  q 301  640x480x8   VESA  
r 303  800x600x8   VESA  s 305 1024x768x8   VESA  t 307 1280x1024x8  VESA  
u 30D  320x200x15  VESA  v 30E  320x200x16  VESA  w 30F  320x200x24  VESA  
x 310  640x480x15  VESA  y 311  640x480x16  VESA  z 312  640x480x24  VESA  
  313  800x600x15  VESA    314  800x600x16  VESA    315  800x600x24  VESA  
  316 1024x768x15  VESA    317 1024x768x16  VESA    318 1024x768x24  VESA  
  319 1280x1024x15 VESA    31A 1280x1024x16 VESA    31B 1280x1024x24 VESA  
  31C 1600x1200x8  VESA    31D 1600x1200x15 VESA    31E 1600x1200x16 VESA  
  31F 1600x1200x24 VESA    346  320x200x8   VESA    348 1152x864x8   VESA  
  349 1152x864x15  VESA    34A 1152x864x16  VESA    34B 1152x864x24  VESA  
  375 1280x768x16  VESA    376 1280x768x24  VESA    378 1280x800x16  VESA  
  379 1280x800x24  VESA    37B 1280x960x16  VESA    37C 1280x960x24  VESA  
  37E 1440x900x16  VESA    37F 1440x900x24  VESA    381 1400x1050x16 VESA  
  382 1400x1050x24 VESA    384 1680x1050x16 VESA    385 1680x1050x24 VESA  
  387 1920x1200x16 VESA    388 1920x1200x24 VESA    38A 2560x1600x16 VESA  
  38B 2560x1600x24 VESA    38D 1280x720x16  VESA    38E 1280x720x24  VESA  
  390 1920x1080x16 VESA    391 1920x1080x24 VESA    393 1600x900x16  VESA  
  394 1600x900x24  VESA    395 1600x900x32  VESA    396 2560x1440x16 VESA  
  397 2560x1440x24 VESA    398 2560x1440x32 VESA    399 3840x2160x16 VESA  
  200   40x25      VESA    201   40x25      VESA    202   80x25      VESA  
  203   80x25      VESA    207   80x25      VESA    213  320x200x8   VESA  
Enter a video mode or "scan" to scan for additional modes: 
```

### Early heap API

Before proceeding further to investigate what the `set_video` function does, it will be useful to take a look at the API for the management of the kernel's early heap. 

After getting the video mode set by the bootloader, we can see resetting the heap value by the `RESET_HEAP` macro. The definition of this macro is in the [arch/x86/boot/boot.h](https://github.com/torvalds/linux/blob/master/arch/x86/boot/boot.h):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/boot.h#L174-L174 -->
```C
#define RESET_HEAP() ((void *)( HEAP = _end ))
```

If you have read the [part](./linux-bootstrap-2.md#kernel-booting-process-part-2), you should remember that we have seen initialization of the heap memory area.The kernel setup code provides a couple of utility macros and functions for managing the early heap. Let's take a look at some of them, especially at ones which we will meet in this chapter.

The `RESET_HEAP` macro resets the heap by setting the `HEAP` variable to the `_end` which represents the end of the early setup kernel's `text` (or code) section. By doing this we just set the heap pointer to the very beginning of the heap.

The next useful macro is:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/boot.h#L184-L185 -->
```C
#define GET_HEAP(type, n) \
	((type *)__get_heap(sizeof(type),__alignof__(type),(n)))
```

The goal of this macro is to allocate memory on the early heap. This macro calls the `__get_heap` function from the same header file with the following three parameters:

- The size of the datatype to be allocated for
- Specifies how variables of this type are to be aligned
- How many items specified by the first parameter to allocate

The implementation of `__get_heap` is:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/boot.h#L175-L183 -->
```C
static inline char *__get_heap(size_t s, size_t a, size_t n)
{
	char *tmp;

	HEAP = (char *)(((size_t)HEAP+(a-1)) & ~(a-1));
	tmp = HEAP;
	HEAP += s*n;
	return tmp;
}
```

Let's try to understand how the `__get_heap` function works. First of all we can see here that `HEAP` pointer is assigned to the [aligned](https://en.wikipedia.org/wiki/Data_structure_alignment) address of the memory. The address is aligned based on the size of data type for which we want to allocate memory. After we have got the initial aligned address, we just move the `HEAP` pointer by the requested size.

The last but not least API of the early heap that we will see is the `heap_free` function which checks the availability of the given size of memory on the heap:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/boot.h#L187-L190 -->
```C
static inline bool heap_free(size_t n)
{
	return (int)(heap_end-HEAP) >= (int)n;
}
```

As you may see, the implementation of this function is pretty trivial. It just subtracts the current value of the heap pointer from the address which represents the end of heap memory area. The function returns `true` if there is enough memory for `n` or `false` otherwise.

### Return to the setup of the video mode

Since the heap pointer is in the right place, we can move directly to video mode initialization. The next step after this is the call to  `store_mode_params` function which stores currently available video mode parameters in the `boot_params.screen_info`. This structure defined in the [include/uapi/linux/screen_info.h](https://github.com/torvalds/linux/blob/master/include/uapi/linux/screen_info.hh) header file and provides basic information about the screen and video mode. Such as current position of the cursor, the BIOS video mode number that was set when the kernel was loaded, the number of text rows and columns and so on. The `store_mode_params` function asks the BIOS services about this information and stores it in this structure for later usage.

The next step is save the current contents of the screen to the heap by calling the `save_screen` function. This function collects all the data which we got in the previous functions (like the rows and columns, and stuff) and stores it in the `saved_screen` structure, which is defined as:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/video.c#L233-L237 -->
```C
static struct saved_screen {
	int x, y;
	int curx, cury;
	u16 *data;
} saved;
```

After the contents of the screen is saved, the next step is to collect currently available video modes in the system. This job is done by the `probe_cards` function defined in the [arch/x86/boot/video-mode.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/video-mode.c). It goes over all `video_cards` and collects the information about them:

```C
for (card = video_cards; card < video_cards_end; card++) {
  /* collecting the number of video modes */
}
```

The `video_cards` is an array defined as:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/video.h#L81-L82 -->
```C
#define __videocard struct card_info __section(".videocards") __attribute__((used))
extern struct card_info video_cards[], video_cards_end[];
```

The `__videocard` macro allows to define structures which describe video cards and the linker will put them into the `video_cards` array. Example of such structure can be found in the [arch/x86/boot/video-vga.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/video-vga.c):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/video-vga.c#L282-L286 -->
```C
static __videocard video_vga = {
	.card_name	= "VGA",
	.probe		= vga_probe,
	.set_mode	= vga_set_mode,
};
```

After the `probe_cards` function executes we have a bunch of structures in our `video_cards` array and the known number of video modes they provide. At the next step the kernel setup code will print menu with available video modes if the `vid_mode=ask` option was passed to the kernel command line and set up the video mode having all the parameters that we have gathered at the previous steps. The video mode is set by the `set_mode` function is defined in [video-mode.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/video-mode.c). This function expects one parameter - the video mode identifier. This identifier is set by the bootloader or set based on the choice of the video modes menu. The `set_mode` function goes over all available video cards defined in the `video_cards` array and if the given mode belongs to the given card, the `card->set_mode()` callback is called to setup the video mode.

Let's take a look at the example of setting up [VGA](https://en.wikipedia.org/wiki/Video_Graphics_Array) video mode:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/video-vga.c#L191-L224 -->
```C
static int vga_set_mode(struct mode_info *mode)
{
	/* Set the basic mode */
	vga_set_basic_mode();

	/* Override a possibly broken BIOS */
	force_x = mode->x;
	force_y = mode->y;

	switch (mode->mode) {
	case VIDEO_80x25:
		break;
	case VIDEO_8POINT:
		vga_set_8font();
		break;
	case VIDEO_80x43:
		vga_set_80x43();
		break;
	case VIDEO_80x28:
		vga_set_14font();
		break;
	case VIDEO_80x30:
		vga_set_80x30();
		break;
	case VIDEO_80x34:
		vga_set_80x34();
		break;
	case VIDEO_80x60:
		vga_set_80x60();
		break;
	}

	return 0;
}
```

The `vga_set_mode` function is responsible for configuring the VGA display to a specific text mode, based on the settings which we collected in the previous steps. The `vga_set_basic_mode` function resets the VGA hardware into a standard text mode. The next statement sets up the video mode based on the video mode that was selected. Most of these functions have very similar implementation based on the `0x10` BIOS interrupt.

After this step, the video mode is configured and we save all the information about it again for later use. Having done this, the video mode setup is complete and now we can take a look at the last preparation before we will see the switch into the protected mode.

## Last preparation before transition into protected mode

Returning to the [`main`](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c) function of the early kernel setup code, we finally can see:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/main.c#L179-L180 -->
```C
	/* Do the last things and invoke protected mode */
	go_to_protected_mode();
```

As the comment says: `Do the last things and invoke protected mode`, so let's see what these last things are and switch into protected mode.

The `go_to_protected_mode` function is defined in [arch/x86/boot/pm.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/pm.c). It contains some routines which make the last preparations before we can jump into protected mode, so let's look at it and try to understand what it does and how it works.

The very first function that we may see in the `go_to_protected_mode` is the `realmode_switch_hook` function.  This function invokes the real mode switch hook if it is present or disables [NMI](http://en.wikipedia.org/wiki/Non-maskable_interrupt) otherwise. The hooks are used if the bootloader runs in a hostile environment. You can read more about hooks in the [boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt) (see **ADVANCED BOOT LOADER HOOKS**). Interrupts must be disabled before switching to protected mode because otherwise the CPU could receive an interrupt when there is no valid interrupt table or handlers. Once the kernel will set up the protected-mode interrupt infrastructure, interrupts will be disabled again.

We will consider only more-less standard use case, when the bootloader does not provide any hooks. So we just disable non-maskable interrupts:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pm.c#L28-L30 -->
```assembly
		asm volatile("cli");
		outb(0x80, 0x70); /* Disable NMI */
		io_delay();
```

At the first line, there is an [inline assembly](../Theory/linux-theory-3.md) statement with the `cli` instruction which clears the [interrupt flag](https://en.wikipedia.org/wiki/Interrupt_flag). After this, external interrupts are disabled. The next line disables NMI (non-maskable interrupt). An interrupt is a signal to the CPU which is emitted by hardware or software. After getting such a signal, the CPU suspends the current instruction sequence, saves its state and transfers control to the interrupt handler. After the interrupt handler has finished its work, it transfers control back to the interrupted instruction. Non-maskable interrupts (NMI) are interrupts which are always processed, independently of permission. They cannot be ignored and are typically used to signal for non-recoverable hardware errors. We will not dive into the details of interrupts now but we will be discussing them in the next posts.

Let's get back to the code. We can see in the second line that we are writing the byte `0x0` to the port `0x80`. After that, a call to the `io_delay` function occurs. `io_delay` causes a small delay and looks like:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/boot.h#L39-L43 -->
```C
static inline void io_delay(void)
{
	const u16 DELAY_PORT = 0x80;
	outb(0, DELAY_PORT);
}
```

To output any byte to the port `0x80` should delay exactly 1 microsecond. This delay is needed to be sure that the change of the NMI mask has fully taken effect. After this delay, the `realmode_switch_hook` function has finished execution and we can be sure that all interrupts are disabled.

The next step is the `enable_a20` function, which enables the [A20 line](http://en.wikipedia.org/wiki/A20_line). Enabling of this line allows kernel to have access above 1 MB.

The `enable_a20` function is defined in [arch/x86/boot/a20.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/a20.c) and tries to enable the `A20` gate using the different approaches. The first is the `a20_test_short` function which checks if `A20` is already enabled or not using the `a20_test` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/a20.c#L54-L74 -->
```C
static int a20_test(int loops)
{
	int ok = 0;
	int saved, ctr;

	set_fs(0x0000);
	set_gs(0xffff);

	saved = ctr = rdfs32(A20_TEST_ADDR);

	while (loops--) {
		wrfs32(++ctr, A20_TEST_ADDR);
		io_delay();	/* Serialize and make delay constant */
		ok = rdgs32(A20_TEST_ADDR+0x10) ^ ctr;
		if (ok)
			break;
	}

	wrfs32(saved, A20_TEST_ADDR);
	return ok;
}
```

To verify whether the `A20` line is already enabled or not, the kernel performs a simple memory test. It begins by setting the `FS` register to `0x0000` and the `GS` register to `0xffff` values. By doing this, an access to `FS:0x200` (`A20_TEST_ADDR`) points into the very beginning of memory, while an access to `GS:0x2010` refers to a location just past the one-megabyte boundary. If the `A20` line is disabled, the latter will wrap around and point to the same physical address.

If the `A20` gate is disabled, the kernel will try to enable it using different methods which you can find in `enable_a20` function. For example, it can be done with a call to the `0x15` BIOS interrupt with `AH` register set to `0x2041`. If this function finished with a failure, print an error message and call the function `die` which will stop the process of the kernel setup.

After the `A20` gate is successfully enabled, the `reset_coprocessor` function is called:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pm.c#L48-L54 -->
```C
static void reset_coprocessor(void)
{
	outb(0, 0xf0);
	io_delay();
	outb(0, 0xf1);
	io_delay();
}
```

This function resets the [math coprocessor](https://en.wikipedia.org/wiki/Floating-point_unit) to be sure it is in a clean state by writing `0` to `0xF0` and then resets it by writing `0` to `0xF1`.

The next step is the `mask_all_interrupts` function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pm.c#L37-L43 -->
```C
static void mask_all_interrupts(void)
{
	outb(0xff, 0xa1);	/* Mask all interrupts on the secondary PIC */
	io_delay();
	outb(0xfb, 0x21);	/* Mask all but cascade on the primary PIC */
	io_delay();
}
```

This function masks or in other words forbids all interrupts on the primary and secondary [PICs](https://en.wikipedia.org/wiki/Programmable_interrupt_controller). This is needed for safeness, we forbid all the interrupts from the `PIC` so nothing can interrupt the CPU while the kernel is doing transition into protected mode.

All the operations before this point, were executed for safe transition to the protected mode. The next operations will prepare the transition to the protected mode. Let's take a look at them.

## Entering Protected Mode

At this point, we are very close to see the switching into protected mode of the Linux kernel. 

Only two steps remain:

- Setting up the Interrupt Descriptor Table
- Setting up the Global Descriptor Table

And that’s all! Once these two structures will be configured, the Linux kernel can make the jump into protected mode.

### Set up the Interrupt Descriptor Table

Before the CPU can safely enter protected mode, it needs to know where to find the handlers that will be triggered in a case of [interrupts and exceptions](https://en.wikipedia.org/wiki/Interrupt). In real mode, the CPU relies on the [Interrupt Vector Table](https://en.wikipedia.org/wiki/Interrupt_vector_table). In the protected mode this mechanism changes to the Interrupt Descriptor Table. 

This is a special structure located in memory which contains descriptors that describes where CPU can find handlers for interrupts and exceptions. The full description of Interrupt Description Table and its entries we will see later, because for now we anyway disabled all the interrupts at the previous steps. Let's take a look at the function which setups zero filled Interrupt Descriptor Table:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pm.c#L94-L98 -->
```C
static void setup_idt(void)
{
	static const struct gdt_ptr null_idt = {0, 0};
	asm volatile("lidtl %0" : : "m" (null_idt));
}
```

As we may see, it just load the IDT which is filled with zero using the `lidtl` instruction. The `null_idt` has type `gdt_ptr` which is structure defined in the same source code file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pm.c#L60-L63 -->
```C
struct gdt_ptr {
	u16 len;
	u32 ptr;
} __attribute__((packed));
```

This structure provides information about the pointer to the Interrupt Descriptor Table.

### Set up Global Descriptor Table

The next is the setup of the Global Descriptor Table. As you may remember, the memory access is based on `segment:offset` addressing in real mode. The protected mode introduces the different model based on the `Global Descriptor Table`. If you forgot the details about the Global Description Table structure, you can find more information in the [previous chapter](./linux-bootstrap-2.md#protected-mode). Instead of fixed segment bases and limits, the CPU now looks for memory regions defined by descriptors located in the Global Descriptor Table. The goal of kernel is to setup these descriptors.

All the job will be done by the `setup_gdt` function which is defined in the same source code file. Let's take a look at the definition of this function:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pm.c#L65-L89 -->
```C
static void setup_gdt(void)
{
	/* There are machines which are known to not boot with the GDT
	   being 8-byte unaligned.  Intel recommends 16 byte alignment. */
	static const u64 boot_gdt[] __attribute__((aligned(16))) = {
		/* CS: code, read/execute, 4 GB, base 0 */
		[GDT_ENTRY_BOOT_CS] = GDT_ENTRY(DESC_CODE32, 0, 0xfffff),
		/* DS: data, read/write, 4 GB, base 0 */
		[GDT_ENTRY_BOOT_DS] = GDT_ENTRY(DESC_DATA32, 0, 0xfffff),
		/* TSS: 32-bit tss, 104 bytes, base 4096 */
		/* We only have a TSS here to keep Intel VT happy;
		   we don't actually use it for anything. */
		[GDT_ENTRY_BOOT_TSS] = GDT_ENTRY(DESC_TSS32, 4096, 103),
	};
	/* Xen HVM incorrectly stores a pointer to the gdt_ptr, instead
	   of the gdt_ptr contents.  Thus, make it static so it will
	   stay in memory, at least long enough that we switch to the
	   proper kernel GDT. */
	static struct gdt_ptr gdt;

	gdt.len = sizeof(boot_gdt)-1;
	gdt.ptr = (u32)&boot_gdt + (ds() << 4);

	asm volatile("lgdtl %0" : : "m" (gdt));
}
```

The initial memory descriptors specified by the items of the `boot_gdt` array. The `setup_gdt` function just loads the pointer to the Global Descriptor Table filled with these items using the `lgdtl` instruction. Let's take a closer look at the memory descriptors definition.

Initially, the 3 memory descriptors specified:

- Code segment
- Memory segment
- Task state segment

We will skip the description of the task state segment for now as it was added there to make [Intel VT](https://en.wikipedia.org/wiki/X86_virtualization#Intel_virtualization_(VT-x)) happy. The other two segments belongs to the memory for kernel code and data sections. Both memory descriptors defined using the `GDT_ENTRY` macro. This macro defined in the [arch/x86/include/asm/segment.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/segment.h) and expects to get three arguments:

- `flags`
- `base`
- `limit`

Let's take a look at the definition of the code memory segment:

```C
[GDT_ENTRY_BOOT_CS] = GDT_ENTRY(DESC_CODE32, 0, 0xfffff),
```

The base address of this memory segment is defined as `0` and limit as `0xFFFFF` or 1 Megabyte. The `DESC_CODE32` describes the flags of this segment. If we take a look at the flags, we will see that granularity (bit `G`) of this segment is set to 4 KB units. This means that the segment covers addresses `0x00000000–0xFFFFFFFF` - entire 4 GB linear address space. The same base address and limit will be defined for the data segment. It is done this way because Linux kernel using so-called [flat memory model](https://en.wikipedia.org/wiki/Flat_memory_model).

Besides the granularity bit, the `DESC_CODE32` specifies other flags. Among them you can find, the this a 32-bit segment which is readable, executable and present in memory. The privilege level is set to the highest value as kernel needs.

Looking at the documentation of the Global Descriptor Table and its entries you can check all the initial segments by yourself. It is not so hard.

## Transition into protected mode

We are standing right before it. Interrupts are disabled, the Interrupt Descriptor Table and Global Descriptor Table are initialized. Finally, the kernel can execute jump into protected mode. But despite good news, we need to return to assembly again 😅

The transition to the protected mode we can find in the [arch/x86/boot/pmjump.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/pmjump.S). Let's take a look at it:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pmjump.S#L24-L39 -->
```assembly
SYM_FUNC_START_NOALIGN(protected_mode_jump)
	movl	%edx, %esi		# Pointer to boot_params table

	xorl	%ebx, %ebx
	movw	%cs, %bx
	shll	$4, %ebx
	addl	%ebx, 2f
	jmp	1f			# Short jump to serialize on 386/486
1:

	movw	$__BOOT_DS, %cx
	movw	$__BOOT_TSS, %di

	movl	%cr0, %edx
	orb	$X86_CR0_PE, %dl	# Protected mode
	movl	%edx, %cr0
```

First of all, we preserve the address of `boot_params` structure in the `esi` register. After this, we compute the real-mode segment base of the current code and add it to the value pointed to by the `2f` label which is the entry point to the protected mode. This is needed because as you remember at the previous step, the code memory segment starts from `0`, so the jump instruction must contain absolute linear address of the entry point.

At the next steps we save the segment addresses of the data and task state in general purpose registers `cx` and `di` and set the `PE` bit in the control `cr0` register. From this point, the protected mode is turned on, and we need just to jump into it, to set proper value of the code segment:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pmjump.S#L41-L44 -->
```assembly
	# Transition to 32-bit mode
	.byte	0x66, 0xea		# ljmpl opcode
2:	.long	.Lin_pm32		# offset
	.word	__BOOT_CS		# segment
```

The kernel is in protected mode now 🥳🥳🥳

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pmjump.S#L47-L49 -->
```assembly
	.code32
	.section ".text32","ax"
SYM_FUNC_START_LOCAL_NOALIGN(.Lin_pm32)
```

Let's look at the first steps taken in the protected mode. First of all we set up the data segment with the data segment address that we preserved in the `cx` register at the previous step:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pmjump.S#L50-L55 -->
```assembly
	# Set up data segments for flat 32-bit mode
	movl	%ecx, %ds
	movl	%ecx, %es
	movl	%ecx, %fs
	movl	%ecx, %gs
	movl	%ecx, %ss
```

Since we are in the protected mode, our segment bases point to zero. Because of this, the stack pointer will point somewhere below the code, so we need to adjust it, at least for debugging purposes:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pmjump.S#L58-L58 -->
```assembly
	addl	%ebx, %esp
```

The last step before the jump into actual 32-bit entry point is to clear the general purpose registers:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pmjump.S#L65-L69 -->
```assembly
	xorl	%ecx, %ecx
	xorl	%edx, %edx
	xorl	%ebx, %ebx
	xorl	%ebp, %ebp
	xorl	%edi, %edi
```

Now everything is ready. The kernel is in the protected mode and we can jump to the next code, address of which was passed in the `eax` register:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/pmjump.S#L74-L74 -->
```assembly
	jmpl	*%eax			# Jump to the 32-bit entrypoint
```

## Conclusion

This is the end of the third part about Linux kernel insides. If you have questions or suggestions, feel free ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).

## Links

Here is the list of the links that you may find useful during reading of this chapter:

- [QEMU](https://www.qemu.org/)
- [VGA](http://en.wikipedia.org/wiki/Video_Graphics_Array)
- [VESA BIOS Extensions](http://en.wikipedia.org/wiki/VESA_BIOS_Extensions)
- [Data structure alignment](http://en.wikipedia.org/wiki/Data_structure_alignment)
- [Non-maskable interrupt](http://en.wikipedia.org/wiki/Non-maskable_interrupt)
- [A20](http://en.wikipedia.org/wiki/A20_line)
- [Math coprocessor](https://en.wikipedia.org/wiki/Floating-point_unit)
- [PIC](https://en.wikipedia.org/wiki/Programmable_interrupt_controller)
- [Interrupts and exceptions](https://en.wikipedia.org/wiki/Interrupt)
- [Interrupt Vector Table](https://en.wikipedia.org/wiki/Interrupt_vector_table)
- [Protected mode](https://en.wikipedia.org/wiki/Protected_mode)
- [Intel VT](https://en.wikipedia.org/wiki/X86_virtualization#Intel_virtualization_(VT-x))
- [Flat memory model](https://en.wikipedia.org/wiki/Flat_memory_model)
- [Previous part](linux-bootstrap-2.md)
