Инициализация ядра. Часть 1.
================================================================================

Первые шаги в коде ядра
--------------------------------------------------------------------------------

Предыдущая [статья](../Booting/linux-bootstrap-5.html) была последней частью главы [процесса загрузки](../Booting/README.md) ядра Linux и теперь мы начинаем погружение в процесс инициализации. После того как образ ядра Linux распакован и помещён в нужное место, ядро начинает свою работу. Все предыдущие части описывают работу кода настройки ядра, который выполняет подготовку до того, как будут выполнены первые байты кода ядра Linux. Теперь мы находимся в ядре, и все части этой главы будут посвящены процессу инициализации ядра, прежде чем оно запустит процесс с помощью [pid](https://en.wikipedia.org/wiki/Process_identifier) `1`. Есть ещё много вещей, который необходимо сделать, прежде чем ядро запустит первый `init` процесс. Мы начнём с точки входа в ядро, которая находится в [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S) и будем двигаться дальше и дальше. Мы увидим первые приготовления, такие как инициализацию начальных таблиц страниц, переход на новый дескриптор в пространстве ядра и многое другое, прежде чем увидим запуск функции `start_kernel` в [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c#L489).

В последней [части](../Booting/linux-bootstrap-5.html) предыдущей [главы](../Booting/README.md) мы остановились на инструкции [jmp](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/compressed/head_64.S) из ассемблерного файла [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/compressed/head_64.S):

```assembly
jmp	*%rax
```

В данный момент регистр `rax` содержит адрес точки входа в ядро Linux, который был получен в результате вызова функции `decompress_kernel` из файла [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/compressed/misc.c). Итак, наша последняя инструкция в коде настройки ядра - это переход на точку входа. Мы уже знаем, где она определена, поэтому мы можем начать изучение того, что делает ядро Linux после запуска.

Первые шаги в ядре
--------------------------------------------------------------------------------

Хорошо, мы получили адрес распакованного образа ядра с помощью функции `decompress_kernel` в регистр `rax`. Как мы уже знаем, начальная точка распакованного образа ядра находится в файле [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S), а также в его начале можно увидеть следующие определения:

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

Определение данной секции расположено в скрипте компоновщика [arch/x86/kernel/vmlinux.lds.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/vmlinux.lds.S#L93):

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

для [x86_64](https://en.wikipedia.org/wiki/X86-64). Определение макроса `__START_KERNEL` находится в заголовочном файле [arch/x86/include/asm/page_types.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/page_types.h) и представлен суммой базового виртуального адреса отображения ядра и физического начала:

```C
#define __START_KERNEL	(__START_KERNEL_map + __PHYSICAL_START)

#define __PHYSICAL_START  ALIGN(CONFIG_PHYSICAL_START, CONFIG_PHYSICAL_ALIGN)
```

Или другими словами:

* Базовый физический адрес ядра Linux - `0x1000000`;
* Базовый виртуальный адрес ядра Linux - `0xffffffff81000000`.

Теперь мы знаем физические и виртуальные адреса по умолчанию подпрограммы `startup_64`, но для того чтобы узнать фактические адреса, мы должны вычислить их с помощью следующего кода:

```assembly
	leaq	_text(%rip), %rbp
	subq	$_text - __START_KERNEL_map, %rbp
```

Да, он определён как `0x1000000`, но может быть другим, например, если включён [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization#Linux). Поэтому наша текущая цель - вычислить разницу между `0x1000000` и тем, где мы действительно загружены. Мы просто помещаем `rip-относительный` адрес в регистр `rbp`, а затем вычитаем из него `$_text - __START_KERNEL_map`. Мы знаем, что скомпилированный виртуальный адрес `_text` равен `0xffffffff81000000`, а физический - `0x1000000`. `__START_KERNEL_map` расширяется до адреса `0xffffffff80000000`, поэтому во второй строке ассемблерного кода мы получим следующее выражение:

```
rbp = 0x1000000 - (0xffffffff81000000 - 0xffffffff80000000)
```

После вычисления регистр `rbp` будет содержать `0`, который представляет разницу между адресом где мы фактически загрузились, и адресом где был скомпилирован код. В нашем случае `ноль` означает, что ядро Linux было загружено по дефолтному адресу и [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization#Linux) отключён.

После того как мы получили адрес `startup_64`, нам необходимо проверить, правильно ли он выровнен. Мы сделаем это с помощью следующего кода:

```assembly
	testl	$~PMD_PAGE_MASK, %ebp
	jnz	bad_address
```

Мы сравниваем нижнюю часть регистра `rbp` с дополняемым значением `PMD_PAGE_MASK`. `PMD_PAGE_MASK` указывает маску для `каталога страниц среднего уровня` (см. [подкачку страниц](../Theory/Paging.md)) и определён как:

```C
#define PMD_PAGE_MASK           (~(PMD_PAGE_SIZE-1))
```

где макрос `PMD_PAGE_SIZE` определён как:

```
#define PMD_PAGE_SIZE           (_AC(1, UL) << PMD_SHIFT)
#define PMD_SHIFT       21
```

Размер `PMD_PAGE_SIZE` можно легко вычислить - он составляет `2` мегабайта. Здесь мы используем стандартную формулу для проверки выравнивания, и если адрес `text` не выровнен по `2` мегабайтам, то переходим на метку `bad_address`.

После этого мы проверяем адрес на то, что он не слишком велик, путём проверки наивысших `18` бит:

```assembly
	leaq	_text(%rip), %rax
	shrq	$MAX_PHYSMEM_BITS, %rax
	jnz	bad_address
```

Адрес не должен превышать `46` бит:

```C
#define MAX_PHYSMEM_BITS       46
```

Хорошо, мы сделали некоторые начальные проверки, и теперь можем двигаться дальше.

Исправление базовых адресов таблиц страниц
--------------------------------------------------------------------------------

Первым шагом, прежде чем начать настройку подкачки страниц "один в один" (identity paging), является исправление следующих адресов:

```assembly
	addq	%rbp, early_level4_pgt + (L4_START_KERNEL*8)(%rip)
	addq	%rbp, level3_kernel_pgt + (510*8)(%rip)
	addq	%rbp, level3_kernel_pgt + (511*8)(%rip)
	addq	%rbp, level2_fixmap_pgt + (506*8)(%rip)
```

Все адреса: `early_level4_pgt`, `level3_kernel_pgt` и другие могут быть некорректными, если `startup_64` не равен адресу по умолчанию - `0x1000000`. Регистр `rbp` содержит разницу адресов, поэтому мы добавляем его к `early_level4_pgt`, `level3_kernel_pgt` и `level2_fixmap_pgt`. Давайте попробуем понять, что означают эти метки. Прежде всего посмотрим на их определение:

```assembly
NEXT_PAGE(early_level4_pgt)
	.fill	511,8,0
	.quad	level3_kernel_pgt - __START_KERNEL_map + _PAGE_TABLE

NEXT_PAGE(level3_kernel_pgt)
	.fill	L3_START_KERNEL,8,0
	.quad	level2_kernel_pgt - __START_KERNEL_map + _KERNPG_TABLE
	.quad	level2_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE

NEXT_PAGE(level2_kernel_pgt)
	PMDS(0, __PAGE_KERNEL_LARGE_EXEC,
		KERNEL_IMAGE_SIZE/PMD_SIZE)

NEXT_PAGE(level2_fixmap_pgt)
	.fill	506,8,0
	.quad	level1_fixmap_pgt - __START_KERNEL_map + _PAGE_TABLE
	.fill	5,8,0

NEXT_PAGE(level1_fixmap_pgt)
	.fill	512,8,0
```

Выглядит сложно, но на самом деле это не так. Прежде всего, давайте посмотрим на `early_level4_pgt`. Он начинается с (4096 - 8) нулевых байтов, это означает, что мы не используем первые `511` записей. После этого мы видим одну запись `level3_kernel_pgt`. Обратите внимание на то, что мы вычитаем из него `__START_KERNEL_map + _PAGE_TABLE`. Как известно, `__START_KERNEL_map` является базовым виртуальным адресом сегмента кода ядра, поэтому, если мы вычтем `__START_KERNEL_map`, мы получим физический адрес `level3_kernel_pgt`. Теперь давайте посмотрим на `_PAGE_TABLE`, это просто права доступа к странице:

```C
#define _PAGE_TABLE     (_PAGE_PRESENT | _PAGE_RW | _PAGE_USER | \
                         _PAGE_ACCESSED | _PAGE_DIRTY)
```

Вы можете больше узнать об этом в статье [Подкачка страниц](../Theory/Paging.html).

`level3_kernel_pgt` хранит две записи, которые отображают пространство ядра. В начале его определения мы видим, что он заполнен нулями `L3_START_KERNEL` или `510` раз. `L3_START_KERNEL` - это индекс в верхнем каталоге страниц, который содержит адрес `__START_KERNEL_map` и равен `510`. После этого мы можем видеть определение двух записей `level3_kernel_pgt`: `level2_kernel_pgt` и `level2_fixmap_pgt`. Первая очень проста - это запись в таблице страниц, которая содержит указатель на каталог страниц среднего уровня, который отображает пространство ядра и содержит права доступа:

```C
#define _KERNPG_TABLE   (_PAGE_PRESENT | _PAGE_RW | _PAGE_ACCESSED | \
                         _PAGE_DIRTY)
```
Второй - `level2_fixmap_pgt` - это виртуальные адреса, которые могут ссылаться на любые физические адреса даже в пространстве ядра. Они представлены одной записью `level2_fixmap_pgt` и "дырой" в `10` мегабайт для отображения [vsyscalls](https://lwn.net/Articles/446528/). `level2_kernel_pgt` вызывает макрос `PDMS`, который выделяет `512` мегабайт из `__START_KERNEL_map` для сегмента ядра `.text` (после этого `512` мегабайт будут модулем пространства памяти).

После того как мы увидели определения этих символов, вернёмся к коду, описанному в начале раздела. Вы должны помнить, что регистр `rbp` содержит разницу между адресом символа `startup_64`, который был получен во время [компоновки](https://en.wikipedia.org/wiki/Linker_%28computing%29) ядра, и фактическим адреса. Итак, на данный момент нам просто нужно добавить эту разницу к базовому адресу некоторых записей таблицы страниц, чтобы получить корректные адреса. В нашем случае это записи:

```assembly
	addq	%rbp, early_level4_pgt + (L4_START_KERNEL*8)(%rip)
	addq	%rbp, level3_kernel_pgt + (510*8)(%rip)
	addq	%rbp, level3_kernel_pgt + (511*8)(%rip)
	addq	%rbp, level2_fixmap_pgt + (506*8)(%rip)
```

последняя запись `early_level4_pgt` является каталогом `level3_kernel_pgt`, последние две записи `level3_kernel_pgt` являются каталогами `level2_kernel_pgt` и `level2_fixmap_pgt` соответственно, и 507 запись `level2_fixmap_pgt` является каталогом `level1_fixmap_pgt`.

После этого у нас будет:

```
early_level4_pgt[511] -> level3_kernel_pgt[0]
level3_kernel_pgt[510] -> level2_kernel_pgt[0]
level3_kernel_pgt[511] -> level2_fixmap_pgt[0]
level2_kernel_pgt[0]   -> 512 Мб, отображённые на ядро
level2_fixmap_pgt[507] -> level1_fixmap_pgt
```

Обратите внимание, что мы не исправили базовый адрес `early_level4_pgt` и некоторых других каталогов таблицы страниц, потому что мы увидим это во время построения/заполнения структур для этих таблиц страниц. После исправления базовых адресов таблиц страниц, мы можем приступить к их построению.

Настройка отображения "один в один" (identity mapping)
--------------------------------------------------------------------------------

Теперь мы можем увидеть настройку отображения "один в один" начальных таблиц страниц. В подкачке, отображённой "один в один", виртуальные адреса сопоставляются с физическими адресами, которые имеют одно и то же значение, `один в один`. Давайте рассмотрим это подробнее. Прежде всего, мы получаем `rip-относительные` адреса `_text` и `_early_level4_pgt` и помещаем их в регистры `rdi` и `rbx`:

```assembly
	leaq	_text(%rip), %rdi
	leaq	early_level4_pgt(%rip), %rbx
```

После этого мы сохраняем адрес `_text` в регистр `rax` и получаем индекс записи глобального каталога страниц, который хранит адрес `_text`, путём сдвига адреса `_text` на `PGDIR_SHIFT`:

```assembly
	movq	%rdi, %rax
	shrq	$PGDIR_SHIFT, %rax
```

где `PGDIR_SHIFT` равен `39`. `PGDIR_SHFT` указывает маску для битов глобального каталога страниц в виртуальном адресе. Существуют макросы для всех типов каталогов страниц:

```C
#define PGDIR_SHIFT     39
#define PUD_SHIFT       30
#define PMD_SHIFT       21
```

После этого мы помещаем адрес первой записи таблицы страниц `early_dynamic_pgts` в регистр `rdx` с правами доступа `_KERNPG_TABLE` (см. выше) и заполняем `early_level4_pgt` двумя записями `early_dynamic_pgts`:

```assembly
	leaq	(4096 + _KERNPG_TABLE)(%rbx), %rdx
	movq	%rdx, 0(%rbx,%rax,8)
	movq	%rdx, 8(%rbx,%rax,8)
```

Регистр `rbx` содержит адрес `early_level4_pgt` и здесь `%rax * 8` - это индекс глобального каталога страниц, занятого адресом `_text`. Итак, здесь мы заполняем две записи `early_level4_pgt` адресами двух записей `early_dynamic_pgts`, который связан с `_text`. `early_dynamic_pgts` является массивом массивов:

```C
extern pmd_t early_dynamic_pgts[EARLY_DYNAMIC_PAGE_TABLES][PTRS_PER_PMD];
```

который будет хранить временные таблицы страниц для раннего ядра и которые мы не будем перемещать в `init_level4_pgt`.

После этого мы добавляем `4096` (размер `early_level4_pgt`) в регистр `rdx` (теперь он содержит адрес первой записи `early_dynamic_pgts`) и помещаем значение регистра `rdi` (теперь он содержит физический адрес `_text`) в регистр `rax`. Далее мы смещаем адрес `_text` на `PUD_SHIFT`, чтобы получить индекс записи из верхнего каталога страниц, который содержит этот адрес, и очищаем старшие биты, для того чтобы получить только связанную с `pud` часть:

```assembly
	addq	$4096, %rdx
	movq	%rdi, %rax
	shrq	$PUD_SHIFT, %rax
	andl	$(PTRS_PER_PUD-1), %eax
```

Поскольку у нас есть индекс верхнего каталога таблиц страниц, мы записываем два адреса второй записи массива `early_dynamic_pgts` в первую запись временного каталога страниц:

```assembly
	movq	%rdx, 4096(%rbx,%rax,8)
	incl	%eax
	andl	$(PTRS_PER_PUD-1), %eax
	movq	%rdx, 4096(%rbx,%rax,8)
```

На следующем шаге мы выполняем ту же операцию для последнего каталога таблиц страниц, но заполняем не две записи, а все, чтобы охватить полный размер ядра.

После заполнения наших начальных каталогов таблиц страниц мы помещаем физический адрес `early_level4_pgt` в регистр `rax` и переходим на метку `1`:

```assembly
	movq	$(early_level4_pgt - __START_KERNEL_map), %rax
	jmp 1f
```

На данный момент это всё. Наша ранняя подкачка страниц настроена и нам нужно совершить последнее приготовление, прежде чем мы перейдём к коду на C и к точке входа в ядро.

Последнее приготовление перед переходом на точку входа в ядро
--------------------------------------------------------------------------------

После перехода на метку `1` мы включаем `PAE`, `PGE` (Paging Global Extension) и помещаем физический адрес `phys_base` (см. выше) в регистр `rax` и заполняем регистр `cr3`:

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
	btl	    $20,%edi
	jnc     1f
	btsl	$_EFER_NX, %eax
	btsq	$_PAGE_BIT_NX,early_pmd_flags(%rip)
1:	wrmsr
```

Если бит [NX](https://en.wikipedia.org/wiki/NX_bit) поддерживается, мы включаем `_EFER_NX` и записываем в него с помощью инструкции `wrmsr`. После того как бит [NX](https://en.wikipedia.org/wiki/NX_bit) установлен, мы устанавливаем некоторые биты в [регистре управления](https://en.wikipedia.org/wiki/Control_register) `cr0`, а именно:

* `X86_CR0_PE` - система в защищённом режиме;
* `X86_CR0_MP` - контролирует взаимодействие инструкций WAIT/FWAIT с помощью флага TS в CR0;
* `X86_CR0_ET` - на 386 позволяло указать, был ли внешний математический сопроцессор 80287 или 80387;
* `X86_CR0_NE` - позволяет включить внутреннюю x87 отчётность об ошибках с плавающей запятой, иначе включает PC-стиль x87 обнаружение ошибок;
* `X86_CR0_WP` - если установлен, CPU не может писать в страницы только для чтения, когда уровень привилегий равен 0;
* `X86_CR0_AM` - проверка выравнивания включена, если установлен AM и флаг AC (в регистре EFLAGS), а уровень привелигий равен 3;
* `X86_CR0_PG` - включает подкачку страниц.

с помощью выполнения данного ассемблерного кода:

```assembly
#define CR0_STATE	(X86_CR0_PE | X86_CR0_MP | X86_CR0_ET | \
			 X86_CR0_NE | X86_CR0_WP | X86_CR0_AM | \
			 X86_CR0_PG)
movl	$CR0_STATE, %eax
movq	%rax, %cr0
```

Мы уже знаем, что для запуска любого кода и даже большего количества [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) кода из ассемблера, нам необходимо настроить стек. Как всегда, мы делаем это путём установки [указателя стека](https://en.wikipedia.org/wiki/Stack_register) на корректное место в памяти и сброса [регистра флагов](https://en.wikipedia.org/wiki/FLAGS_register):

```assembly
movq initial_stack(%rip), %rsp
pushq $0
popfq
```

Самое интересное здесь - `initial_stack`. Этот символ определён в файле [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S) и выглядит следующим образом:

```assembly
GLOBAL(initial_stack)
    .quad  init_thread_union+THREAD_SIZE-8
```

Макрос `GLOBAL` нам уже знаком. Он определён в файле [arch/x86/include/asm/linkage.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/linkage.h) и раскрывается до `глобального` определения символа:

```C
#define GLOBAL(name)    \
         .globl name;           \
         name:
```

Макрос `THREAD_SIZE` определён в [arch/x86/include/asm/page_64_types.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/page_64_types.h) и зависит от значения макроса `KASAN_STACK_ORDER`:

```C
#define THREAD_SIZE_ORDER       (2 + KASAN_STACK_ORDER)
#define THREAD_SIZE  (PAGE_SIZE << THREAD_SIZE_ORDER)
```

когда [kasan](http://lxr.free-electrons.com/source/Documentation/kasan.txt) отключён, а `PAGE_SIZE` равен `4096` байтам. Таким образом, `THREAD_SIZE` будет раскрыт до `16` килобайт и представляет собой размер стека потока. Почему `потока`? Возможно, вы уже знаете, что каждый [процесс](https://en.wikipedia.org/wiki/Process_%28computing%29) может иметь [родительские](https://en.wikipedia.org/wiki/Parent_process) и [дочерние](https://en.wikipedia.org/wiki/Child_process) процессы. На самом деле родительский и дочерний процесс различаются в стеке. Для нового процесса выделяется новый стек ядра. В ядре Linux этот стек представлен [объединением (union)](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B) со структурой `thread_info`.

Как мы видим, `init_thread_union` представлен [объединением](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B) `thread_union`. Раньше это объединение выглядело следующим образом:

```C
union thread_union {
         struct thread_info thread_info;
         unsigned long stack[THREAD_SIZE/sizeof(long)];
};
```

но начиная с версии `4.9-rc1` `thread_info` была перемещена в структуру `task_struct`, представляющую потоки. На данный момент `thread_union` выглядит так:

```C
union thread_union {
#ifndef CONFIG_THREAD_INFO_IN_TASK
	struct thread_info thread_info;
#endif
	unsigned long stack[THREAD_SIZE/sizeof(long)];
};
```

где `CONFIG_THREAD_INFO_IN_TASK` - параметр конфигурации ядра, включённый для архитектуры `x86_64`. Поскольку в этой книге мы рассматриваем только архитектуру `x86_64`, экземпляр `thread_union` будет содержать только стек, а структура `thread_info` будет помещена в `task_struct`.

`init_thread_union` выглядит следующим образом:

```
union thread_union init_thread_union __init_task_data = {
#ifndef CONFIG_THREAD_INFO_IN_TASK
	INIT_THREAD_INFO(init_task)
#endif
};
```

который представляет собой только стек потока. Теперь мы можем понять это выражение:

```assembly
GLOBAL(initial_stack)
    .quad  init_thread_union+THREAD_SIZE-8
```


где символ `initial_stack` указывает на начало массива `thread_union.stack` + `THREAD_SIZE`, который равен 16 килобайтам и - 8 байт. Здесь нам нужно вычесть `8` байт в верхней части стека. Это необходимо для обеспечения незаконного доступа следующей страницы памяти.

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

Это необходимо, поскольку теперь ядро работает в нижних адресах пользовательского пространства, но вскоре ядро будет работать в своём собственном пространстве. Теперь давайте посмотрим на определение `early_gdt_descr`. Глобальная таблица дескриптор содержит `32` записи:

```C
#define GDT_ENTRIES 32
```

для кода ядра, данных, сегментов локального хранилища потоков и т.д. Теперь давайте посмотрим на определение `early_gdt_descr_base`.

`gdt_page` определена как:

```C
struct gdt_page {
	struct desc_struct gdt[GDT_ENTRIES];
} __attribute__((aligned(PAGE_SIZE)));
```

в файле [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/desc.h). Она содержит одно поле `gdt`, которое является массивом структур `desc_struct`:

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

и представляет собой знакомый нам дескриптор `GDT`. Также мы можем отметить, что структура `gdt_page` выровнена по `PAGE_SIZE`, равному `4096` байтам. Это значит, что `gdt` займёт одну страницу. Теперь попробуем понять, что такое `INIT_PER_CPU_VAR`. `INIT_PER_CPU_VAR` это макрос, определённый в [arch/x86/include/asm/percpu.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/percpu.h), который просто совершает конкатенацию `init_per_cpu__` с заданным параметром:

```C
#define INIT_PER_CPU_VAR(var) init_per_cpu__##var
```

После того, как макрос `INIT_PER_CPU_VAR` будет раскрыт, мы будем иметь `init_per_cpu__gdt_page`. Мы можем видеть это в [скрипте компоновщика](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/vmlinux.lds.S):

```
#define INIT_PER_CPU(x) init_per_cpu__##x = x + __per_cpu_load
INIT_PER_CPU(gdt_page);
```

После того как макросы `INIT_PER_CPU_VAR` и `INIT_PER_CPU` будут раскрыты до `init_per_cpu__gdt_page` мы получим смещение от `__per_cpu_load`. После этих расчётов мы получим корректный базовый адрес нового `GDT`.

Переменные, локальные для каждого процессора (`per-CPU variables`), являются особенностью ядра версии 2.6. Вы уже можете понять что это, исходя из названия. Когда мы создаём `per-CPU` переменную, каждый процессор будет иметь свою собственную копию этой переменной. Здесь мы создаём `per-CPU` переменную `gdt_page`. Существует много преимуществ для переменных этого типа, например, нет блокировок, поскольку каждый процессор работает со своей собственной копией переменной и т.д. Таким образом, каждое ядро на многопроцессорной машине будет иметь свою собственную таблицу `GDT` и каждая запись в таблице будет представлять сегмент памяти, к которому можно получить доступ из потока, который запускался на ядре. Подробнее о `per-CPU` переменных можно почитать в статье [Concepts/per-cpu](Concepts/per-cpu.md).

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

Нам необходимо поместить `MSR_GS_BASE` в регистр `ecx` и загрузить данные из `eax` и `edx` (которые указывают на `initial_gs`) с помощью инструкции `wrmsr`. Мы не используем регистры сегментов `cs`, `fs`, `ds` и `ss` для адресации в 64-битном режиме, но могут использоваться регистры `fs` и `gs`. `fs` и `gs` имеют скрытую часть (как мы видели в режиме реальных адресов для `cs`) и эта часть содержит дескриптор, который отображён на [моделезависимый регистр](https://en.wikipedia.org/wiki/Model-specific_register). Таким образом, выше мы можем видеть `0xc0000101` - это MSR-адрес `gs.base`. Когда произошёл [системный вызов](https://en.wikipedia.org/wiki/System_call) или [прерывание](https://en.wikipedia.org/wiki/Interrupt), в точке входа нет стека ядра, поэтому значение `MSR_GS_BASE` будет хранить адрес стека прерываний.

На следующем шаге мы помещаем адрес структуры параметров загрузки режима реальных адресов в регистр `rdi` (напомним, что `rsi` содержит указатель на эту структуру с самого начала) и переходим к коду на C:

```assembly
	movq	initial_code(%rip), %rax
	pushq	$__KERNEL_CS	# устанавливает корректный cs
	pushq	%rax		# целевой адрес в отрицательном пространстве
	lretq
```

Здесь мы помещаем адрес `initial_code` в `rax` и помещаем фейковый адрес `__KERNEL_CS` и адрес `initial_code` в стек. После этого мы видим инструкцию `lretq`, означающую что после неё адрес возврата будет извлечён из стека (теперь это адрес `initial_code`) и будет совершён переход по нему. `initial_code` определён в том же файле исходного кода и выглядит следующим образом:

```assembly
	.balign	8
	GLOBAL(initial_code)
	.quad	x86_64_start_kernel
	...
	...
	...
```

Как мы видим `initial_code` содержит адрес `x86_64_start_kernel`, определённой в [arch/x86/kerne/head64.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head64.c):

```C
asmlinkage __visible void __init x86_64_start_kernel(char * real_mode_data) {
	...
	...
	...
}
```

У неё есть один аргумент - `real_mode_data` (помните, ранее мы помещали адрес данных режима реальных адресов в регистр `rdi`).

Это первый C код в ядре!

Далее в start_kernel
--------------------------------------------------------------------------------

Мы увидим последние приготовления, прежде чем сможем перейти к "точке входа в ядро" - к функции `start_kernel` в файле [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c#L489).

Прежде всего в функции `x86_64_start_kernel` мы видим некоторый проверки:

```C
BUILD_BUG_ON(MODULES_VADDR < __START_KERNEL_map);
BUILD_BUG_ON(MODULES_VADDR - __START_KERNEL_map < KERNEL_IMAGE_SIZE);
BUILD_BUG_ON(MODULES_LEN + KERNEL_IMAGE_SIZE > 2*PUD_SIZE);
BUILD_BUG_ON((__START_KERNEL_map & ~PMD_MASK) != 0);
BUILD_BUG_ON((MODULES_VADDR & ~PMD_MASK) != 0);
BUILD_BUG_ON(!(MODULES_VADDR > __START_KERNEL));
BUILD_BUG_ON(!(((MODULES_END - 1) & PGDIR_MASK) == (__START_KERNEL & PGDIR_MASK)));
BUILD_BUG_ON(__fix_to_virt(__end_of_fixed_addresses) <= MODULES_END);
```

например, виртуальные адреса пространства модулей не меньше, чем базовый адрес кода ядра (`__STAT_KERNEL_map`), код ядра с модулями не меньше образа ядра и т.д. `BUILD_BUG_ON` является макросом и выглядит следующим образом:

```C
#define BUILD_BUG_ON(condition) ((void)sizeof(char[1 - 2*!!(condition)]))
```

Давайте попробуем понять, как работает этот трюк. Возьмём, например, первое условие: `MODULES_VADDR < __START_KERNEL_map`. `!!conditions` тоже самое что и `condition != 0`. Таким образом, если `MODULES_VADDR < __START_KERNEL_map` истинно, мы получим `1` в `!!(condition)` или ноль, если ложно. После `2*!!(condition)` мы получим или `2` или `0`. В конце вычислений мы можем получить два разных поведения:

* У нас будет ошибка компиляции, поскольку мы попытаемся получить размер `char` массива с отрицательным индексом (вполне возможно, но в нашем случае `MODULES_VADDR` не может быть меньше `__START_KERNEL_map`);
* Ошибки компиляции не будет.

На этом всё. Очень интересный C-трюк для получения ошибки компиляции, которая зависит от некоторых констант.

На следующем шаге мы видим вызов функции `cr4_init_shadow`, которая сохраняет копии `cr4` для каждого процессора. Переключения контекста могут изменять биты в `cr4`, поэтому нам нужно сохранить `cr4` для каждого процессора. После этого происходит вызов функции `reset_early_page_tables`, которая сбрасывает все записи глобального каталога страниц и записывает новый указатель на PGT в `cr3`:

```C
for (i = 0; i < PTRS_PER_PGD-1; i++)
	early_level4_pgt[i].pgd = 0;

next_early_pgt = 0;

write_cr3(__pa_nodebug(early_level4_pgt));
```

Вскоре мы создадим новые таблицы страниц. Далее в цикле мы проходим по всему глобальному каталогу страниц (`PTRS_PER_PGD` равен `512`) и обнуляем его. После этого мы устанавливаем `next_early_pgt` в ноль (подробнее об этом в следующей статье) и записываем физический адрес `early_level4_pgt` в `cr3`. `__pa_nodebug` - макрос, который выглядит следующим образом:

```C
((unsigned long)(x) - __START_KERNEL_map + phys_base)
```

После этого мы очищаем `_bss` от `__bss_stop` до `__bss_start` и следующим шагом будет настройка начальных обработчиков `IDT`. Это большой раздел, поэтому мы увидим его в следующей статье.

Заключение
--------------------------------------------------------------------------------

Это конец первой части об инициализации ядра Linux.

В следующей части мы увидим инициализацию начальных обработчиков прерываний, отображение памяти пространства ядра и многое другое.

**От переводчика: пожалуйста, имейте в виду, что английский - не мой родной язык, и я очень извиняюсь за возможные неудобства. Если вы найдёте какие-либо ошибки или неточности в переводе, пожалуйста, пришлите pull request в [linux-insides-ru](https://github.com/proninyaroslav/linux-insides-ru).**

Ссылки
--------------------------------------------------------------------------------

* [Моделезависимый регистр](http://en.wikipedia.org/wiki/Model-specific_register)
* [Подкачка страниц](Theory/Paging.md)
* [Предыдущая часть - Декомпрессия ядра](https://proninyaroslav.gitbooks.io/linux-insides-ru/content/Booting/linux-bootstrap-5.html)
* [Бит NX](http://en.wikipedia.org/wiki/NX_bit)
* [ASLR](http://en.wikipedia.org/wiki/Address_space_layout_randomization)
