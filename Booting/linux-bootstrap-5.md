Процесс загрузки ядра. Часть 5.
================================================================================

Декомпрессия ядра
--------------------------------------------------------------------------------

Это пятая часть серии `Процесса загрузки ядра`. Мы видели переход в 64-битный режим в предыдущей [части](linux-bootstrap-4.md) и в этой части мы продолжим с этого момента. Прежде чем мы перейдём к коду ядра, мы увидим последние шаги: подготовку к декомпрессии ядра, перемещение и, непосредственно, декомпрессию ядра. Итак... давайте снова погрузимся в код ядра.

Подготовка к декомпрессии ядра
--------------------------------------------------------------------------------

Мы остановились прямо перед переходом к 64-битной точке входа - `startup_64`, расположенной в [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S). В предыдущей части мы уже видели переход к `startup_64` в `startup_32`:

```assembly
	pushl	$__KERNEL_CS
	leal	startup_64(%ebp), %eax
	...
	...
	...
	pushl	%eax
	...
	...
	...
	lret
```

в предыдущей части, `startup_64` начал свою работу. Так как мы загрузили новую глобальную таблицу дескрипторов, и был переход CPU в другой режим (в нашем случае в 64-битный режим), мы можем видеть настройку сегментов данных в начале `startup_64`:

```assembly
	.code64
	.org 0x200
ENTRY(startup_64)
	xorl	%eax, %eax
	movl	%eax, %ds
	movl	%eax, %es
	movl	%eax, %ss
	movl	%eax, %fs
	movl	%eax, %gs
```

Все сегментные регистры, кроме `cs`, теперь указывают на `ds`, равный `0x18` (если вы не понимаете, почему `0x18`, прочтите предыдущую часть).

Следующий шаг - вычисление разницы между адресом, по которому скомпилировано ядро, и адресом, по которому оно было загружено:

```assembly
#ifdef CONFIG_RELOCATABLE
	leaq	startup_32(%rip), %rbp
	movl	BP_kernel_alignment(%rsi), %eax
	decl	%eax
	addq	%rax, %rbp
	notq	%rax
	andq	%rax, %rbp
	cmpq	$LOAD_PHYSICAL_ADDR, %rbp
	jge	1f
#endif
	movq	$LOAD_PHYSICAL_ADDR, %rbp
1:
	leaq	z_extract_offset(%rbp), %rbx
```

`rbp` содержит начальный адрес распакованного ядра и после выполнения этого кода регистр `rbx` будет содержать адрес релокации ядра для декомпрессии. Такой код мы уже видели в `startup_32` (вы можете прочитать об этом в предыдущей части - [Расчёт адреса релокации](https://github.com/proninyaroslav/linux-insides-ru/blob/master/Booting/linux-bootstrap-4.md#Расчёт-адреса-релокации)), но нам снова нужно вычислить его, поскольку загрузчик может использовать 64-битный протокол загрузки и в этом случае `startup_32` просто не будет выполнен.

На следующем шаге мы видим установку указателя стека и сброс регистра флагов:

```assembly
	leaq	boot_stack_end(%rbx), %rsp

	pushq	$0
	popfq
```

Как вы можете видеть выше, регистр `rbx` содержит начальный адрес кода декомпрессора ядра, и мы помещаем этот адрес со смещением `boot_stack_end` в регистр `rsp`, который представляет указатель на вершину стека. После этого шага стек будет корректным. Вы можете найти определение `boot_stack_end` в конце [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

```assembly
	.bss
	.balign 4
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
boot_stack:
	.fill BOOT_STACK_SIZE, 1, 0
boot_stack_end:
```

Он расположен в конце секции `.bss`, прямо перед таблицей `.pgtable`. Если вы посмотрите сценарий компоновщика [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/vmlinux.lds.S), вы найдёте определения `.bss` и `.pgtable`.

После того как стек был настроен, мы можем скопировать сжатое ядро по адресу, который мы получили выше после вычисления адреса релокации распакованного ядра. Прежде чем перейти к деталям, давайте посмотрим на этот ассемблерный код:

```assembly
	pushq	%rsi
	leaq	(_bss-8)(%rip), %rsi
	leaq	(_bss-8)(%rbx), %rdi
	movq	$_bss, %rcx
	shrq	$3, %rcx
	std
	rep	movsq
	cld
	popq	%rsi
```

Прежде всего, мы помещаем `rsi` в стек. Нам нужно сохранить значение `rsi`, потому что теперь этот регистр хранит указатель на `boot_params`, которая является структурой режима реальных адресов, содержащая связанные с загрузкой данные (вы должны помнить эту структуру, мы заполняли её в начале кода настройки ядра). В конце этого кода мы снова восстановим указатель на `boot_params` в `rsi`. 

Следующие две инструкции `leaq` вычисляют  эффективные адреса `rip` и `rbx` со смещением `_bss - 8` и помещают их в `rsi` и `rdi`. Зачем мы вычисляем эти адреса? На самом деле сжатый образ ядра находится между этим кодом копирования (от `startup_32` до текущего кода) и кодом декомпрессии. Вы можете проверить это, посмотрев сценарий компоновщика - [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/vmlinux.lds.S):

```
	. = 0;
	.head.text : {
		_head = . ;
		HEAD_TEXT
		_ehead = . ;
	}
	.rodata..compressed : {
		*(.rodata..compressed)
	}
	.text :	{
		_text = .; 	/* Text */
		*(.text)
		*(.text.*)
		_etext = . ;
	}
```

Обратите внимание, что секция `.head.text` содержит `startup_32`. Вы можете помнить это из предыдущей части:

```assembly
	__HEAD
	.code32
ENTRY(startup_32)
...
...
...
```

Секция `.text` содержит код декомпрессии:

```assembly
	.text
relocated:
...
...
...
/*
 * Делает декомпрессию и переходит на новое ядро.
 */
...
```

`.rodata..compressed` содержит сжатый образ ядра. Таким образом, `rsi` будет содержать абсолютный адрес `_bss - 8`, а `rdi` будет содержать относительный адрес релокации `_bss - 8`. Когда мы сохраняем эти адреса в регистрах, мы помещаем адрес `_bss` в регистр `rcx`. Как вы можете видеть в скрипте компоновщика `vmlinux.lds.S`, он находится в конце всех секций с кодом настройки/ядра. Теперь мы можем начать копирование данных из `rsi` в `rdi` по `8` байт с помощью инструкции `movsq`. 

Обратите внимание на инструкцию `std` перед копированием данных: она устанавливает флаг `DF`, означающий, что `rsi` и `rdi` будут уменьшаться. Другими словами, мы будем копировать байты задом наперёд. В конце мы очищаем флаг `DF` с помощью инструкции `cld` и восстанавливаем структуру `boot_params` в `rsi`.

После релокации мы имеем адрес секции `.text` и совершаем переход по нему:

```assembly
	leaq	relocated(%rbx), %rax
	jmp	*%rax
```

Последняя подготовка перед декомпрессией ядра
--------------------------------------------------------------------------------

В предыдущем абзаце мы видели, что секция `.text` начинается с метки `relocated`. Первое, что она делает - очищает секцию `bss`:

```assembly
	xorl	%eax, %eax
	leaq    _bss(%rip), %rdi
	leaq    _ebss(%rip), %rcx
	subq	%rdi, %rcx
	shrq	$3, %rcx
	rep	stosq
```

Нам нужно инициализировать секцию `.bss`, потому что скоро мы перейдём к коду на [C](https://en.wikipedia.org/wiki/C_%28programming_language%29). Здесь мы просто очищаем `eax`, помещаем адрес `_bss` в `rdi` и `_ebss` в `rcx`, и заполняем его нулями с помощью инструкции `rep stosq`.

В конце мы видим вызов функции `decompress_kernel`:

```assembly
	pushq	%rsi
	movq	$z_run_size, %r9
	pushq	%r9
	movq	%rsi, %rdi
	leaq	boot_heap(%rip), %rsi
	leaq	input_data(%rip), %rdx
	movl	$z_input_len, %ecx
	movq	%rbp, %r8
	movq	$z_output_len, %r9
	call	decompress_kernel
	popq	%r9
	popq	%rsi
```

Мы снова устанавливаем `rdi` в указатель на структуру `boot_params` и вызываем `decompress_kernel` из [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c) с семью аргументами:

* `rmode` - указатель на структуру [boot_params](https://github.com/torvalds/linux/blob/master//arch/x86/include/uapi/asm/bootparam.h#L114), которая заполнена загрузчиком или во время ранней инициализации ядра;
* `heap` - указатель на `boot_heap`, представляющий собой начальный адрес ранней загрузочной кучи;
* `input_data` - указатель на начало сжатого ядра или, другими словами, указатель на `arch/x86/boot/compressed/vmlinux.bin.bz2`;
* `input_len` - размер сжатого ядра;
* `output` - начальный адрес будущего распакованного ядра;
* `output_len` - размер распакованного ядра;
* `run_size` - объём пространства, необходимый для запуска ядра, включая секции `.bss` и `.brk`.

Все аргументы буду передаваться через регистры согласно [двоичному интерфейсу приложений System V (ABI)](http://www.x86-64.org/documentation/abi.pdf). Мы закончили подготовку и переходим к декомпрессии ядра.

Декомпрессия ядра
--------------------------------------------------------------------------------

Как мы видели в предыдущем абзаце, функция `decompress_kernel` определена [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c) и содержит семь аргументов. Эта функция начинается с инициализации видео/консоли, которую мы уже видели в предыдущих частях. Нам нужно сделать это ещё раз, потому что мы не знаем, находились ли мы в [режиме реальных адресов](https://en.wikipedia.org/wiki/Real_mode), использовался ли загрузчик, или загрузчик использовал 32 или 64-битный протокол загрузки.

После первых шагов инициализации мы сохраняем указатели на начало и конец свободной памяти:

```C
free_mem_ptr     = heap;
free_mem_end_ptr = heap + BOOT_HEAP_SIZE;
```

где `heap` является вторым параметром функции `decompress_kernel`, который мы получили в [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

```assembly
leaq	boot_heap(%rip), %rsi
```

Как вы видели выше, `boot_heap` определён как:

```assembly
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
```

где `BOOT_HEAP_SIZE` - это макрос, который раскрывается в `0x8000` (`0x400000` в случае `bzip2` ядра) и представляет собой размер кучи.

После инициализации указателей кучи, следующий шаг - вызов функции `choose_random_location` из [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c#L425). Как можно догадаться из названия функции, она выбирает ячейку памяти, в которой будет разархивирован образ ядра. Может показаться странным, что нам нужно найти или даже `выбрать` место для декомпрессии сжатого образа ядра, но ядро Linux поддерживает технологию [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization), которая позволяет загрузить распакованное ядро по случайному адресу из соображений безопасности. Давайте откроем файл [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c#L425) и посмотри на `choose_random_location`.

Во-первых, если опция `CONFIG_HIBERNATION` установлена, `choose_random_location` пытается найти опцию `kaslr`, в противном случае опцию `nokaslr`:

```C
#ifdef CONFIG_HIBERNATION
	if (!cmdline_find_option_bool("kaslr")) {
		debug_putstr("KASLR disabled by default...\n");
		goto out;
	}
#else
	if (cmdline_find_option_bool("nokaslr")) {
		debug_putstr("KASLR disabled by cmdline...\n");
		goto out;
	}
#endif
```

Если опция конфигурации ядра `CONFIG_HIBERNATION` включена во время конфигурации ядра и в командной строке отсутствует опция `kaslr`, выводится надпись `KASLR disabled by default...` и совершается переход на метку `out`:

```C
out:
	return (unsigned char *)choice;
```

где мы просто возвращаем параметр `output`, который мы передали в `choose_random_location`, без изменений. Если опция `CONFIG_HIBERNATION` выключена и опция `nokaslr` присутствует, мы снова переходим на метку `out`.

На время предположим, что ядро сконфигурировано с включённой рандомизацией и попытаемся понять, что такое `kASLR`. Мы можем найти информацию об этом в [документации](https://github.com/torvalds/linux/blob/master/Documentation/kernel-parameters.txt):

```
kaslr/nokaslr [X86]

Включение/выключение базового смещения ASLR ядра и модуля
(рандомизация размещения адресного пространства), если оно встроено в ядро. 
Если выбран CONFIG_HIBERNATION, kASLR отключён по умолчанию. 
Если kASLR включён, спящий режим будет выключен.
```

Это означает, что мы можем передать опцию `kaslr` в командную строку ядра и получить случайный адрес для распаковки ядра (вы можете прочитать больше о ASLR [здесь](https://en.wikipedia.org/wiki/Address_space_layout_randomization)). Итак, наша текущая цель - найти случайный адрес, где мы сможем `безопасно` распаковать ядро Linux. Повторюсь: `безопасно`. Что это означает в данном контексте? Вы можете помнить, что помимо кода декомпрессора и непосредственно образа ядра в памяти есть несколько небезопасных мест. Например, образ [initrd](https://en.wikipedia.org/wiki/Initrd) также находится в памяти, и мы не должны перекрывать его распакованным ядро.

Следующая функция поможет нам найти безопасное место, где мы можем распаковать ядро. Это функция `mem_avoid_init`. Она определена в том же [файле](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/kaslr.c) исходного кода и принимает 4 аргумента, которые мы видели в функции `decompress_kernel`:

* `input_data` - указатель на начало сжатого ядра, или, другими словами, указатель на `arch/x86/boot/compressed/vmlinux.bin.bz2`;
* `input_len` - размер сжатого ядра;
* `output` - начальный адрес будущего распакованного ядра;
* `output_len` - размер распакованного ядра.

Основной точкой этой функции является заполнение массива структур `mem_vector`:

```C
#define MEM_AVOID_MAX 5

static struct mem_vector mem_avoid[MEM_AVOID_MAX];
```

где структура `mem_vector` содержит информацию о небезопасных областях памяти:

```C
struct mem_vector {
	unsigned long start;
	unsigned long size;
};
```

Реализация `mem_avoid_init` довольна проста. Давайте взглянем на часть этой функции:

```C
	...
	...
	...
	initrd_start  = (u64)real_mode->ext_ramdisk_image << 32;
	initrd_start |= real_mode->hdr.ramdisk_image;
	initrd_size  = (u64)real_mode->ext_ramdisk_size << 32;
	initrd_size |= real_mode->hdr.ramdisk_size;
	mem_avoid[1].start = initrd_start;
	mem_avoid[1].size = initrd_size;
	...
	...
	...
```

Здесь мы видим расчёт начального адреса и размера [initrd](http://en.wikipedia.org/wiki/Initrd). `ext_ramdisk_image` - старшие `32 бита` поля `ramdisk_image` из заголовка настройки и `ext_ramdisk_size` - старшие 32 бита поля `ramdisk_size` из [протокола загрузки](https://github.com/torvalds/linux/blob/master/Documentation/x86/boot.txt):

```
Offset	Proto	Name		Meaning
/Size
...
...
...
0218/4	2.00+	ramdisk_image	адрес загрузки initrd (установлен загрузчиком)
021C/4	2.00+	ramdisk_size	размер initrd (установлен загрузчиком)
...
```

`ext_ramdisk_image` и `ext_ramdisk_size` могут быть найдены в [Documentation/x86/zero-page.txt](https://github.com/torvalds/linux/blob/master/Documentation/x86/zero-page.txt):

```
Offset	Proto	Name		Meaning
/Size
...
...
...
0C0/004	ALL	ext_ramdisk_image старшие 32 бита ramdisk_image
0C4/004	ALL	ext_ramdisk_size  старшие 32 бита ramdisk_size
...
```

Итак, мы берём `ext_ramdisk_image` и `ext_ramdisk_size`, сдвигаем их влево на `32` (теперь они будут содержать младшие 32 бита в старших битах) и получаем начальный адрес и размер `initrd`. Далее мы сохраняем их в массиве `mem_avoid`.

Следующим шагом после того как мы собрали все небезопасные области памяти в массиве `mem_avoid`, будет поиск случайного адреса, который не пересекается с небезопасными областями, используя функцию `find_random_addr`. Прежде всего, мы можем видеть выравнивание выходного адреса в функции `find_random_addr`:

```C
minimum = ALIGN(minimum, CONFIG_PHYSICAL_ALIGN);
```

Вы можете помнить опцию конфигурации `CONFIG_PHYSICAL_ALIGN` из предыдущей части. Эта опция предоставляет значение, по которому ядро должно быть выровнено, и по умолчанию оно составляет `0x200000`. После получения выровненного выходного адреса, мы просматриваем области памяти, которые мы получили с помощью BIOS-сервиса [e820](https://en.wikipedia.org/wiki/E820) и собираем подходящие для распакованного образа ядра:

```C
for (i = 0; i < real_mode->e820_entries; i++) {
	process_e820_entry(&real_mode->e820_map[i], minimum, size);
}
```

Напомним, что мы собрали `e820_entries` во [второй части](https://github.com/proninyaroslav/linux-insides-ru/blob/master/Booting/linux-bootstrap-2.md#Обнаружение-памяти). Функция `process_e820_entry` совершает некоторые проверки: что область памяти `e820` не является `non-RAM`, что начальный адрес области памяти не больше максимального допустимого смещения `aslr` offset, и что область памяти находится выше минимальной локации загрузки:

```C
struct mem_vector region, img;

if (entry->type != E820_RAM)
	return;

if (entry->addr >= CONFIG_RANDOMIZE_BASE_MAX_OFFSET)
	return;

if (entry->addr + entry->size < minimum)
	return;
```

После этого мы сохраняем начальный адрес и размер области памяти `e820` в структуре `mem_vector` (мы видели определение этой структуры выше):

```C
region.start = entry->addr;
region.size = entry->size;
```

Во время сохранения значений мы также выравниваем `region.start`, как это делали в функции `find_random_addr` и проверяем, что мы не получили адрес, который находится за пределами области оригинальной памяти:

```C
region.start = ALIGN(region.start, CONFIG_PHYSICAL_ALIGN);

if (region.start > entry->addr + entry->size)
	return;
```

На следующем этапе мы уменьшаем размер области памяти, чтобы не включить отклонённые области в начале, и гарантируем, что последний адрес в области памяти меньше, чем `CONFIG_RANDOMIZE_BASE_MAX_OFFSET`, поэтому конец образа ядра будет меньше чем максимальное смещение `aslr`:

```C
region.size -= region.start - entry->addr;

if (region.start + region.size > CONFIG_RANDOMIZE_BASE_MAX_OFFSET)
		region.size = CONFIG_RANDOMIZE_BASE_MAX_OFFSET - region.start;
```

И наконец, мы просматриваем все небезопасные области памяти и проверяем, что область не перекрывает небезопасные области, такие как командная строка ядра, initrd и т.д:

```C
for (img.start = region.start, img.size = image_size ;
	     mem_contains(&region, &img) ;
	     img.start += CONFIG_PHYSICAL_ALIGN) {
		if (mem_avoid_overlap(&img))
			continue;
		slots_append(img.start);
	}
```

Если область памяти не перекрывает небезопасные области, мы вызываем функцию `slots_append` с начальным адресом области. Функция `slots_append` просто собирает начальные адреса областей памяти в массив `slots`:

```C
slots[slot_max++] = addr;
```

который определён как:

```C
static unsigned long slots[CONFIG_RANDOMIZE_BASE_MAX_OFFSET /
			   CONFIG_PHYSICAL_ALIGN];
static unsigned long slot_max;
```

После завершения `process_e820_entry` у нас будет массив адресов, безопасных для распакованного ядра. Затем мы вызываем функцию `slots_fetch_random` для того, чтобы получить случайный адрес из этого массива:

```C
if (slot_max == 0)
	return 0;

return slots[get_random_long() % slot_max];
```

где функция `get_random_long` проверяет различные флаги CPU, такие как `X86_FEATURE_RDRAND` или `X86_FEATURE_TSC`, и выбирает метод для получения случайного числа (это может быть инструкция RDRAND, счётчик временных меток, программируемый интервальный таймер и т.д.). После извлечения случайного адреса, `choose_random_location` завершает свою работу.

Теперь вернёмся к [misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c#L404). После получения адреса для образа ядра мы должны были совершить некоторые проверки и убедиться в том, что полученный случайный адрес правильно выровнен и является корректным.

После этого мы увидим знакомое сообщение:

```
Decompressing Linux... 
```

и вызываем функцию `__decompress`, которая будет распаковывать ядро. Функция `__decompress` зависит от того, какой алгоритм декомпрессии был выбран во время компиляции:

```C
#ifdef CONFIG_KERNEL_GZIP
#include "../../../../lib/decompress_inflate.c"
#endif

#ifdef CONFIG_KERNEL_BZIP2
#include "../../../../lib/decompress_bunzip2.c"
#endif

#ifdef CONFIG_KERNEL_LZMA
#include "../../../../lib/decompress_unlzma.c"
#endif

#ifdef CONFIG_KERNEL_XZ
#include "../../../../lib/decompress_unxz.c"
#endif

#ifdef CONFIG_KERNEL_LZO
#include "../../../../lib/decompress_unlzo.c"
#endif

#ifdef CONFIG_KERNEL_LZ4
#include "../../../../lib/decompress_unlz4.c"
#endif
```

После того как ядро распаковано, остаются две последние функции - `parse_elf` и `handle_relocations`. Основное назначение этих функций - переместить распакованный образ ядра в правильное место памяти. Дело в том, что декомпрессор распаковывает [на месте](https://en.wikipedia.org/wiki/In-place_algorithm), и нам всё равно нужно переместить ядро на правильный адрес. Как мы уже знаем, образ ядра является исполняемым файлом [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format), поэтому главной целью функции `parse_elf` является перемещение загружаемых сегментов на правильный адрес. Мы можем видеть загружаемые сегменты в выводе программы `readelf`:

```
readelf -l vmlinux

Elf file type is EXEC (Executable file)
Entry point 0x1000000
There are 5 program headers, starting at offset 64

Program Headers:
  Type           Offset             VirtAddr           PhysAddr
                 FileSiz            MemSiz              Flags  Align
  LOAD           0x0000000000200000 0xffffffff81000000 0x0000000001000000
                 0x0000000000893000 0x0000000000893000  R E    200000
  LOAD           0x0000000000a93000 0xffffffff81893000 0x0000000001893000
                 0x000000000016d000 0x000000000016d000  RW     200000
  LOAD           0x0000000000c00000 0x0000000000000000 0x0000000001a00000
                 0x00000000000152d8 0x00000000000152d8  RW     200000
  LOAD           0x0000000000c16000 0xffffffff81a16000 0x0000000001a16000
                 0x0000000000138000 0x000000000029b000  RWE    200000
```

Цель функции `parse_elf` - загрузить эти сегменты по адресу `output`, который мы получили с помощью функции `choose_random_location`. Эта функция начинается с проверки сигнатуры [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format):

```C
Elf64_Ehdr ehdr;
Elf64_Phdr *phdrs, *phdr;

memcpy(&ehdr, output, sizeof(ehdr));

if (ehdr.e_ident[EI_MAG0] != ELFMAG0 ||
   ehdr.e_ident[EI_MAG1] != ELFMAG1 ||
   ehdr.e_ident[EI_MAG2] != ELFMAG2 ||
   ehdr.e_ident[EI_MAG3] != ELFMAG3) {
   error("Kernel is not a valid ELF file");
   return;
}
```

и если файл некорректный, функция выводит сообщение об ошибке и останавливается. Если же `ELF` файл корректный, мы просматриваем все заголовки из указанного `ELF` файла и копируем все загружаемые сегменты с правильным адресом в выходной буфер:

```C
	for (i = 0; i < ehdr.e_phnum; i++) {
		phdr = &phdrs[i];

		switch (phdr->p_type) {
		case PT_LOAD:
#ifdef CONFIG_RELOCATABLE
			dest = output;
			dest += (phdr->p_paddr - LOAD_PHYSICAL_ADDR);
#else
			dest = (void *)(phdr->p_paddr);
#endif
			memcpy(dest,
			       output + phdr->p_offset,
			       phdr->p_filesz);
			break;
		default: /* Игнорируем остальные PT_* */ break;
		}
	}
```

С этого момента все загружаемые сегменты находятся в правильном месте. Последняя функция - `handle_relocations` - корректирует адреса в образе ядра и вызывается только в том случае, если `kASLR` был включён во время конфигурации ядра.

После перемещения ядра мы возвращаемся из `decompress_kernel` обратно в [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S). Адрес ядра находится в регистре `rax` и мы совершаем переход по нему:

```assembly
jmp	*%rax
```

На этом всё. Теперь мы в ядре!

Заключение
--------------------------------------------------------------------------------

Это конец пятой и последней части процесса загрузки ядра Linux. Мы больше не увидим статей о загрузке ядра (возможны обновления этой и предыдущих статей), но будет много статей о других внутренних компонентах ядра. 

Следующая глава посвящена инициализации ядра, и мы увидим первые шаги в коде инициализации ядра Linux.

**От переводчика: пожалуйста, имейте в виду, что английский - не мой родной язык, и я очень извиняюсь за возможные неудобства. Если вы найдёте какие-либо ошибки или неточности в переводе, пожалуйста, пришлите pull request в [linux-insides-ru](https://github.com/proninyaroslav/linux-insides-ru).**

Ссылки
--------------------------------------------------------------------------------

* [Рандомизация размещения адресного пространства](https://en.wikipedia.org/wiki/Address_space_layout_randomization)
* [initrd](http://en.wikipedia.org/wiki/Initrd)
* [long mode](http://en.wikipedia.org/wiki/Long_mode)
* [bzip2](http://www.bzip.org/)
* [Инструкция RDdRand](http://en.wikipedia.org/wiki/RdRand)
* [Счётчик временных меток](http://en.wikipedia.org/wiki/Time_Stamp_Counter)
* [Программируемый интервальный таймер](http://en.wikipedia.org/wiki/Intel_8253)
* [Предыдущий пост](linux-bootstrap-4.md)
