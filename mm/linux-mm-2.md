Linux kernel memory management Part 2.
================================================================================

Fix-Mapped Addresses and ioremap
--------------------------------------------------------------------------------

`Fix-Mapped` addresses are a set of special compile-time addresses whose corresponding physical address do not have to be a linear address minus `__START_KERNEL_map`. Each fix-mapped address maps one page frame and the kernel uses them as pointers that never change their address. That is the main point of these addresses. As the comment says: `to have a constant address at compile time, but to set the physical address only in the boot process`. You can remember that in the earliest [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-1.html), we already set the `level2_fixmap_pgt`:

```assembly
NEXT_PAGE(level2_fixmap_pgt)
	.fill	506,8,0
	.quad	level1_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE
	.fill	5,8,0

NEXT_PAGE(level1_fixmap_pgt)
	.fill	512,8,0
```

As you can see `level2_fixmap_pgt` is right after the `level2_kernel_pgt` which is kernel code+data+bss. Every fix-mapped address is represented by an integer index which is defined in the `fixed_addresses` enum from the [arch/x86/include/asm/fixmap.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/fixmap.h). For example it contains entries for `VSYSCALL_PAGE` - if emulation of legacy vsyscall page is enabled, `FIX_APIC_BASE` for local [apic](h
ttp://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller) and etc... In a virtual memory fix-mapped area is placed in the modules area:

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

Here `__end_of_permanent_fixed_addresses` is an element of the `fixed_addresses` enum and as I wrote above: Every fix-mapped address is represented by an integer index which is defined in the `fixed_addresses`. `PAGE_SHIFT` determines size of a page. For example size of the one page we can get with the `1 << PAGE_SHIFT`. In our case we need to get the size of the fix-mapped area, but not only of one page, that's why we are using `__end_of_permanent_fixed_addresses` for getting the size of the fix-mapped area. In my case it's a little more than `536` killobytes. In your case it might be a different number, because the size depends on amount of the fix-mapped addresses which are depends on your kernel's configuration.

The second `FIXADDR_START` macro just extracts from the last address of the fix-mapped area its size for getting base virtual address of the fix-mapped area. `FIXADDR_TOP` is rounded up address from the base address of the [vsyscall](https://lwn.net/Articles/446528/) space:

```C
#define FIXADDR_TOP     (round_up(VSYSCALL_ADDR + PAGE_SIZE, 1<<PMD_SHIFT) - PAGE_SIZE)
```

The `fixed_addresses` enums are used as an index to get the virtual address using the `fix_to_virt` function. Implementation of this function is easy:
 
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

`virt_to_fix` takes virtual address, checks that this address is between `FIXADDR_START` and `FIXADDR_TOP` and calls `__virt_to_fix` macro which implemented as:

```C
#define __virt_to_fix(x)        ((FIXADDR_TOP - ((x)&PAGE_MASK)) >> PAGE_SHIFT)
```

A PFN is simply an index within physical memory that is counted in page-sized units. PFN for a physical address could be trivially defined as (page_phys_addr >> PAGE_SHIFT);

`__virt_to_fix` clears the first 12 bits in the given address, subtracts it from the last address the of `fix-mapped` area (`FIXADDR_TOP`) and shifts right result on `PAGE_SHIFT` which is `12`. Let me explain how it works. As I already wrote we will clear the first 12 bits in the given address with `x & PAGE_MASK`. As we subtract this from the `FIXADDR_TOP`, we will get the last 12 bits of the `FIXADDR_TOP` which are present. We know that the first 12 bits of the virtual address represent the offset in the page frame. With the shiting it on `PAGE_SHIFT` we will get `Page frame number` which is just all bits in a virtual address besides the first 12 offset bits. `Fix-mapped` addresses are used in different [places](http://lxr.free-electrons.com/ident?i=fix_to_virt) in the linux kernel. `IDT` descriptor stored there, [Intel Trusted Execution Technology](http://en.wikipedia.org/wiki/Trusted_Execution_Technology) UUID stored in the `fix-mapped` area started from `FIX_TBOOT_BASE` index, [Xen](http://en.wikipedia.org/wiki/Xen) bootmap and many more... We already saw a little about `fix-mapped` addresses in the fifth [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-5.html) about linux kernel initialization. We used `fix-mapped` area in the early `ioremap` initialization. Let's look on it and try to understand what is it `ioremap`, how it is implemented in the kernel and how it is releated to the `fix-mapped` addresses.

ioremap
--------------------------------------------------------------------------------

Linux kernel provides many different primitives to manage memory. For this moment we will touch `I/O memory`. Every device is controlled by reading/writing from/to its registers. For example a driver can turn off/on a device by writing to its registers or get the state of a device by reading from its registers. Besides registers, many devices have buffers where a driver can write something or read from there. As we know for this moment there are two ways to access device's registers and data buffers:

* through the I/O ports;
* mapping of the all registers to the memory address space;

In the first case every control register of a device has a number of input and output port. And driver of a device can read from a port and write to it with two `in` and `out` instructions which we already saw. If you want to know about currently registered port regions, you can know they by accessing of `/proc/ioports`:

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

`/proc/ioporst` provides information about what driver used address of a `I/O` ports region. All of these memory regions, for example `0000-0cf7`, were claimed with the `request_region` function from the [include/linux/ioport.h](https://github.com/torvalds/linux/blob/master/include/linux/ioport.h). Actually `request_region` is a macro which defied as:

```C
#define request_region(start,n,name)   __request_region(&ioport_resource, (start), (n), (name), 0)
```

As we can see it takes three parameters:

* `start` -  begin of region;
* `n`     -  length of region;
* `name`  -  name of requester.

`request_region` allocates `I/O` port region. Very often `check_region` function called before the `request_region` to check that the given address range is available and `release_region` to release memory region. `request_region` returns pointer to the `resource` structure. `resource` structure presents abstraction for a tree-like subset of system resources. We already saw `resource` structure in the firth part about kernel [initialization](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-5.html) process and it looks as:

```C
struct resource {
        resource_size_t start;
        resource_size_t end;
        const char *name;
        unsigned long flags;
        struct resource *parent, *sibling, *child;
};
```

and contains start and end addresses of the resource, name and etc... Every `resource` structure contains pointers to the `parent`, `slibling` and `child` resources. As it has parent and childs, it means that every subset of resuorces has root `resource` structure. For example, for `I/O` ports it is `ioport_resource` structure:

```C
struct resource ioport_resource = {
         .name   = "PCI IO",
         .start  = 0,
         .end    = IO_SPACE_LIMIT,
        .flags  = IORESOURCE_IO,
};
EXPORT_SYMBOL(ioport_resource);
```

Or for `iomem`, it is `iomem_resource` structure:

```C
struct resource iomem_resource = {
        .name   = "PCI mem",
        .start  = 0,
        .end    = -1,
        .flags  = IORESOURCE_MEM,
};
```

As I wrote about `request_regions` is used for registering of I/O port region and this macro used in many [places](http://lxr.free-electrons.com/ident?i=request_region) in the kernel. For example let's look at [drivers/char/rtc.c](https://github.com/torvalds/linux/blob/master/char/rtc.c). This source code file provides [Real Time Clock](http://en.wikipedia.org/wiki/Real-time_clock) interface in the linux kernel. As every kernel module, `rtc` module contains `module_init` definition:

```C
module_init(rtc_init);
```

where `rtc_init` is `rtc` initialization function. This function defined in the same `rtc.c` source code file. In the `rtc_init` function we can see a couple calls of the `rtc_request_region` functions, which wrap `request_region` for example:

```C
r = rtc_request_region(RTC_IO_EXTENT);
```

where `rtc_request_region` calls:

```C
r = request_region(RTC_PORT(0), size, "rtc");
```

Here `RTC_IO_EXTENT` is a size of memory region and it is `0x8`, `"rtc"` is a name of region and `RTC_PORT` is:

```C
#define RTC_PORT(x)     (0x70 + (x))
```

So with the `request_region(RTC_PORT(0), size, "rtc")` we register memory region, started at `0x70` and with size `0x8`. Let's look on the `/proc/ioports`:

```
~$ sudo cat /proc/ioports | grep rtc
0070-0077 : rtc0
```

So, we got it! Ok, it was ports. The second way is use of `I/O` memory. As I wrote above this way is mapping of control registers and memory of a device to the memory address space. `I/O` memory is a set of contiguous addresses which are provided by a device to CPU through a bus. All memory-mapped I/O addresses are not used by the kernel directly. There is a special `ioremap` function which allows us to covert the physical address on a bus to the kernel virtual address or in another words `ioremap` maps I/O physical memory region to access it from the kernel. The `ioremap` function takes two parameters:

* start of the memory region;
* size of the memory region;

I/O memory mapping API provides function for the checking, requesting and release of a memory region as this does I/O ports API. There are three functions for it:

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

Part of these addresses is from the call of the `e820_reserve_resources` function. We can find call of this function in the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c) and the function itself defined in the [arch/x86/kernel/e820.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/e820.c). `e820_reserve_resources` goes through the [e820](http://en.wikipedia.org/wiki/E820) map and inserts memory regions to the root `iomem` resource structure. All `e820` memory regions which are will be inserted to the `iomem` resource will have following types:

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

and we can see it in the `/proc/iomem` (read above).

Now let's try to understand how `ioremap` works. We already know a little about `ioremap`, we saw it in the fifth [part](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-5.html) about linux kernel initialization. If you have read this part, you can remember the call of the `early_ioremap_init` function from the [arch/x86/mm/ioremap.c](https://github.com/torvalds/linux/blob/master/arch/x86/mm/ioremap.c). Initialization of the `ioremap` is split inn two parts: there is the early part which we can use before the normal `ioremap` is available and the normal `ioremap` which is available after `vmalloc` initialization and call of the `paging_init`. We do not know anything about `vmalloc` for now, so let's consider early initialization of the `ioremap`. First of all `early_ioremap_init` checks that `fixmap` is aligned on page middle directory boundary:

```C
BUILD_BUG_ON((fix_to_virt(0) + PAGE_SIZE) & ((1 << PMD_SHIFT) - 1));
```

more about `BUILD_BUG_ON` you can read in the first part about [Linux Kernel initialization](http://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-1.html). So `BUILD_BUG_ON` macro raises compilation error if the given expression is true. In the next step after this check, we can see call of the `early_ioremap_setup` function from the [mm/early_ioremap.c](https://github.com/torvalds/linux/blob/master/mm/early_ioremap.c). This function presents generic initialization of the `ioremap`. `early_ioremap_setup` function fills the `slot_virt` array with the virtual addresses of the early fixmaps. All early fixmaps are after `__end_of_permanent_fixed_addresses` in memory. They are stats from the `FIX_BITMAP_BEGIN` (top) and ends with `FIX_BITMAP_END` (down). Actually there are `512` temporary boot-time mappings, used by early `ioremap`:

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

`slot_virt` contains virtual addresses of the `fix-mapped` areas, `prev_map` array contains addresses of the early ioremap areas. Note that I wrote above: `Actually there are 512 temporary boot-time mappings, used by early ioremap` and you can see that all arrays defined with the `__initdata` attribute which means that this memory will be released after kernel initialization process. After `early_ioremap_setup` finished to work, we're getting page middle directory where early ioremap beginning with the `early_ioremap_pmd` function which just gets the base address of the page global directory and calculates the page middle directory for the given address:

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

After this we fills `bm_pte` (early ioremap page table entries) with zeros and call the `pmd_populate_kernel` function:

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

The `pmd_popularte_kernel` function defined in the [arch/x86/include/asm/pgalloc.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/pgalloc.) and populates given page middle directory (`pmd`) with the given page table entries (`bm_pte`):

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

As early `ioremap` is setup, we can use it. It provides two functions:

* early_ioremap
* early_iounmap

for mapping/unmapping of IO physical address to virtual address. Both functions depends on `CONFIG_MMU` configuration option. [Memory management unit](http://en.wikipedia.org/wiki/Memory_management_unit) is a special block of memory management. Main purpose of this block is translation physical addresses to the virtual. Techinically memory management unit knows about high-level page table address (`pgd`) from the `cr3` control register. If `CONFIG_MMU` options is set to `n`, `early_ioremap` just returns the given physical address and `early_iounmap` does not nothing. In other way, if `CONFIG_MMU` option is set to `y`, `early_ioremap` calls `__early_ioremap` which takes three parameters:

* `phys_addr` - base physicall address of the `I/O` memory region to map on virtual addresses;
* `size`      - size of the `I/O` memroy region;
* `prot`      - page table entry bits.

First of all in the `__early_ioremap`, we goes through the all early ioremap fixmap slots and check first free are in the `prev_map` array and remember it's number in the `slot` variable and set up size as we found it:

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

Here we are using `PAGE_MASK` for clearing all bits in the `phys_addr` besides first 12 bits. `PAGE_MASK` macro defined as:

```C
#define PAGE_MASK       (~(PAGE_SIZE-1))
```

We know that size of a page is 4096 bytes or `1000000000000` in binary. `PAGE_SIZE - 1` will be `111111111111`, but with `~`, we will get `000000000000`, but as we use `~PAGE_MASK` we will get `111111111111` again. On the second line we do the same but clear first 12 bits and getting page-aligned size of the area on the third line. We getting aligned area and now we need to get the number of pages which are occupied by the new `ioremap` are and calculate the fix-mapped index from `fixed_addresses` in the next steps:

```C
nrpages = size >> PAGE_SHIFT;
idx = FIX_BTMAP_BEGIN - NR_FIX_BTMAPS*slot;
```

Now we can fill `fix-mapped` area with the given physical addresses. Every iteration in the loop, we call `__early_set_fixmap` function from the [arch/x86/mm/ioremap.c](https://github.com/torvalds/linux/blob/master/arch/x86/mm/ioremap.c), increase given physical address on page size which is `4096` bytes and update `addresses` index and number of pages: 

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

In the next step of the `early_ioremap_pte` we check the given page flags with the `pgprot_val` macro and calls `set_pte` or `pte_clear` depends on it:

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

flags, so we call `set_pte` function for setting page table entry which works in the same manner as `set_pmd` but for PTEs (read above about it). As we set all `PTEs` in the loop, we can see the call of the `__flush_tlb_one` function:

```C
__flush_tlb_one(addr);
```

This function defined in the [arch/x86/include/asm/tlbflush.h](https://github.com/torvalds/linux/blob/master) and calls `__flush_tlb_single` or `__flush_tlb` depends on value of the `cpu_has_invlpg`:

```C
static inline void __flush_tlb_one(unsigned long addr)
{
        if (cpu_has_invlpg)
                __flush_tlb_single(addr);
        else
                __flush_tlb();
}
```

`__flush_tlb_one` function invalidates given address in the [TLB](http://en.wikipedia.org/wiki/Translation_lookaside_buffer). As you just saw we updated paging structure, but `TLB` not informed of changes, that's why we need to do it manually. There are two ways how to do it. First is update `cr3` control register and `__flush_tlb` function does this:

```C
native_write_cr3(native_read_cr3());
```

The second method is to use `invlpg` instruction invalidates `TLB` entry. Let's look on `__flush_tlb_one` implementation. As you can see first of all it checks `cpu_has_invlpg` which defined as: 

```C
#if defined(CONFIG_X86_INVLPG) || defined(CONFIG_X86_64)
# define cpu_has_invlpg         1
#else
# define cpu_has_invlpg         (boot_cpu_data.x86 > 3)
#endif
```

If a CPU support `invlpg` instruction, we call the `__flush_tlb_single` macro which expands to the call of the `__native_flush_tlb_single`:

```C
static inline void __native_flush_tlb_single(unsigned long addr)
{
        asm volatile("invlpg (%0)" ::"r" (addr) : "memory");
}
```

or call `__flush_tlb` which just updates `cr3` register as we saw it above. After this step execution of the `__early_set_fixmap` function is finsihed and we can back to the `__early_ioremap` implementation. As we set fixmap area for the given address, need to save the base virtual address of the I/O Re-mapped area in the `prev_map` with the `slot` index:

```C
prev_map[slot] = (void __iomem *)(offset + slot_virt[slot]);
```

and return it.

The second function is - `early_iounmap` - unmaps an `I/O` memory region. This function takes two parameters: base address and size of a `I/O` region and generally looks very similar on `early_ioremap`. It also goes through fixmap slots and looks for slot with the given address. After this it gets the index of the fixmap slot and calls `__late_clear_fixmap` or `__early_set_fixmap` depends on `after_paging_init` value. It calls `__early_set_fixmap` with on difference then it does `early_ioremap`: it passes `zero` as physicall address. And in the end it sets address of the I/O memory region to `NULL`:

```C
prev_map[slot] = NULL;
```

That's all about `fixmaps` and `ioremap`. Of course this part does not cover full features of the `ioremap`, it was only early ioremap, but there is also normal ioremap. But we need to know more things than now before it.

So, this is the end!

Conclusion
--------------------------------------------------------------------------------

This is the end of the second part about linux kernel memory management. If you have questions or suggestions, ping me on twitter [0xAX](https://twitter.com/0xAX), drop me an [email](anotherworldofworld@gmail.com) or just create an [issue](https://github.com/0xAX/linux-internals/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me a PR to [linux-internals](https://github.com/0xAX/linux-internals).**

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
