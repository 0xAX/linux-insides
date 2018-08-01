Процесс загрузки ядра. Часть 6.
================================================================================

Введение
--------------------------------------------------------------------------------

Это шестая часть серии `Процесса загрузки ядра`. В [предыдущей части](Booting/linux-bootstrap-5.md) мы увидели конец процесса загрузки ядра. Но мы пропустили некоторые важные дополнительные детали.

Как вы помните, точкой входа ядра Linux является функция `start_kernel` из файла [main.c](https://github.com/torvalds/linux/blob/v4.16/init/main.c), которая начинает выполнение по адресу `LOAD_PHYSICAL_ADDR`. Этот адрес зависит от параметра конфигурации ядра `CONFIG_PHYSICAL_START`, который по умолчанию равен `0x1000000`:

```
config PHYSICAL_START
	hex "Physical address where the kernel is loaded" if (EXPERT || CRASH_DUMP)
	default "0x1000000"
	---help---
	  This gives the physical address where the kernel is loaded.
      ...
      ...
      ...
```

Это значение может быть изменено во время конфигурации ядра, но также может быть выбрано случайно. Для этого во время конфигурации ядра должна быть включена опция `CONFIG_RANDOMIZE_BASE`.

В этом случае будет рандомизирован физический адрес, по которому будет загружен и распакован образ ядра Linux. В этой части рассматривается случай, когда эта опция включена и адрес загрузки образа ядра будет рандомизирован из [соображений безопасности](https://en.wikipedia.org/wiki/Address_space_layout_randomization).

Инициализация таблиц страниц
--------------------------------------------------------------------------------

Перед тем как декомпрессор ядра начнёт поиск случайного адреса из диапазона, по которому ядро будет распаковано и загружено, таблицы страниц, отображённые "один в один" (identity mapped page tables), должны быть инициализированы. Если [загрузчик](https://en.wikipedia.org/wiki/Booting) использует [16-битный или 32-битный протокол загрузки](https://github.com/torvalds/linux/blob/v4.16/Documentation/x86/boot.txt), у нас уже есть таблицы страниц. Но в любом случае нам могут понадобиться новые страницы по требованию, если декомпрессор ядра выберет диапазон памяти за их пределами. Вот почему нам нужно создать новые таблицы таблиц, отображённые "один в один".

Да, создание таблиц является одним из первых шагов во время рандомизации адреса загрузки. Но прежде чем мы это рассмотрим, давайте попробуем вспомнить, откуда мы пришли к этому вопросу.

В [предыдущей части](linux-bootstrap-5.md), мы увидели переход в [long mode](https://en.wikipedia.org/wiki/Long_mode)  и переход к точке входа декомпрессора ядра - функции `extract_kernel`. Рандомизация начинается с вызова данной функции:

```C
void choose_random_location(unsigned long input,
                            unsigned long input_size,
                            unsigned long *output,
                            unsigned long output_size,
                            unsigned long *virt_addr)
{}
```

Как мы можем видеть, эта функция принимает следующие пять параметров:

  * `input`;
  * `input_size`;
  * `output`;
  * `output_isze`;
  * `virt_addr`.

Попытаемся понять что это за параметры. Первый параметр, `input`,  поступает из параметров функции `extract_kernel`, расположенной в файле [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/misc.c):

```C
asmlinkage __visible void *extract_kernel(void *rmode, memptr heap,
				                          unsigned char *input_data,
				                          unsigned long input_len,
				                          unsigned char *output,
				                          unsigned long output_len)
{
  ...
  ...
  ...
  choose_random_location((unsigned long)input_data, input_len,
                         (unsigned long *)&output,
				         max(output_len, kernel_total_size),
				         &virt_addr);
  ...
  ...
  ...
}
```

Этот параметр передаётся из кода ассемблера:

```C
leaq	input_data(%rip), %rdx
```

в файле [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S). `input_data` генерируется маленькой программой [mkpiggy](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/mkpiggy.c). Если вы компилировали ядро Linux своими руками, вы можете найти сгенерированный этой программой файл, расположенный в `linux/arch/x86/boot/compressed/piggy.S`. В моём случае этот файл выглядит так:

```assembly
.section ".rodata..compressed","a",@progbits
.globl z_input_len
z_input_len = 6988196
.globl z_output_len
z_output_len = 29207032
.globl input_data, input_data_end
input_data:
.incbin "arch/x86/boot/compressed/vmlinux.bin.gz"
input_data_end:
```

Как вы можете видеть, он содержит четыре глобальных символа. Первые два, `z_input_len` и `z_output_len`, являются размерами сжатого и несжатого `vmlinux.bin.gz`. Третий - это наш `input_data` и он указывает на образ ядра Linux в бинарном формате (все отладочные символы, комментарии и информация о релокации удаляются). И последний, `input_data_end`, указывает на конец сжатого образа ядра.

Таким образом, наш первый параметр функции `choose_random_location` является указателем на сжатый образ ядра, встроенный в объектный файл `piggy.o`.

Второй параметр функции `choose_random_location` - `z_input_len`, который мы уже видели.

Третий и четвёртый параметры функции `choose_random_location` - это адрес, по которому размещено распакованное ядро и размер образа распакованного ядра. Адрес, по которому будет размещён образ ядра, получен из [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S) и это адрес `startup_32`, выровненный по границе 2 мегабайт. Размер распакованного ядра также получен из `piggy.S`, как и `z_output_len`.

Последним параметром функции `choose_random_location` является виртуальный адрес физического адреса загрузки ядра. По умолчанию он совпадает с физическим адресом загрузки по умолчанию:

```C
unsigned long virt_addr = LOAD_PHYSICAL_ADDR;
```

который зависит от конфигурации ядра:

```C
#define LOAD_PHYSICAL_ADDR ((CONFIG_PHYSICAL_START \
				+ (CONFIG_PHYSICAL_ALIGN - 1)) \
				& ~(CONFIG_PHYSICAL_ALIGN - 1))
```

Теперь посмотрим на реализацию функции `choose_random_location`. Она начинается с проверки опции `nokaslr` из командной строки ядра:

```C
if (cmdline_find_option_bool("nokaslr")) {
	warn("KASLR disabled: 'nokaslr' on cmdline.");
	return;
}
```

и если параметр установлен, `choose_random_location` завершает свою работу и адрес загрузки ядра не будет рандомизрован. Связанные параметры командной строки можно найти в [документации ядра](https://github.com/torvalds/linux/blob/v4.16/Documentation/admin-guide/kernel-parameters.rst):

```
kaslr/nokaslr [X86]

Включение/выключение базового смещения ASLR ядра и модуля
(рандомизация размещения адресного пространства), если оно встроено в ядро.
Если выбран CONFIG_HIBERNATION, kASLR отключён по умолчанию.
Если kASLR включён, спящий режим будет выключен.
```

Предположим, что мы не передали `nokaslr` в командную строку ядра, а также включён параметр конфигурации ядра `CONFIG_RANDOMIZE_BASE`. В этом случае мы добавляем флаг `kASLR` к флагам загрузки ядра:

```C
boot_params->hdr.loadflags |= KASLR_FLAG;
```

и следующим шагом является вызов функции:

```C
initialize_identity_maps();
```

расположенной в файле [arch/x86/boot/compressed/kaslr_64.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/kaslr_64.c). Эта функция начинается с инициализации экземпляра структуры `x86_mapping_info`:

```C
mapping_info.alloc_pgt_page = alloc_pgt_page;
mapping_info.context = &pgt_data;
mapping_info.page_flag = __PAGE_KERNEL_LARGE_EXEC | sev_me_mask;
mapping_info.kernpg_flag = _KERNPG_TABLE;
```

Определение структуры `x86_mapping_info` расположено в файле [arch/x86/include/asm/init.h](https://github.com/torvalds/linux/blob/v4.16/arch/x86/include/asm/init.h):

```C
struct x86_mapping_info {
	void *(*alloc_pgt_page)(void *);
	void *context;
	unsigned long page_flag;
	unsigned long offset;
	bool direct_gbpages;
	unsigned long kernpg_flag;
};
```

Эта структура предоставляет информацию об отображениях памяти. Как вы помните из предыдущей части, мы уже настроили начальные страницы с 0 до `4G`. На данный момент нам может потребоваться доступ к памяти выше `4G` для загрузки ядра в случайном месте. Таким образом, функция `initialize_identity_maps` выполняет инициализацию области памяти для возможной новой таблицы страниц. Прежде всего, давайте взглянем на определение структуры `x86_mapping_info`.

`alloc_pgt_page` - это функция обратного вызова, которая будет вызываться для выделения пространства под запись в таблице страниц. Поле `context` является экземпляром структуры` alloc_pgt_data`, которая в нашем случае будет использоваться для отслеживания выделенных таблиц страниц. Поля `page_flag` и` kernpg_flag` являются флагами страниц. Первый представляет флаги для записей `PMD` или `PUD`. Второе поле `kernpg_flag` представляет флаги для страниц ядра, которые позже можно переопределить. Поле `direct_gbpages` представляет поддержку больших страниц, а последнее поле, `offset` представляет смещение между виртуальными адресами ядра и физическими адресами до уровня `PMD`.

`alloc_pgt_page` просто проверяет, есть ли место для новой страницы, и выделяет новую страницу:

```C
entry = pages->pgt_buf + pages->pgt_buf_offset;
pages->pgt_buf_offset += PAGE_SIZE;
```

в буфере из структуры:

```C
struct alloc_pgt_data {
	unsigned char *pgt_buf;
	unsigned long pgt_buf_size;
	unsigned long pgt_buf_offset;
};
```

и возвращает адрес новой страницы. Последняя цель функции `initialize_identity_maps` заключается в инициализации `pgdt_buf_size` и` pgt_buf_offset`. Поскольку мы только в фазе инициализации, функция `initialze_identity_maps` устанавливает` pgt_buf_offset` в ноль:

```C
pgt_data.pgt_buf_offset = 0;
```

и `pgt_data.pgt_buf_size` будет установлен в `77824` или `69632` в зависимости от того, какой протокол загрузки использует загрузчик (64-битный или 32-битный). Тоже самое и для `pgt_data.pgt_buf`. Если загрузчик загрузил ядро в `startup_32`, `pgdt_data.pgdt_buf` укажет на на конец таблицы страниц, которая уже была инициализирована в [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S):

```C
pgt_data.pgt_buf = _pgtable + BOOT_INIT_PGT_SIZE;
```

где `_pgtable` указывает на начало этой таблицы страниц [_pgtable](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/vmlinux.lds.S). В случае, если загрузчик использовал 64-битный протокол загрузки и загрузил ядро в `startup_64`, ранние таблицы страниц должны быть созданы самим загрузчиком и ` _pgtable` будет просто перезаписан:

```C
pgt_data.pgt_buf = _pgtable
```

После инициализации буфера для новых таблиц страниц мы можем вернуться к функции `select_random_location`.

Избежание зарезервированных диапазонов памяти
--------------------------------------------------------------------------------

После того как таблицы страниц, отображённые "один в один", инициализированы, мы можем начать выбор случайного местоположения, по которому мы поместим распакованный образ ядра. Но, как вы можете догадаться, мы не можем выбрать абсолютно любой адрес. Существует зарезервированные области памяти. Эти адреса занимают некоторые важные вещи, например, [initrd](https://en.wikipedia.org/wiki/Initial_ramdisk), командная строка ядра и т.д. Функция

```C
mem_avoid_init(input, input_size, *output);
```

поможет нам это сделать. Все небезопасные области памяти будут собраны в массив:

```C
struct mem_vector {
	unsigned long long start;
	unsigned long long size;
};

static struct mem_vector mem_avoid[MEM_AVOID_MAX];
```

Где `MEM_AVOID_MAX` находится в [перечислении](https://en.wikipedia.org/wiki/Enumerated_type#C) `mem_avoid_index`, который представляет собой различные типы зарезервированных областей памяти:

```C
enum mem_avoid_index {
	MEM_AVOID_ZO_RANGE = 0,
	MEM_AVOID_INITRD,
	MEM_AVOID_CMDLINE,
	MEM_AVOID_BOOTPARAMS,
	MEM_AVOID_MEMMAP_BEGIN,
	MEM_AVOID_MEMMAP_END = MEM_AVOID_MEMMAP_BEGIN + MAX_MEMMAP_REGIONS - 1,
	MEM_AVOID_MAX,
};
```

Оба расположены в файле [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/kaslr.c).

Давайте посмотрим на реализацию функции `mem_avoid_init`. Основная цель этой функции - хранить информацию о зарезервированных областях памяти, описанных в перечислении `mem_avoid_index` в массиве` mem_avoid`, и создавать новые страницы для таких областей в нашем новом буфере, отображённом "один в один". Многочисленные части для функции `mem_avoid_index` аналогичны, давайте посмотрим на одну из них:

```C
mem_avoid[MEM_AVOID_ZO_RANGE].start = input;
mem_avoid[MEM_AVOID_ZO_RANGE].size = (output + init_size) - input;
add_identity_map(mem_avoid[MEM_AVOID_ZO_RANGE].start,
		 mem_avoid[MEM_AVOID_ZO_RANGE].size);
```

В начале функция `mem_avoid_init` пытается избежать области памяти, которая используется для текущей декомпрессии ядра. Мы заполняем запись из массива `mem_avoid` с указанием начала и размера такой области и вызываем функцию ` add_identity_map`, которая должна создать страницы, отображённые "один в один", для этого региона. Функция `add_identity_map` определена в файле [arch/x86/boot/compressed/kaslr_64.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/kaslr_64.c):

```C
void add_identity_map(unsigned long start, unsigned long size)
{
	unsigned long end = start + size;

	start = round_down(start, PMD_SIZE);
	end = round_up(end, PMD_SIZE);
	if (start >= end)
		return;

	kernel_ident_mapping_init(&mapping_info, (pgd_t *)top_level_pgt,
				  start, end);
}
```

Как мы можем видеть, она выравнивает область памяти по границе 2 мегабайт и проверяет заданные начальные и конечные адреса.

В конце она вызывает функцию `kernel_ident_mapping_init` из файла [arch/x86/mm/ident_map.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/mm/ident_map.c) и передаёт экземпляр `mapping_info`, который мы инициализировали ранее, адрес таблицы страниц верхнего уровня и адреса области памяти, для которой необходимо создать новое отображение "один в один".

Функция `kernel_ident_mapping_init` устанавливает флаги по умолчанию для новых страниц, если они не были заданы:

```C
if (!info->kernpg_flag)
	info->kernpg_flag = _KERNPG_TABLE;
```

и начинает создание 2 мегабайтных (из-за бита `PSE` в `mapping_info.page_flag`) страничных записей (`PGD -> P4D -> PUD -> PMD` в случае [пятиуровневых таблиц страниц](https://lwn.net/Articles/717293/) или `PGD -> PUD -> PMD` в случае [четырёхуровневых таблиц страниц](https://lwn.net/Articles/117749/)), относящихся к указанным адресам.

```C
for (; addr < end; addr = next) {
	p4d_t *p4d;

	next = (addr & PGDIR_MASK) + PGDIR_SIZE;
	if (next > end)
		next = end;

    p4d = (p4d_t *)info->alloc_pgt_page(info->context);
	result = ident_p4d_init(info, p4d, addr, next);

    return result;
}
```

Прежде всего, мы находим следующую запись `глобального каталога страниц` для данного адреса, и если она больше, чем `end` данной области памяти, мы устанавливаем её в `end`. После этого мы выделяем новую страницу с нашим обратным вызовом `x86_mapping_info`, который мы уже рассмотрели выше, и вызываем функцию` ident_p4d_init`. Функция `ident_p4d_init` будет делать то же самое, но для низкоуровневых каталогов страниц (` p4d` -> `pud` ->` pmd`).

На этом всё.

Новые страницы, связанные с зарезервированными адресами, находятся в наших таблицах страниц. Это не конец функции `mem_avoid_init`, но другие части схожи. Они просто создают страницы для [initrd](https://en.wikipedia.org/wiki/Initial_ramdisk), командной строки ядра и т.д.

Теперь мы можем вернуться к функции `choose_random_location`.

Рандомизация физического адреса
--------------------------------------------------------------------------------

После сохранения зарезервированных областей памяти в массиве `mem_avoid` и создания для них страниц, отображённых "один в один", мы выбираем минимальный доступный адрес для произвольного выбора области памяти:

```C
min_addr = min(*output, 512UL << 20);
```

Он должен быть меньше чем `512` мегабайт. Значение `512` мегабайт было выбрано для того, чтобы избежать неизвестных вещей в нижней части памяти.

Следующим шагом будет выбор случайных физических и виртуальных адресов для загрузки ядра. Сначала физические адреса:

```C
random_addr = find_random_phys_addr(min_addr, output_size);
```

Функция `find_random_phys_addr` определена в [том же](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/kaslr.c) файле:

```
static unsigned long find_random_phys_addr(unsigned long minimum,
                                           unsigned long image_size)
{
	minimum = ALIGN(minimum, CONFIG_PHYSICAL_ALIGN);

	if (process_efi_entries(minimum, image_size))
		return slots_fetch_random();

	process_e820_entries(minimum, image_size);
	return slots_fetch_random();
}
```

Основная задача `process_efi_entries` - найти все подходящие диапазоны памяти в доступной для загрузки ядра памяти. Если ядро скомпилировано и запущено на системе без поддержки [EFI](https://en.wikipedia.org/wiki/Unified_Extensible_Firmware_Interface), поиск областей памяти продолжиться в регионах [e820](https://en.wikipedia.org/wiki/E820). Все найденные области памяти будут сохранены в массиве:

```C
struct slot_area {
	unsigned long addr;
	int num;
};

#define MAX_SLOT_AREA 100

static struct slot_area slot_areas[MAX_SLOT_AREA];
```

Для декомпрессии ядро выберет случайный индекс из этого массива. Этот выбор будет выполнен функцией `slots_fetch_random`. Основная задача функции `slots_fetch_random` заключается в выборе случайного диапазона памяти из массива `slot_areas` с помощью функции `kaslr_get_random_long`:

```C
slot = kaslr_get_random_long("Physical") % slot_max;
```

Функция `kaslr_get_random_long` определена в файле [arch/x86/lib/kaslr.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/lib/kaslr.c) и просто возвращает случайное число. Обратите внимание, что случайное число будет получено разными способами, зависящими от конфигурации ядра (выбор случайного числа, основываясь на [счётчике времени](https://en.wikipedia.org/wiki/Time_Stamp_Counter), [rdrand](https://en.wikipedia.org/wiki/RdRand) и т.д.).

Рандомизация виртуального адреса
--------------------------------------------------------------------------------

После того как декомпрессором ядра была выбрана случайная область памяти, для неё будут созданы новые страницы, отображённые "один в один":

```C
random_addr = find_random_phys_addr(min_addr, output_size);

if (*output != random_addr) {
		add_identity_map(random_addr, output_size);
		*output = random_addr;
}
```

После этого `output` будет хранить базовый адрес области памяти, где будет распаковано ядро. Но на данный момент, как вы помните, мы рандомизировали только физический адрес. В случае архитектуры [x86_64](https://en.wikipedia.org/wiki/X86-64) виртуальный адрес также должен быть рандомизирован:

```C
if (IS_ENABLED(CONFIG_X86_64))
	random_addr = find_random_virt_addr(LOAD_PHYSICAL_ADDR, output_size);

*virt_addr = random_addr;
```

В архитектуре, отличной от `x86_64`, случайный виртуальный адрес будет совпадать со случайным физическим. Функция `find_random_virt_addr` вычисляет количество диапазонов виртуальной памяти, которые могут содержать образ ядра, и вызывает `kaslr_get_random_long`, которую мы уже видели ранее, когда пытались найти случайный `физический` адрес.

Теперь мы имеет как физические базовые случайные адреса (`*output`), так и виртуальные (`*virt_addr`) случайные адреса для декомпрессии ядра.

На этом всё.

Заключение
--------------------------------------------------------------------------------

Это конец шестой и последней части процесса загрузки ядра Linux. Мы больше не увидим статей о загрузке ядра (возможны обновления этой и предыдущих статей), но будет много статей о других внутренних компонентах ядра.

Следующая глава посвящена инициализации ядра, и мы увидим первые шаги в коде инициализации ядра Linux.

**От переводчика: пожалуйста, имейте в виду, что английский - не мой родной язык, и я очень извиняюсь за возможные неудобства. Если вы найдёте какие-либо ошибки или неточности в переводе, пожалуйста, пришлите pull request в [linux-insides-ru](https://github.com/proninyaroslav/linux-insides-ru).**

Ссылки
--------------------------------------------------------------------------------

* [Рандомизация размещения адресного пространства](https://en.wikipedia.org/wiki/Address_space_layout_randomization)
* [Протокол загрузки ядра Linux](https://github.com/torvalds/linux/blob/v4.16/Documentation/x86/boot.txt)
* [Long mode](https://en.wikipedia.org/wiki/Long_mode)
* [initrd](https://en.wikipedia.org/wiki/Initial_ramdisk)
* [Перечисляемый тип](https://en.wikipedia.org/wiki/Enumerated_type#C)
* [Четырёхуровневые таблицы страниц](https://lwn.net/Articles/117749/)
* [Пятиуровневые таблицы страниц](https://lwn.net/Articles/717293/)
* [EFI](https://en.wikipedia.org/wiki/Unified_Extensible_Firmware_Interface)
* [e820](https://en.wikipedia.org/wiki/E820)
* [Счётчик времени](https://en.wikipedia.org/wiki/Time_Stamp_Counter)
* [rdrand](https://en.wikipedia.org/wiki/RdRand)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [Предыдущая часть](linux-bootstrap-5.md)
