Kernel initialization. Part 2.
================================================================================

Начальная обработка прерываний и исключений
--------------------------------------------------------------------------------

В предыдущей [части](linux-initialization-1.md) мы остановились перед настройкой начальных обработчиков прерываний. На данный момент мы находимся в распакованном ядре Linux, у нас есть базовая структура [подкачки](https://en.wikipedia.org/wiki/Page_table) для начальной загрузки, и наша текущая цель - завершить начальную подготовку до того, как основной код ядра начнёт свою работу.

Мы уже начали эту подготовку в предыдущей [первой](linux-initialization-1.md) части этой [главы](README.md). Мы продолжим в этой части и узнаем больше об обработке прерываний и исключений.

Как вы можете помнить, мы остановились перед этим циклом:

```C
for (i = 0; i < NUM_EXCEPTION_VECTORS; i++)
	set_intr_gate(i, early_idt_handler_array[i]);
```

из файла [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head64.c). Но прежде чем начать разбирать этот код, нам нужно знать о прерываниях и обработчиках.

Некоторая теория
--------------------------------------------------------------------------------

Прерывание - это событие, вызванное программным или аппаратным обеспечением в CPU. Например, пользователь нажал клавишу на клавиатуре. Во время прерывания, CPU останавливает текущую задачу и передаёт управление специальной процедуре - [обработчику прерываний](https://en.wikipedia.org/wiki/Interrupt_handler). Обработчик прерываний обрабатывает прерывания и передаёт управление обратно к ранее остановленной задаче. Мы можем разделить прерывания на три типа:

* Программные прерывания - когда программное обеспечение сигнализирует CPU, что ему нужно обратиться к ядру. Эти прерывания обычно используются для системных вызовов;
* Аппаратные прерывания - когда происходит аппаратное событие, например нажатие кнопки на клавиатуре;
* Исключения - прерывания, генерируемые процессором, когда CPU обнаруживает ошибку, например деление на ноль или доступ к странице памяти, которая не находится в ОЗУ.

Каждому прерыванию и исключению присваивается уникальный номер - `номер вектора`. `Номер вектора` может быть любым числом от `0` до `255`. Существует обычная практика использовать первые `32` векторных номеров для исключений, а номера от `32` до `255` для пользовательских прерываний. Мы можем видеть это в коде выше - `NUM_EXCEPTION_VECTORS`, определённый как:

```C
#define NUM_EXCEPTION_VECTORS 32
```

CPU использует номер вектора как индекс в `таблице векторов прерываний` (мы рассмотрим её позже). Для перехвата прерываний CPU использует [APIC](http://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller). В следующей таблице показаны исключения `0-31`:

```
-------------------------------------------------------------------------------------------------------
|Вектор|Мнемоника|Описание              |Тип    |Код ошибки|Источник                                   |
-------------------------------------------------------------------------------------------------------
|0     | #DE     |Деление на ноль       |Ошибка |Нет       |DIV и IDIV                                 |
|------------------------------------------------------------------------------------------------------
|1     | #DB     |Зарезервировано       |О/Л    |Нет       |                                           |
|------------------------------------------------------------------------------------------------------
|2     | ---     |Немаск. прервания     |Прерыв.|Нет       |Внешние NMI                                |
|------------------------------------------------------------------------------------------------------
|3     | #BP     |Исключение отладки    |Ловушка|Нет       |INT 3                                      |
|------------------------------------------------------------------------------------------------------
|4     | #OF     |Переполнение          |Ловушка|Нет       |Иснтрукция INTO                            |
|------------------------------------------------------------------------------------------------------
|5     | #BR     |Вызод за границы      |Ошибка |Нет       |Инструкция BOUND                           |
|------------------------------------------------------------------------------------------------------
|6     | #UD     |Неверный опкод        |Ошибка |Нет       |Инструкция UD2                             |
|------------------------------------------------------------------------------------------------------
|7     | #NM     |Устройство недоступно |Ошибка |Нет       |Плавающая точка или [F]WAIT                |
|------------------------------------------------------------------------------------------------------
|8     | #DF     |Двойная ошибка        |Авария |Да        |Инструкция, которую могут генерировать NMI |
|------------------------------------------------------------------------------------------------------
|9     | ---     |Зарезервировано       |Ошибка |Нет       |                                           |
|------------------------------------------------------------------------------------------------------
|10    | #TS     |Неверный TSS          |Ошибка |Да        |Смена задачи или доступ к TSS              |
|------------------------------------------------------------------------------------------------------
|11    | #NP     |Сегмент отсутствует   |Ошибка |Нет       |Доступ к регистру сегмента                 |
|------------------------------------------------------------------------------------------------------
|12    | #SS     |Ошибка сегмента стека |Ошибка |Да        |Операции со стеком                         |
|------------------------------------------------------------------------------------------------------
|13    | #GP     |Общее нарушение защиты|Ошибка |Да        |Ссылка на память                           |
|------------------------------------------------------------------------------------------------------
|14    | #PF     |Ошибка страницы       |Ошибка |Да        |Ссылка на память                           |
|------------------------------------------------------------------------------------------------------
|15    | ---     |Зарезервировано       |       |Нет       |                                           |
|------------------------------------------------------------------------------------------------------
|16    | #MF     |Ошибка x87 FPU        |Ошибка |Нет       |Плавающая точка или [F]WAIT                |
|------------------------------------------------------------------------------------------------------
|17    | #AC     |Проверка выравнивания |Ошибка |Да        |Ссылка на данные                           |
|------------------------------------------------------------------------------------------------------
|18    | #MC     |Проверка машины       |Авария |Нет       |                                           |
|------------------------------------------------------------------------------------------------------
|19    | #XM     |Исключение SIMD       |Ошибка |Нет       |Инструкции SSE[2,3]                        |
|------------------------------------------------------------------------------------------------------
|20    | #VE     |Искл. виртуализации   |Ошибка |Нет       |Гипервизор                                 |
|------------------------------------------------------------------------------------------------------
|21-31 | ---     |Зарезервировано       |Прерыв.|Нет       |Внешние прерывания                         |
-------------------------------------------------------------------------------------------------------
```

Исключения делятся на три типа:

* Ошибки (Faults) - исключения, по окончании обработки которых прерванная команда повторяется;
* Ловушки (Traps) - исключения, при обработке которых CPU сохраняет состояние, следующее за командой, вызвавшей исключение;
* Аварии (Aborts) - исключения, при обработке которых CPU не сохраняет состояния и не имеет возможности вернуться к месту
исключения

Для реагирования на прерывание CPU использует специальную структуру - таблицу векторов прерываний (Interrupt Descriptor Table, IDT). IDT является массивом 8-байтных дескрипторов, наподобие глобальной таблицы дескрипторов, но записи в IDT называются `шлюзами` (gates). CPU умножает номер вектора на 8 для того чтобы найти индекс записи IDT. Но в 64-битном режиме IDT представляет собой массив 16-байтных дескрипторов и CPU умножает номер вектора на 16. Из предыдущей части мы помним, что CPU использует специальный регистр `GDTR` для поиска глобальной таблицы дескрипторов, поэтому CPU использует специальный регистр `IDTR` для таблицы векторов прерываний и инструкцию `lidt` для загрузки базового адреса таблицы в этот регистр.

Запись IDT в 64-битном режиме имеет следующую структуру:

```
127                                                                             96
 --------------------------------------------------------------------------------
|                                                                               |
|                                Зарезервировано                                |
|                                                                               |
 --------------------------------------------------------------------------------
95                                                                              64
 --------------------------------------------------------------------------------
|                                                                               |
|                               Смещение 63..32                                 |
|                                                                               |
 --------------------------------------------------------------------------------
63                               48 47      46  44   42    39             34    32
 --------------------------------------------------------------------------------
|                                  |       |  D  |   |     |      |   |   |     |
|       Смещение 31..16            |   P   |  P  | 0 |Тип  |0 0 0 | 0 | 0 | IST |
|                                  |       |  L  |   |     |      |   |   |     |
 --------------------------------------------------------------------------------
31                                   16 15                                      0
 --------------------------------------------------------------------------------
|                                      |                                        |
|          Селектор сегмента           |                 Смещение 15..0         |
|                                      |                                        |
 --------------------------------------------------------------------------------
```

где:

* `Смещение` - смещение к точки входа обработчика прерывания;
* `DPL` - Уровень привилегий сегмента (Descriptor Privilege Level);
* `P` - флаг присутствия сегмента;
* `Селектор сегмента` - селектор сегмента кода в GDT или LDT
* `IST` - обеспечивает возможность переключения на новый стек для обработки прерываний.

И последнее поле `Тип` описывает тип записи `IDT`. Существует три различных типа обработчиков для прерываний:

* Дескриптор задачи
* Дескриптор прерывания
* Дескриптор ловушки

Дескрипторы прерываний и ловушек содержат дальний указатель на точку входа обработчика прерываний. Различие между этими типами заключается в том, как CPU обрабатывает флаг `IF`. Если обработчик прерываний был вызван через шлюз прерывания, CPU очищает флаг `IF` чтобы предотвратить другие прерывания, пока выполняется текущий обработчик прерываний. После выполнения текущего обработчика прерываний CPU снова устанавливает флаг `IF` с помощью инструкции `iret`.

Остальные биты в шлюзе прерывания зарезервированы и должны быть равны 0. Теперь давайте посмотрим, как CPU обрабатывает прерывания:

* CPU сохраняет регистр флагов, `CS`, и указатель на инструкцию в стеке.
* Если прерывание вызывает код ошибки (например, `#PF`), CPU сохраняет ошибку в стеке после указателя на инструкцию;
* После выполнения обработчика прерываний для возврата из него используется инструкция `iret`.

Теперь вернёмся к коду.

Заполнение и загрузка IDT
--------------------------------------------------------------------------------

We stopped at the following point:

```C
for (i = 0; i < NUM_EXCEPTION_VECTORS; i++)
	set_intr_gate(i, early_idt_handler_array[i]);
```

Here we call `set_intr_gate` in the loop, which takes two parameters:

* Number of an interrupt or `vector number`;
* Address of the idt handler.

and inserts an interrupt gate to the `IDT` table which is represented by the `&idt_descr` array. First of all let's look on the `early_idt_handler_array` array. It is an array which is defined in the [arch/x86/include/asm/segment.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/segment.h) header file contains addresses of the first `32` exception handlers:

```C
#define EARLY_IDT_HANDLER_SIZE   9
#define NUM_EXCEPTION_VECTORS	32

extern const char early_idt_handler_array[NUM_EXCEPTION_VECTORS][EARLY_IDT_HANDLER_SIZE];
```

The `early_idt_handler_array` is `288` bytes array which contains address of exception entry points every nine bytes. Every nine bytes of this array consist of two bytes optional instruction for pushing dummy error code if an exception does not provide it, two bytes instruction for pushing vector number to the stack and five bytes of `jump` to the common exception handler code.

As we can see, We're filling only first 32 `IDT` entries in the loop, because all of the early setup runs with interrupts disabled, so there is no need to set up interrupt handlers for vectors greater than `32`. The `early_idt_handler_array` array contains generic idt handlers and we can find its definition in the [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S) assembly file. For now we will skip it, but will look it soon. Before this we will look on the implementation of the `set_intr_gate` macro.

The `set_intr_gate` macro is defined in the [arch/x86/include/asm/desc.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/desc.h) header file and looks:

```C
#define set_intr_gate(n, addr)                         \
         do {                                                            \
                 BUG_ON((unsigned)n > 0xFF);                             \
                 _set_gate(n, GATE_INTERRUPT, (void *)addr, 0, 0,        \
                           __KERNEL_CS);                                 \
                 _trace_set_gate(n, GATE_INTERRUPT, (void *)trace_##addr,\
                                 0, 0, __KERNEL_CS);                     \
         } while (0)
```

First of all it checks with that passed interrupt number is not greater than `255` with `BUG_ON` macro. We need to do this check because we can have only `256` interrupts. After this, it make a call of the `_set_gate` function which writes address of an interrupt gate to the `IDT`:

```C
static inline void _set_gate(int gate, unsigned type, void *addr,
	                         unsigned dpl, unsigned ist, unsigned seg)
{
         gate_desc s;
         pack_gate(&s, type, (unsigned long)addr, dpl, ist, seg);
         write_idt_entry(idt_table, gate, &s);
         write_trace_idt_entry(gate, &s);
}
```

At the start of `_set_gate` function we can see call of the `pack_gate` function which fills `gate_desc` structure with the given values:

```C
static inline void pack_gate(gate_desc *gate, unsigned type, unsigned long func,
                             unsigned dpl, unsigned ist, unsigned seg)
{
        gate->offset_low        = PTR_LOW(func);
        gate->segment           = __KERNEL_CS;
        gate->ist               = ist;
        gate->p                 = 1;
        gate->dpl               = dpl;
        gate->zero0             = 0;
        gate->zero1             = 0;
        gate->type              = type;
        gate->offset_middle     = PTR_MIDDLE(func);
        gate->offset_high       = PTR_HIGH(func);
}
```

As I mentioned above, we fill gate descriptor in this function. We fill three parts of the address of the interrupt handler with the address which we got in the main loop (address of the interrupt handler entry point). We are using three following macros to split address on three parts:

```C
#define PTR_LOW(x) ((unsigned long long)(x) & 0xFFFF)
#define PTR_MIDDLE(x) (((unsigned long long)(x) >> 16) & 0xFFFF)
#define PTR_HIGH(x) ((unsigned long long)(x) >> 32)
```

With the first `PTR_LOW` macro we get the first `2` bytes of the address, with the second `PTR_MIDDLE` we get the second `2` bytes of the address and with the third `PTR_HIGH` macro we get the last `4` bytes of the address. Next we setup the segment selector for interrupt handler, it will be our kernel code segment - `__KERNEL_CS`. In the next step we fill `Interrupt Stack Table` and `Descriptor Privilege Level` (highest privilege level) with zeros. And we set `GAT_INTERRUPT` type in the end.

Now we have filled IDT entry and we can call `native_write_idt_entry` function which just copies filled `IDT` entry to the `IDT`:

```C
static inline void native_write_idt_entry(gate_desc *idt, int entry, const gate_desc *gate)
{
        memcpy(&idt[entry], gate, sizeof(*gate));
}
```

After that main loop will finished, we will have filled `idt_table` array of `gate_desc` structures and we can load `Interrupt Descriptor table` with the call of the:

```C
load_idt((const struct desc_ptr *)&idt_descr);
```

Where `idt_descr` is:

```C
struct desc_ptr idt_descr = { NR_VECTORS * 16 - 1, (unsigned long) idt_table };
```

and `load_idt` just executes `lidt` instruction:

```C
asm volatile("lidt %0"::"m" (*dtr));
```

You can note that there are calls of the `_trace_*` functions in the `_set_gate` and other functions. These functions fills `IDT` gates in the same manner that `_set_gate` but with one difference. These functions use `trace_idt_table` the `Interrupt Descriptor Table` instead of `idt_table` for tracepoints (we will cover this theme in the another part).

Okay, now we have filled and loaded `Interrupt Descriptor Table`, we know how the CPU acts during an interrupt. So now time to deal with interrupts handlers.

Early interrupts handlers
--------------------------------------------------------------------------------

As you can read above, we filled `IDT` with the address of the `early_idt_handler_array`. We can find it in the [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S) assembly file:

```assembly
	.globl early_idt_handler_array
early_idt_handlers:
	i = 0
	.rept NUM_EXCEPTION_VECTORS
	.if (EXCEPTION_ERRCODE_MASK >> i) & 1
	pushq $0
	.endif
	pushq $i
	jmp early_idt_handler_common
	i = i + 1
	.fill early_idt_handler_array + i*EARLY_IDT_HANDLER_SIZE - ., 1, 0xcc
	.endr
```

We can see here, interrupt handlers generation for the first `32` exceptions. We check here, if exception has an error code then we do nothing, if exception does not return error code, we push zero to the stack. We do it for that would stack was uniform. After that we push exception number on the stack and jump on the `early_idt_handler_array` which is generic interrupt handler for now. As we may see above, every nine bytes of the `early_idt_handler_array` array consists from optional push of an error code, push of `vector number` and jump instruction. We can see it in the output of the `objdump` util:

```
$ objdump -D vmlinux
...
...
...
ffffffff81fe5000 <early_idt_handler_array>:
ffffffff81fe5000:       6a 00                   pushq  $0x0
ffffffff81fe5002:       6a 00                   pushq  $0x0
ffffffff81fe5004:       e9 17 01 00 00          jmpq   ffffffff81fe5120 <early_idt_handler_common>
ffffffff81fe5009:       6a 00                   pushq  $0x0
ffffffff81fe500b:       6a 01                   pushq  $0x1
ffffffff81fe500d:       e9 0e 01 00 00          jmpq   ffffffff81fe5120 <early_idt_handler_common>
ffffffff81fe5012:       6a 00                   pushq  $0x0
ffffffff81fe5014:       6a 02                   pushq  $0x2
...
...
...
```

As i wrote above, CPU pushes flag register, `CS` and `RIP` on the stack. So before `early_idt_handler` will be executed, stack will contain following data:

```
|--------------------|
| %rflags            |
| %cs                |
| %rip               |
| rsp --> error code |
|--------------------|
```

Now let's look on the `early_idt_handler_common` implementation. It locates in the same [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S#L343) assembly file and first of all we can see check for [NMI](http://en.wikipedia.org/wiki/Non-maskable_interrupt). We don't need to handle it, so just ignore it in the `early_idt_handler_common`:

```assembly
	cmpl $2,(%rsp)
	je .Lis_nmi
```

where `is_nmi`:

```assembly
is_nmi:
	addq $16,%rsp
	INTERRUPT_RETURN
```

drops an error code and vector number from the stack and call `INTERRUPT_RETURN` which is just expands to the `iretq` instruction. As we checked the vector number and it is not `NMI`, we check `early_recursion_flag` to prevent recursion in the `early_idt_handler_common` and if it's correct we save general registers on the stack:

```assembly
	pushq %rax
	pushq %rcx
	pushq %rdx
	pushq %rsi
	pushq %rdi
	pushq %r8
	pushq %r9
	pushq %r10
	pushq %r11
```

We need to do it to prevent wrong values of registers when we return from the interrupt handler. After this we check segment selector in the stack:

```assembly
	cmpl $__KERNEL_CS,96(%rsp)
	jne 11f
```

which must be equal to the kernel code segment and if it is not we jump on label `11` which prints `PANIC` message and makes stack dump.

After the code segment was checked, we check the vector number, and if it is `#PF` or [Page Fault](https://en.wikipedia.org/wiki/Page_fault), we put value from the `cr2` to the `rdi` register and call `early_make_pgtable` (well see it soon):

```assembly
	cmpl $14,72(%rsp)
	jnz 10f
	GET_CR2_INTO(%rdi)
	call early_make_pgtable
	andl %eax,%eax
	jz 20f
```

If vector number is not `#PF`, we restore general purpose registers from the stack:

```assembly
	popq %r11
	popq %r10
	popq %r9
	popq %r8
	popq %rdi
	popq %rsi
	popq %rdx
	popq %rcx
	popq %rax
```

and exit from the handler with `iret`.

It is the end of the first interrupt handler. Note that it is very early interrupt handler, so it handles only Page Fault now. We will see handlers for the other interrupts, but now let's look on the page fault handler.

Page fault handling
--------------------------------------------------------------------------------

In the previous paragraph we saw first early interrupt handler which checks interrupt number for page fault and calls `early_make_pgtable` for building new page tables if it is. We need to have `#PF` handler in this step because there are plans to add ability to load kernel above `4G` and make access to `boot_params` structure above the 4G.

You can find implementation of the `early_make_pgtable` in the [arch/x86/kernel/head64.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head64.c) and takes one parameter - address from the `cr2` register, which caused Page Fault. Let's look on it:

```C
int __init early_make_pgtable(unsigned long address)
{
	unsigned long physaddr = address - __PAGE_OFFSET;
	unsigned long i;
	pgdval_t pgd, *pgd_p;
	pudval_t pud, *pud_p;
	pmdval_t pmd, *pmd_p;
	...
	...
	...
}
```

It starts from the definition of some variables which have `*val_t` types. All of these types are just:

```C
typedef unsigned long   pgdval_t;
```

Also we will operate with the `*_t` (not val) types, for example `pgd_t` and etc... All of these types defined in the [arch/x86/include/asm/pgtable_types.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/pgtable_types.h) and represent structures like this:

```C
typedef struct { pgdval_t pgd; } pgd_t;
```

For example,

```C
extern pgd_t early_level4_pgt[PTRS_PER_PGD];
```

Here `early_level4_pgt` presents early top-level page table directory which consists of an array of `pgd_t` types and `pgd` points to low-level page entries.

After we made the check that we have no invalid address, we're getting the address of the Page Global Directory entry which contains `#PF` address and put it's value to the `pgd` variable:

```C
pgd_p = &early_level4_pgt[pgd_index(address)].pgd;
pgd = *pgd_p;
```

In the next step we check `pgd`, if it contains correct page global directory entry we put physical address of the page global directory entry and put it to the `pud_p` with:

```C
pud_p = (pudval_t *)((pgd & PTE_PFN_MASK) + __START_KERNEL_map - phys_base);
```

where `PTE_PFN_MASK` is a macro:

```C
#define PTE_PFN_MASK            ((pteval_t)PHYSICAL_PAGE_MASK)
```

which expands to:

```C
(~(PAGE_SIZE-1)) & ((1 << 46) - 1)
```

or

```
0b1111111111111111111111111111111111111111111111
```

which is 46 bits to mask page frame.

If `pgd` does not contain correct address we check that `next_early_pgt` is not greater than `EARLY_DYNAMIC_PAGE_TABLES` which is `64` and present a fixed number of buffers to set up new page tables on demand. If `next_early_pgt` is greater than `EARLY_DYNAMIC_PAGE_TABLES` we reset page tables and start again. If `next_early_pgt` is less than `EARLY_DYNAMIC_PAGE_TABLES`, we create new page upper directory pointer which points to the current dynamic page table and writes it's physical address with the `_KERPG_TABLE` access rights to the page global directory:

```C
if (next_early_pgt >= EARLY_DYNAMIC_PAGE_TABLES) {
	reset_early_page_tables();
    goto again;
}

pud_p = (pudval_t *)early_dynamic_pgts[next_early_pgt++];
for (i = 0; i < PTRS_PER_PUD; i++)
	pud_p[i] = 0;
*pgd_p = (pgdval_t)pud_p - __START_KERNEL_map + phys_base + _KERNPG_TABLE;
```

After this we fix up address of the page upper directory with:

```C
pud_p += pud_index(address);
pud = *pud_p;
```

In the next step we do the same actions as we did before, but with the page middle directory. In the end we fix address of the page middle directory which contains maps kernel text+data virtual addresses:

```C
pmd = (physaddr & PMD_MASK) + early_pmd_flags;
pmd_p[pmd_index(address)] = pmd;
```

After page fault handler finished it's work and as result our `early_level4_pgt` contains entries which point to the valid addresses.

Conclusion
--------------------------------------------------------------------------------

This is the end of the second part about linux kernel insides. If you have questions or suggestions, ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new). In the next part we will see all steps before kernel entry point - `start_kernel` function.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [GNU assembly .rept](https://sourceware.org/binutils/docs-2.23/as/Rept.html)
* [APIC](http://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller)
* [NMI](http://en.wikipedia.org/wiki/Non-maskable_interrupt)
* [Page table](https://en.wikipedia.org/wiki/Page_table)
* [Interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler)
* [Page Fault](https://en.wikipedia.org/wiki/Page_fault),
* [Previous part](https://proninyaroslav.gitbooks.io/linux-insides-ru/content/Initialization/linux-initialization-1.html)
