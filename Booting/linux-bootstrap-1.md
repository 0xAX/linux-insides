# Kernel Booting Process — Part 1

If you’ve read my earlier [posts](https://github.com/0xAX/asm) about [assembly language](https://en.wikipedia.org/wiki/Assembly_language) for Linux x86_64, you might see that I started to get interested in low-level programming. I’ve written a set of articles on assembly programming for [x86_64](https://en.wikipedia.org/wiki/X86-64) Linux and, in parallel, began exploring the Linux kernel source code. I’ve always been fascinated by what happens under the hood — how programs execute on a CPU, how they’re laid out in memory, how the kernel schedules processes and manages resources, how the network stack operates at a low level, and many other details. This series is a way of sharing my journey.

> [!NOTE]
> This is not official Linux kernel documentation, it is a learning project. I’m not a professional Linux kernel developer, and I don’t write kernel code as part of my daily job. Learning how the Linux kernel works is just my hobby. If you find anything unclear, spot an error, or have questions or suggestions, feel free to reach out - you always can ping me on X [0xAX](https://twitter.com/0xAX), send me an [email](mailto:anotherworldofworld@gmail.com) or open a new [issue](https://github.com/0xAX/linux-insides/issues/new). Your feedback is always welcome and appreciated.

The main goal of this series is to provide a guide to the Linux kernel for readers who want to begin learning how it works. We will explore not only what the kernel does, but will try to understand how and why it does it. Despite being considered to be understandable for anyone who is interested in Linux kernel, it is highly recommended to have some prior knowledge before starting to read these notes. If you want to experiment with the kernel code, first of all it is best to have a [Linux distribution](https://en.wikipedia.org/wiki/Linux_distribution) installed. Besides that, on these pages we will see much of [C](https://en.wikipedia.org/wiki/C_(programming_language)) and [assembly](https://en.wikipedia.org/wiki/Assembly_language) code, so the good understanding of these programming languages is highly required.

> [!IMPORTANT]
> I started writing this series when the latest version of the kernel was `3.18`. A lot has changed since then, and I am in the process of updating the content to reflect modern kernels where possible — now focusing on v6.16+. I’ll continue revising the posts as the kernel evolves.

That’s enough introduction — let’s dive into the Linux kernel!

## The Magic Power Button - What happens next?

Although this is a series of posts about Linux kernel, we will not jump straight into kernel code. First, let’s step back and look at what happens before the kernel even comes into play. Everything starts from the turning on a computer. And we will start from this point as well.

When you press the "magic" power button on your laptop or desktop computer, the [motherboard](https://en.wikipedia.org/wiki/Motherboard) sends a signal to the [power supply](https://en.wikipedia.org/wiki/Power_supply). In response, the power supply delivers the proper amount of electricity to other components of the computer. Once the motherboard receives the [power good signal](https://en.wikipedia.org/wiki/Power_good_signal), it triggers the CPU to start. The CPU then performs a reset: it clears any leftover data in its registers and loads predefined values into each of them, preparing for the very first instructions of the boot process.

Each **x86_64** processor begins execution in a special mode called [real mode](https://en.wikipedia.org/wiki/Real_mode). This mode exists for historical reasons - to be compatible with the earliest processors. Real mode is supported on all x86-compatible processors — from the original [8086](https://en.wikipedia.org/wiki/Intel_8086) to today’s modern 64-bit CPUs.

The **8086** was a 16-bit microprocessor. Basically it means that its general-purpose registers and instruction pointer were `16` bits wide. However, the chip was designed with a `20-bit` physical memory address bus — the set of electrical lines used to select memory locations. With `20` address lines, the CPU can form addresses from `0x00000` to `0xFFFFF`, giving access to exactly `1 MB` of physical memory or `2^20` bytes.

Because the registers on **8086** processors were only `16` bits wide, the largest value they could hold was `0xFFFF` which equals 64 KB. This means that, using just a single 16-bit value, the CPU could only directly address 64 KB of memory at a time. This leads us to the question - how can a processor with 16-bit registers access 20-bit addresses? The answer is [memory segmentation](https://en.wikipedia.org/wiki/Memory_segmentation).

To make use of the entire 1 MB space provided by the 20-bit address bus, the **8086** used a scheme called [memory segmentation](https://en.wikipedia.org/wiki/Memory_segmentation). All memory is divided into small, fixed-size segments of `65_536` bytes each. Instead of using just one value to identify a memory location, a CPU uses the two:

1. Segment selector — identifies the starting point (base address) of a 64 KB segment. Represented by the value of the `cs` (code-segment) register.
2. Offset — specifies how far into that segment the target address is. Represented by the value of the `ip` register.

In real mode, the base address for a given segment selector is calculated as:

```
Base Address = Segment Selector << 4
```

To compute the final physical memory address, the CPU adds the base address to the offset:

```
Physical Address = Base Address + Offset
```

For example, if the value of the `cs:ip` is `0x2000:0x0010`, then the corresponding physical address will be:

```python
>>> hex((0x2000 << 4) + 0x0010)
'0x20010'
```

If we take the largest possible values for the segment selector and the offset - `0xFFFF:0xFFFF`, the resulting address will be:

```python
>>> hex((0xffff << 4) + 0xffff)
'0x10ffef'
```

This gives us the address `0x10FFEF`, which is `65_520` bytes past the 1 MB boundary. Since, in real mode on the original **8086** CPU, the CPU could only access the first 1 MB of memory, any address above `0xFFFFF` would wrap around back to the beginning of the address space. On modern **386+** CPUs the physical bus is wider even in real mode, but the address computation still based on the `segment:offset`.

Now that we understand the basics of real mode and its memory addressing limitations, let’s return to the state after a hardware reset.

## First code executed after reset

The system has just been powered on, the reset signal has been released, and the processor is waking up to execute first instructions. The [80386](https://en.wikipedia.org/wiki/Intel_80386) and later CPUs set the following [register](https://en.wikipedia.org/wiki/X86#x86_registers) values after a hardware reset:

| Register           | Value        | Meaning                                                                        |
| ------------------ | ------------ | ------------------------------------------------------------------------------ |
| `ip`               | `0xFFF0`     | Instruction pointer; execution starts here within the current code segment     |
| `cs` (selector)    | `0xF000`     | Visible code segment selector value after reset                                |
| `cs` (base)        | `0xFFFF0000` | Hidden descriptor base address loaded into `cs` during reset                   |

In real mode, the base address is normally formed by shifting the 16-bit segment selector value 4 bits left to produce a 20-bit physical address. However, after the hardware reset the first instruction will be located at the special address. We may see that the segment selector in the `cs` register is loaded with `0xF000` but the hidden base address is loaded with `0xFFFF0000`. Instead of using the usual formula to get the address, the processor uses this value as the base address of the first instruction. Having the value of the base address and the offset (from the `ip` register), the starting address will be:

```python
>>> hex(0xffff0000 + 0xfff0)
'0xfffffff0'
```

We got `0xFFFFFFF0`, which is 16 bytes below 4GB. This is the very first address where the CPU starts the execution after reset. This address has special name - [reset vector](https://en.wikipedia.org/wiki/Reset_vector). It is the memory location at which the CPU expects to find the first instruction to execute after reset. Usually it contains a [jump](https://en.wikipedia.org/wiki/JMP_%28x86_instruction%29) (`jmp`) instruction which points to the [BIOS](https://en.wikipedia.org/wiki/BIOS) or [UEFI](https://en.wikipedia.org/wiki/UEFI) entry point. For example, if we take a look at the [source code](https://github.com/coreboot/coreboot/blob/main/src/cpu/x86/reset16.S) of the [coreboot](https://www.coreboot.org/), we will see it there:

<!-- https://raw.githubusercontent.com/coreboot/coreboot/refs/heads/main/src/cpu/x86/entry16.S#L155-L159 -->
```assembly
  /* This is the first instruction the CPU runs when coming out of reset. */
.section ".reset", "ax", %progbits
.globl _start
_start:
	jmp		_start16bit
```

To prove that this code is located at the `0xFFFFFFF0` address, we may take a look at the [linker script](https://github.com/coreboot/coreboot/blob/master/src/arch/x86/bootblock.ld):

<!-- https://raw.githubusercontent.com/coreboot/coreboot/refs/heads/master/src/arch/x86/bootblock.ld#L72-L78 -->
```linker-script
	. = 0xfffffff0;
	_X86_RESET_VECTOR = .;
	.reset . : {
		*(.reset);
		. = _X86_RESET_VECTOR_FILLING;
		BYTE(0);
	}
```

The address `0xFFFFFFF0` is much larger than `0xFFFFF` (1MB). How can the CPU access this address in real mode? The answer is simple. Most likely you have something more modern than **8086** CPU with 20-bit address bus. More modern processors starts in real mode but with 32-bit or 64-bit bus.

When the CPU wakes up, it reads the jump at the `0xFFFFFFF0` address, jump into the firmware, and the long chain of the boot process begins. This is the very first step on the way to boot the Linux kernel.

## From Power-On to Bootloader

We stopped at the point when a CPU jumps from the reset vector to the firmware. On a legacy PC, that means the BIOS. On modern computers it is UEFI. In the next chapters we will see the booting processes on a legacy PC using the BIOS, and later UEFI.

The first job of BIOS is to bring the system into a working state. It runs a series of hardware checks and initializations — memory tests, peripheral setup, chipset configuration — all part of the [POST](https://en.wikipedia.org/wiki/Power-on_self-test) routine. Once everything is checked, the next step is to find an operating system to boot. The BIOS doesn’t pick just a random disk. It follows a boot order, a list stored in its configuration.

When the BIOS tries to boot from a hard drive, it looks for a [boot sector](https://en.wikipedia.org/wiki/Boot_sector). On hard drives partitioned with an [MBR partition layout](https://en.wikipedia.org/wiki/Master_boot_record), the boot sector is stored in the first `446` bytes of the first sector, where each sector is `512` bytes. The final two bytes of the first sector must be `0x55` and `0xAA`. These two last bytes says to BIOS somewhat like "yes - this device is bootable". Once the BIOS finds the valid boot sector, it copies it into the fixed memory location at `0x7C00`, jumps to there and start executing it.

In general, real mode's memory map is as follows:

| Address Range         | Description                          |
|-----------------------|--------------------------------------|
| 0x00000000–0x000003FF | Real Mode Interrupt Vector Table     |
| 0x00000400–0x000004FF | BIOS Data Area                       |
| 0x00000500–0x00007BFF | Unused                               |
| 0x00007C00–0x00007DFF | Bootloader                           |
| 0x00007E00–0x0009FFFF | Unused                               |
| 0x000A0000–0x000BFFFF | Video RAM (VRAM) Memory              |
| 0x000B0000–0x000B7777 | Monochrome Video Memory              |
| 0x000B8000–0x000BFFFF | Color Video Memory                   |
| 0x000C0000–0x000C7FFF | Video ROM BIOS                       |
| 0x000C8000–0x000EFFFF | BIOS Shadow Area                     |
| 0x000F0000–0x000FFFFF | System BIOS                          |

We can do a simple experiment and create a very primitive boot code:

```assembly
;;
;; Note: this example is written using NASM assembler
;;
[BITS 16]

boot:
    ;; Symbol to print
    mov al, '!'
    ;; TTY-style text output
    mov ah, 0x0e
    ;; Position where to print the character
    mov bh, 0x00
    ;; Color
    mov bl, 0x07
    ;; Interrupt call
    int 0x10
    jmp $

times 510-($-$$) db 0

db 0x55
db 0xaa
```

You can build and run this code using the following commands:

```bash
nasm -f bin boot.S && qemu-system-x86_64 boot -nographic
```

This will instruct [QEMU](https://www.qemu.org/) virtual machine to use the `boot` binary that we just built as a disk image. Since the binary generated by the assembly code above fulfills the requirements of the boot sector (we end it with the magic sequence), QEMU will treat the binary as the master boot record (MBR) of a disk image.

If you did everything correctly, you will see something like this after run of the command above:

```
SeaBIOS (version 1.17.0-5.fc42)

iPXE (https://ipxe.org) 00:03.0 CA00 PCI2.10 PnP PMM+06FCAEC0+06F0AEC0 CA00

Booting from Hard Disk...
!
```

Of course, a real-world boot sector has "slightly" speaking more code for loading of an operating system instead of printing an exclamation mark, but it may interesting to experiment. In this example, we can see that the code will be executed in `16-bit` real mode which is specified by the `[BITS 16]` directive. After starting, it calls the [0x10](https://en.wikipedia.org/wiki/INT_10H) interrupt, which just prints the `!` symbol. The `times` directive will pad that number of bytes up to `510th` byte with zeros. In the end we "hard-code" the last two magic bytes `0xAA` and `0x55`. To exit from the virtual machine, you can press - `Ctrl+a x`.

From this point onwards, the BIOS hands control over to the bootloader.

## The Bootloader Stage

There are a number of different bootloaders that can boot Linux kernel, such as [GRUB 2](https://www.gnu.org/software/grub/), [syslinux](http://www.syslinux.org/wiki/index.php/The_Syslinux_Project), [systemd-boot](https://www.freedesktop.org/wiki/Software/systemd/systemd-boot/), and others. The Linux kernel has a [Boot protocol](https://github.com/torvalds/linux/blob/master/Documentation/arch/x86/boot.rst) which specifies the requirements for a bootloader to implement Linux support. In this chapter, we will take a short look how GRUB 2 does loading.

Continuing from where we left off - the BIOS has now selected a boot device, found its boot sector, loaded it into memory and passed control to the code located there. GRUB 2 bootloader consists of multiple [stages](https://www.gnu.org/software/grub/manual/grub/grub.html#Images). The first stage of the boot code is in the [boot.S](https://github.com/rhboot/grub2/blob/master/grub-core/boot/i386/pc/boot.S) source code file. Due to limited amount of space for the first boot sector, this code has only single goal - to load [core image](https://www.gnu.org/software/grub/manual/grub/html_node/Images.html) into memory and jump to it.

The core image starts with [diskboot.S](https://github.com/rhboot/grub2/blob/master/grub-core/boot/i386/pc/diskboot.S), which is usually stored right after the first sector of the disk. The code from the `diskboot.S` file loads the rest of the core image into memory. The core image contains the code of the loader itself and drivers for reading different filesystems. After the whole core image is loaded into memory, the execution continues from the [grub_main](https://github.com/rhboot/grub2/blob/master/grub-core/kern/main.c) function. This is where GRUB sets up the environment it needs to operate:

- Initializes the console so messages and menus can be displayed.
- Sets the root device — the disk from which GRUB will read files modules and configuration files.
- Loads and parses the GRUB configuration file.
- Loads required modules.

Once these tasks are complete, we may see the familiar GRUB menu where we can choose the operating system we want to load. When we select one of the menu entries, GRUB executes the [boot](https://www.gnu.org/software/grub/manual/grub/grub.html#boot) command which boots the selected operating system. So how the loader loads the Linux kernel? To answer on this question, we need to get back to the Linux kernel boot protocol.

As we can read in the [documentation](https://github.com/torvalds/linux/blob/master/Documentation/arch/x86/boot.rst), the bootloader must load the kernel into memory, fill some fields in the kernel setup header and pass control to the kernel code. The very first part of the kernel code is so-called kernel setup header and setup code. The kernel setup header is a special structure embedded in the early Linux boot code and provides fields that describes how kernel should be loaded and started. The setup header is started at the `0x01F1` offset from the beginning of the kernel image. We may look at the boot [linker script](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld) to confirm the value of this offset:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/setup.ld#L70-70 -->
```linker-script
	. = ASSERT(hdr == 0x1f1, "The setup header has the wrong offset!");
```

The kernel [setup header](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S) is split on two parts and the first part starts from the following fields:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L233-L241 -->
```assembly
	.globl	hdr
hdr:
		.byte setup_sects - 1
root_flags:	.word ROOT_RDONLY
syssize:	.long ZO__edata / 16
ram_size:	.word 0			/* Obsolete */
vid_mode:	.word SVGA_MODE
root_dev:	.word 0			/* Default to major/minor 0/0 */
boot_flag:	.word 0xAA55
```

The bootloader may fill some of these fields in the setup header which marked as being type `write` or `modify` in the Linux boot protocol. The values set by the bootloader will be taken from its configuration or will be calculated during boot. Of course we will not go over full descriptions and explanations of all the fields of the kernel setup header. Instead, we will take a look closer at this or that field if we will meet it during our research of the kernel code.

According to the Linux kernel boot protocol, memory will be mapped as follows after loading the kernel:

```
              ~                        ~
              |  Protected-mode kernel |
100000        +------------------------+
              |  I/O memory hole       |
0A0000        +------------------------+
              |  Reserved for BIOS     |      Leave as much as possible unused
              ~                        ~
              |  Command line          |      (Can also be below the X+10000 mark)
X+10000       +------------------------+
              |  Stack/heap            |      For use by the kernel real-mode code.
X+08000       +------------------------+
              |  Kernel setup          |      The kernel real-mode code.
              |  Kernel boot sector    |      The kernel legacy boot sector.
X             +------------------------+
              |  Boot loader           |      <- Boot sector entry point 0000:7C00
001000        +------------------------+
              |  Reserved for MBR/BIOS |
000800        +------------------------+
              |  Typically used by MBR |
000600        +------------------------+
              |  BIOS use only         |
000000        +------------------------+

... where the address X is as low as the design of the boot loader permits.
```

We can see that when the bootloader transfers control to the kernel, execution starts right after the kernel’s boot sector — that is, at the address `X` plus the length of the boot sector. The value of this `X` depends on how the kernel loaded. For example if I try to load kernel just with [qemu](https://www.qemu.org/), the starting address of the kernel image is at `0x10000`:

```bash
hexdump -C /tmp/dump | grep MZ
00010000  4d 5a 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |MZ..............|
```

Linux kernel image starts from `4D 5A` bytes as you may see in the beginning of the kernel setup code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L42-46 -->
```assembly
	.code16
	.section ".bstext", "ax"
#ifdef CONFIG_EFI_STUB
	# "MZ", MS-DOS header
	.word	IMAGE_DOS_SIGNATURE
```

If you want to get a similar memory dump, follow these steps. First of all, you need to build kernel. If you do not know how to do it, you can find detailed instruction [here](https://github.com/0xAX/linux-insides/blob/master/Misc/linux-misc-1.md). On the diagram above, we can see that the `Protected-mode` kernel starts from `0x100000`. Knowing this address we can start the kernel in the qemu virtual machine with the following command:

```bash
sudo qemu-system-x86_64 -kernel ./linux/arch/x86/boot/bzImage \
                        -nographic                            \
                        -append "console=ttyS0 nokaslr"       \
                        -initrd /boot/initramfs-6.17.0-rc1-g8f5ae30d69d7.img -s -S
```

After the virtual machine is started, we can attach the debugger to it, set up a breakpoint on the entry point and get the dump:

```bash
gdb vmlinux
(gdb) target remote :1234
(gdb) hbreak *0x100000
(gdb) c
Continuing.

Breakpoint 1, 0x0000000000100000 in ?? ()
(gdb) dump binary memory /tmp/dump 0x0000 0x20000
```

After this you should be able to find your dump in the `/tmp/dump`.

If we try to load Linux kernel using GRUB 2 bootloader, this `X` address will be `0x90000`. Let's take a look how to do it and check. First of all you need to prepare image with kernel and GRUB 2. To do so execute the following commands:

```bash
qemu-img create hdd.img 64M
parted hdd.img --script mklabel msdos
parted hdd.img --script mkpart primary ext2 1MiB 100%
parted hdd.img --script set 1 boot on
sudo losetup -fP hdd.img
sudo mkfs.ext2 /dev/loop0p1
sudo mount /dev/loop0p1 /mnt/tmp
sudo mkdir -p /mnt/tmp/boot/grub
sudo grub2-install \
  --target=i386-pc \
  --boot-directory=/mnt/tmp/boot \
  /dev/loop0
sudo cp ./arch/x86/boot/bzImage /mnt/tmp/boot/
sudo tee /mnt/tmp/boot/grub/grub.cfg > /dev/null <<EOF
terminal_input serial
terminal_output serial
set timeout=0
set default=0
set debug=linux

menuentry "Linux" {
    linux /boot/bzImage
}
EOF
sudo umount /mnt/tmp
sudo losetup -d /dev/loop0
```

Now we can run qemu virtual machine with our image:

```bash
qemu-system-x86_64 -drive format=raw,file=hdd.img -m 256M -s -S -no-reboot -no-shutdown -vga virtio
```

Connect with [gdb](https://sourceware.org/gdb/) debugger and setup breakpoint:

```
$ gdb
(gdb) target remote localhost:1234
Remote debugging using localhost:1234
(gdb) break *0x90200
Breakpoint 1 at 0x90200
(gdb) c
Continuing.
```

If you did everything correctly, you will see the GRUB 2 prompt in the qemu window. Execute the following commands:

```
set pager=1
set debug=all
linux /boot/bzImage
boot
```

During the execution of the `linux` command, you will see the debug line:

```
relocator: min_addr = 0x0, max_addr = 0xffffffff, target = 0x90000
```

That confirms that the kernel image will be loaded at the `0x90000` address. During execution of the `boot` command, the breakpoint should be caught. In debugger you can execute `i r` command and see that we are at the `0x9020:0x0000`

```
rip            0x0                 0x0
cs             0x9020              36896
```

If you continue to execute `s i` commands in the debugger CLI, you will go step by step by the early kernel setup code. If you exit from debugger you will see the continuation of the kernel loading procedure.

## The Beginning of the Kernel Setup Stage

The bootloader has now loaded the Linux kernel and the kernel setup code into memory, filled the header fields, and then jumped to the corresponding memory address. Finally, we are in the kernel 🎉

Technically, the kernel itself hasn't run yet but only early kernel setup code. First, the kernel setup part must switch from the real mode to [protected mode](https://en.wikipedia.org/wiki/Protected_mode), and after this switch to the [long mode](https://en.wikipedia.org/wiki/Long_mode), to configure the kernel decompressor, and finally decompress the kernel and jump to it. Execution of the kernel setup code starts from [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S) at the `_start` symbol:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L246-L252 -->
```assembly
_start:
		# Explicitly enter this as bytes, or the assembler
		# tries to generate a 3-byte jump here, which causes
		# everything else to push off to the wrong offset.
		.byte	0xeb		# short (2-byte) jump
		.byte	start_of_setup-1f
1:
```

The very first instruction we encounter here is the jump specified by the `0xEB` opcode. The second byte is the distance where to jump. If you’ve never met the `Nf` syntax before, `1f` means the next label `1` that will appear in the code. And immediately after those two bytes is the label `1` which is located right before the beginning of the second part of the kernel setup header. Right after the second part of the setup header, we see the `.entrytext` section, which starts at the `start_of_setup` label. This is exactly the place where the execution will be continued. But from where we are jumping? After the kernel setup code receives control from the bootloader, the first `jmp` instruction is located at the `0x200` bytes offset from the start of the loaded kernel image. This can be seen in both the Linux kernel boot protocol and the GRUB 2 [source code](https://github.com/rhboot/grub2/blob/master/grub-core/loader/i386/pc/linux.c):

```C
segment = grub_linux_real_target >> 4;
state.gs = state.fs = state.es = state.ds = state.ss = segment;
state.cs = segment + 0x20;
state.ip = 0;
```

Here, `grub_linux_real_target` is the physical load address of the setup code. As we have seen in the previous section, this address is usually `0x90000`. Shifting it right by four divides it by `16`, converting a physical address into a segment value - that’s how real mode memory segmentation works. Then GRUB adds `0x20` to `cs` before starting execution. Why `0x20`? Let's remember that in real mode, physical addresses are computed as:

```
Physical = (cs << 4) + ip
```

With `ip = 0` and `cs` increased by `0x20`, the offset from the start of the loaded image is:

```
0x20 << 4 = 0x200
```

This is 512 bytes — exactly the offset where our jump instruction resides in the image.

After the jump to the `start_of_setup` label, the kernel setup code enters the very first phase of its real work:

- Unifying the segment registers
- Establishing a valid stack
- Clearing the `.bss` section
- Transitioning into C code

In the next sections, we’ll walk through each of these steps in detail.

### Aligning the segment registers

First of all, the kernel setup code ensures that the `ds` and `es` segment registers point to the same address. Next, it clears the [direction flag](https://en.wikipedia.org/wiki/Direction_flag) using the `cld` instruction:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L546-L551 -->
```assembly
	.section ".entrytext", "ax"
start_of_setup:
# Force %es = %ds
	movw	%ds, %ax
	movw	%ax, %es
	cld
```

We need to do both of these two things to clear the [bss](https://en.wikipedia.org/wiki/.bss) section properly a bit later. From this point we are sure that both `ds` and `es` segment registers point to the same address - `0x9000`.

### Stack Setup

We need to prepare for C language environment. The next step is to setup the stack. Let's take a look at the next lines of the code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L558-L561 -->
```assembly
	movw	%ss, %dx
	cmpw	%ax, %dx	# %ds == %ss?
	movw	%sp, %dx
	je	2f		# -> assume %sp is reasonably set
```

Here we compare the value of the `ss` and `ds` registers. According to the comment around this code, only old versions of the [LILO](https://en.wikipedia.org/wiki/LILO_(bootloader)) bootloader may set these registers to different values. So we will skip all the "edge cases" and consider only single case when the value of the `ss` register equal to `ds`. Since the values of these registers are equal, we jump to the `2` label:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L572-L578 -->
```assembly
2:	# Now %dx should point to the end of our stack space
	andw	$~3, %dx	# dword align (might as well...)
	jnz	3f
	movw	$0xfffc, %dx	# Make sure we're not zero
3:	movw	%ax, %ss
	movzwl	%dx, %esp	# Clear upper half of %esp
	sti			# Now we should have a working stack
```

`dx` register stores stack pointer value whish should point to the top of the stack. The value of the stack pointer is `0x9000`. GRUB 2 bootloader sets it during loading of the Linux kernel image and the address is defined by the:

<!-- https://raw.githubusercontent.com/rhboot/grub2/refs/heads/master/include/grub/i386/linux.h#L34-L34 -->
```C
#define GRUB_LINUX_SETUP_STACK		0x9000
```

At the next step we check that the address is aligned by four bytes and if yes jump to the label `3`. If the stack pointer is not aligned, we set it to `0xFFFC` value. The reason for this that we can not have stack pointer equal to zero as it grows down during pushing something on the stack. The `0xFFFC` value is the highest 4‑byte aligned address below `0x10000`. If the value of the stack pointer is aligned, we continue to use the aligned value.

From this point we have a correct stack and starts from `0x9000:0x9000` and grows down:

![early-stack](./images/early-stack.svg)

### BSS Setup

Before the kernel can switch to C code, two final tasks must be done:

- Verify the “magic” signature.
- Clear the `.bss` section.

The first is the signature checking:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L588-L589 -->
```assembly
	cmpl	$0x5a5aaa55, setup_sig
	jne	setup_bad
```

This simply compares the [setup_sig](https://github.com/torvalds/linux/blob/master/arch/x86/boot/setup.ld) constant value placed by the linker with the magic number `0x5A5AAA55`. If they are not equal, the setup code reports a fatal error and stops execution. The main goal of this check is to ensure we are actually running a valid Linux kernel setup binary, loaded into the proper place by the bootloader.

With the magic number confirmed, and knowing our segment registers and stack are already in the proper state, the only initialization left is to clear the `.bss` section. The section of memory is used to store statically allocated, uninitialized data. Let's take a look at the initialization of this memory area:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L592-L597 -->
```assembly
	movw	$__bss_start, %di
	movw	$_end+3, %cx
	xorl	%eax, %eax
	subw	%di, %cx
	shrw	$2, %cx
	rep stosl
```

The main goal of this code is to clear or in other words to fill with zeros the memory area between `__bss_start` and `_end`. To fill this memory area with zeros, the `rep stos` instruction is used. This instruction puts the value of the `eax` register to the destination pointed by the `es:di`. That is why we unified the values of the `ds` and `es` registers. The `rep` prefix specifies the repetition of the `stos` instruction based on the value of the `cx` register.

To clear this memory area, at first we set the borders of this area - from the [__bss_start](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/setup.ld) to `_end + 3`. We add `3` bytes to the `_end` address because we are going to write zeros in double words or 4 bytes at a time). Adding three bytes ensures that when we later divide by four, any reminder at the end of the memory area still get covered. After we setup the borders of the memory area and fill the `eax` with 0 using the `xor` instruction, the `rep stosl` does its job.

The effect of this code is that zeros are written through the all memory from `__bss_start` to `_end`. To know exact addresses of them we can inspect `setup.elf` file with [readelf](https://en.wikipedia.org/wiki/Readelf) utility:

```bash
$ readelf -a arch/x86/boot/setup.elf  | grep bss
  [12] .bss              NOBITS          00003f00 004efc 001380 00  WA  0   0 32
   00     .bstext .header .entrytext .inittext .initdata .text .text32 .rodata .videocards .data .signature .bss
   145: 00005280     0 NOTYPE  GLOBAL DEFAULT   12 __bss_end
   169: 00003f00     0 NOTYPE  GLOBAL DEFAULT   12 __bss_start
```

These offsets inside the setup segment. Since in our case the kernel image is loaded at physical address `0x90000`, the symbols translate to:

- __bss_start = 0x90000 + 0x3f00 = 0x93F00
- __bss_end = 0x90000 + 0x5280 = 0x95280

The following diagram illustrates how the setup image, `.bss`, and the stack region are laid out in memory:

![bss](./images/early-bss.svg)

### Jump to C code

At this point we have initialized the [stack](#stack-setup) and [.bss](#bss-setup) sections. The last instruction of the early kernel setup assembly is to jump to C code:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/boot/header.S#L600-L600 -->
```assembly
	calll	main
```

The `main()` function is located in [arch/x86/boot/main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c) source code file.

What's happening there, we will see in the next chapter.

## Conclusion

This is the end of the first part about Linux kernel insides. If you have questions or suggestions, feel free ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new). In the next part, we will see the first C code that executes in the Linux kernel setup, the implementation of memory routines such as `memset`, `memcpy`, `earlyprintk`, early console implementation and initialization, and much more.

## Links

Here is the list of the links that you may find useful during reading of this chapter:

- [Intel 80386 programmer's reference manual 1986](http://css.csail.mit.edu/6.858/2014/readings/i386.pdf)
- [Minimal Boot Loader for Intel® Architecture](https://www.cs.cmu.edu/~410/doc/minimal_boot.pdf)
- [Minimal Boot Loader in Assembler with comments](https://github.com/Stefan20162016/linux-insides-code/blob/master/bootloader.asm)
- [8086](https://en.wikipedia.org/wiki/Intel_8086)
- [80386](https://en.wikipedia.org/wiki/Intel_80386)
- [Reset vector](https://en.wikipedia.org/wiki/Reset_vector)
- [Real mode](https://en.wikipedia.org/wiki/Real_mode)
- [Linux kernel boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.rst)
- [Ralf Brown's Interrupt List](http://www.ctyme.com/intr/int.htm)
- [Power supply](https://en.wikipedia.org/wiki/Power_supply)
- [Power good signal](https://en.wikipedia.org/wiki/Power_good_signal)
