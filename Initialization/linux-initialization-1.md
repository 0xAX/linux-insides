Инициализация ядра. Часть 1.
================================================================================

Первые шаги в коде ядра
--------------------------------------------------------------------------------

Предыдущая [статья](../Booting/linux-bootstrap-5.html) была последней частью главы [процесса загрузки](../Booting/README.md) ядра Linux и теперь мы начинаем погружение в процесс инициализации. После того как образ ядра Linux распакован и помещён в нужное место, ядро начинает свою работу. Все предыдущие части описывают работу кода настройки ядра, который выполняет подготовку до того, как будут выполнены первые байты кода ядра Linux. Теперь мы находимся в ядре, и все части этой главы будут посвящены процессу инициализации ядра, прежде чем оно запустит процесс с помощью [pid](https://en.wikipedia.org/wiki/Process_identifier) `1`. Есть ещё много вещей, который необходимо сделать, прежде чем ядро запустит первый `init` процесс. Мы начнём с точки входа в ядро, которая находится в [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) и будем двигаться дальше и дальше. Мы увидим первые приготовления, такие как инициализацию начальных таблиц страниц, переход на новый дескриптор в пространстве ядра и многое другое, прежде чем вы увидим запуск функции `start_kernel` в [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c#L489).

В последней [части](../Booting/linux-bootstrap-5.html) предыдущей [главы](../Booting/README.md) мы остановились на инструкции [jmp](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S) из ассемблерного файла исходного кода [arch/x86/boot/compressed/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/head_64.S):

```assembly
jmp	*%rax
```

В данный момент регистр `rax` содержит адрес точки входа в ядро Linux, который был получен в результате вызова функции `decompress_kernel` из файла [arch/x86/boot/compressed/misc.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/compressed/misc.c). Итак, наша последняя инструкция в коде настройки ядра - это переход на точку входа в ядро. Мы уже знаем, где определена точка входа в ядро linux, поэтому мы можем начать изучение того, что делает ядро Linux после запуска.

Первые шаги в ядре
--------------------------------------------------------------------------------

Хорошо, мы получили адрес распакованного образа ядра с помощью функции `decompress_kernel` в регистр `rax`. Как мы уже знаем, начальная точка распакованного образа ядра начинается в файле [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S), а также в его начале можно увидеть следующие определения:

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

Мы можем видеть определение подпрограммы `startup_64` в секции `__HEAD`, которая является просто макросом, раскрываемым до определения исполняемой секции `.head.text`:

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

Помимо определения секции `.text`, мы можем понять виртуальные и физические адреса по умолчанию из скрипта компоновщика. Обратите внимание, что адрес `_text` - это счётчик местоположения, определённый как:

```
. = __START_KERNEL;
```

для [x86_64](https://en.wikipedia.org/wiki/X86-64). Определение макроса `__START_KERNEL` находится в заголовочном файле [arch/x86/include/asm/page_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/page_types.h) и представлен суммой базового виртуального адреса отображения ядра и физического старта:

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

Да, оно определено как `0x1000000`, но может быть другим, например, если включен [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization#Linux). Поэтому наша текущая цель - вычислить разницу между `0x1000000` и где мы действительно загружены. Мы просто помещаем адрес `rip-relative` в регистр `rbp`, а затем вычитаем из него `$_text - __START_KERNEL_map`. Мы знаем, что скомпилированный виртуальный адрес `_text` равен `0xffffffff81000000`, а физический - `0x1000000`. The `__START_KERNEL_map` расширяется до адреса `0xffffffff80000000`, поэтому на второй строке ассемблерного кода мы получим следующее выражение:

```
rbp = 0x1000000 - (0xffffffff81000000 - 0xffffffff80000000)
```

После вычисления регистр `rbp` будет содержать `0`, который представляет разницу между адресами, где мы фактически загрузились, и где был скомпилирован код. В нашем случае `ноль` означает, что ядро Linux было загружено по дефолтному адресу и [kASLR](https://en.wikipedia.org/wiki/Address_space_layout_randomization#Linux) отключен.

После того как мы получили адрес `startup_64`, нам необходимо проверить чтобы этот адрес правильно выровнен. Мы сделаем это с помощью следующего кода:

```assembly
	testl	$~PMD_PAGE_MASK, %ebp
	jnz	bad_address
```

Мы сравниваем нижнюю часть регистра `rbp` с дополняемым значением `PMD_PAGE_MASK`. `PMD_PAGE_MASK` указывает маску для `Каталога страниц среднего уровня` (см. [подкачку страниц](../Theory/Paging.md)) и определена как:

```C
#define PMD_PAGE_MASK           (~(PMD_PAGE_SIZE-1))
```

где макрос `PMD_PAGE_SIZE` определён как:

```
#define PMD_PAGE_SIZE           (_AC(1, UL) << PMD_SHIFT)
#define PMD_SHIFT       21
```

Можно легко вычислить, что размер `PMD_PAGE_SIZE` составляет `2` мегабайта. Здесь мы используем стандартную формулу для проверки выравнивания, и если адрес `text` не выровнен по `2` мегабайтам, мы переходим на метку `bad_address`.

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

Все адреса: `early_level4_pgt`, `level3_kernel_pgt` и другие могут быть некорректными, если `startup_64` не равен адресу по умолчанию - `0x1000000`. Регистр `rbp` содержит адрес разницы, поэтому мы добавляем его к `early_level4_pgt`, `level3_kernel_pgt` и `level2_fixmap_pgt`. Давайте попробуем понять, что означают эти метки. Прежде всего давайте посмотрим на их определение:

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

Выглядит сложно, но на самом деле это не так. Прежде всего, давайте посмотрим на `early_level4_pgt`. Он начинается с (4096 - 8) байтов нулей, это означает, что мы не используем первые `511` записей. И после этого мы видим одну запись `level3_kernel_pgt`. Обратите внимание, что мы вычитаем из него `__START_KERNEL_map + _PAGE_TABLE`. Как известно, `__START_KERNEL_map` является базовым виртуальным адресом сегмента кода ядра, поэтому, если мы вычтем `__START_KERNEL_map`, мы получим физический адрес `level3_kernel_pgt`. Теперь давайте посмотрим на `_PAGE_TABLE`, это просто права доступа к странице:

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
Второй - `level2_fixmap_pgt` это виртуальные адреса, которые могут ссылаться на любые физические адреса даже в пространстве ядра. Они представлены одной записью `level2_fixmap_pgt` и "дырой" в `10` мегабайт для отображения [vsyscalls](https://lwn.net/Articles/446528/). `level2_kernel_pgt` вызывает макрос `PDMS`, который выделяет `512` мегабайт из `__START_KERNEL_map` для сегмента ядра `.text` (после этого `512` мегабайт будут модулем пространства памяти).

После того как мы увидели определения этих символов, вернёмся к коду, описанному в начале раздела. Вы помните, что регистр `rbp` содержит разницу между адресом символа `startup_64`, который был получен получен во время [компоновки](https://en.wikipedia.org/wiki/Linker_%28computing%29) ядра и фактического адреса. Итак, на этот момент нам просто нужно добавить эту разницу к базовому адресу некоторых записей таблицы страниц, чтобы получить корректные адреса. В нашем случае эти записи:

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

Обратите внимание, что мы не исправляли базовый адрес `early_level4_pgt` и некоторых других каталогов таблицы страниц, потому что мы увидим это во время построения/заполнения структур для этих таблиц страниц. После исправления базовых адресов таблиц страниц, мы можем приступить к их построению.

Настройка отображения "один в один" (identity mapping)
--------------------------------------------------------------------------------

Теперь мы можем увидеть настройку отображения "один в один" начальных таблиц страниц. В подкаче, отображённой "один в один", виртуальные адреса сопоставляются с физическими адресами, которые имеют одно и то же значение, `один в один`. Давайте рассмотрим это подробнее. Прежде всего, мы получаем `rip-относительный` адрес `_text` и `_early_level4_pgt` и помещаем их в регистры `rdi` и `rbx`:

```assembly
	leaq	_text(%rip), %rdi
	leaq	early_level4_pgt(%rip), %rbx
```

После этого мы сохраняем адрес `_text` в регистр `rax` и получаем индекс записи глобального каталога страниц, который хранит адрес `_text` address, путём сдвига адреса `_text` на `PGDIR_SHIFT`:

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

Регистр `rbx` содержит адрес `early_level4_pgt` и здесь `%rax * 8` - это индекс глобального каталога страниц, занятого адресом `_text`s. Итак, здесь мы заполняем две записи `early_level4_pgt` адресом двух записей `early_dynamic_pgts`, который связан с `_text`. `early_dynamic_pgts` является массивом массивов:

```C
extern pmd_t early_dynamic_pgts[EARLY_DYNAMIC_PAGE_TABLES][PTRS_PER_PMD];
```

который будет хранить временные таблицы страниц для раннего ядра и которые мы не будем перемещать в `init_level4_pgt`.

После этого мы добавляем `4096` (размер`early_level4_pgt`) в регистр `rdx` (теперь он содержит адрес первой записи `early_dynamic_pgts`) и помещаем значение регистра `rdi` (теперь он содержит физический адрес `_text`) в регистр `rax`. Теперь мы смещаем адрес `_text` на `PUD_SHIFT`, чтобы получить индекс записи из верхнего каталога страниц, который содержит этот адрес, и очищает старшие биты, для того чтобы получить только связанную с `pud` часть:

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

На следующем шаге мы выполняем ту же операцию для последнего каталога таблиц страниц, но заполняем не две записи, а все записи, чтобы охватить полный размер ядра.

После заполнения наших начальных каталогов таблиц страниц мы помещаем физический адрес `early_level4_pgt` в регистр `rax` и переходим на метку `1`:

```assembly
	movq	$(early_level4_pgt - __START_KERNEL_map), %rax
	jmp 1f
```

На данный момент это всё. Наша ранняя подкачка страниц подготовлена и нам нужно совершить последнее приготовление, прежде чем мы перейдём к коду на C и к точке входа в ядро.

Последнее приготовление перед переходом на точку входа в ядро
--------------------------------------------------------------------------------

After that we jump to the label `1` we enable `PAE`, `PGE` (Paging Global Extension) and put the physical address of the `phys_base` (see above) to the `rax` register and fill `cr3` register with it:

```assembly
1:
	movl	$(X86_CR4_PAE | X86_CR4_PGE), %ecx
	movq	%rcx, %cr4

	addq	phys_base(%rip), %rax
	movq	%rax, %cr3
```

In the next step we check that CPU supports [NX](http://en.wikipedia.org/wiki/NX_bit) bit with:

```assembly
	movl	$0x80000001, %eax
	cpuid
	movl	%edx,%edi
```

We put `0x80000001` value to the `eax` and execute `cpuid` instruction for getting the extended processor info and feature bits. The result will be in the `edx` register which we put to the `edi`.

Now we put `0xc0000080` or `MSR_EFER` to the `ecx` and call `rdmsr` instruction for the reading model specific register.

```assembly
	movl	$MSR_EFER, %ecx
	rdmsr
```

The result will be in the `edx:eax`. General view of the `EFER` is following:

```
63                                                                              32
┌───────────────────────────────────────────────────────────────────────────────┐
│                                                                               │
│                                Reserved MBZ                                   │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
31                            16  15      14      13   12  11   10  9  8 7  1   0
┌──────────────────────────────┬───┬───────┬───────┬────┬───┬───┬───┬───┬───┬───┐
│                              │ T │       │       │    │   │   │   │   │   │   │
│ Reserved MBZ                 │ C │ FFXSR | LMSLE │SVME│NXE│LMA│MBZ│LME│RAZ│SCE│
│                              │ E │       │       │    │   │   │   │   │   │   │
└──────────────────────────────┴───┴───────┴───────┴────┴───┴───┴───┴───┴───┴───┘
```

We will not see all fields in details here, but we will learn about this and other `MSRs` in a special part about it. As we read `EFER` to the `edx:eax`, we check `_EFER_SCE` or zero bit which is `System Call Extensions` with `btsl` instruction and set it to one. By the setting `SCE` bit we enable `SYSCALL` and `SYSRET` instructions. In the next step we check 20th bit in the `edi`, remember that this register stores result of the `cpuid` (see above). If `20` bit is set (`NX` bit) we just write `EFER_SCE` to the model specific register.

```assembly
	btsl	$_EFER_SCE, %eax
	btl	    $20,%edi
	jnc     1f
	btsl	$_EFER_NX, %eax
	btsq	$_PAGE_BIT_NX,early_pmd_flags(%rip)
1:	wrmsr
```

If the [NX](https://en.wikipedia.org/wiki/NX_bit) bit is supported we enable `_EFER_NX`  and write it too, with the `wrmsr` instruction. After the [NX](https://en.wikipedia.org/wiki/NX_bit) bit is set, we set some bits in the `cr0` [control register](https://en.wikipedia.org/wiki/Control_register), namely:

* `X86_CR0_PE` - system is in protected mode;
* `X86_CR0_MP` - controls interaction of WAIT/FWAIT instructions with TS flag in CR0;
* `X86_CR0_ET` - on the 386, it allowed to specify whether the external math coprocessor was an 80287 or 80387;
* `X86_CR0_NE` - enable internal x87 floating point error reporting when set, else enables PC style x87 error detection;
* `X86_CR0_WP` - when set, the CPU can't write to read-only pages when privilege level is 0;
* `X86_CR0_AM` - alignment check enabled if AM set, AC flag (in EFLAGS register) set, and privilege level is 3;
* `X86_CR0_PG` - enable paging.

by the execution following assembly code:

```assembly
#define CR0_STATE	(X86_CR0_PE | X86_CR0_MP | X86_CR0_ET | \
			 X86_CR0_NE | X86_CR0_WP | X86_CR0_AM | \
			 X86_CR0_PG)
movl	$CR0_STATE, %eax
movq	%rax, %cr0
```

We already know that to run any code, and even more [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) code from assembly, we need to setup a stack. As always, we are doing it by the setting of [stack pointer](https://en.wikipedia.org/wiki/Stack_register) to a correct place in memory and resetting [flags](https://en.wikipedia.org/wiki/FLAGS_register) register after this:

```assembly
movq initial_stack(%rip), %rsp
pushq $0
popfq
```

The most interesting thing here is the `initial_stack`. This symbol is defined in the [source](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head_64.S) code file and looks like:

```assembly
GLOBAL(initial_stack)
    .quad  init_thread_union+THREAD_SIZE-8
```

The `GLOBAL` is already familiar to us from. It defined in the [arch/x86/include/asm/linkage.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/linkage.h) header file expands to the `global` symbol definition:

```C
#define GLOBAL(name)    \
         .globl name;           \
         name:
```

The `THREAD_SIZE` macro is defined in the [arch/x86/include/asm/page_64_types.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/page_64_types.h) header file and depends on value of the `KASAN_STACK_ORDER` macro:

```C
#define THREAD_SIZE_ORDER       (2 + KASAN_STACK_ORDER)
#define THREAD_SIZE  (PAGE_SIZE << THREAD_SIZE_ORDER)
```

We consider when the [kasan](http://lxr.free-electrons.com/source/Documentation/kasan.txt) is disabled and the `PAGE_SIZE` is `4096` bytes. So the `THREAD_SIZE` will expands to `16` kilobytes and represents size of the stack of a thread. Why is `thread`? You may already know that each [process](https://en.wikipedia.org/wiki/Process_%28computing%29) may have parent [processes](https://en.wikipedia.org/wiki/Parent_process) and [child](https://en.wikipedia.org/wiki/Child_process) processes. Actually, a parent process and child process differ in stack. A new kernel stack is allocated for a new process. In the Linux kernel this stack is represented by the [union](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B) with the `thread_info` structure.

And as we can see the `init_thread_union` is represented by the `thread_union` [union](https://en.wikipedia.org/wiki/Union_type#C.2FC.2B.2B). Earlier this union looked like:

```C
union thread_union {
         struct thread_info thread_info;
         unsigned long stack[THREAD_SIZE/sizeof(long)];
};
```

but from the Linux kernel `4.9-rc1` release, `thread_info` was moved to the `task_struct` structure which represents a thread. So, for now `thread_union` looks like:

```C
union thread_union {
#ifndef CONFIG_THREAD_INFO_IN_TASK
	struct thread_info thread_info;
#endif
	unsigned long stack[THREAD_SIZE/sizeof(long)];
};
```

where the `CONFIG_THREAD_INFO_IN_TASK` kernel configuration option is enabled for `x86_64` architecture. So, as we consider only `x86_64` architecture in this book, an instance of `thread_union` will contain only stack and `thread_info` structure will be placed in the `task_struct`.

The `init_thread_union` looks like:

```
union thread_union init_thread_union __init_task_data = {
#ifndef CONFIG_THREAD_INFO_IN_TASK
	INIT_THREAD_INFO(init_task)
#endif
};
```

which represents just thread stack. Now we may understand this expression:

```assembly
GLOBAL(initial_stack)
    .quad  init_thread_union+THREAD_SIZE-8
```


that `initial_stack` symbol points to the start of the `thread_union.stack` array + `THREAD_SIZE` which is 16 killobytes and - 8 bytes. Here we need to subtract `8` bytes at the to of stack. This is necessary to guarantee illegal access of the next page memory.

After the early boot stack is set, to update the [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table) with the `lgdt` instruction:

```assembly
lgdt	early_gdt_descr(%rip)
```

where the `early_gdt_descr` is defined as:

```assembly
early_gdt_descr:
	.word	GDT_ENTRIES*8-1
early_gdt_descr_base:
	.quad	INIT_PER_CPU_VAR(gdt_page)
```

We need to reload `Global Descriptor Table` because now kernel works in the low userspace addresses, but soon kernel will work in its own space. Now let's look at the definition of `early_gdt_descr`. Global Descriptor Table contains `32` entries:

```C
#define GDT_ENTRIES 32
```

for kernel code, data, thread local storage segments and etc... it's simple. Now let's look at the definition of the `early_gdt_descr_base`.

First of `gdt_page` defined as:

```C
struct gdt_page {
	struct desc_struct gdt[GDT_ENTRIES];
} __attribute__((aligned(PAGE_SIZE)));
```

in the [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/desc.h). It contains one field `gdt` which is array of the `desc_struct` structure which is defined as:

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

and presents familiar to us `GDT` descriptor. Also we can note that `gdt_page` structure aligned to `PAGE_SIZE` which is `4096` bytes. It means that `gdt` will occupy one page. Now let's try to understand what is `INIT_PER_CPU_VAR`. `INIT_PER_CPU_VAR` is a macro which defined in the [arch/x86/include/asm/percpu.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/percpu.h) and just concats `init_per_cpu__` with the given parameter:

```C
#define INIT_PER_CPU_VAR(var) init_per_cpu__##var
```

After the `INIT_PER_CPU_VAR` macro will be expanded, we will have `init_per_cpu__gdt_page`. We can see in the [linker script](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S):

```
#define INIT_PER_CPU(x) init_per_cpu__##x = x + __per_cpu_load
INIT_PER_CPU(gdt_page);
```

As we got `init_per_cpu__gdt_page` in `INIT_PER_CPU_VAR` and `INIT_PER_CPU` macro from linker script will be expanded we will get offset from the `__per_cpu_load`. After this calculations, we will have correct base address of the new GDT.

Generally per-CPU variables is a 2.6 kernel feature. You can understand what it is from its name. When we create `per-CPU` variable, each CPU will have will have its own copy of this variable. Here we creating `gdt_page` per-CPU variable. There are many advantages for variables of this type, like there are no locks, because each CPU works with its own copy of variable and etc... So every core on multiprocessor will have its own `GDT` table and every entry in the table will represent a memory segment which can be accessed from the thread which ran on the core. You can read in details about `per-CPU` variables in the [Theory/per-cpu](https://proninyaroslav.gitbooks.io/linux-insides-ru/content/Concepts/per-cpu.html) post.

As we loaded new Global Descriptor Table, we reload segments as we did it every time:

```assembly
	xorl %eax,%eax
	movl %eax,%ds
	movl %eax,%ss
	movl %eax,%es
	movl %eax,%fs
	movl %eax,%gs
```

After all of these steps we set up `gs` register that it post to the `irqstack` which represents special stack where [interrupts](https://en.wikipedia.org/wiki/Interrupt) will be handled on:

```assembly
	movl	$MSR_GS_BASE,%ecx
	movl	initial_gs(%rip),%eax
	movl	initial_gs+4(%rip),%edx
	wrmsr
```

where `MSR_GS_BASE` is:

```C
#define MSR_GS_BASE             0xc0000101
```

We need to put `MSR_GS_BASE` to the `ecx` register and load data from the `eax` and `edx` (which are point to the `initial_gs`) with `wrmsr` instruction. We don't use `cs`, `fs`, `ds` and `ss` segment registers for addressing in the 64-bit mode, but `fs` and `gs` registers can be used. `fs` and `gs` have a hidden part (as we saw it in the real mode for `cs`) and this part contains descriptor which mapped to [Model Specific Registers](https://en.wikipedia.org/wiki/Model-specific_register). So we can see above `0xc0000101` is a `gs.base` MSR address. When a [system call](https://en.wikipedia.org/wiki/System_call) or [interrupt](https://en.wikipedia.org/wiki/Interrupt) occurred, there is no kernel stack at the entry point, so the value of the `MSR_GS_BASE` will store address of the interrupt stack.

In the next step we put the address of the real mode bootparam structure to the `rdi` (remember `rsi` holds pointer to this structure from the start) and jump to the C code with:

```assembly
	movq	initial_code(%rip), %rax
	pushq	$__KERNEL_CS	# set correct cs
	pushq	%rax		# target address in negative space
	lretq
```

Here we put the address of the `initial_code` to the `rax` and push fake address, `__KERNEL_CS` and the address of the `initial_code` to the stack. After this we can see `lretq` instruction which means that after it return address will be extracted from stack (now there is address of the `initial_code`) and jump there. `initial_code` is defined in the same source code file and looks:

```assembly
	.balign	8
	GLOBAL(initial_code)
	.quad	x86_64_start_kernel
	...
	...
	...
```

As we can see `initial_code` contains address of the `x86_64_start_kernel`, which is defined in the [arch/x86/kerne/head64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/head64.c) and looks like this:

```C
asmlinkage __visible void __init x86_64_start_kernel(char * real_mode_data) {
	...
	...
	...
}
```

It has one argument is a `real_mode_data` (remember that we passed address of the real mode data to the `rdi` register previously).

This is first C code in the kernel!

Next to start_kernel
--------------------------------------------------------------------------------

We need to see last preparations before we can see "kernel entry point" - start_kernel function from the [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c#L489).

First of all we can see some checks in the `x86_64_start_kernel` function:

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

There are checks for different things like virtual addresses of modules space is not fewer than base address of the kernel text - `__STAT_KERNEL_map`, that kernel text with modules is not less than image of the kernel and etc... `BUILD_BUG_ON` is a macro which looks as:

```C
#define BUILD_BUG_ON(condition) ((void)sizeof(char[1 - 2*!!(condition)]))
```

Let's try to understand how this trick works. Let's take for example first condition: `MODULES_VADDR < __START_KERNEL_map`. `!!conditions` is the same that `condition != 0`. So it means if `MODULES_VADDR < __START_KERNEL_map` is true, we will get `1` in the `!!(condition)` or zero if not. After `2*!!(condition)` we will get or `2` or `0`. In the end of calculations we can get two different behaviors:

* We will have compilation error, because try to get size of the char array with negative index (as can be in our case, because `MODULES_VADDR` can't be less than `__START_KERNEL_map` will be in our case);
* No compilation errors.

That's all. So interesting C trick for getting compile error which depends on some constants.

In the next step we can see call of the `cr4_init_shadow` function which stores shadow copy of the `cr4` per cpu. Context switches can change bits in the `cr4` so we need to store `cr4` for each CPU. And after this we can see call of the `reset_early_page_tables` function where we resets all page global directory entries and write new pointer to the PGT in `cr3`:

```C
for (i = 0; i < PTRS_PER_PGD-1; i++)
	early_level4_pgt[i].pgd = 0;

next_early_pgt = 0;

write_cr3(__pa_nodebug(early_level4_pgt));
```

Soon we will build new page tables. Here we can see that we go through all Page Global Directory Entries (`PTRS_PER_PGD` is `512`) in the loop and make it zero. After this we set `next_early_pgt` to zero (we will see details about it in the next post) and write physical address of the `early_level4_pgt` to the `cr3`. `__pa_nodebug` is a macro which will be expanded to:

```C
((unsigned long)(x) - __START_KERNEL_map + phys_base)
```

After this we clear `_bss` from the `__bss_stop` to `__bss_start` and the next step will be setup of the early `IDT` handlers, but it's big concept so we will see it in the next part.

Conclusion
--------------------------------------------------------------------------------

This is the end of the first part about linux kernel initialization.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

In the next part we will see initialization of the early interruption handlers, kernel space memory mapping and a lot more.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Model Specific Register](http://en.wikipedia.org/wiki/Model-specific_register)
* [Paging](https://proninyaroslav.gitbooks.io/linux-insides-ru/content/Theory/Paging.html)
* [Previous part - Kernel decompression](https://proninyaroslav.gitbooks.io/linux-insides-ru/content/Booting/linux-bootstrap-5.html)
* [NX](http://en.wikipedia.org/wiki/NX_bit)
* [ASLR](http://en.wikipedia.org/wiki/Address_space_layout_randomization)
