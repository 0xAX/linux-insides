Linux kernel memory management Part 2.
================================================================================

Fix-Mapped Addresses and ioremap
--------------------------------------------------------------------------------

`Fix-Mapped` addresses are a set of special compile-time addresses whose corresponding physical addresses do not have to be a linear address minus `__START_KERNEL_map`. Each fix-mapped address maps one page frame and the kernel uses them as pointers that never change their address. That is the main point of these addresses. As the comment says: `to have a constant address at compile time, but to set the physical address only in the boot process`. You can remember that in the earliest [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-1.html), we already set the `level2_fixmap_pgt`:

```assembly
NEXT_PAGE(level2_fixmap_pgt)
	.fill	506,8,0
	.quad	level1_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE
	.fill	5,8,0

NEXT_PAGE(level1_fixmap_pgt)
	.fill	512,8,0
```

As you can see `level2_fixmap_pgt` is right after the `level2_kernel_pgt` which is kernel code+data+bss. Every fix-mapped address is represented by an integer index which is defined in the `fixed_addresses` enum from the [arch/x86/include/asm/fixmap.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/fixmap.h). For example it contains entries for `VSYSCALL_PAGE` - if emulation of legacy vsyscall page is enabled, `FIX_APIC_BASE` for local [apic](http://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller), etc. In virtual memory fix-mapped area is placed in the modules area:

```
       +-----------+-----------------+---------------+------------------+
       |           |                 |               |                  |
       |kernel text|      kernel     |               |    vsyscalls     |
       | mapping   |       text      |    Modules    |    fix-mapped    |
       |from phys 0|       data      |               |    addresses     |
       |           |                 |               |                  |
       +-----------+-----------------+---------------+------------------+
__START_KERNEL_map   __START_KERNEL    MODULES_VADDR            0xffffffffffffffff
```

Base virtual address and size of the `fix-mapped` area are presented by the two following macro:

```C
#define FIXADDR_SIZE	(__end_of_permanent_fixed_addresses << PAGE_SHIFT)
#define FIXADDR_START		(FIXADDR_TOP - FIXADDR_SIZE)
```

Here `__end_of_permanent_fixed_addresses` is an element of the `fixed_addresses` enum and as I wrote above: Every fix-mapped address is represented by an integer index which is defined in the `fixed_addresses`. `PAGE_SHIFT` determines the size of a page. For example size of the one page we can get with the `1 << PAGE_SHIFT`. In our case we need to get the size of the fix-mapped area, but not only of one page, that's why we are using `__end_of_permanent_fixed_addresses` for getting the size of the fix-mapped area. In my case it's a little more than `536` kilobytes. In your case it might be a different number, because the size depends on amount of the fix-mapped addresses which are depends on your kernel's configuration.

The second `FIXADDR_START` macro just subtracts the fix-mapped area size from the last address of the fix-mapped area to get its base virtual address. `FIXADDR_TOP` is a rounded up address from the base address of the [vsyscall](https://lwn.net/Articles/446528/) space:

```C
#define FIXADDR_TOP     (round_up(VSYSCALL_ADDR + PAGE_SIZE, 1<<PMD_SHIFT) - PAGE_SIZE)
```

The `fixed_addresses` enums are used as an index to get the virtual address by the `fix_to_virt` function. Implementation of this function is easy:
 
```C
static __always_inline unsigned long fix_to_virt(const unsigned int idx)
{
        BUILD_BUG_ON(idx >= __end_of_fixed_addresses);
        return __fix_to_virt(idx);
}
```

first of all it checks that the index given for the `fixed_addresses` enum is not greater or equal than `__end_of_fixed_addresses` with the `BUILD_BUG_ON` macro and then returns the result of the `__fix_to_virt` macro:

```C
#define __fix_to_virt(x)        (FIXADDR_TOP - ((x) << PAGE_SHIFT))
```

Here we shift left the given `fix-mapped` address index on the `PAGE_SHIFT` which determines size of a page as I wrote above and subtract it from the `FIXADDR_TOP` which is the highest address of the `fix-mapped` area. There is an inverse function for getting `fix-mapped` address from a virtual address:

```C
static inline unsigned long virt_to_fix(const unsigned long vaddr)
{
        BUG_ON(vaddr >= FIXADDR_TOP || vaddr < FIXADDR_START);
        return __virt_to_fix(vaddr);
}
```

`virt_to_fix` takes a virtual address, checks that this address is between `FIXADDR_START` and `FIXADDR_TOP` and calls the `__virt_to_fix` macro which implemented as:

```C
#define __virt_to_fix(x)        ((FIXADDR_TOP - ((x)&PAGE_MASK)) >> PAGE_SHIFT)
```

A PFN is simply an index within physical memory that is counted in page-sized units. PFN for a physical address could be trivially defined as (page_phys_addr >> PAGE_SHIFT);

`__virt_to_fix` clears the first 12 bits in the given address, subtracts it from the last address the of `fix-mapped` area (`FIXADDR_TOP`) and shifts the result right on `PAGE_SHIFT` which is `12`. Let me explain how it works. As I already wrote we will clear the first 12 bits in the given address with `x & PAGE_MASK`. As we subtract this from the `FIXADDR_TOP`, we will get the last 12 bits of the `FIXADDR_TOP` which are present. We know that the first 12 bits of the virtual address represent the offset in the page frame. With the shifting it on `PAGE_SHIFT` we will get `Page frame number` which is just all bits in a virtual address besides the first 12 offset bits. `Fix-mapped` addresses are used in different [places](http://lxr.free-electrons.com/ident?i=fix_to_virt) in the linux kernel. `IDT` descriptor stored there, [Intel Trusted Execution Technology](http://en.wikipedia.org/wiki/Trusted_Execution_Technology) UUID stored in the `fix-mapped` area started from `FIX_TBOOT_BASE` index, [Xen](http://en.wikipedia.org/wiki/Xen) bootmap and many more... We already saw a little about `fix-mapped` addresses in the fifth [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-5.html) about of the linux kernel initialization. We use `fix-mapped` area in the early `ioremap` initialization. Let's look at it more closely and try to understand what `ioremap` is, how it is implemented in the kernel and how it is related to the `fix-mapped` addresses.

ioremap
--------------------------------------------------------------------------------

The Linux kernel provides many different primitives to manage memory. For this moment we will touch `I/O memory`. Every device is controlled by reading/writing from/to its registers. For example a driver can turn off/on a device by writing to its registers or get the state of a device by reading from its registers. Besides registers, many devices have buffers where a driver can write something or read from there. As we know for this moment there are two ways to access device's registers and data buffers:

* through the I/O ports;
* mapping of the all registers to the memory address space;

In the first case every control register of a device has a number of input and output port. A device driver can read from a port and write to it with two `in` and `out` instructions which we already saw. If you want to know about currently registered port regions, you can learn about them by accessing `/proc/ioports`:

```
$ cat /proc/ioports
0000-0cf7 : PCI Bus 0000:00
  0000-001f : dma1
  0020-0021 : pic1
  0040-0043 : timer0
  0050-0053 : timer1
  0060-0060 : keyboard
  0064-0064 : keyboard
  0070-0077 : rtc0
  0080-008f : dma page reg
  00a0-00a1 : pic2
  00c0-00df : dma2
  00f0-00ff : fpu
    00f0-00f0 : PNP0C04:00
  03c0-03df : vesafb
  03f8-03ff : serial
  04d0-04d1 : pnp 00:06
  0800-087f : pnp 00:01
  0a00-0a0f : pnp 00:04
  0a20-0a2f : pnp 00:04
  0a30-0a3f : pnp 00:04
0cf8-0cff : PCI conf1
0d00-ffff : PCI Bus 0000:00
...
...
...
```

`/proc/ioports` provides information about which driver uses which address of a `I/O` port region. All of these memory regions, for example `0000-0cf7`, were claimed with the `request_region` function from the [include/linux/ioport.h](https://github.com/torvalds/linux/blob/master/include/linux/ioport.h). Actually `request_region` is a macro which is defined as:

```C
#define request_region(start,n,name)   __request_region(&ioport_resource, (start), (n), (name), 0)
```

As we can see it takes three parameters:

* `start` -  begin of region;
* `n`     -  length of region;
* `name`  -  name of requester.

`request_region` allocates an `I/O` port region. Very often the `check_region` function is called before the `request_region` to check that the given address range is available and the `release_region` function to release the memory region. `request_region` returns a pointer to the `resource` structure. The `resource` structure represents an abstraction for a tree-like subset of system resources. We already saw the `resource` structure in the fifth part of the kernel [initialization](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-5.html) process and it looks as follows:

```C
struct resource {
        resource_size_t start;
        resource_size_t end;
        const char *name;
        unsigned long flags;
        struct resource *parent, *sibling, *child;
};
```

and contains start and end addresses of the resource, the name, etc. Every `resource` structure contains pointers to the `parent`, `sibling` and `child` resources. As it has a parent and a childs, it means that every subset of resources has root `resource` structure. For example, for `I/O` ports it is the `ioport_resource` structure:

```C
struct resource ioport_resource = {
         .name   = "PCI IO",
         .start  = 0,
         .end    = IO_SPACE_LIMIT,
        .flags  = IORESOURCE_IO,
};
EXPORT_SYMBOL(ioport_resource);
```

Or for `iomem`, it is the `iomem_resource` structure:

```C
struct resource iomem_resource = {
        .name   = "PCI mem",
        .start  = 0,
        .end    = -1,
        .flags  = IORESOURCE_MEM,
};
```

As I have mentioned before, `request_regions` is used to register I/O port regions and this macro is used in many [places](http://lxr.free-electrons.com/ident?i=request_region) in the kernel. For example let's look at [drivers/char/rtc.c](https://github.com/torvalds/linux/blob/master/drivers/char/rtc.c). This source code file provides the [Real Time Clock](http://en.wikipedia.org/wiki/Real-time_clock) interface in the linux kernel. As every kernel module, `rtc` module contains `module_init` definition:

```C
module_init(rtc_init);
```

where `rtc_init` is the `rtc` initialization function. This function is defined in the same `rtc.c` source code file. In the `rtc_init` function we can see a couple of calls to the `rtc_request_region` functions, which wrap `request_region` for example:

```C
r = rtc_request_region(RTC_IO_EXTENT);
```

where `rtc_request_region` calls:

```C
r = request_region(RTC_PORT(0), size, "rtc");
```

Here `RTC_IO_EXTENT` is the size of the memory region and it is `0x8`, `"rtc"` is the name of the region and `RTC_PORT` is:

```C
#define RTC_PORT(x)     (0x70 + (x))
```

So with the `request_region(RTC_PORT(0), size, "rtc")` we register a memory region that starts at `0x70` and and has a size of `0x8`. Let's look at `/proc/ioports`:

```
~$ sudo cat /proc/ioports | grep rtc
0070-0077 : rtc0
```

So, we got it! Ok, that was it for the I/O ports. The second way to communicate with drivers is through the use of `I/O` memory. As I have mentioned above this works by mapping the control registers and the memory of a device to the memory address space. `I/O` memory is a set of contiguous addresses which are provided by a device to the CPU through a bus. None of the memory-mapped I/O addresses are used by the kernel directly. There is a special `ioremap` function which allows us to convert the physical address on a bus to a kernel virtual address. In other words, `ioremap` maps I/O physical memory regions to make them accessible from the kernel. The `ioremap` function takes two parameters:

* start of the memory region;
* size of the memory region;

The I/O memory mapping API provides functions to check, request and release memory regions as I/O memory. There are three functions for that:

* `request_mem_region`
* `release_mem_region`
* `check_mem_region`

```
~$ sudo cat /proc/iomem
...
...
...
be826000-be82cfff : ACPI Non-volatile Storage
be82d000-bf744fff : System RAM
bf745000-bfff4fff : reserved
bfff5000-dc041fff : System RAM
dc042000-dc0d2fff : reserved
dc0d3000-dc138fff : System RAM
dc139000-dc27dfff : ACPI Non-volatile Storage
dc27e000-deffefff : reserved
defff000-deffffff : System RAM
df000000-dfffffff : RAM buffer
e0000000-feafffff : PCI Bus 0000:00
  e0000000-efffffff : PCI Bus 0000:01
    e0000000-efffffff : 0000:01:00.0
  f7c00000-f7cfffff : PCI Bus 0000:06
    f7c00000-f7c0ffff : 0000:06:00.0
    f7c10000-f7c101ff : 0000:06:00.0
      f7c10000-f7c101ff : ahci
  f7d00000-f7dfffff : PCI Bus 0000:03
    f7d00000-f7d3ffff : 0000:03:00.0
      f7d00000-f7d3ffff : alx
...
...
...
```

Part of these addresses are from the call of the `e820_reserve_resources` function. We can find a call to this function in the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c) and the function itself is defined in [arch/x86/kernel/e820.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/e820.c). `e820_reserve_resources` goes through the [e820](http://en.wikipedia.org/wiki/E820) map and inserts memory regions into the root `iomem` resource structure. All `e820` memory regions which are inserted into the `iomem` resource have the following types:

```C
static inline const char *e820_type_to_string(int e820_type)
{
	switch (e820_type) {
	case E820_RESERVED_KERN:
	case E820_RAM:	return "System RAM";
	case E820_ACPI:	return "ACPI Tables";
	case E820_NVS:	return "ACPI Non-volatile Storage";
	case E820_UNUSABLE:	return "Unusable memory";
	default:	return "reserved";
	}
}
```

and we can see them in the `/proc/iomem` (read above).

Now let's try to understand how `ioremap` works. We already know a little about `ioremap`, we saw it in the fifth [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-5.html) about linux kernel initialization. If you have read this part, you can remember the call of the `early_ioremap_init` function from the [arch/x86/mm/ioremap.c](https://github.com/torvalds/linux/blob/master/arch/x86/mm/ioremap.c). Initialization of the `ioremap` is split into two parts: there is the early part which we can use before the normal `ioremap` is available and the normal `ioremap` which is available after `vmalloc` initialization and the call of `paging_init`. We do not know anything about `vmalloc` for now, so let's consider early initialization of the `ioremap`. First of all `early_ioremap_init` checks that `fixmap` is aligned on page middle directory boundary:

```C
BUILD_BUG_ON((fix_to_virt(0) + PAGE_SIZE) & ((1 << PMD_SHIFT) - 1));
```

more about `BUILD_BUG_ON` you can read in the first part about [Linux Kernel initialization](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-1.html). So `BUILD_BUG_ON` macro raises a compilation error if the given expression is true. In the next step after this check, we can see call of the `early_ioremap_setup` function from the [mm/early_ioremap.c](https://github.com/torvalds/linux/blob/master/mm/early_ioremap.c). This function presents generic initialization of the `ioremap`. `early_ioremap_setup` function fills the `slot_virt` array with the virtual addresses of the early fixmaps. All early fixmaps are after `__end_of_permanent_fixed_addresses` in memory. They start at `FIX_BITMAP_BEGIN` (top) and end with `FIX_BITMAP_END` (down). Actually there are `512` temporary boot-time mappings, used by early `ioremap`:

```
#define NR_FIX_BTMAPS		64
#define FIX_BTMAPS_SLOTS	8
#define TOTAL_FIX_BTMAPS	(NR_FIX_BTMAPS * FIX_BTMAPS_SLOTS)
```

and `early_ioremap_setup`:

```C
void __init early_ioremap_setup(void)
{
        int i;

        for (i = 0; i < FIX_BTMAPS_SLOTS; i++)
                if (WARN_ON(prev_map[i]))
                        break;

        for (i = 0; i < FIX_BTMAPS_SLOTS; i++)
                slot_virt[i] = __fix_to_virt(FIX_BTMAP_BEGIN - NR_FIX_BTMAPS*i);
}
```

the `slot_virt` and other arrays are defined in the same source code file:

```C
static void __iomem *prev_map[FIX_BTMAPS_SLOTS] __initdata;
static unsigned long prev_size[FIX_BTMAPS_SLOTS] __initdata;
static unsigned long slot_virt[FIX_BTMAPS_SLOTS] __initdata;
```

`slot_virt` contains the virtual addresses of the `fix-mapped` areas, `prev_map` array contains addresses of the early ioremap areas. Note that I wrote above: `Actually there are 512 temporary boot-time mappings, used by early ioremap` and you can see that all arrays are defined with the `__initdata` attribute which means that this memory will be released after the kernel initialization process. After `early_ioremap_setup` has finished its work, we're getting page middle directory where early ioremap begins with the `early_ioremap_pmd` function which just gets the base address of the page global directory and calculates the page middle directory for the given address:

```C
static inline pmd_t * __init early_ioremap_pmd(unsigned long addr)
{
	pgd_t *base = __va(read_cr3());
	pgd_t *pgd = &base[pgd_index(addr)];
	pud_t *pud = pud_offset(pgd, addr);
	pmd_t *pmd = pmd_offset(pud, addr);
	return pmd;
}
```

After this we fill `bm_pte` (early ioremap page table entries) with zeros and call the `pmd_populate_kernel` function:

```C
pmd = early_ioremap_pmd(fix_to_virt(FIX_BTMAP_BEGIN));
memset(bm_pte, 0, sizeof(bm_pte));
pmd_populate_kernel(&init_mm, pmd, bm_pte);
```

`pmd_populate_kernel` takes three parameters:

* `init_mm` - memory descriptor of the `init` process (you can read about it in the previous [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-5.html));
* `pmd`     - page middle directory of the beginning of the `ioremap` fixmaps;
* `bm_pte`  - early `ioremap` page table entries array which defined as:

```C
static pte_t bm_pte[PAGE_SIZE/sizeof(pte_t)] __page_aligned_bss;
```

The `pmd_populate_kernel` function is defined in the [arch/x86/include/asm/pgalloc.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/pgalloc.) and populates the page middle directory (`pmd`) provided as an argument with the given page table entries (`bm_pte`):

```C
static inline void pmd_populate_kernel(struct mm_struct *mm,
                                       pmd_t *pmd, pte_t *pte)
{
        paravirt_alloc_pte(mm, __pa(pte) >> PAGE_SHIFT);
        set_pmd(pmd, __pmd(__pa(pte) | _PAGE_TABLE));
}
```

where `set_pmd` is:

```C
#define set_pmd(pmdp, pmd)              native_set_pmd(pmdp, pmd)
```

and `native_set_pmd` is:

```C
static inline void native_set_pmd(pmd_t *pmdp, pmd_t pmd)
{
        *pmdp = pmd;
}
```

That's all. Early `ioremap` is ready to use. There are a couple of checks in the `early_ioremap_init` function, but they are not so important, anyway initialization of the `ioremap` is finished.

Use of early ioremap
--------------------------------------------------------------------------------

As soon as early `ioremap` has been setup successfully, we can use it. It provides two functions:

* early_ioremap
* early_iounmap

for mapping/unmapping of I/O physical address to virtual address. Both functions depend on the `CONFIG_MMU` configuration option. [Memory management unit](http://en.wikipedia.org/wiki/Memory_management_unit) is a special block of memory management. The main purpose of this block is the translation of physical addresses to virtual addresses. The memory management unit knows about the high-level page table addresses (`pgd`) from the `cr3` control register. If `CONFIG_MMU` options is set to `n`, `early_ioremap` just returns the given physical address and `early_iounmap` does nothing. If `CONFIG_MMU` option is set to `y`, `early_ioremap` calls `__early_ioremap` which takes three parameters:

* `phys_addr` - base physical address of the `I/O` memory region to map on virtual addresses;
* `size`      - size of the `I/O` memory region;
* `prot`      - page table entry bits.

First of all in the `__early_ioremap`, we go through all early ioremap fixmap slots and search for the first free one in the `prev_map` array. When we found it we remember its number in the `slot` variable and set up size:

```C
slot = -1;
for (i = 0; i < FIX_BTMAPS_SLOTS; i++) {
	if (!prev_map[i]) {
		slot = i;
		break;
	}
}
...
...
...
prev_size[slot] = size;
last_addr = phys_addr + size - 1;
```


In the next spte we can see the following code:

```C
offset = phys_addr & ~PAGE_MASK;
phys_addr &= PAGE_MASK;
size = PAGE_ALIGN(last_addr + 1) - phys_addr;
```

Here we are using `PAGE_MASK` for clearing all bits in the `phys_addr` except the first 12 bits. `PAGE_MASK` macro is defined as:

```C
#define PAGE_MASK       (~(PAGE_SIZE-1))
```

We know that size of a page is 4096 bytes or `1000000000000` in binary. `PAGE_SIZE - 1` will be `111111111111`, but with `~`, we will get `000000000000`, but as we use `~PAGE_MASK` we will get `111111111111` again. On the second line we do the same but clear the first 12 bits and getting page-aligned size of the area on the third line. We getting aligned area and now we need to get the number of pages which are occupied by the new `ioremap` area and calculate the fix-mapped index from `fixed_addresses` in the next steps:

```C
nrpages = size >> PAGE_SHIFT;
idx = FIX_BTMAP_BEGIN - NR_FIX_BTMAPS*slot;
```

Now we can fill `fix-mapped` area with the given physical addresses. On every iteration in the loop, we call the `__early_set_fixmap` function from the [arch/x86/mm/ioremap.c](https://github.com/torvalds/linux/blob/master/arch/x86/mm/ioremap.c), increase the given physical address by the page size which is `4096` bytes and update the `addresses` index and the number of pages:

```C
while (nrpages > 0) {
	__early_set_fixmap(idx, phys_addr, prot);
	phys_addr += PAGE_SIZE;
	--idx;
    --nrpages;
}
```

The `__early_set_fixmap` function gets the page table entry (stored in the `bm_pte`, see above) for the given physical address with:

```C
pte = early_ioremap_pte(addr);
```

In the next step of `early_ioremap_pte` we check the given page flags with the `pgprot_val` macro and call `set_pte` or `pte_clear` depending on the flags given:

```C
if (pgprot_val(flags))
		set_pte(pte, pfn_pte(phys >> PAGE_SHIFT, flags));
	else
		pte_clear(&init_mm, addr, pte);
```

As you can see above, we passed `FIXMAP_PAGE_IO` as flags to the `__early_ioremap`. `FIXMPA_PAGE_IO` expands to the:

```C
(__PAGE_KERNEL_EXEC | _PAGE_NX)
```

flags, so we call `set_pte` function to set the page table entry which works in the same manner as `set_pmd` but for PTEs (read above about it). As we have set all `PTEs` in the loop, we can now take a look at the call of the `__flush_tlb_one` function:

```C
__flush_tlb_one(addr);
```

This function is defined in [arch/x86/include/asm/tlbflush.h](https://github.com/torvalds/linux/blob/master) and calls `__flush_tlb_single` or `__flush_tlb` depending on the value of `cpu_has_invlpg`:

```C
static inline void __flush_tlb_one(unsigned long addr)
{
        if (cpu_has_invlpg)
                __flush_tlb_single(addr);
        else
                __flush_tlb();
}
```

The `__flush_tlb_one` function invalidates the given address in the [TLB](http://en.wikipedia.org/wiki/Translation_lookaside_buffer). As you just saw we updated the paging structure, but `TLB` is not informed of the changes, that's why we need to do it manually. There are two ways to do it. The first is to update the `cr3` control register and the `__flush_tlb` function does this:

```C
native_write_cr3(native_read_cr3());
```

The second method is to use the `invlpg` instruction to invalidate the `TLB` entry. Let's look at the `__flush_tlb_one` implementation. As you can see, first of all the function checks `cpu_has_invlpg` which is defined as:

```C
#if defined(CONFIG_X86_INVLPG) || defined(CONFIG_X86_64)
# define cpu_has_invlpg         1
#else
# define cpu_has_invlpg         (boot_cpu_data.x86 > 3)
#endif
```

If a CPU supports the `invlpg` instruction, we call the `__flush_tlb_single` macro which expands to the call of `__native_flush_tlb_single`:

```C
static inline void __native_flush_tlb_single(unsigned long addr)
{
        asm volatile("invlpg (%0)" ::"r" (addr) : "memory");
}
```

or call `__flush_tlb` which just updates the `cr3` register as we have seen. After this step execution of the `__early_set_fixmap` function is finished and we can go back to the `__early_ioremap` implementation. When we have set up the fixmap area for the given address, we need to save the base virtual address of the I/O Re-mapped area in the `prev_map` using the `slot` index:

```C
prev_map[slot] = (void __iomem *)(offset + slot_virt[slot]);
```

and return it.

The second function, `early_iounmap`, unmaps an `I/O` memory region. This function takes two parameters: base address and size of a `I/O` region and generally looks very similar to `early_ioremap`. It also goes through fixmap slots and looks for a slot with the given address. After that, it gets the index of the fixmap slot and calls `__late_clear_fixmap` or `__early_set_fixmap` depending on the `after_paging_init` value. It calls `__early_set_fixmap` with one difference to how `early_ioremap` does it: `early_iounmap` passes `zero` as physical address. And in the end it sets the address of the I/O memory region to `NULL`:

```C
prev_map[slot] = NULL;
```

That's all about `fixmaps` and `ioremap`. Of course this part does not cover all features of `ioremap`, only early ioremap but there is also normal ioremap. But we need to know more things before we study that in more detail.

So, this is the end!

Conclusion
--------------------------------------------------------------------------------

This is the end of the second part about linux kernel memory management. If you have questions or suggestions, ping me on twitter [0xAX](https://twitter.com/0xAX), drop me an [email](anotherworldofworld@gmail.com) or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me a PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [apic](http://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller)
* [vsyscall](https://lwn.net/Articles/446528/)
* [Intel Trusted Execution Technology](http://en.wikipedia.org/wiki/Trusted_Execution_Technology)
* [Xen](http://en.wikipedia.org/wiki/Xen)
* [Real Time Clock](http://en.wikipedia.org/wiki/Real-time_clock)
* [e820](http://en.wikipedia.org/wiki/E820)
* [Memory management unit](http://en.wikipedia.org/wiki/Memory_management_unit)
* [TLB](http://en.wikipedia.org/wiki/Translation_lookaside_buffer)
* [Paging](http://0xax.gitbooks.io/linux-insides/content/Theory/Paging.html)
* [Linux kernel memory management Part 1.](http://0xax.gitbooks.io/linux-insides/content/mm/linux-mm-1.html)
