Процесс загрузки ядра. Часть 5.
================================================================================

Декомпрессия ядра
--------------------------------------------------------------------------------

Это пятая часть серии `Процесса загрузки ядра`. Мы видели переход в 64-битный режим в предыдущей [части](linux-bootstrap-4.md) и в этой части мы продолжим с этого момента. Прежде чем мы перейдём к коду ядра, мы увидим последние шаги: подготовку к декомпрессии ядра, перемещение и, непосредственно, декомпрессию ядра. Итак... давайте снова погрузимся в код ядра.

Подготовка к декомпрессии ядра
--------------------------------------------------------------------------------

Мы остановились прямо перед переходом к `64-битной` точке входа - `startup_64`, расположенной в [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S). В предыдущей части мы уже видели переход к `startup_64` в `startup_32`:

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

Так как мы загрузили новую `глобальную таблицу дескрипторов`, и был переход CPU в другой режим (в нашем случае в `64-битный` режим), мы можем видеть настройку сегментов данных в начале `startup_64`:

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

Все сегментные регистры, кроме регистра `cs`, теперь сброшены после того как мы перешли в `long mode`.

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

На следующем шаге мы видим установку указателя стека, сброс регистра флагов и установку `GDT` заново из-за того, что в случае `64-битного` протокола `32-битный` сегмент кода может быть проигнорирован загрузчиком:

```assembly
    leaq	boot_stack_end(%rbx), %rsp

	leaq	gdt(%rip), %rax
	movq	%rax, gdt64+2(%rip)
	lgdt	gdt64(%rip)

	pushq	$0
	popfq
```

Если вы посмотрите на исходный код ядра Linux после команды `lgdt gdt64(%rip)`, вы увидите, что есть некоторый дополнительный код. Этот код необходим для включения [пятиуровневой страничной организации](https://lwn.net/Articles/708526/), в случае необходимости. В этой книге мы рассмотрим только четырёхуровневую страничную организацию, поэтому этот код будет проигнорирован.

Как вы можете видеть выше, регистр `rbx` содержит начальный адрес кода декомпрессора ядра, и мы помещаем этот адрес со смещением `boot_stack_end` в регистр `rsp`, который представляет указатель на вершину стека. После этого шага стек будет корректным. Вы можете найти определение `boot_stack_end` в конце [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S):

```assembly
	.bss
	.balign 4
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
boot_stack:
	.fill BOOT_STACK_SIZE, 1, 0
boot_stack_end:
```

Он расположен в конце секции `.bss`, прямо перед таблицей `.pgtable`. Если вы посмотрите сценарий компоновщика [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/vmlinux.lds.S), вы найдёте определения `.bss` и `.pgtable`.

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

Следующие две инструкции `leaq` вычисляют  эффективные адреса `rip` и `rbx` со смещением `_bss - 8` и помещают их в `rsi` и `rdi`. Зачем мы вычисляем эти адреса? На самом деле сжатый образ ядра находится между этим кодом копирования (от `startup_32` до текущего кода) и кодом декомпрессии. Вы можете проверить это, посмотрев сценарий компоновщика - [arch/x86/boot/compressed/vmlinux.lds.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/vmlinux.lds.S):

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

В конце мы видим вызов функции `extract_kernel`:

```assembly
	pushq	%rsi
	movq	%rsi, %rdi
	leaq	boot_heap(%rip), %rsi
	leaq	input_data(%rip), %rdx
	movl	$z_input_len, %ecx
	movq	%rbp, %r8
	movq	$z_output_len, %r9
	call	extract_kernel
	popq	%rsi
```

Мы снова устанавливаем `rdi` в указатель на структуру `boot_params` и сохраняем его в стек. В то же время мы устанавливаем `rsi` для указания на область, которая должа использоваться для распаковки ядра. Последним шагом является подготовка параметров `extract_kernel` и вызов этой функции для распаковки ядра. Функция `extract_kernel` определена в [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/misc.c) и принимает шесть аргументов:

* `rmode` - указатель на структуру [boot_params](https://github.com/torvalds/linux/blob/v4.16//arch/x86/include/uapi/asm/bootparam.h#L114), которая заполнена загрузчиком или во время ранней инициализации ядра;
* `heap` - указатель на `boot_heap`, представляющий собой начальный адрес ранней загрузочной кучи;
* `input_data` - указатель на начало сжатого ядра или, другими словами, указатель на `arch/x86/boot/compressed/vmlinux.bin.bz2`;
* `input_len` - размер сжатого ядра;
* `output` - начальный адрес будущего распакованного ядра;
* `output_len` - размер распакованного ядра;

Все аргументы буду передаваться через регистры согласно [двоичному интерфейсу приложений System V (ABI)](http://www.x86-64.org/documentation/abi.pdf). Мы закончили подготовку и переходим к декомпрессии ядра.

Декомпрессия ядра
--------------------------------------------------------------------------------

Как мы видели в предыдущем абзаце, функция `extract_kernel` определена [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/misc.c) и содержит шесть аргументов. Эта функция начинается с инициализации видео/консоли, которую мы уже видели в предыдущих частях. Нам нужно сделать это ещё раз, потому что мы не знаем, находились ли мы в [режиме реальных адресов](https://en.wikipedia.org/wiki/Real_mode), использовался ли загрузчик, или загрузчик использовал `32` или `64-битный` протокол загрузки.

После первых шагов инициализации мы сохраняем указатели на начало и конец свободной памяти:

```C
free_mem_ptr     = heap;
free_mem_end_ptr = heap + BOOT_HEAP_SIZE;
```

где `heap` является вторым параметром функции `extract_kernel`, который мы получили в [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S):

```assembly
leaq	boot_heap(%rip), %rsi
```

Как вы видели выше, `boot_heap` определён как:

```assembly
boot_heap:
	.fill BOOT_HEAP_SIZE, 1, 0
```

где `BOOT_HEAP_SIZE` - это макрос, который раскрывается в `0x10000` (`0x400000` в случае `bzip2` ядра) и представляет собой размер кучи.

После инициализации указателей кучи, следующий шаг - вызов функции `choose_random_location` из [arch/x86/boot/compressed/kaslr.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/kaslr.c#L425). Как можно догадаться из названия функции, она выбирает ячейку памяти, в которой будет разархивирован образ ядра. Может показаться странным, что нам нужно найти или даже `выбрать` место для декомпрессии сжатого образа ядра, но ядро Linux поддерживает технологию [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization), которая позволяет загрузить распакованное ядро по случайному адресу из соображений безопасности.

Мы не будем рассматривать рандомизацию адреса загрузки ядра Linux в этой части, но сделаем это в следующей части.

Теперь мы вернёмся к [misc.c](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/misc.c#L404). После получения адреса для образа ядра мы должны были совершить некоторые проверки и убедиться в том, что полученный случайный адрес правильно выровнен и является корректным:

```C
if ((unsigned long)output & (MIN_KERNEL_ALIGN - 1))
	error("Destination physical address inappropriately aligned");

if (virt_addr & (MIN_KERNEL_ALIGN - 1))
	error("Destination virtual address inappropriately aligned");

if (heap > 0x3fffffffffffUL)
	error("Destination address too large");

if (virt_addr + max(output_len, kernel_total_size) > KERNEL_IMAGE_SIZE)
	error("Destination virtual address is beyond the kernel mapping area");

if ((unsigned long)output != LOAD_PHYSICAL_ADDR)
    error("Destination address does not match LOAD_PHYSICAL_ADDR");

if (virt_addr != LOAD_PHYSICAL_ADDR)
	error("Destination virtual address changed when not relocatable");
```

После этого мы увидим знакомое сообщение:

```
Decompressing Linux...
```

и вызываем функцию `__decompress`:

```C
__decompress(input_data, input_len, NULL, NULL, output, output_len, NULL, error);
```

которая будет распаковывать ядро. Реализация функции `__decompress` зависит от того, какой алгоритм декомпрессии был выбран во время компиляции:

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

и если файл некорректный, функция выводит сообщение об ошибке и останавливается. Если же `ELF` файл корректный, мы просматриваем все заголовки из указанного `ELF` файла и копируем все загружаемые сегменты с правильным адресом, выровненным по 2 мегабайтам, в выходной буфер:


```C
	for (i = 0; i < ehdr.e_phnum; i++) {
		phdr = &phdrs[i];

		switch (phdr->p_type) {
		case PT_LOAD:
#ifdef CONFIG_X86_64
			if ((phdr->p_align % 0x200000) != 0)
				error("Alignment of LOAD segment isn't multiple of 2MB");
#endif
#ifdef CONFIG_RELOCATABLE
			dest = output;
			dest += (phdr->p_paddr - LOAD_PHYSICAL_ADDR);
#else
			dest = (void *)(phdr->p_paddr);
#endif
			memmove(dest, output + phdr->p_offset, phdr->p_filesz);
			break;
		default:
			break;
		}
	}
```

С этого момента все загружаемые сегменты находятся в правильном месте.

Следующим шагом после функции `parse_elf` является вызов функции `handle_relocations`. Реализация этой функции зависит от опции конфигурации ядра `CONFIG_X86_NEED_RELOCS`, и если она включена, то эта функция корректирует адреса в образе ядра и вызывается только в том случае, если во время конфигурации ядра была включена опция конфигурации `CONFIG_RANDOMIZE_BASE`. Реализация функции `handle_relocations` достаточно проста. Эта функция вычитает значение `LOAD_PHYSICAL_ADDR` из значения базового адреса загрузки ядра и, таким образом, мы получаем разницу между тем, где ядро было слинковано для загрузки и тем, где оно было фактически загружено. После этого мы можем выполнить релокацию ядра, поскольку мы знаем фактический адрес, по которому было загружено ядро, адрес по которому оно было слинковано для запуска и таблицу релокации, которая находится в конце образа ядра.

После перемещения ядра мы возвращаемся из `extract_kernel` обратно в [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/v4.16/arch/x86/boot/compressed/head_64.S).

Адрес ядра находится в регистре `rax` и мы совершаем переход по нему:

```assembly
jmp	*%rax
```

На этом всё. Теперь мы в ядре!

Заключение
--------------------------------------------------------------------------------

Это конец пятой части процесса загрузки ядра Linux. Мы больше не увидим статей о загрузке ядра (возможны обновления этой и предыдущих статей), но будет много статей о других внутренних компонентах ядра.

В следующей главе будут описаны более подробные сведения о процессе загрузки ядра Linux, например рандомизация адреса загрузки и т.д.

**От переводчика: пожалуйста, имейте в виду, что английский - не мой родной язык, и я очень извиняюсь за возможные неудобства. Если вы найдёте какие-либо ошибки или неточности в переводе, пожалуйста, пришлите pull request в [linux-insides-ru](https://github.com/proninyaroslav/linux-insides-ru).**

Ссылки
--------------------------------------------------------------------------------

* [Рандомизация размещения адресного пространства](https://en.wikipedia.org/wiki/Address_space_layout_randomization)
* [initrd](https://en.wikipedia.org/wiki/Initrd)
* [long mode](https://en.wikipedia.org/wiki/Long_mode)
* [bzip2](http://www.bzip.org/)
* [Инструкция RDdRand](https://en.wikipedia.org/wiki/RdRand)
* [Счётчик временных меток](https://en.wikipedia.org/wiki/Time_Stamp_Counter)
* [Программируемый интервальный таймер](https://en.wikipedia.org/wiki/Intel_8253)
* [Предыдущий пост](linux-bootstrap-4.md)
