Инициализация ядра. Часть 3.
================================================================================

Последние приготовления перед точкой входа ядра
--------------------------------------------------------------------------------

Это третья часть серии Инициализация ядра. В предыдущей [части](linux-initialization-2.md) мы увидели начальную обработку прерываний и исключений и продолжим погружение в процесс инициализации ядра Linux в текущей части. Наша следующая точка - "точка входа ядра" - функция `start_kernel` из файла [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c). Да, технически это не точка входа ядра, а начало кода ядра, который не зависит от определенной архитектуры. Но прежде чем мы вызовем функцию `start_kernel`, мы должны совершить некоторые приготовления. Давайте продолжим.

Снова boot_params
--------------------------------------------------------------------------------

В предыдущей части мы остановились на настройке таблицы векторов прерываний и её загрузки в регистр `IDTR`. На следующем шаге мы можем видеть вызов функции `copy_bootdata`:

```C
copy_bootdata(__va(real_mode_data));
```

Эта функция принимает один аргумент - виртуальный адрес `real_mode_data`. Вы должны помнить, что мы передали адрес структуры  `boot_params` из [arch/x86/include/uapi/asm/bootparam.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/uapi/asm/bootparam.h#L114) в функцию `x86_64_start_kernel` как первый параметр  [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S):

```
	/* rsi is pointer to real mode structure with interesting info.
	   pass it to C */
	movq	%rsi, %rdi
```

Взглянем на макрос `__va`. Этот макрос определён в [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c):

```C
#define __va(x)                 ((void *)((unsigned long)(x)+PAGE_OFFSET))
```

где `PAGE_OFFSET` это `__PAGE_OFFSET` (`0xffff880000000000` и базовый виртуальный адрес прямого отображения всей физической памяти). Таким образом, мы получаем виртуальный адрес структуры `boot_params` и передаем его функции `copy_bootdata`, в которой мы копируем `real_mod_data` в ` boot_params`, объявленный в файле [arch/x86/include/asm/setup.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/setup.h)

```C
extern struct boot_params boot_params;
```

Давайте посмотрим на реализацию `copy_boot_data`:

```C
static void __init copy_bootdata(char *real_mode_data)
{
	char * command_line;
	unsigned long cmd_line_ptr;

	memcpy(&boot_params, real_mode_data, sizeof boot_params);
	sanitize_boot_params(&boot_params);
	cmd_line_ptr = get_cmd_line_ptr();
	if (cmd_line_ptr) {
		command_line = __va(cmd_line_ptr);
		memcpy(boot_command_line, command_line, COMMAND_LINE_SIZE);
	}
}
```

Прежде всего, обратите внимание на то что эта функция объявлена с префиксом `__init`. Это означает, что эта функция будет использоваться только во время инициализации и используемая память будет освобождена.

Мы можем видеть объявление двух переменных для командной строки ядра и копирование `real_mode_data` в `boot_params` функцией `memcpy`. Далее следует вызов функции `sanitize_boot_params`, который заполняет некоторые поля структуры `boot_params`, такие как `ext_ramdisk_image` и т.д, если загрузчики не инициализировал неизвестные поля в `boot_params` нулём. После этого мы получаем адрес командной строки вызовом функции `get_cmd_line_ptr`:

```C
unsigned long cmd_line_ptr = boot_params.hdr.cmd_line_ptr;
cmd_line_ptr |= (u64)boot_params.ext_cmd_line_ptr << 32;
return cmd_line_ptr;
```

который получает 64-битный адрес командной строки из заголовочного файла загрузки ядра и возвращает его. На последнем шаге мы проверяем `cmd_line_ptr`, получаем его виртуальный адрес и копируем его в `boot_command_line`, который представляет собой всего лишь массив байтов:

```C
extern char __initdata boot_command_line[];
```

После этого мы имеем скопированную командную строку ядра и структуру `boot_params`. На следующем шаге мы видим вызов функции `load_ucode_bsp`, которая загружает процессорный микрокод, его мы здесь не увидим.

После загрузки микрокода мы можем видеть проверку функции `console_loglevel` и` early_printk`, которая печатает строку `Kernel Alive`. Но вы никогда не увидите этот вывод, потому что `early_printk` еще не инициализирован. Это небольшая ошибка в ядре, и я (*[0xAX](https://github.com/0xAX), автор оригинальной книги - Прим. пер.*) отправил патч - [коммит](http://git.kernel.org/cgit/linux/kernel/git/tip/tip.git/commit/?id=91d8f0416f3989e248d3a3d3efb821eda10a85d2), чтобы исправить её.

Перемещение по страницам инициализации
--------------------------------------------------------------------------------

На следующем шаге, когда мы скопировали структуру `boot_params`, нам нужно перейти от ранних таблиц страницы к таблицам страниц для процесса инициализации. Мы уже настроили ранние таблицы страниц, вы можете прочитать об этом в предыдущей [части](linux-initialization-1.md) и сбросили это всё функцией `reset_early_page_tables` (вы тоже можете прочитать об этом в предыдущей части) и сохранили только отображение страниц ядра. После этого мы вызываем функцию `clear_page`:

```C
	clear_page(init_level4_pgt);
```

с аргументом `init_level4_pgt`, который определён в файле [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S) и выглядит следующим образом:

```assembly
NEXT_PAGE(init_level4_pgt)
	.quad   level3_ident_pgt - __START_KERNEL_map + _KERNPG_TABLE
	.org    init_level4_pgt + L4_PAGE_OFFSET*8, 0
	.quad   level3_ident_pgt - __START_KERNEL_map + _KERNPG_TABLE
	.org    init_level4_pgt + L4_START_KERNEL*8, 0
	.quad   level3_kernel_pgt - __START_KERNEL_map + _PAGE_TABLE
```

который отображает первые 2 гигабайта и 512 мегабайта для кода ядра, данных и bss. Функция `clear_page` определена в  [arch/x86/lib/clear_page_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/lib/clear_page_64.S). Давайте взглянем на неё:

```assembly
ENTRY(clear_page)
	CFI_STARTPROC
	xorl %eax,%eax
	movl $4096/64,%ecx
	.p2align 4
	.Lloop:
    decl	%ecx
#define PUT(x) movq %rax,x*8(%rdi)
	movq %rax,(%rdi)
	PUT(1)
	PUT(2)
	PUT(3)
	PUT(4)
	PUT(5)
	PUT(6)
	PUT(7)
	leaq 64(%rdi),%rdi
	jnz	.Lloop
	nop
	ret
	CFI_ENDPROC
	.Lclear_page_end:
	ENDPROC(clear_page)
```

Как вы можете понять из имени функции, она очищает или заполняет нулями таблицы страниц. Прежде всего обратите внимание, что эта функция начинается с макросов `CFI_STARTPROC` и `CFI_ENDPROC`, которые раскрываются до директив сборки GNU:

```C
#define CFI_STARTPROC           .cfi_startproc
#define CFI_ENDPROC             .cfi_endproc
```

и использутся для отладки. После макроса `CFI_STARTPROC` мы обнуляем регистр `eax` и помещаем 64 в `ecx` (это будет счётчик). Далее мы видим цикл, который начинается с метки `.Lloop` и декремента `ecx`. После этого мы помещаем нуль из регистра `rax` в `rdi`, который теперь содержит базовый адрес `init_level4_pgt` и выполняем ту же процедуру семь раз, но каждый раз перемещаем смещение `rdi` на 8. После этого первые 64 байта `init_level4_pgt` будут заполнены нулями. На следующем шаге мы снова помещаем адрес `init_level4_pgt` со смещением 64 байта в `rdi` и повторяем все операции до тех пор, пока `ecx` не будет равен нулю. В итоге мы получим `init_level4_pgt`, заполненный нулями.

После заполнения нулями `init_level4_pgt`, мы помещяем последнюю запись в `init_level4_pgt`:

```C
init_level4_pgt[511] = early_level4_pgt[511];
```

Вы должны помнить, что мы очистили все записи `early_level4_pgt` функцией `reset_early_page_table` и сохранили только отображение ядра.

Последний шаг в функции `x86_64_start_kernel` заключается в вызове функции `x86_64_start_reservations`:

```C
x86_64_start_reservations(real_mode_data);
```

с аргументов `real_mode_data`. Функция `x86_64_start_reservations` определена в том же файле исходного кода что и `x86_64_start_kernel`:

```C
void __init x86_64_start_reservations(char *real_mode_data)
{
	if (!boot_params.hdr.version)
		copy_bootdata(__va(real_mode_data));

	reserve_ebda_region();

	start_kernel();
}
```

Это последняя функция перед входом в точку ядра - `start_kernel`. Давайте посмотрим, что он делает и как это работает.

Последний шаг перед точкой входа в ядро
--------------------------------------------------------------------------------

First of all we can see in the `x86_64_start_reservations` function the check for `boot_params.hdr.version`:

```C
if (!boot_params.hdr.version)
	copy_bootdata(__va(real_mode_data));
```

and if it is zero we call `copy_bootdata` function again with the virtual address of the `real_mode_data` (read about its implementation).

In the next step we can see the call of the `reserve_ebda_region` function which defined in the [arch/x86/kernel/head.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head.c). This function reserves memory block for the `EBDA` or Extended BIOS Data Area. The Extended BIOS Data Area located in the top of conventional memory and contains data about ports, disk parameters and etc...

Let's look on the `reserve_ebda_region` function. It starts from the checking is paravirtualization enabled or not:

```C
if (paravirt_enabled())
	return;
```

we exit from the `reserve_ebda_region` function if paravirtualization is enabled because if it enabled the extended bios data area is absent. In the next step we need to get the end of the low memory:

```C
lowmem = *(unsigned short *)__va(BIOS_LOWMEM_KILOBYTES);
lowmem <<= 10;
```

We're getting the virtual address of the BIOS low memory in kilobytes and convert it to bytes with shifting it on 10 (multiply on 1024 in other words). After this we need to get the address of the extended BIOS data are with the:

```C
ebda_addr = get_bios_ebda();
```

where `get_bios_ebda` function defined in the [arch/x86/include/asm/bios_ebda.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/bios_ebda.h) and looks like:

```C
static inline unsigned int get_bios_ebda(void)
{
	unsigned int address = *(unsigned short *)phys_to_virt(0x40E);
	address <<= 4;
	return address;
}
```

Let's try to understand how it works. Here we can see that we converting physical address `0x40E` to the virtual, where `0x0040:0x000e` is the segment which contains base address of the extended BIOS data area. Don't worry that we are using `phys_to_virt` function for converting a physical address to virtual address. You can note that previously we have used `__va` macro for the same point, but `phys_to_virt` is the same:

```C
static inline void *phys_to_virt(phys_addr_t address)
{
         return __va(address);
}
```

only with one difference: we pass argument with the `phys_addr_t` which depends on `CONFIG_PHYS_ADDR_T_64BIT`:

```C
#ifdef CONFIG_PHYS_ADDR_T_64BIT
	typedef u64 phys_addr_t;
#else
	typedef u32 phys_addr_t;
#endif
```

This configuration option is enabled by `CONFIG_PHYS_ADDR_T_64BIT`. After that we got virtual address of the segment which stores the base address of the extended BIOS data area, we shift it on 4 and return. After this `ebda_addr` variables contains the base address of the extended BIOS data area.

In the next step we check that address of the extended BIOS data area and low memory is not less than `INSANE_CUTOFF` macro

```C
if (ebda_addr < INSANE_CUTOFF)
	ebda_addr = LOWMEM_CAP;

if (lowmem < INSANE_CUTOFF)
	lowmem = LOWMEM_CAP;
```

which is:

```C
#define INSANE_CUTOFF		0x20000U
```

or 128 kilobytes. In the last step we get lower part in the low memory and extended bios data area and call `memblock_reserve` function which will reserve memory region for extended bios data between low memory and one megabyte mark:

```C
lowmem = min(lowmem, ebda_addr);
lowmem = min(lowmem, LOWMEM_CAP);
memblock_reserve(lowmem, 0x100000 - lowmem);
```

`memblock_reserve` function is defined at [mm/block.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/mm/block.c) and takes two parameters:

* base physical address;
* region size.

and reserves memory region for the given base address and size. `memblock_reserve` is the first function in this book from linux kernel memory manager framework. We will take a closer look on memory manager soon, but now let's look at its implementation.

First touch of the linux kernel memory manager framework
--------------------------------------------------------------------------------

In the previous paragraph we stopped at the call of the `memblock_reserve` function and as i said before it is the first function from the memory manager framework. Let's try to understand how it works. `memblock_reserve` function just calls:

```C
memblock_reserve_region(base, size, MAX_NUMNODES, 0);
```

function and passes 4 parameters there:

* physical base address of the memory region;
* size of the memory region;
* maximum number of numa nodes;
* flags.

At the start of the `memblock_reserve_region` body we can see definition of the `memblock_type` structure:

```C
struct memblock_type *_rgn = &memblock.reserved;
```

which presents the type of the memory block and looks:

```C
struct memblock_type {
         unsigned long cnt;
         unsigned long max;
         phys_addr_t total_size;
         struct memblock_region *regions;
};
```

As we need to reserve memory block for extended bios data area, the type of the current memory region is reserved where `memblock` structure is:

```C
struct memblock {
         bool bottom_up;
         phys_addr_t current_limit;
         struct memblock_type memory;
         struct memblock_type reserved;
#ifdef CONFIG_HAVE_MEMBLOCK_PHYS_MAP
         struct memblock_type physmem;
#endif
};
```

and describes generic memory block. You can see that we initialize `_rgn` by assigning it to the address of the `memblock.reserved`. `memblock` is the global variable which looks:

```C
struct memblock memblock __initdata_memblock = {
	.memory.regions		= memblock_memory_init_regions,
	.memory.cnt		= 1,
	.memory.max		= INIT_MEMBLOCK_REGIONS,
	.reserved.regions	= memblock_reserved_init_regions,
	.reserved.cnt		= 1,
	.reserved.max		= INIT_MEMBLOCK_REGIONS,
#ifdef CONFIG_HAVE_MEMBLOCK_PHYS_MAP
	.physmem.regions	= memblock_physmem_init_regions,
	.physmem.cnt		= 1,
	.physmem.max		= INIT_PHYSMEM_REGIONS,
#endif
	.bottom_up		= false,
	.current_limit		= MEMBLOCK_ALLOC_ANYWHERE,
};
```

We will not dive into detail of this variable, but we will see all details about it in the parts about memory manager. Just note that `memblock` variable defined with the `__initdata_memblock` which is:

```C
#define __initdata_memblock __meminitdata
```

and `__meminit_data` is:

```C
#define __meminitdata    __section(.meminit.data)
```

From this we can conclude that all memory blocks will be in the `.meminit.data` section. After we defined `_rgn` we print information about it with `memblock_dbg` macros. You can enable it by passing `memblock=debug` to the kernel command line.

After debugging lines were printed next is the call of the following function:

```C
memblock_add_range(_rgn, base, size, nid, flags);
```

which adds new memory block region into the `.meminit.data` section. As we do not initialize `_rgn` but it just contains `&memblock.reserved`, we just fill passed `_rgn` with the base address of the extended BIOS data area region, size of this region and flags:

```C
if (type->regions[0].size == 0) {
    WARN_ON(type->cnt != 1 || type->total_size);
    type->regions[0].base = base;
    type->regions[0].size = size;
    type->regions[0].flags = flags;
    memblock_set_region_node(&type->regions[0], nid);
    type->total_size = size;
    return 0;
}
```

After we filled our region we can see the call of the `memblock_set_region_node` function with two parameters:

* address of the filled memory region;
* NUMA node id.

where our regions represented by the `memblock_region` structure:

```C
struct memblock_region {
    phys_addr_t base;
	phys_addr_t size;
	unsigned long flags;
#ifdef CONFIG_HAVE_MEMBLOCK_NODE_MAP
    int nid;
#endif
};
```

NUMA node id depends on `MAX_NUMNODES` macro which is defined in the [include/linux/numa.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/numa.h):

```C
#define MAX_NUMNODES    (1 << NODES_SHIFT)
```

where `NODES_SHIFT` depends on `CONFIG_NODES_SHIFT` configuration parameter and defined as:

```C
#ifdef CONFIG_NODES_SHIFT
  #define NODES_SHIFT     CONFIG_NODES_SHIFT
#else
  #define NODES_SHIFT     0
#endif
```

`memblick_set_region_node` function just fills `nid` field from `memblock_region` with the given value:

```C
static inline void memblock_set_region_node(struct memblock_region *r, int nid)
{
         r->nid = nid;
}
```

After this we will have first reserved `memblock` for the extended bios data area in the `.meminit.data` section. `reserve_ebda_region` function finished its work on this step and we can go back to the [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head64.c).

We finished all preparations before the kernel entry point! The last step in the `x86_64_start_reservations` function is the call of the:

```C
start_kernel()
```

function from [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c) file.

That's all for this part.

Conclusion
--------------------------------------------------------------------------------

It is the end of the third part about linux kernel insides. In next part we will see the first initialization steps in the kernel entry point - `start_kernel` function. It will be the first step before we will see launch of the first `init` process.

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [BIOS data area](http://stanislavs.org/helppc/bios_data_area.html)
* [What is in the extended BIOS data area on a PC?](http://www.kryslix.com/nsfaq/Q.6.html)
* [Previous part](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-2.md)
