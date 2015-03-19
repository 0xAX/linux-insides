Paging
================================================================================

Introduction
--------------------------------------------------------------------------------

In the fifth [part](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-5.html) of the series `Linux kernel booting process` we finished to learn what and how kernel does on the earliest stage. In the next step kernel will initialize different things like `initrd` mounting, lockdep initialization, and many many different things, before we can see how the kernel will run the first init process.

Yeah, there will be many different things, but many many and once again many work with **memory**.

In my view, memory management is one of the most complex part of the linux kernel and in system programming generally. So before we will proceed with the kernel initialization stuff, we will get acquainted with the paging.

`Paging` is a process of translation a linear memory address to a physical address. If you have read previous parts, you can remember that we saw segmentation in the real mode when physical address calculated by shifting a segment register on four and adding offset. Or also we saw segmentation in the protected mode, where we used the tables of descriptors and base addresses from descriptors with offsets to calculate physical addresses. Now we are in 64-bit mode and that we will see paging.

As Intel manual says:

```
Paging provides a mech-anism for implementing a conventional demand-paged, virtual-memory system where sections of a program’s execution environment are mapped into physical memory as needed.
```

So... I will try to explain how paging works in theory in this post. Of course it will be closely related with the linux kernel for `x86_64`, but we will not go into deep details (at least in this post).

Enabling paging
--------------------------------------------------------------------------------

There are three paging modes:

* 32-bit paging;
* PAE paging;
* IA-32e paging.

We will see explanation only last mode here. To enable `IA-32e paging` paging mode need to do following things:

* set `CR0.PG` bit;
* set `CR4.PAE` bit;
* set `IA32_EFER.LME` bit.

We already saw setting of this bits in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

```assembly
movl	$(X86_CR0_PG | X86_CR0_PE), %eax
movl	%eax, %cr0
```

and

```assembly
movl	$MSR_EFER, %ecx
rdmsr
btsl	$_EFER_LME, %eax
wrmsr
```

Paging structures
--------------------------------------------------------------------------------

Paging divides the linear address space into fixed-size pages. Pages can be mapped into the physical address space or even external storage. This fixed size is `4096` bytes for the `x86_64` linux kernel. For a linear address translation to a physical address used special structures. Every structure is `4096` bytes size and contains `512` entries (this only for `PAE` and `IA32_EFER.LME` modes). Paging structures are hierarchical and linux kernel uses 4 level paging for `x86_64`. CPU uses a part of the linear address to identify entry of the another paging structure which is at the lower level or physical memory region (`page frame`) or physical address in this region (`page offset`). The address of the top level paging structure located in the `cr3` register. We already saw this in the [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

```assembly
leal	pgtable(%ebx), %eax
movl	%eax, %cr3
```

We built page table structures and put the address of the top-level structure to the `cr3` register. Here `cr3` is used to store the address of the top-level `PML4` structure or `Page Global Directory` as it calls in linux kernel. `cr3` is 64-bit register and has the following structure:

```
63                  52 51                                                        32
 --------------------------------------------------------------------------------
|                     |                                                          |
|    Reserved MBZ     |            Address of the top level structure            |
|                     |                                                          |
 --------------------------------------------------------------------------------
31                                  12 11            5     4     3 2             0
 --------------------------------------------------------------------------------
|                                     |               |  P  |  P  |              |
|  Address of the top level structure |   Reserved    |  C  |  W  |    Reserved  |
|                                     |               |  D  |  T  |              |
 --------------------------------------------------------------------------------
```

These fields have the following meanings:

* Bits 2:0 - ignored;
* Bits 51:12 - stores the address of the top level paging structure;
* Bit 3 and 4 - PWT or Page-Level Writethrough and PCD or Page-level cache disable indicate. These bits control the way the page or Page Table is handled by the hardware cache; 
* Reserved - reserved must be 0;
* Bits 63:52 - reserved must be 0.

The linear address translation address is following:

* Given linear address arrives to the [MMU](http://en.wikipedia.org/wiki/Memory_management_unit) instead of memory bus. 
* 64-bit linear address splits on some parts. Only low 48 bits are significant, it means that `2^48` or 256 TBytes of linear-address space may be accessed at any given time.
* `cr3` register stores the address of the 4 top-level paging structure.
* `47:39` bits of the given linear address stores an index into the paging structure level-4, `38:30` bits stores index into the paging structure level-3, `29:21` bits stores an index into the paging structure level-2, `20:12` bits stores an index into the paging structure level-1 and `11:0` bits provide the byte offset into the physical page.

schematically, we can imagine it like this:

![4-level paging](http://oi58.tinypic.com/207mb0x.jpg)

Every access to a linear address is either a supervisor-mode access or a user-mode access. This access determined by the `CPL` (current privilege level). If `CPL < 3` it is a supervisor mode access level and user mode access level in other ways. For example top level page table entry contains access bits and has the following structure:

```
63  62                  52 51                                                    32
 --------------------------------------------------------------------------------
| N |                     |                                                     |
|   |     Available       |     Address of the paging structure on lower level  |
| X |                     |                                                     |
 --------------------------------------------------------------------------------
31                                              12 11  9 8 7 6 5   4   3 2 1     0
 --------------------------------------------------------------------------------
|                                                |     | M |I| | P | P |U|W|    |
| Address of the paging structure on lower level | AVL | B |G|A| C | W | | |  P |
|                                                |     | Z |N| | D | T |S|R|    |
 --------------------------------------------------------------------------------
```

Where:

* 63 bit - N/X bit (No Execute Bit) - presents ability to execute the code from physical pages mapped by the table entry;
* 62:52 bits - ignored by CPU, used by system software;
* 51:12 bits - stores physical address of the lower level paging structure;
* 12:9  bits - ignored by CPU;
* MBZ - must be zero bits;
* Ignored bits;
* A - accessed bit indicates was physical page or page structure accessed;
* PWT and PCD used for cache;
* U/S - user/supervisor bit controls user access to the all physical pages mapped by this table entry;
* R/W - read/write bit controls read/write access to the all physical pages mapped by this table entry;
* P - present bit. Current bit indicates was page table or physical page loaded into primary memory or not.

Ok, now we know about paging structures and it's entries. Let's see some details about 4-level paging in linux kernel.

Paging structures in linux kernel
--------------------------------------------------------------------------------

As i wrote about linux kernel for `x86_64` uses 4-level page tables. Their names are:

* Page Global Directory
* Page Upper  Directory
* Page Middle Directory
* Page Table Entry

After that you compiled and installed linux kernel, you can note `System.map` file which stores address of the functions that are used by the kernel. Note that addresses are virtual. For example:

```
$ grep "start_kernel" System.map
ffffffff81efe497 T x86_64_start_kernel
ffffffff81efeaa2 T start_kernel
```

We can see `0xffffffff81efe497` here. I'm not sure that you have so big RAM. But anyway `start_kernel` and `x86_64_start_kernel` will be executed. The address space in `x86_64` is `2^64` size, but it's too large, that's why used smaller address space, only 48-bits wide. So we have situation when physical address limited with 48 bits, but addressing still performed with 64 bit pointers. How to solve this problem? Ok, look on the diagram: 

```
0xffffffffffffffff  +-----------+
                    |           |
                    |           | Kernelspace
                    |           |
 0xffff800000000000 +-----------+
                    |           |
                    |           |
                    |   hole    |
                    |           |
                    |           |
0x00007fffffffffff  +-----------+
                    |           |
                    |           |  Userspace
                    |           |
0x0000000000000000  +-----------+
```

This solution is `sign extension`. Here we can see that low 48 bits of a virtual address can be used for addressing. Bits `63:48` can be or 0 or 1. Note that all virtual address space is spliten on 2 parts:

* Kernel space
* Userspace

Userspace occupies the lower part of the virtual address space, from `0x000000000000000` to `0x00007fffffffffff` and kernel space occupies the highest part from the `0xffff8000000000` to `0xffffffffffffffff`. Note that bits `63:48` is 0 for userspace and 1 for kernel space. All addresses which are in kernel space and in userspace or in another words which higher `63:48` bits zero or one calls `canonical` addresses. There is `non-canonical` area between these memory regions. Together this two memory regions (kernel space and user space) are exactly `2^48` bits. We can find virtual memory map with 4 level page tables in the [Documentation/x86/x86_64/mm.txt](https://github.com/torvalds/linux/blob/master/Documentation/x86/x86_64/mm.txt):

```
0000000000000000 - 00007fffffffffff (=47 bits) user space, different per mm
hole caused by [48:63] sign extension
ffff800000000000 - ffff87ffffffffff (=43 bits) guard hole, reserved for hypervisor
ffff880000000000 - ffffc7ffffffffff (=64 TB) direct mapping of all phys. memory
ffffc80000000000 - ffffc8ffffffffff (=40 bits) hole
ffffc90000000000 - ffffe8ffffffffff (=45 bits) vmalloc/ioremap space
ffffe90000000000 - ffffe9ffffffffff (=40 bits) hole
ffffea0000000000 - ffffeaffffffffff (=40 bits) virtual memory map (1TB)
... unused hole ...
ffffec0000000000 - fffffc0000000000 (=44 bits) kasan shadow memory (16TB)
... unused hole ...
ffffff0000000000 - ffffff7fffffffff (=39 bits) %esp fixup stacks
... unused hole ...
ffffffff80000000 - ffffffffa0000000 (=512 MB)  kernel text mapping, from phys 0
ffffffffa0000000 - ffffffffff5fffff (=1525 MB) module mapping space
ffffffffff600000 - ffffffffffdfffff (=8 MB) vsyscalls
ffffffffffe00000 - ffffffffffffffff (=2 MB) unused hole
```

We can see here memory map for user space, kernel space and non-canonical area between. User space memory map is simple. Let's take a closer look on the kernel space. We can see that it starts from the guard hole which reserved for hypervisor. We can find definition of this guard hole in the [arch/x86/include/asm/page_64_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/page_64_types.h):

```C
#define __PAGE_OFFSET _AC(0xffff880000000000, UL)
```

Previously this guard hole and `__PAGE_OFFSET` was from `0xffff800000000000` to `0xffff80ffffffffff` for preventing of access to non-canonical area, but later was added 3 bits for hypervisor.

Next is the lowest usable address in kernel space - `ffff880000000000`. This virtual memory region is for direct mapping of the all physical memory. After the memory space which mapped all physical address - guard hole, it needs to be between direct mapping of the all physical memory and vmalloc area. After the virtual memory map for the first terabyte and unused hole after it, we can see `kasan` shadow memory. It was added by the [commit](https://github.com/torvalds/linux/commit/ef7f0d6a6ca8c9e4b27d78895af86c2fbfaeedb2) and provides kernel address sanitizer. After next unused hole we can se `esp` fixup stacks (we will talk about it in the other parts) and the start of the kernel text mapping from the physical address - `0`. We can find definition of this address in the same file as the `__PAGE_OFFSET`:

```C
#define __START_KERNEL_map      _AC(0xffffffff80000000, UL)
```

Usually kernel's `.text` start here with the `CONFIG_PHYSICAL_START` offset. We saw it in the post about [ELF64](https://github.com/0xAX/linux-insides/blob/master/Theory/ELF.md):

```
readelf -s vmlinux | grep ffffffff81000000
     1: ffffffff81000000     0 SECTION LOCAL  DEFAULT    1 
 65099: ffffffff81000000     0 NOTYPE  GLOBAL DEFAULT    1 _text
 90766: ffffffff81000000     0 NOTYPE  GLOBAL DEFAULT    1 startup_64
```

Here i checked `vmlinux` with the `CONFIG_PHYSICAL_START` is `0x1000000`. So we have the start point of the kernel `.text` - `0xffffffff80000000` and offset - `0x1000000`, the resulted virtual address will be `0xffffffff80000000 + 1000000 = 0xffffffff81000000`.

After the kernel `.text` region, we can see virtual memory region for kernel modules, `vsyscalls` and 2 megabytes unused hole.

We know how looks kernel's virtual memory map and now we can see how a virtual address translates into physical. Let's take for example following address:

```
0xffffffff81000000
```

In binary it will be:

```
1111111111111111 111111111 111111110 000001000 000000000 000000000000
      63:48        47:39     38:30     29:21     20:12      11:0
```

The given virtual address split on some parts as i wrote above:

* `63:48` - bits not used;
* `47:39` - bits of the given linear address stores an index into the paging structure level-4; 
* `38:30` - bits stores index into the paging structure level-3;
* `29:21` - bits stores an index into the paging structure level-2;
* `20:12` - bits stores an index into the paging structure level-1;
* `11:0`  - bits provide the byte offset into the physical page.

That is all. Now you know a little about `paging` theory and we can go ahead in the kernel source code and see first initialization steps.

Conclusion
--------------------------------------------------------------------------------

It's the end of this short part about paging theory. Of course this post doesn't cover all details about paging, but soon we will see it on practice how linux kernel builds paging structures and work with it.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-internals](https://github.com/0xAX/linux-internals).**


Links
--------------------------------------------------------------------------------

* [Paging on Wikipedia](http://en.wikipedia.org/wiki/Paging)
* [Intel 64 and IA-32 architectures software developer's manual volume 3A](http://www.intel.com/content/www/us/en/processors/architectures-software-developer-manuals.html)
* [MMU](http://en.wikipedia.org/wiki/Memory_management_unit)
* [ELF64](https://github.com/0xAX/linux-insides/blob/master/Theory/ELF.md)
* [Documentation/x86/x86_64/mm.txt](https://github.com/torvalds/linux/blob/master/Documentation/x86/x86_64/mm.txt)
* [Last part - Kernel booting process](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-5.html)
