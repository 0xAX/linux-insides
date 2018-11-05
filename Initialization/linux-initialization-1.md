Инициализация ядра. Часть 1.
================================================================================

Первые шаги в коде ядра
--------------------------------------------------------------------------------

Предыдущая [статья](../Booting/linux-bootstrap-6.md) была последней частью главы [процесса загрузки](../Booting/README.md) ядра Linux и теперь мы начинаем погружение в процесс инициализации. После того как образ ядра Linux распакован и помещён в нужное место, ядро начинает свою работу. Все предыдущие части описывают работу кода настройки ядра, который выполняет подготовку до того, как будут выполнены первые байты кода ядра Linux. Теперь мы находимся в ядре, и все части этой главы будут посвящены процессу инициализации ядра, прежде чем оно запустит процесс с помощью [pid](https://en.wikipedia.org/wiki/Process_identifier) `1`. Есть ещё много вещей, который необходимо сделать, прежде чем ядро запустит первый `init` процесс. Мы начнём с точки входа в ядро, которая находится в [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) и будем двигаться дальше и дальше. Мы увидим первые приготовления, такие как инициализацию начальных таблиц страниц, переход на новый дескриптор в пространстве ядра и многое другое, прежде чем увидим запуск функции `start_kernel` в [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c#L489).

В последней [части](../Booting/linux-bootstrap-6.md) предыдущей [главы](../Booting/README.md) мы остановились на инструкции [jmp](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) из ассемблерного файла [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

```assembly
jmp	*%rax
```

В данный момент регистр `rax` содержит адрес точки входа в ядро Linux, который был получен в результате вызова функции `decompress_kernel` из файла [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c). Итак, наша последняя инструкция в коде настройки ядра - это переход на точку входа. Мы уже знаем, где определена точка входа ядра Linux, поэтому мы можем начать изучать, что делает ядро Linux после запуска.

Первые шаги в ядре
--------------------------------------------------------------------------------

Хорошо, мы получили адрес распакованного образа ядра с помощью функции `decompress_kernel` в регистр `rax`. Как мы уже знаем, начальная точка распакованного образа ядра находится в файле [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S), а также в его начале можно увидеть следующие определения:

```assembly0
    .text
	__HEAD
	.code64
	.globl startup_64
startup_64:
	...
	...
	...
```

Мы можем видеть определение подпрограммы `startup_64` в секции `__HEAD`, которая является просто макросом, раскрывающимся до определения исполняемой секции `.head.text`:

```C
#define __HEAD		.section	".head.text","ax"
```

Определение данной секции расположено в скрипте компоновщика [arch/x86/kernel/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S#L93):

```
.text : AT(ADDR(.text) - LOAD_OFFSET) {
	_text = .;
	...
	...
	...
} :text = 0x9090
```

Помимо определения секции `.text` из скрипта компоновщика, мы можем понять виртуальные и физические адреса по умолчанию. Обратите внимание, что адрес `_text` - это счётчик местоположения, определённый как:

```
. = __START_KERNEL;
```

для [x86_64](https://en.wikipedia.org/wiki/X86-64). Определение макроса `__START_KERNEL` находится в заголовочном файле [arch/x86/include/asm/page_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/page_types.h) и представлен суммой базового виртуального адреса отображения ядра и физического начала:

```C
#define __START_KERNEL	(__START_KERNEL_map + __PHYSICAL_START)

#define __PHYSICAL_START  ALIGN(CONFIG_PHYSICAL_START, CONFIG_PHYSICAL_ALIGN)
```

Или другими словами:

* Базовый физический адрес ядра Linux - `0x1000000`;
* Базовый виртуальный адрес ядра Linux - `0xffffffff81000000`.

После того как мы очистили конфигурацию CPU, мы вызываем функцию `__startup_64`, которая определена в [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head64.c:

```assembly
	leaq	_text(%rip), %rdi
	pushq	%rsi
	call	__startup_64
	popq	%rsi
```

```C
unsigned log __head __startup_64(unsigned long physaddr,
				 struct boot_params *bp)
{
	unsigned long load_delta, *p;
	unsigned long pgtable_flags;
	pgdval_t *pgd;
	p4dval_t *p4d;
	pudval_t *pud;
	pmdval_t *pmd, pmd_entry;
	pteval_t *mask_ptr;
	bool la57;
	int i;
	unsigned int *next_pgt_ptr;
	...
	...
	...
}
```

Поскольку [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization#Linux) включен, адрес `start_64` может отличаться от адреса, скомпилированного для запуска, поэтому нам нужно вычислить дельту с помощью следующего кода:

```C
	load_delta = physaddr - (unsigned long)(_text - __START_KERNEL_map);
```

В результате `load_delta` содержит дельту между адресом, скомпилированным для запуска, и текущим адресом.

После того как мы получили дельту, мы проверяем правильность выравнивания адреса `_text` по `2` мегабайтам. Мы сделаем это с помощью следующего кода:

```assembly
	if (load_delta & ~PMD_PAGE_MASK)
		for (;;);
```

Если адрес `_text` не выровнен по `2` мегабайтам, мы входим в бесконечный цикл. `PMD_PAGE_MASK` указывает маску для `промежуточного каталога страниц` (см. [страничную организацию памяти](../Theory/linux-theory-1.md)) и определён как:

```C
#define PMD_PAGE_MASK           (~(PMD_PAGE_SIZE-1))
```

где макрос `PMD_PAGE_SIZE` определён как:

```
#define PMD_PAGE_SIZE           (_AC(1, UL) << PMD_SHIFT)
#define PMD_SHIFT		21
```

Размер `PMD_PAGE_SIZE` можно легко вычислить - он составляет `2` мегабайта.

Если поддержка [SME](https://en.wikipedia.org/wiki/Zen_(microarchitecture)#Enhanced_security_and_virtualization_support) включена, мы активируем её и включаем маску шифрования SME в `load_delta`:

```C
	sme_enable(bp);
	load_delta += sme_get_me_mask();
```

Хорошо, мы сделали некоторые начальные проверки, и теперь можем двигаться дальше.

Исправление базовых адресов таблиц страниц
--------------------------------------------------------------------------------

На следующем этапе мы исправляем физические адреса в таблице страниц:

```C
	pgd = fixup_pointer(&early_top_pgt, physaddr);
	pud = fixup_pointer(&level3_kernel_pgt, physaddr);
	pmd = fixup_pointer(level2_fixmap_pgt, physaddr);
```

Давайте рассмотрим определение функции `fixup_pointer`, которая возвращает физический адрес переданного аргумента:

```C
static void __head *fixup_pointer(void *ptr, unsigned long physaddr)
{
	return ptr - (void *)_text + (void *)physaddr;
}
```

Затем мы сосредоточимся на `early_top_pgt` и других табличных символах, которые мы видели выше. Давайте попробуем понять, что означают эти символы. Прежде всего посмотрим на их определение:

```assembly
NEXT_PAGE(early_top_pgt)
	.fill	512,8,0
	.fill	PTI_USER_PGD_FILL,8,0

NEXT_PAGE(level3_kernel_pgt)
	.fill	L3_START_KERNEL,8,0
	.quad	level2_kernel_pgt - __START_KERNEL_map + _KERNPG_TABLE_NOENC
	.quad	level2_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC

NEXT_PAGE(level2_kernel_pgt)
	PMDS(0, __PAGE_KERNEL_LARGE_EXEC,
		KERNEL_IMAGE_SIZE/PMD_SIZE)

NEXT_PAGE(level2_fixmap_pgt)
	.fill	506,8,0
	.quad	level1_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC
	.fill	5,8,0

NEXT_PAGE(level1_fixmap_pgt)
	.fill	512,8,0
```

Выглядит сложно, но на самом деле это не так. Прежде всего, давайте посмотрим на `early_top_pgt`. Он начинается с `4096` нулевых байтов (или `8192` байт если включён `CONFIG_PAGE_TABLE_ISOLATION`), это означает, что мы не используем первые `511` записей. После этого мы видим одну запись `level3_kernel_pgt`. В начале его определения мы видим, что он заполнен `4080` байтами нулей (`L3_START_KERNEL` равен `510`). Впоследствии он хранит две записи, которые отображают пространство ядра. Обратите внимание, что мы вычитаем `__START_KERNEL_map` из `level2_kernel_pgt` и `level2_fixmap_pgt`. Как известно, `__START_KERNEL_map` является базовым виртуальным адресом текстового сегмента ядра, поэтому, если мы вычтем `__START_KERNEL_map`, мы получим физические адреса `level2_kernel_pgt` и `level2_fixmap_pgt`.

```C
#define _KERNPG_TABLE_NOENC   (_PAGE_PRESENT | _PAGE_RW | _PAGE_ACCESSED | \
			       _PAGE_DIRTY)
#define _PAGE_TABLE_NOENC     (_PAGE_PRESENT | _PAGE_RW | _PAGE_USER | \
			       _PAGE_ACCESSED | _PAGE_DIRTY)
```

`level2_kernel_pgt` - это запись в таблице страниц, содержащая указатель на промежуточный каталог страниц, которая отображает пространство ядра. Она вызывает макрос `PDMS`, который создает `512` мегабайт из `__START_KERNEL_map` для `.text` ядра (после того как эти `512` мегабайт будут областью памяти модуля).

`level2_fixmap_pgt` - это виртуальные адреса, которые могут ссылаться на любые физические адреса даже в пространстве ядра. Они представлены `4048` байтами нулей, значением `level1_fixmap_pgt`, `8` мегабайтами, зарезервированными для отображения `vsyscalls` и `2` мегабайта пустого пространства.

Вы можете больше узнать об этом в статье [страничная организация памяти](../Theory/linux-theory-1.md).

Теперь, после того как мы увидели определения этих символов, вернёмся к коду. Мы инициализируем последнюю запись `pgd` с помощью `level3_kernel_pgt`:

```C
pgd[pgd_index(__START_KERNEL_map)] = level3_kernel_pgt - __START_KERNEL_map + _PAGE_TABLE_NOENC;
```

Все адреса `p*d` могут быть неверными, если `startup_64` не равен адресу по умолчанию - `0x1000000`. Вы должны помнить, что `load_delta` содержит дельта между адресом метки `startup_64`, который был получен во время [компоновки](https://en.wikipedia.org/wiki/Linker_%28computing%29) ядра и фактическим адресом. Таким образом, мы добавляем дельту к некоторым записям `p*d`:

```C
	pgd[pgd_index(__START_KERNEL_map)] += load_delta;
	pud[510] += load_delta;
	pud[511] += load_delta;
	pmd[506] += load_delta;
```

После этого у нас будет:

```
early_top_pgt[511] -> level3_kernel_pgt[0]
level3_kernel_pgt[510] -> level2_kernel_pgt[0]
level3_kernel_pgt[511] -> level2_fixmap_pgt[0]
level2_kernel_pgt[0]   -> 512 Мб, отображённые на ядро
level2_fixmap_pgt[506] -> level1_fixmap_pgt
```

Обратите внимание, что мы не исправили базовый адрес `early_top_pgt` и некоторых других каталогов таблицы страниц, потому что мы увидим это во время построения/заполнения структур этих таблиц страниц. После исправления базовых адресов таблиц страниц, мы можем приступить к их построению.

Настройка отображения "один в один" (identity mapping)
--------------------------------------------------------------------------------

Теперь мы можем увидеть настройку отображения "один в один" начальных таблиц страниц. В страничной организации с отображением "один в один", виртуальные адреса идентичны физическими адресами. Давайте рассмотрим это подробнее. Прежде всего, мы заменим `pud` и `pmd` указателем на первую и вторую запись `early_dynamic_pgts`:

```C
	next_pgt_ptr = fixup_pointer(&next_early_pgt, physaddr);
	pud = fixup_pointer(early_dynamic_pgts[(*next_pgt_ptr)++], physaddr);
	pmd = fixup_pointer(early_dynamic_pgts[(*next_pgt_ptr)++], physaddr);
```

Давайте посмотри на определение `early_dynamic_pgts`:

```assembly
NEXT_PAGE(early_dynamic_pgts)
	.fill	512*EARLY_DYNAMIC_PAGE_TABLES,8,0
```

которая будет хранить временные таблицы страниц раннего ядра.

Затем мы инициализируем `pgtable_flags`, который позже будет использоваться при инициализации записей `p*d`:

```C
	pgtable_flags = _KERNPG_TABLE_NOENC + sme_get_me_mask();
```

Функция `sme_get_me_mask` возвращает `sme_me_mask`, который был инициализирован в функции `sme_enable`.

Далее мы заполняем две записи `pgd` с помощью `pud` плюс `pgtable_flags`, который мы инициализировали ранее:

```C
	i = (physaddr >> PGDIR_SHIFT) % PTRS_PER_PGD;
	pgd[i + 0] = (pgdval_t)pud + pgtable_flags;
	pgd[i + 1] = (pgdval_t)pud + pgtable_flags;
```

`PGDIR_SHFT` обозначате маску для бит глобального каталога страниц в виртуальном адресе. Здесь мы вычисляем по модулю `PTRS_PER_PGD` (который раскрывается до `512`), чтобы не получить доступ к индексу, превышающему `512`. Для всех типов каталогов страниц есть свой макрос:

```C
#define PGDIR_SHIFT     39
#define PTRS_PER_PGD	512
#define PUD_SHIFT       30
#define PTRS_PER_PUD	512
#define PMD_SHIFT       21
#define PTRS_PER_PMD	512
```

Мы делаем почти то же самое:

```C
	i = (physaddr >> PUD_SHIFT) % PTRS_PER_PUD;
	pud[i + 0] = (pudval_t)pmd + pgtable_flags;
	pud[i + 1] = (pudval_t)pmd + pgtable_flags;
```

Затем мы инициализируем `pmd_entry` и отфильтровываем неподдерживаемые биты `__PAGE_KERNEL_ *`:

```C
	pmd_entry = __PAGE_KERNEL_LARGE_EXEC & ~_PAGE_GLOBAL;
	mask_ptr = fixup_pointer(&__supported_pte_mask, physaddr);
	pmd_entry &= *mask_ptr;
	pmd_entry += sme_get_me_mask();
	pmd_entry += physaddr;
```

Далее мы заполняем все записи `pmd`, чтобы покрыть полный размер ядра:

```C
	for (i = 0; i < DIV_ROUND_UP(_end - _text, PMD_SIZE); i++) {
		int idx = i + (physaddr >> PMD_SHIFT) % PTRS_PER_PMD;
		pmd[idx] = pmd_entry + i * PMD_SIZE;
	}
```

Затем мы исправляем виртуальные адреса текста+данных ядра. Обратите внимание, что мы можем записать недопустимые `pmd`, если ядро было перемещено (функция `cleanup_highmap` исправляет это вместе с отображениями вне `_end`).

```C
	pmd = fixup_pointer(level2_kernel_pgt, physaddr);
	for (i = 0; i < PTRS_PER_PMD; i++) {
		if (pmd[i] & _PAGE_PRESENT)
			pmd[i] += load_delta;
	}
```

Далее мы удаляем маску шифрования памяти для получения истинного физического адреса (помните, что `load_delta` включает в себя маску):

```C
	*fixup_long(&phys_base, physaddr) += load_delta - sme_get_me_mask();
```

`phys_base` должен соответствовать первой записи в `level2_kernel_pgt`.

В качестве последнего шага функции `__startup_64` мы зашифровываем ядро (если активен SME) и возвращаем маску шифрования SME, которая будет использоваться в качестве модификатора для начальной записи каталога страницы, запрограммированной в регистр `cr3`:

```C
	sme_encrypt_kernel(bp);
	return sme_get_me_mask();
```

Теперь вернемся к ассемблерному коду. Мы готовимся к следующему разделу со следующим кодом:

```assembly
	addq	$(early_top_pgt - __START_KERNEL_map), %rax
	jmp 1f
```

который добавляет физический адрес `early_top_pgt` к регистру `rax` и теперь регистр `rax` содержит сумму адреса и маски шифрования SME.

На данный момент это всё. Наша ранняя страничная структура настроена и нам нужно совершить последнее приготовление, прежде чем мы перейдем к точке входа в ядро.

Последнее приготовление перед переходом на точку входа в ядро
--------------------------------------------------------------------------------

После перехода на метку `1` мы включаем `PAE`, `PGE` (Paging Global Extension) и помещаем содержимое `phys_base` (см. выше) в регистр `rax` и заполняем регистр `cr3`:

```assembly
1:
	movl	$(X86_CR4_PAE | X86_CR4_PGE), %ecx
	movq	%rcx, %cr4

	addq	phys_base(%rip), %rax
	movq	%rax, %cr3
```

На следующем шаге мы проверяем, поддерживает ли процессор бит [NX](http://en.wikipedia.org/wiki/NX_bit):

```assembly
	movl	$0x80000001, %eax
	cpuid
	movl	%edx,%edi
```

Мы помещаем значение `0x80000001` в `eax` и выполняем инструкцию `cpuid` для получения расширенной информации о процессоре и битах. Полученный результат находится в регистре `edx`, который мы помещаем в `edi`.

Теперь мы помещаем `0xc0000080` (`MSR_EFER`) в `ecx` и вызываем инструкцию `rdmsr` для чтения моделезависимого регистра.

```assembly
	movl	$MSR_EFER, %ecx
	rdmsr
```

Результат находится в `edx:eax`. Общий вид `EFER` следующий:

```
63                                                                              32
┌───────────────────────────────────────────────────────────────────────────────┐
│                                                                               │
│                                Зарезервированный MBZ                          │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
31                            16  15      14      13   12  11   10  9  8 7  1   0
┌──────────────────────────────┬───┬───────┬───────┬────┬───┬───┬───┬───┬───┬───┐
│                              │ T │       │       │    │   │   │   │   │   │   │
│ Зарезервированный MBZ        │ C │ FFXSR | LMSLE │SVME│NXE│LMA│MBZ│LME│RAZ│SCE│
│                              │ E │       │       │    │   │   │   │   │   │   │
└──────────────────────────────┴───┴───────┴───────┴────┴───┴───┴───┴───┴───┴───┘
```

Здесь мы не увидим все поля, но узнаем об этих и других `MSR` в специальной части. Когда мы считываем `EFER` в `edx:eax`, мы проверяем `_EFER_SCE` или нулевой бит, являющийся `System Call Extensions` с инструкцией `btsl` и устанавливаем его в единицу. С помощью бита `SCE` мы включаем инструкции `SYSCALL` и `SYSRET`. На следующем шаге мы проверяем 20 бит в регистре `edi`, который хранит результат `cpuid` (см. выше). Если `20` бит установлен (бит `NX`), мы просто записываем `EFER_SCE` в моделезависимый регистр.

```assembly
	btsl	$_EFER_SCE, %eax
	btl	$20,%edi
	jnc     1f
	btsl	$_EFER_NX, %eax
	btsq	$_PAGE_BIT_NX,early_pmd_flags(%rip)
1:	wrmsr
```

Если бит [NX](https://en.wikipedia.org/wiki/NX_bit) поддерживается, мы включаем `_EFER_NX` и записываем в него с помощью инструкции `wrmsr`. После того как бит [NX](https://en.wikipedia.org/wiki/NX_bit) установлен, мы устанавливаем некоторые биты в [регистре управления](https://en.wikipedia.org/wiki/Control_register) `cr0`:

```C
	movl	$CR0_STATE, %eax
	movq	%rax, %cr0
```

в частности следующие биты:

* `X86_CR0_PE` - система в защищённом режиме;
* `X86_CR0_MP` - контролирует взаимодействие инструкций WAIT/FWAIT с помощью флага TS в CR0;
* `X86_CR0_ET` - на 386 позволяло указать, был ли внешний математический сопроцессор 80287 или 80387;
* `X86_CR0_NE` - позволяет включить внутреннюю x87 отчётность об ошибках с плавающей запятой, иначе включает PC-стиль x87 обнаружение ошибок;
* `X86_CR0_WP` - если установлен, CPU не может писать в страницы только для чтения, когда уровень привилегий равен 0;
* `X86_CR0_AM` - проверка выравнивания включена, если установлен AM и флаг AC (в регистре EFLAGS), а уровень привелигий равен 3;
* `X86_CR0_PG` - включает страничную организацию.

Мы уже знаем, что для запуска любого кода и даже большего количества [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) кода из ассемблера, нам необходимо настроить стек. Как всегда, мы делаем это путём установки [указателя стека](https://en.wikipedia.org/wiki/Stack_register) на корректное место в памяти и сброса [регистра флагов](https://en.wikipedia.org/wiki/FLAGS_register):

```assembly
movq initial_stack(%rip), %rsp
pushq $0
popfq
```

Самое интересное здесь - `initial_stack`. Этот символ определён в файле [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) и выглядит следующим образом:

```assembly
GLOBAL(initial_stack)
    .quad  init_thread_union + THREAD_SIZE - SIZEOF_PTREGS
```

Макрос `THREAD_SIZE` определён в [arch/x86/include/asm/page_64_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/page_64_types.h) и зависит от значения макроса `KASAN_STACK_ORDER`:

```C
#ifdef CONFIG_KASAN
#define KASAN_STACK_ORDER 1
#else
#define KASAN_STACK_ORDER 0
#endif

#define THREAD_SIZE_ORDER       (2 + KASAN_STACK_ORDER)
#define THREAD_SIZE  (PAGE_SIZE << THREAD_SIZE_ORDER)
```

когда [kasan](https://github.com/torvalds/linux/blob/master/Documentation/dev-tools/kasan.rst) отключён, а `PAGE_SIZE` равен `4096` байтам. Таким образом, `THREAD_SIZE` будет раскрыт до `16` килобайт и представляет собой размер стека потока. Почему `потока`? Возможно, вы уже знаете, что каждый [процесс](https://en.wikipedia.org/wiki/Process_%28computing%29) может иметь [родительский процесс](https://en.wikipedia.org/wiki/Parent_process) и [дочерний процессы](https://en.wikipedia.org/wiki/Child_process). На самом деле родительский и дочерний процесс различаются в стеке. Для нового процесса выделяется новый стек ядра. В ядре Linux этот стек представлен [объединением (union)](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B) со структурой `thread_info`.

`init_thread_union` представлен `thread_union` и определён в файле [include/linux/sched.h](https://github.com/torvalds/linux/blob/master/include/linux/sched.h):

```C
union thread_union {
#ifndef CONFIG_ARCH_TASK_STRUCT_ON_STACK
	struct task_struct task;
#endif
#ifndef CONFIG_THREAD_INFO_IN_TASK
	struct thread_info thread_info;
#endif
	unsigned long stack[THREAD_SIZE/sizeof(long)];
};
```

где `CONFIG_THREAD_INFO_IN_TASK` - параметр конфигурации ядра, включённый для архитектуры `ia64`, а `CONFIG_THREAD_INFO_IN_TASK` - параметр конфигурации ядра, включённый для архитектуры `x86_64`. Таким образом, структура `thread_info` будет помещена в структуру `task_struct` вместо объединения `thread_union`.

`init_thread_union` расположен в файле [include/asm-generic/vmlinux.lds.h](https://github.com/torvalds/blob/master/include/asm-generic/vmlinux.lds.h) как часть макроса `INIT_TASK_DATA`:

```C
#define INIT_TASK_DATA(align)  \
	...                    \
	init_thread_union = .; \
	...
```

Данный макрос используется в [arch/x86/kernel/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S) следующим образом:

```
.data : AT(ADDR(.data) - LOAD_OFFSET) {
	...
	INIT_TASK_DATA(THREAD_SIZE)
	...
} :data
```

Теперь мы можем понять это выражение:

```assembly
GLOBAL(initial_stack)
    .quad  init_thread_union + THREAD_SIZE - SIZEOF_PTREGS
```


где символ `initial_stack` указывает на начало массива `thread_union.stack` + `THREAD_SIZE`, который равен 16 килобайтам и - `SIZEOF_PTREGS`, который является соглашением, помогающее unwinder'у ядра надёжно обнаруживать конец стека.

После настройки начального загрузочного стека, необходимо обновить [глобальную таблицу дескрипторов](https://en.wikipedia.org/wiki/Global_Descriptor_Table) с помощью инструкции `lgdt`:

```assembly
lgdt	early_gdt_descr(%rip)
```

где `early_gdt_descr` определён как:

```assembly
early_gdt_descr:
	.word	GDT_ENTRIES*8-1
early_gdt_descr_base:
	.quad	INIT_PER_CPU_VAR(gdt_page)
```

Это необходимо, поскольку теперь ядро работает в нижних адресах пользовательского пространства, но вскоре ядро будет работать в своём собственном пространстве.

Теперь давайте посмотрим на определение `early_gdt_descr`. Макрос `GDT_ENTRIES` раскрывается до `32`, поэтому глобальная таблица дескрипторов содержит `32` записи для кода ядра, данных, сегментов локального хранилища потоков и т.д.

Теперь давайте посмотрим на определение `early_gdt_descr_base`. Структура `gdt_page` определена в [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/desc.h):

```C
struct gdt_page {
	struct desc_struct gdt[GDT_ENTRIES];
} __attribute__((aligned(PAGE_SIZE)));
```

Она содержит одно поле `gdt`, которое является массивом структур `desc_struct`:

```C
struct desc_struct {
         union {
                 struct {
                         unsigned int a;
                         unsigned int b;
                 };
                 struct {
                         u16 limit0;
                         u16 base0;
                         unsigned base1: 8, type: 4, s: 1, dpl: 2, p: 1;
                         unsigned limit: 4, avl: 1, l: 1, d: 1, g: 1, base2: 8;
                 };
         };
 } __attribute__((packed));
```

который выглядит знакомым дескриптором `GDT`. Можно отметить, что структура `gdt_page` выровнена по `PAGE_SIZE`, равному `4096` байтам. Это значит, что `gdt` займёт одну страницу.

Теперь попробуем понять, что такое `INIT_PER_CPU_VAR`. `INIT_PER_CPU_VAR` это макрос, определённый в [arch/x86/include/asm/percpu.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/percpu.h), который просто совершает конкатенацию `init_per_cpu__` с заданным параметром:

```C
#define INIT_PER_CPU_VAR(var) init_per_cpu__##var
```

После того, как макрос `INIT_PER_CPU_VAR` будет раскрыт, мы будем иметь `init_per_cpu__gdt_page`. Мы можем видеть инициализацию `init_per_cpu__gdt_page` в [скрипте компоновщика](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S):

```
#define INIT_PER_CPU(x) init_per_cpu__##x = x + __per_cpu_load
INIT_PER_CPU(gdt_page);
```

После того как макросы `INIT_PER_CPU_VAR` и `INIT_PER_CPU` будут раскрыты до `init_per_cpu__gdt_page` мы получим смещение от `__per_cpu_load`. После этих расчётов мы получим корректный базовый адрес нового `GDT`.

Переменные, локальные для каждого процессора (`per-CPU variables`), являются особенностью ядра версии 2.6. Вы уже можете понять что это, исходя из названия. Когда мы создаём `per-CPU` переменную, каждый процессор будет иметь свою собственную копию этой переменной. Здесь мы создаём `per-CPU` переменную `gdt_page`. Существует много преимуществ для переменных этого типа, например, нет блокировок, поскольку каждый процессор работает со своей собственной копией переменной и т.д. Таким образом, каждое ядро на многопроцессорной машине будет иметь свою собственную таблицу `GDT` и каждая запись в таблице будет представлять сегмент памяти, к которому можно получить доступ из потока, который запускался на ядре. Подробнее о `per-CPU` переменных можно почитать в статье [Concepts/linux-cpu-1](../Concepts/linux-cpu-1.md).

После загрузки новой глобальной таблицы дескрипторов мы перезагружаем сегменты:

```assembly
	xorl %eax,%eax
	movl %eax,%ds
	movl %eax,%ss
	movl %eax,%es
	movl %eax,%fs
	movl %eax,%gs
```

После всех этих шагов мы настраиваем регистр `gs`, указывающий на `irqstack`, который представляет собой специальный стек для обработки [прерываний](https://en.wikipedia.org/wiki/Interrupt):

```assembly
	movl	$MSR_GS_BASE,%ecx
	movl	initial_gs(%rip),%eax
	movl	initial_gs+4(%rip),%edx
	wrmsr
```

где `MSR_GS_BASE`:

```C
#define MSR_GS_BASE             0xc0000101
```

Нам необходимо поместить `MSR_GS_BASE` в регистр `ecx` и загрузить данные из `eax` и `edx` (которые указывают на `initial_gs`) с помощью инструкции `wrmsr`. Мы не используем регистры сегментов `cs`, `fs`, `ds` и `ss` для адресации в 64-битном режиме, но могут использоваться регистры `fs` и `gs`. `fs` и `gs` имеют скрытую часть (как мы видели в режиме реальных адресов для `cs`) и эта часть содержит дескриптор, который отображён на [моделезависимый регистр](https://en.wikipedia.org/wiki/Model-specific_register). Таким образом, выше мы можем видеть `0xc0000101` - это MSR-адрес `gs.base`. В точке входа нет стека ядра, поэтому когда происходит [системный вызов](https://en.wikipedia.org/wiki/System_call) или [прерывание](https://en.wikipedia.org/wiki/Interrupt), значение `MSR_GS_BASE` будет хранить адрес стека прерываний.

На следующем шаге мы помещаем адрес структуры параметров загрузки режима реальных адресов в регистр `rdi` (напомним, что `rsi` содержит указатель на эту структуру с самого начала) и переходим к коду на C:

```assembly
	pushq	$.Lafter_lret	# поиещает адрес возврата в стек для unwinder'а
	xorq	%rbp, %rbp	# очищает указатель фрейма
	movq	initial_code(%rip), %rax
	pushq	$__KERNEL_CS	# устанавливает корректный cs
	pushq	%rax		# целевой адрес в отрицательном пространстве
	lretq
.Lafter_lret:
```

Здесь мы помещаем адрес `initial_code` в `rax` и помещаем возвращаемый адрес `__KERNEL_CS` и адрес `initial_code` в стек. После этого мы видим инструкцию `lretq`, означающую что после неё адрес возврата будет извлечён из стека (теперь это адрес `initial_code`) и будет совершён переход по нему. `initial_code` определён в том же файле исходного кода и выглядит следующим образом:

```assembly
	.balign	8
	GLOBAL(initial_code)
	.quad	x86_64_start_kernel
	...
	...
	...
```

Как мы видим `initial_code` содержит адрес `x86_64_start_kernel`, определённой в [arch/x86/kerne/head64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head64.c):

```C
asmlinkage __visible void __init x86_64_start_kernel(char * real_mode_data)
{
	...
	...
	...
}
```

У неё есть один аргумент - `real_mode_data` (помните, ранее мы помещали адрес данных режима реальных адресов в регистр `rdi`).

Далее в start_kernel
--------------------------------------------------------------------------------

Мы увидим последние приготовления, прежде чем сможем перейти к "точке входа в ядро" - к функции `start_kernel` в файле [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c).

Прежде всего в функции `x86_64_start_kernel` мы видим некоторый проверки:

```C
BUILD_BUG_ON(MODULES_VADDR < __START_KERNEL_map);
BUILD_BUG_ON(MODULES_VADDR - __START_KERNEL_map < KERNEL_IMAGE_SIZE);
BUILD_BUG_ON(MODULES_LEN + KERNEL_IMAGE_SIZE > 2*PUD_SIZE);
BUILD_BUG_ON((__START_KERNEL_map & ~PMD_MASK) != 0);
BUILD_BUG_ON((MODULES_VADDR & ~PMD_MASK) != 0);
BUILD_BUG_ON(!(MODULES_VADDR > __START_KERNEL));
MAYBE_BUILD_BUG_ON(!(((MODULES_END - 1) & PGDIR_MASK) == (__START_KERNEL & PGDIR_MASK)));
BUILD_BUG_ON(__fix_to_virt(__end_of_fixed_addresses) <= MODULES_END);
```

например, виртуальный адрес пространства модуля не меньше, чем базовый адрес кода ядра (`__STAT_KERNEL_map`), код ядра с модулями не меньше образа ядра и т.д. `BUILD_BUG_ON` является макросом и выглядит следующим образом:

```C
#define BUILD_BUG_ON(condition) ((void)sizeof(char[1 - 2*!!(condition)]))
```

Давайте попробуем понять, как работает этот трюк. Возьмём, например, первое условие: `MODULES_VADDR < __START_KERNEL_map`. `!!conditions` тоже самое что и `condition != 0`. Таким образом, если `MODULES_VADDR < __START_KERNEL_map` истинно, мы получим `1` в `!!(condition)` или ноль, если ложно. После `2*!!(condition)` мы получим или `2` или `0`. В конце вычислений мы можем получить два разных поведения:

* У нас будет ошибка компиляции, поскольку мы попытаемся получить размер `char` массива с отрицательным индексом (вполне возможно, но в нашем случае `MODULES_VADDR` не может быть меньше `__START_KERNEL_map`);
* Ошибки компиляции не будет.

На этом всё. Очень интересный C-трюк для получения ошибки компиляции, которая зависит от некоторых констант.

На следующем шаге мы видим вызов функции `cr4_init_shadow`, которая сохраняет копии `cr4` для каждого процессора. Переключения контекста могут изменять биты в `cr4`, поэтому нам нужно сохранить `cr4` для каждого процессора. После этого происходит вызов функции `reset_early_page_tables`, которая сбрасывает все записи глобального каталога страниц и записывает новый указатель на PGT в `cr3`:

```C
	memset(early_top_pgt, 0, sizeof(pgd_t)*(PTRS_PER_PGD-1));
	next_early_pgt = 0;
	write_cr3(__sme_pa_nodebug(early_top_pgt));
```

Вскоре мы создадим новые таблицы страниц. Далее в цикле мы обнуляем все записи глобального каталога страниц. После этого мы устанавливаем `next_early_pgt` в ноль (подробнее об этом в следующей статье) и записываем физический адрес `early_top_pgt` в `cr3`.

После этого мы очищаем `_bss` от `__bss_stop` до `__bss_start`, а также `init_top_pgt`. `init_top_pgt` определён в [arch/x86/kerne/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S):

```assembly
NEXT_PGD_PAGE(init_top_pgt)
	.fill	512,8,0
	.fill	PTI_USER_PGD_FILL,8,0
```
Это то же самое определение, что и `early_top_pgt`.

Следующим шагом будет настройка начальных обработчиков `IDT`. Это большой раздел, поэтому мы увидим его в следующей статье.

Заключение
--------------------------------------------------------------------------------

Это конец первой части об инициализации ядра Linux.

В следующей части мы увидим инициализацию начальных обработчиков прерываний, отображение памяти пространства ядра и многое другое.

**От переводчика: пожалуйста, имейте в виду, что английский - не мой родной язык, и я очень извиняюсь за возможные неудобства. Если вы найдёте какие-либо ошибки или неточности в переводе, пожалуйста, пришлите pull request в [linux-insides-ru](https://github.com/proninyaroslav/linux-insides-ru).**

Ссылки
--------------------------------------------------------------------------------

* [Моделезависимый регистр](http://en.wikipedia.org/wiki/Model-specific_register)
* [Страничная организация памяти](../Theory/linux-theory-1.md)
* [Предыдущая часть - Рандомизация адреса ядра](../Booting/linux-bootstrap-6.md)
* [Бит NX](http://en.wikipedia.org/wiki/NX_bit)
* [ASLR](http://en.wikipedia.org/wiki/Address_space_layout_randomization)
