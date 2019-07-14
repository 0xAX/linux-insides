Инициализация ядра. Часть 4.
================================================================================

Точка входа в ядро
================================================================================

Если вы читали предыдущую часть - [Последние приготовления перед точкой входа в ядро](linux-initialization-3.md), вы можете помнить, что мы завершили все действия по предварительной инициализации и остановились прямо перед вызовом функции `start_kernel` из [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c). `start_kernel` это точка входа общего и независимого от архитектуры кода ядра, хотя мы будем возвращаться в папку `arch/` много раз. Если вы заглянете внутрь функции `start_kernel`, то увидите, что эта функция очень большая. На данный момент она содержит около 86 вызовов функций. Да, она очень большая и, конечно, эта часть не будет охватывать все процессы, которые происходят в этой функции. В текущей части мы только начнем это делать. Эта часть и все последующие, которые будут описаны в главе [Процесс инициализации ядра](README.md), охватят её.


Основная цель `start_kernel` - завершить процесс инициализации ядра и запустить первый процесс `init`. Перед запуском первого процесса `start_kernel` должен сделать много вещей, такие как: включить [блокировщик валидатора](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt), инициализировать идентификатор процессора, включить начальную подсистему [cgroups](http://en.wikipedia.org/wiki/Cgroups), настроить области для каждого CPU, инициализировать различные кэши в [vfs](http://en.wikipedia.org/wiki/Virtual_file_system), инициализировать менеджер памяти, rcu, vmalloc, планировщик, IRQ, ACPI и многое другое. Только после этих шагов мы увидим запуск первого процесса `init` в последней части этой главы. Так много кода ядра ждет нас, давайте начнем.

**ПРИМЕЧАНИЕ: Все части этой большой главы `Процесс инициализации ядра Linux` не будут касаться отладки. Для этого будет отдельная глава.**

Немного об атрибутах функции
---------------------------------------------------------------------------------

Как я писал выше, функция `start_kernel` определена в [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c). Эта функция определена с атрибутом `__init` и, как вы уже знаете из других частей, все функции, которые определены с этим атрибутом, необходимы во время инициализации ядра.

```C
#define __init      __section(.init.text) __cold notrace
```

После завершения процесса инициализации, ядро осободит эти секции вызовом функции `free_initmem`. Также обратите внимание, что `__init` определена двумя атрибутами:` __cold` и `notrace`. Цель первого атрибута - отметить, что функция используется редко, и компилятор должен оптимизировать размер этой функции. Второй атрибут определён следующий образом:

```C
#define notrace __attribute__((no_instrument_function))
```

где `no_instrument_function` говорит компилятору не генерировать вызовы функции профилирования.

В определении функции `start_kernel` вы также можете увидеть атрибут `__visible`, который раскрывается в следующее выражение:

```
#define __visible __attribute__((externally_visible))
```

где `externally_visible` сообщает компилятору, что кто-то использует эту функцию или переменную, чтобы предотвратить маркировку этой функции/переменной как `unusable`. Вы можете найти определение этого и других макро-атрибутов в [include/linux/init.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/init.h).

Первые шаги в start_kernel
--------------------------------------------------------------------------------

В начале `start_kernel` вы можете увидеть определение этих двух переменных:

```C
char *command_line;
char *after_dashes;
```

Первая представляет собой указатель на командную строку ядра, а вторая будет содержать результат функции `parse_args`, которая анализирует входную строку с параметрами в форме `name = value`, ищет конкретные ключевые слова и вызывает верные обработчики. Мы не будем сейчас вдаваться в детали, связанные с этими двумя переменными, но увидим это в следующих частях. На следующем шаге мы видим вызов функции `set_task_stack_end_magic`. Эта функция берет адрес `init_task` и устанавливает для нее `STACK_END_MAGIC` (`0x57AC6E9D`). `init_task` представляет собой начальную структуру задачи:

```C
struct task_struct init_task = INIT_TASK(init_task);
```

где `task_struct` хранит всю информацию о процессе. Я не буду объяснять эту структуру в данной книге, потому что она очень большая. Вы можете найти её определение в [include/linux/sched.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/sched.h#L1278). На данный момент `task_struct` содержит более 100 полей! Хотя вы не увидите объяснения `task_struct` в этой книге, мы будем использовать её очень часто, поскольку это фундаментальная структура, которая описывает `процесс` в ядре Linux. Я буду описывать значение полей этой структуры по мере того как мы будем встречать их на практике.

Вы можете видеть определение `init_task` и она инициализирована макросом `INIT_TASK`. Этот макрос взят из [include/linux/init_task.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/init_task.h) и просто заполняет `init_task` значениями для первого процесса. Например, он устанавливает:

* начальное состояние процесса в ноль или `runnable`. Runnable процесс - это процесс, который ожидает запуска на CPU;
* начальные флаги процесса - `PF_KTHREAD`, что означает поток ядра;
* список выполняемых задач;
* адресное пространство процесса;
* начальный стек процесса в `&init_thread_info`, который является `init_thread_union.thread_info`, и `initthread_union` имеет тип `thread_union`, который содержит `thread_info` и стек процесса:

```C
union thread_union {
	struct thread_info thread_info;
    unsigned long stack[THREAD_SIZE/sizeof(long)];
};
```

Каждый процесс имеет свой собственный стек и он составляет 16 килобайт или 4 страницы в `x86_64`. Мы можем заметить, что он определён как массив `unsigned long`. Следующее поле `thread_union` - это структура `thread_info`, которая занимает 52 байта:

```C
struct thread_info {
        struct task_struct      *task;
        struct exec_domain      *exec_domain;
        __u32                   flags;
        __u32                   status;
        __u32                   cpu;
        int                     saved_preempt_count;
        mm_segment_t            addr_limit;
        struct restart_block    restart_block;
        void __user             *sysenter_return;
        unsigned int            sig_on_uaccess_error:1;
        unsigned int            uaccess_err:1;
};
```

`thread_info` содержит специфичную для архитектуры информацию о потоке. Мы знаем, что в `x86_64` стек уменьшается и в нашем случае `thread_union.thread_info` размещена в нижней части стека. Таким образом, стек процесса составляет 16 килобайт и `thread_info` находится внизу. Оставшийся размер потока будет составлять `16 килобайт - 62 байта = 16332 байта`. Обратите внимание, что `thread_union` представлен как [union](http://en.wikipedia.org/wiki/Union_type), а не как структура, это означает, что `thread_info` и стек совместно используют одно и то же пространство памяти.

Схематически это можно представить следующим образом:

```C
+-----------------------+
|                       |
|                       |
|         стек          |
|                       |
|_______________________|
|          |            |
|          |            |
|          |            |
|__________↓____________|             +--------------------+
|                       |             |                    |
|      thread_info      |<----------->|     task_struct    |
|                       |             |                    |
+-----------------------+             +--------------------+
```

http://www.quora.com/In-Linux-kernel-Why-thread_info-structure-and-the-kernel-stack-of-a-process-binds-in-union-construct

Таким образом, макрос `INIT_TASK` заполняет эти поля в `task_struct`, а также многие другие. Как я уже писал выше, я не буду описывать все поля и значения в макросе `INIT_TASK`, но скоро мы их увидим.

Теперь вернёмся к функции `set_task_stack_end_magic`. Эта функция определена в [kernel/fork.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/fork.c#L297) и устанавливает [стековый индикатор ("канарейка")](http://en.wikipedia.org/wiki/Stack_buffer_overflow) в стек процесса `init` для предотвращения его переполнения.

```C
void set_task_stack_end_magic(struct task_struct *tsk)
{
	unsigned long *stackend;
	stackend = end_of_stack(tsk);
	*stackend = STACK_END_MAGIC; /* для обнаружения переполнения */
}
```

Его реализация проста. `set_task_stack_end_magic` получает конец стека для заданной `task_struct` с помощью функции `end_of_stack`. Ранее (теперь для всех архитектур, кроме `x86_64`) стек был расположен в структуре `thread_info`. Таким образом, конец стека процессов зависит от параметра конфигурации `CONFIG_STACK_GROWSUP`. Как мы знаем, в `x86_64` стек растёт вниз. Таким образом, конец стека процесса будет следующим:

```C
(unsigned long *)(task_thread_info(p) + 1);
```

где `task_thread_info` просто возвращает стек, который мы заполнили с помощью мароса `INIT_TASK`:

```C
#define task_thread_info(task)  ((struct thread_info *)(task)->stack)
```

Начиная с релиза ядра Linux `v4.9-rc1` структура `thread_info` может содержать только флаги, а указатель стека находится в структуре `task_struct`, которая представляет поток в ядре Linux. Это зависит от параметра конфигурации ядра `CONFIG_THREAD_INFO_IN_TASK`, который по умолчанию включен для `x86_64`. Вы можете быть убедиться в этом, если загляните в файл конфигурации сборки [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c) :

```
config THREAD_INFO_IN_TASK
	bool
	help
	  Select this to move thread_info off the stack into task_struct.  To
	  make this work, an arch will need to remove all thread_info fields
	  except flags and fix any runtime bugs.

	  One subtle change that will be needed is to use try_get_task_stack()
	  and put_task_stack() in save_thread_stack_tsk() and get_wchan().
```

и в [arch/x86/Kconfig](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/Kconfig):

```
config X86
	def_bool y
        ...
        ...
        ...
        select THREAD_INFO_IN_TASK
        ...
        ...
        ...
```

Поэтому мы можем просто получить конец стека потока из заданной структуры `task_struct`:

```C
#ifdef CONFIG_THREAD_INFO_IN_TASK
static inline unsigned long *end_of_stack(const struct task_struct *task)
{
	return task->stack;
}
#endif
```

Когда мы получили конец стека `init` процесса, мы записываем туда `STACK_END_MAGIC`. После того, как `"канарейка"` установлена, мы можем проверить это следующим образом:

```C
if (*end_of_stack(task) != STACK_END_MAGIC) {
        //
        //  здесь обрабатываем переполнение стека
	//
}
```

Следующая функция после `set_task_stack_end_magic` - `smp_setup_processor_id`. Эта функция имеет пустое тело для `x86_64`:

```C
void __init __weak smp_setup_processor_id(void)
{
}
```

так как она реализована только для некоторых архитектур, таких как [s390](http://en.wikipedia.org/wiki/IBM_ESA/390) и [arm64](http://en.wikipedia.org/wiki/ARM_architecture#64.2F32-bit_architecture).

Следующая функция в `start_kernel` - это `debug_objects_early_init`. Реализация данной функции почти такая же, как у `lockdep_init`, но в отличии от неё заполняет хеши для отладки объектов. Как я писал выше в этой главе мы не увидим объяснения этой и других функций, предназначенных для отладки.

После функции `debug_object_early_init` мы можем видеть вызов функции `boot_init_stack_canary`, которая заполняет `task_struct-> canary` значением `"канарейки"` для опции gcc `-fstack-protector`. Эта опция зависит от параметра конфигурации `CONFIG_CC_STACKPROTECTOR` и, если этот параметр отключён, функция `boot_init_stack_canary` ничего не делает, в противном случае она генерирует случайные числа на основе пула энтропии и [TSC](http://en.wikipedia.org/wiki/Time_Stamp_Counter):

```C
get_random_bytes(&canary, sizeof(canary));
tsc = __native_read_tsc();
canary += tsc + (tsc << 32UL);
```

После того как мы получили случайное число, мы заполняем поле `stack_canary` в` task_struct`:

```C
current->stack_canary = canary;
```

и запишите это значение в верхнюю часть стека IRQ:

```C
this_cpu_write(irq_stack_union.stack_canary, canary); // читайте ниже об this_cpu_write
```

Опять же, здесь мы не будем вдаваться в подробности, мы расскажем об этом в части о [IRQ](http://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29). Когда `"канарейка"` установлена, мы отключаем локальные и начальные загрузочные IRQ и регистрируем загрузочный CPU в картах CPU. Мы отключаем локальные IRQ (прерывания для текущего процессора) с помощью макроса `local_irq_disable`, который раскрывается в вызов функции `arch_local_irq_disable` из [include/linux/percpu-defs.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/percpu-defs.h):

```C
static inline notrace void arch_local_irq_disable(void)
{
        native_irq_disable();
}
```

Где `native_irq_disable` - это инструкция `cli` для `x86_64`. Поскольку прерывания отключены, мы можем зарегистрировать текущий CPU с заданным идентификатором в битовой карте CPU.

Первая активация процессора
---------------------------------------------------------------------------------

The current function from the `start_kernel` is `boot_cpu_init`. This function initializes various CPU masks for the bootstrap processor. First of all it gets the bootstrap processor id with a call to:

```C
int cpu = smp_processor_id();
```

For now it is just zero. If the `CONFIG_DEBUG_PREEMPT` configuration option is disabled, `smp_processor_id` just expands to the call of `raw_smp_processor_id` which expands to the:

```C
#define raw_smp_processor_id() (this_cpu_read(cpu_number))
```

`this_cpu_read` as many other function like this (`this_cpu_write`, `this_cpu_add` and etc...) defined in the [include/linux/percpu-defs.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/percpu-defs.h) and presents `this_cpu` operation. These operations provide a way of optimizing access to the [per-cpu](http://0xax.gitbooks.io/linux-insides/content/Concepts/linux-cpu-1.html) variables which are associated with the current processor. In our case it is `this_cpu_read`:

```
__pcpu_size_call_return(this_cpu_read_, pcp)
```

Remember that we have passed `cpu_number` as `pcp` to the `this_cpu_read` from the `raw_smp_processor_id`. Now let's look at the `__pcpu_size_call_return` implementation:

```C
#define __pcpu_size_call_return(stem, variable)                         \
({                                                                      \
        typeof(variable) pscr_ret__;                                    \
        __verify_pcpu_ptr(&(variable));                                 \
        switch(sizeof(variable)) {                                      \
        case 1: pscr_ret__ = stem##1(variable); break;                  \
        case 2: pscr_ret__ = stem##2(variable); break;                  \
        case 4: pscr_ret__ = stem##4(variable); break;                  \
        case 8: pscr_ret__ = stem##8(variable); break;                  \
        default:                                                        \
                __bad_size_call_parameter(); break;                     \
        }                                                               \
        pscr_ret__;                                                     \
})
```

Yes, it looks a little strange but it's easy. First of all we can see the definition of the `pscr_ret__` variable with the `int` type. Why int? Ok, `variable` is `common_cpu` and it was declared as per-cpu int variable:

```C
DECLARE_PER_CPU_READ_MOSTLY(int, cpu_number);
```

In the next step we call `__verify_pcpu_ptr` with the address of `cpu_number`. `__veryf_pcpu_ptr` used to verify that the given parameter is a per-cpu pointer. After that we set `pscr_ret__` value which depends on the size of the variable. Our `common_cpu` variable is `int`, so it 4 bytes in size. It means that we will get `this_cpu_read_4(common_cpu)` in `pscr_ret__`. In the end of the `__pcpu_size_call_return` we just call it. `this_cpu_read_4` is a macro:

```C
#define this_cpu_read_4(pcp)       percpu_from_op("mov", pcp)
```

which calls `percpu_from_op` and pass `mov` instruction and per-cpu variable there. `percpu_from_op` will expand to the inline assembly call:

```C
asm("movl %%gs:%1,%0" : "=r" (pfo_ret__) : "m" (common_cpu))
```

Let's try to understand how it works and what it does. The `gs` segment register contains the base of per-cpu area. Here we just copy `common_cpu` which is in memory to the `pfo_ret__` with the `movl` instruction. Or with another words:

```C
this_cpu_read(common_cpu)
```

is the same as:

```C
movl %gs:$common_cpu, $pfo_ret__
```

As we didn't setup per-cpu area, we have only one - for the current running CPU, we will get `zero` as a result of the `smp_processor_id`.

As we got the current processor id, `boot_cpu_init` sets the given CPU online, active, present and possible with the:

```C
set_cpu_online(cpu, true);
set_cpu_active(cpu, true);
set_cpu_present(cpu, true);
set_cpu_possible(cpu, true);
```

All of these functions use the concept - `cpumask`. `cpu_possible` is a set of CPU ID's which can be plugged in at any time during the life of that system boot. `cpu_present` represents which CPUs are currently plugged in. `cpu_online` represents subset of the `cpu_present` and indicates CPUs which are available for scheduling. These masks depend on the `CONFIG_HOTPLUG_CPU` configuration option and if this option is disabled `possible == present` and `active == online`. Implementation of the all of these functions are very similar. Every function checks the second parameter. If it is `true`, it calls `cpumask_set_cpu` or `cpumask_clear_cpu` otherwise.

For example let's look at `set_cpu_possible`. As we passed `true` as the second parameter, the:

```C
cpumask_set_cpu(cpu, to_cpumask(cpu_possible_bits));
```

will be called. First of all let's try to understand the `to_cpumask` macro. This macro casts a bitmap to a `struct cpumask *`. CPU masks provide a bitmap suitable for representing the set of CPU's in a system, one bit position per CPU number. CPU mask presented by the `cpumask` structure:

```C
typedef struct cpumask { DECLARE_BITMAP(bits, NR_CPUS); } cpumask_t;
```

which is just bitmap declared with the `DECLARE_BITMAP` macro:

```C
#define DECLARE_BITMAP(name, bits) unsigned long name[BITS_TO_LONGS(bits)]
```

As we can see from its definition, the `DECLARE_BITMAP` macro expands to the array of `unsigned long`. Now let's look at how the `to_cpumask` macro is implemented:

```C
#define to_cpumask(bitmap)                                              \
        ((struct cpumask *)(1 ? (bitmap)                                \
                            : (void *)sizeof(__check_is_bitmap(bitmap))))
```

I don't know about you, but it looked really weird for me at the first time. We can see a ternary operator here which is `true` every time, but why the `__check_is_bitmap` here? It's simple, let's look at it:

```C
static inline int __check_is_bitmap(const unsigned long *bitmap)
{
        return 1;
}
```

Yeah, it just returns `1` every time. Actually we need in it here only for one purpose: at compile time it checks that the given `bitmap` is a bitmap, or in other words it checks that the given `bitmap` has a type of `unsigned long *`. So we just pass `cpu_possible_bits` to the `to_cpumask` macro for converting the array of `unsigned long` to the `struct cpumask *`. Now we can call `cpumask_set_cpu` function with the `cpu` - 0 and `struct cpumask *cpu_possible_bits`. This function makes only one call of the `set_bit` function which sets the given `cpu` in the cpumask. All of these `set_cpu_*` functions work on the same principle.

If you're not sure that this `set_cpu_*` operations and `cpumask` are not clear for you, don't worry about it. You can get more info by reading the special part about it - [cpumask](http://0xax.gitbooks.io/linux-insides/content/Concepts/linux-cpu-2.html) or [documentation](https://www.kernel.org/doc/Documentation/cpu-hotplug.txt).

As we activated the bootstrap processor, it's time to go to the next function in the `start_kernel.` Now it is `page_address_init`, but this function does nothing in our case, because it executes only when all `RAM` can't be mapped directly.

Print linux banner
---------------------------------------------------------------------------------

The next call is `pr_notice`:

```C
#define pr_notice(fmt, ...) \
    printk(KERN_NOTICE pr_fmt(fmt), ##__VA_ARGS__)
```

as you can see it just expands to the `printk` call. At this moment we use `pr_notice` to print the Linux banner:

```C
pr_notice("%s", linux_banner);
```

which is just the kernel version with some additional parameters:

```
Linux version 4.0.0-rc6+ (alex@localhost) (gcc version 4.9.1 (Ubuntu 4.9.1-16ubuntu6) ) #319 SMP
```

Architecture-dependent parts of initialization
---------------------------------------------------------------------------------

The next step is architecture-specific initialization. The Linux kernel does it with the call of the `setup_arch` function. This is a very big function like `start_kernel` and we do not have time to consider all of its implementation in this part. Here we'll only start to do it and continue in the next part. As it is `architecture-specific`, we need to go again to the `arch/` directory. The `setup_arch` function defined in the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/setup.c) source code file and takes only one argument - address of the kernel command line.

This function starts from the reserving memory block for the kernel `_text` and `_data` which starts from the `_text` symbol (you can remember it from the [arch/x86/kernel/head_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/head_64.S#L46)) and ends before `__bss_stop`. We are using `memblock` for the reserving of memory block:

```C
memblock_reserve(__pa_symbol(_text), (unsigned long)__bss_stop - (unsigned long)_text);
```

You can read about `memblock` in the [Linux kernel memory management Part 1.](http://0xax.gitbooks.io/linux-insides/content/MM/linux-mm-1.html). As you can remember `memblock_reserve` function takes two parameters:

* base physical address of a memory block;
* size of a memory block.

We can get the base physical address of the `_text` symbol with the `__pa_symbol` macro:

```C
#define __pa_symbol(x) \
	__phys_addr_symbol(__phys_reloc_hide((unsigned long)(x)))
```

First of all it calls `__phys_reloc_hide` macro on the given parameter. The `__phys_reloc_hide` macro does nothing for `x86_64` and just returns the given parameter. Implementation of the `__phys_addr_symbol` macro is easy. It just subtracts the symbol address from the base address of the kernel text mapping base virtual address (you can remember that it is `__START_KERNEL_map`) and adds `phys_base` which is the base address of `_text`:

```C
#define __phys_addr_symbol(x) \
 ((unsigned long)(x) - __START_KERNEL_map + phys_base)
```

After we got the physical address of the `_text` symbol, `memblock_reserve` can reserve a memory block from the `_text` to the `__bss_stop - _text`.

Reserve memory for initrd
---------------------------------------------------------------------------------

In the next step after we reserved place for the kernel text and data is reserving place for the [initrd](http://en.wikipedia.org/wiki/Initrd). We will not see details about `initrd` in this post, you just may know that it is temporary root file system stored in memory and used by the kernel during its startup. The `early_reserve_initrd` function does all work. First of all this function gets the base address of the ram disk, its size and the end address with:

```C
u64 ramdisk_image = get_ramdisk_image();
u64 ramdisk_size  = get_ramdisk_size();
u64 ramdisk_end   = PAGE_ALIGN(ramdisk_image + ramdisk_size);
```

All of these parameters are taken from `boot_params`. If you have read the chapter about [Linux Kernel Booting Process](https://proninyaroslav.gitbooks.io/linux-insides-ru/content/Booting/index.html), you must remember that we filled the `boot_params` structure during boot time. The kernel setup header contains a couple of fields which describes ramdisk, for example:

```
Field name:	ramdisk_image
Type:		write (obligatory)
Offset/size:	0x218/4
Protocol:	2.00+

  The 32-bit linear address of the initial ramdisk or ramfs.  Leave at
  zero if there is no initial ramdisk/ramfs.
```

So we can get all the information that interests us from `boot_params`. For example let's look at `get_ramdisk_image`:

```C
static u64 __init get_ramdisk_image(void)
{
        u64 ramdisk_image = boot_params.hdr.ramdisk_image;

        ramdisk_image |= (u64)boot_params.ext_ramdisk_image << 32;

        return ramdisk_image;
}
```

Here we get the address of the ramdisk from the `boot_params` and shift left it on `32`. We need to do it because as you can read in the [Documentation/x86/zero-page.txt](https://github.com/0xAX/linux/blob/master/Documentation/x86/zero-page.txt):

```
0C0/004	ALL	ext_ramdisk_image ramdisk_image high 32bits
```

So after shifting it on 32, we're getting a 64-bit address in `ramdisk_image` and we return it. `get_ramdisk_size` works on the same principle as `get_ramdisk_image`, but it used `ext_ramdisk_size` instead of `ext_ramdisk_image`. After we got ramdisk's size, base address and end address, we check that bootloader provided ramdisk with the:

```C
if (!boot_params.hdr.type_of_loader ||
    !ramdisk_image || !ramdisk_size)
	return;
```

and reserve memory block with the calculated addresses for the initial ramdisk in the end:

```C
memblock_reserve(ramdisk_image, ramdisk_end - ramdisk_image);
```

Conclusion
---------------------------------------------------------------------------------

It is the end of the fourth part about the Linux kernel initialization process. We started to dive in the kernel generic code from the `start_kernel` function in this part and stopped on the architecture-specific initialization in the `setup_arch`. In the next part we will continue with architecture-dependent initialization steps.

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me a PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [GCC function attributes](https://gcc.gnu.org/onlinedocs/gcc/Function-Attributes.html)
* [this_cpu operations](https://www.kernel.org/doc/Documentation/this_cpu_ops.txt)
* [cpumask](http://www.crashcourse.ca/wiki/index.php/Cpumask)
* [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt)
* [cgroups](http://en.wikipedia.org/wiki/Cgroups)
* [stack buffer overflow](http://en.wikipedia.org/wiki/Stack_buffer_overflow)
* [IRQs](http://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29)
* [initrd](http://en.wikipedia.org/wiki/Initrd)
* [Previous part](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-3.md)
