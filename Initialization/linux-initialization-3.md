Инициализация ядра. Часть 3.
================================================================================

Последние приготовления перед точкой входа в ядро
--------------------------------------------------------------------------------

Это третья часть серии Инициализация ядра. В предыдущей [части](linux-initialization-2.md) мы увидели начальную обработку прерываний и исключений и продолжим погружение в процесс инициализации ядра Linux в текущей части. Наша следующая точка - "точка входа в ядро" - функция `start_kernel` из файла [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c). Да, технически это не точка входа в ядро, а начало кода ядра, который не зависит от определённой архитектуры. Но прежде чем мы вызовем функцию `start_kernel`, мы должны совершить некоторые приготовления. Давайте продолжим.

Снова boot_params
--------------------------------------------------------------------------------

В предыдущей части мы остановились на настройке таблицы векторов прерываний и её загрузки в регистр `IDTR`. На следующем шаге мы можем видеть вызов функции `copy_bootdata`:

```C
copy_bootdata(__va(real_mode_data));
```

Эта функция принимает один аргумент - виртуальный адрес `real_mode_data`. Вы должны помнить, что мы передали адрес структуры  `boot_params` из [arch/x86/include/uapi/asm/bootparam.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/uapi/asm/bootparam.h#L114) в функцию `x86_64_start_kernel` как первый параметр в [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S):

```
	/* rsi is pointer to real mode structure with interesting info.
	   pass it to C */
	movq	%rsi, %rdi
```

Взглянем на макрос `__va`. Этот макрос определён в [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c):

```C
#define __va(x)                 ((void *)((unsigned long)(x)+PAGE_OFFSET))
```

где `PAGE_OFFSET` это `__PAGE_OFFSET` (`0xffff880000000000` и базовый виртуальный адрес прямого отображения всей физической памяти). Таким образом, мы получаем виртуальный адрес структуры `boot_params` и передаём его функции `copy_bootdata`, в которой мы копируем `real_mod_data` в ` boot_params`, объявленный в файле [arch/x86/include/asm/setup.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/setup.h)

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

Прежде всего, обратите внимание на то, что эта функция объявлена с префиксом `__init`. Это означает, что эта функция будет использоваться только во время инициализации и используемая память будет освобождена.

Мы можем видеть объявление двух переменных для командной строки ядра и копирование `real_mode_data` в `boot_params` функцией `memcpy`. Далее следует вызов функции `sanitize_boot_params`, которая заполняет некоторые поля структуры `boot_params`, такие как `ext_ramdisk_image` и т.д, если загрузчики не инициализировал неизвестные поля в `boot_params` нулём. После этого мы получаем адрес командной строки вызовом функции `get_cmd_line_ptr`:

```C
unsigned long cmd_line_ptr = boot_params.hdr.cmd_line_ptr;
cmd_line_ptr |= (u64)boot_params.ext_cmd_line_ptr << 32;
return cmd_line_ptr;
```

который получает 64-битный адрес командной строки из заголовочного файла загрузки ядра и возвращает его. На последнем шаге мы проверяем `cmd_line_ptr`, получаем его виртуальный адрес и копируем его в `boot_command_line`, который представляет собой всего лишь массив байтов:

```C
extern char __initdata boot_command_line[];
```

После этого мы имеем скопированную командную строку ядра и структуру `boot_params`. На следующем шаге происходит вызов функции `load_ucode_bsp`, которая загружает процессорный микрокод, его мы здесь не увидим.

После загрузки микрокода мы можем видеть проверку функции `console_loglevel` и `early_printk`, которая печатает строку `Kernel Alive`. Но вы никогда не увидите этот вывод, потому что `early_printk` еще не инициализирован. Это небольшая ошибка в ядре, и я (*[0xAX](https://github.com/0xAX), автор оригинальной книги - Прим. пер.*) отправил патч - [коммит](http://git.kernel.org/cgit/linux/kernel/git/tip/tip.git/commit/?id=91d8f0416f3989e248d3a3d3efb821eda10a85d2), чтобы исправить её.

Перемещение по страницам инициализации
--------------------------------------------------------------------------------

На следующем шаге, когда мы скопировали структуру `boot_params`, нам нужно перейти от начальных таблиц страниц к таблицам страниц для процесса инициализации. Мы уже настроили начальные таблицы страниц, вы можете прочитать об этом в предыдущей [части](linux-initialization-1.md) и сбросили это всё функцией `reset_early_page_tables` (вы тоже можете прочитать об этом в предыдущей части) и сохранили только отображение страниц ядра. После этого мы вызываем функцию `clear_page`:

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

Он отображает первые 2 гигабайта и 512 мегабайта для кода ядра, данных и bss. Функция `clear_page` определена в  [arch/x86/lib/clear_page_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/lib/clear_page_64.S). Давайте взглянем на неё:

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

и используются для отладки. После макроса `CFI_STARTPROC` мы обнуляем регистр `eax` и помещаем 64 в `ecx` (это будет счётчик). Далее мы видим цикл, который начинается с метки `.Lloop` и декремента `ecx`. После этого мы помещаем нуль из регистра `rax` в `rdi`, который теперь содержит базовый адрес `init_level4_pgt` и выполняем ту же процедуру семь раз, но каждый раз перемещаем смещение `rdi` на 8. После этого первые 64 байта `init_level4_pgt` будут заполнены нулями. На следующем шаге мы снова помещаем адрес `init_level4_pgt` со смещением 64 байта в `rdi` и повторяем все операции до тех пор, пока `ecx` не будет равен нулю. В итоге мы получим `init_level4_pgt`, заполненный нулями.

После заполнения нулями `init_level4_pgt`, мы помещаем последнюю запись в `init_level4_pgt`:

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

В первую очередь мы видим проверку `boot_params.hdr.version` в функции `x86_64_start_reservations`:

```C
if (!boot_params.hdr.version)
	copy_bootdata(__va(real_mode_data));
```

и если он равен нулю то снова вызывается функция `copy_bootdata` с виртуальным адресом `real_mode_data`.

В следующем шаге мы видим вызов функции `reserve_ebda_region`, определённой в файле [arch/x86/kernel/head.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head.c). Эта функция резервирует блок памяти для `EBDA` или `Extended BIOS Data Area`. `Extended BIOS Data Area` расположена в верхних адресах основной области памяти (conventional memory) и содержит данные о портах, параметрах диска и т.д.

Давайте посмотрим на функцию `reserve_ebda_region`. Он начинается с проверки, включена ли паравиртуализация или нет:

```C
if (paravirt_enabled())
	return;
```

если паравиртуализация включена, мы выходим из функции `reserve_ebda_region`, потому что `EBDA` отсутствует. На следующем шаге нам нужно получить конец нижней области памяти:

```C
lowmem = *(unsigned short *)__va(BIOS_LOWMEM_KILOBYTES);
lowmem <<= 10;
```

Мы получаем виртуальный адрес нижней области памяти BIOS в килобайтах и преобразуем его в байты, сдвигая его на 10 (другими словами умножаем на 1024). После этого нам нужно получить адрес `EBDA`:

```C
ebda_addr = get_bios_ebda();
```

Функция `get_bios_ebda` определена в файле [arch/x86/include/asm/bios_ebda.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/bios_ebda.h):

```C
static inline unsigned int get_bios_ebda(void)
{
	unsigned int address = *(unsigned short *)phys_to_virt(0x40E);
	address <<= 4;
	return address;
}
```

Давайте попробуем понять, как это работает. Мы видим преобразование физического адреса `0x40E` в виртуальный, где `0x0040: 0x000e` - это сегмент, который содержит базовый адрес `EBDA`. Не беспокойтесь о том, что мы используем функцию `phys_to_virt` для преобразования физического адреса в виртуальный. Вы можете заметить, что ранее мы использовали макрос `__va`, но `phys_to_virt` - это то же самое:

```C
static inline void *phys_to_virt(phys_addr_t address)
{
         return __va(address);
}
```

только с одним отличием: мы передаем аргумент `phys_addr_t`, который зависит от `CONFIG_PHYS_ADDR_T_64BIT`:

```C
#ifdef CONFIG_PHYS_ADDR_T_64BIT
	typedef u64 phys_addr_t;
#else
	typedef u32 phys_addr_t;
#endif
```

Мы получили виртуальный адрес сегмента, в котором хранится базовый адрес `EBDA`. Мы сдвигаем его на 4 и возвращаем как результат. После этого переменная `ebda_addr` содержит базовый адрес `EBDA`.

На следующем шаге мы проверяем, что адрес `EBDA` и нижняя область памяти не меньше, чем значение макроса `INSANE_CUTOFF`:

```C
if (ebda_addr < INSANE_CUTOFF)
	ebda_addr = LOWMEM_CAP;

if (lowmem < INSANE_CUTOFF)
	lowmem = LOWMEM_CAP;
```

где `INSANE_CUTOFF`:

```C
#define INSANE_CUTOFF		0x20000U
```

или 128 килобайт. На последнем шаге мы получаем нижнюю часть нижней области памяти и `EBDA` и вызываем функцию `memblock_reserve`, которая резервирует область памяти для `EBDA` между нижней областью памяти и одномегабайтной меткой:

```C
lowmem = min(lowmem, ebda_addr);
lowmem = min(lowmem, LOWMEM_CAP);
memblock_reserve(lowmem, 0x100000 - lowmem);
```

функция `memblock_reserve` определена в [mm/block.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/mm/block.c) и принимает два аргумента:

* базовый физический адрес;
* размер области памяти.

и резервирует область памяти для заданного базового адреса и размера. `memblock_reserve` - первая функция в этой книге из фреймворка менеджера памяти ядра Linux. Мы скоро рассмотрим менеджер памяти, но пока что посмотрим на его реализацию.

Первое знакомство с фреймворком менеджера памяти ядра Linux
--------------------------------------------------------------------------------

В предыдущем абзаце мы остановились на вызове функции `memblock_reserve` и, как я уже сказал, это первая функция из фреймворка менеджера памяти. Давайте попробуем понять, как это работает. `memblock_reserve` просто вызывает функцию:

```C
memblock_reserve_region(base, size, MAX_NUMNODES, 0);
```

и передаёт ей 4 аргумента:

* физический базовый адрес области памяти;
* размер области памяти;
* максимально число NUMA-узлов;
* флаги.

В начале тела функции `memblock_reserve_region` мы можем видеть определение структуры `memblock_type`:

```C
struct memblock_type *_rgn = &memblock.reserved;
```

которая представляет тип блока памяти:

```C
struct memblock_type {
         unsigned long cnt;
         unsigned long max;
         phys_addr_t total_size;
         struct memblock_region *regions;
};
```

Поскольку нам необходимо зарезервировать блок памяти для `EBDA`, тип текущей области памяти зарезервирован так же, где и структура `memblock`:

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

и описывает общий блок памяти. Мы инициализируем `_rgn` адресом `memblock.reserved`. `memblock` - глобальная переменная:

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

Мы не будем погружаться в детали этой переменной, но мы увидим все подробности об этом в частях о менеджере памяти. Просто отметьте, что переменная `memblock` определена с помощью` __initdata_memblock`:

```C
#define __initdata_memblock __meminitdata
```

где `__meminit_data`:

```C
#define __meminitdata    __section(.meminit.data)
```

Из этого можно сделать вывод, что все блоки памяти будут в секции `.meminit.data`. После того как мы определили `_rgn`, мы печатаем информацию об этом с помощью макроса `memblock_dbg`. Вы можете включить его, передав `memblock = debug` в командную строку ядра.

После печати строк отладки следует вызов функции `memblock_add_range`:

```C
memblock_add_range(_rgn, base, size, nid, flags);
```

которая добавляет новую область блока памяти в секцию `.meminit.data`. Поскольку мы не инициализируем `_rgn` и он содержит `&memblock.reserved`, мы просто заполняем переданный `_rgn` базовым адресом `EBDA`, размером этой области  и флагами:

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

После заполнения нашей области памяти мы видим вызов функции `memblock_set_region_node` с двумя аргументами:

* адрес заполненной области памяти;
* id NUMA-узла.

где наши области памяти представлены структурой `memblock_region`:

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

Id NUMA-узла зависит от макроса `MAX_NUMNODES`, определённого в файле [include/linux/numa.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/numa.h):

```C
#define MAX_NUMNODES    (1 << NODES_SHIFT)
```

где `NODES_SHIFT` зависит от параметра конфигурации `CONFIG_NODES_SHIFT`:

```C
#ifdef CONFIG_NODES_SHIFT
  #define NODES_SHIFT     CONFIG_NODES_SHIFT
#else
  #define NODES_SHIFT     0
#endif
```

Функция `memblick_set_region_node` просто заполняет поле `nid` из `memblock_region` заданным значением:

```C
static inline void memblock_set_region_node(struct memblock_region *r, int nid)
{
         r->nid = nid;
}
```

После этого у нас будет первый зарезервированный `memblock` для `EBDA` в секции `.meminit.data`. Функция `reserve_ebda_region` завершила работу над этим шагом, и мы можем вернуться в [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head64.c).

Мы закончили все приготовления! Последним шагом в функции `x86_64_start_reservations` является вызов функции `start_kernel`:

```C
start_kernel()
```

расположенной в [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c).

Заключение
--------------------------------------------------------------------------------

Это конец третей части инициализации ядра Linux. В следующей части мы увидим первые шаги инициализации в точке входа в ядро - `start_kernel`. Это будет первый шаг, прежде чем мы увидим запуск первого процесса `init`.

**От переводчика: пожалуйста, имейте в виду, что английский - не мой родной язык, и я очень извиняюсь за возможные неудобства. Если вы найдёте какие-либо ошибки или неточности в переводе, пожалуйста, пришлите pull request в [linux-insides-ru](https://github.com/proninyaroslav/linux-insides-ru).**

Ссылки
--------------------------------------------------------------------------------

* [BIOS data area](http://stanislavs.org/helppc/bios_data_area.html)
* [Что такое Extended BIOS Data Area](http://www.kryslix.com/nsfaq/Q.6.html)
* [Предыдущая часть](linux-initialization-2.md)
