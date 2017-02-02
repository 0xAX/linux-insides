Процесс загрузки ядра. Часть 3.
================================================================================

Инициализация видеорежима и переход в защищённый режим
--------------------------------------------------------------------------------

Это третья часть серии `Процесса загрузки ядра`. В предыдущей [части](linux-bootstrap-2.md#kernel-booting-process-part-2) мы остановились прямо перед вызовом функции `set_video` из [main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c#L181). В этой части мы увидим:

- Инициализацию видеорежима в коде настройки ядра,
- подготовка перед переключением в защищённый режим,
- переход в защищённый режим

**ПРИМЕЧАНИЕ** Если вы ничего не знаете о защищённом режиме, вы можете найти некоторую информацию о нём в предыдущей [части](linux-bootstrap-2.md#protected-mode). Также есть несколько [ссылок](linux-bootstrap-2.md#links), которые могут помочь вам.

Как я уже писал ранее, мы будем начинать с функции `set_video`, которая определена в [arch/x86/boot/video.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/video.c#L315). Как мы можем видеть, она начинает работу с получения видеорежима из структуры `boot_params.hdr`:

```C
u16 mode = boot_params.hdr.vid_mode;
```

которую мы заполнили в функции `copy_boot_params` (вы можете прочитать об этом в предыдущем посте). `vid_mode`является обязательным полем, которое заполняется загрузчиком. Вы можете найти информацию об этом в протоколе загрузки ядра:

```
Offset	Proto	Name		Meaning
/Size
01FA/2	ALL	    vid_mode	Video mode control
```

Как мы можем прочесть из протокола загрузки ядра Linux:

```
vga=<mode>
	<mode> here is either an integer (in C notation, either
	decimal, octal, or hexadecimal) or one of the strings
	"normal" (meaning 0xFFFF), "ext" (meaning 0xFFFE) or "ask"
	(meaning 0xFFFD).  This value should be entered into the
	vid_mode field, as it is used by the kernel before the command
	line is parsed.
```

Таким образом, мы можем добавить параметр `vga` в конфигурационный файл GRUB или любого другого загрузчика и он передаст его в командную строку ядра. Как говорится в описании, этот параметр может иметь разные значения. Например, это может быть целым числом `0xFFFD` или `ask`. Если передать `ask` в `vga`, вы увидите примерно такое меню:

![video mode setup menu](http://oi59.tinypic.com/ejcz81.jpg)

которое попросит выбрать видеорежим. Мы посмотрим на его реализацию, но перед этим рассмотрим некоторые другие вещи.

Типы данных ядра
--------------------------------------------------------------------------------

Ранее мы видели определения различных типов данных в коде настройки ядра, таких как `u16` и т.д. Давайте взглянем  на несколько типов данных, предоставляемых ядром:


|  Тип   | char | short | int | long | u8 | u16 | u32 | u64 |
|--------|------|-------|-----|------|----|-----|-----|-----|
| Размер |  1   |   2   |  4  |   8  |  1 |  2  |  4  |  8  |

Во время чтения исходного кода ядра вы будете часто встречать эти типы, так что было бы неплохо запомнить их.

API кучи
--------------------------------------------------------------------------------

После того как мы получим `vid_mode` из `boot_params.hdr` в функции `set_video`, мы можем видеть вызов `RESET_HEAP`. `RESET_HEAP` представляет собой макрос, определённый в [boot.h](https://github.com/torvalds/linux/blob/master/arch/x86/boot/boot.h#L199):

```C
#define RESET_HEAP() ((void *)( HEAP = _end ))
```

Если вы читали вторую часть, то помните, что мы инициализировали кучу с помощью функции [`init_heap`](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c#L116).  У нас есть несколько полезных функций для кучи, которые определены в `boot.h`:

```C
#define RESET_HEAP()
```

Как мы видели чуть выше, он сбрасывает кучу, установив переменную `HEAP` в `_end`, где `_end` просто `extern char _end[];`

Следующий макрос - `GET_HEAP`:

```C
#define GET_HEAP(type, n) \
	((type *)__get_heap(sizeof(type),__alignof__(type),(n)))
```

для выделения кучи. Он вызывает внутреннюю функцию `__get_heap` с тремя параметрами:

* размер типа в байтах, который должен быть выделен
* `__alignof__(type)` показывает, как переменные этого типа выровнены
* `n` говорит о том, сколько элементов нужно выделить

Реализация `__get_heap`:

```C
static inline char *__get_heap(size_t s, size_t a, size_t n)
{
	char *tmp;

	HEAP = (char *)(((size_t)HEAP+(a-1)) & ~(a-1));
	tmp = HEAP;
	HEAP += s*n;
	return tmp;
}
```

и в дальнейшем мы увидим её использование, что-то вроде:

```C
saved.data = GET_HEAP(u16, saved.x * saved.y);
```

Давайте попробуем понять принцип работы `__get_heap`. Мы видим, что `HEAP` (который равен `_end` после `RESET_HEAP()`) является адресом выровненной памяти в соответсвии с параметром `a`. После этого мы сохраняем адрес памяти `HEAP` в переменную `tmp`, перемещаем `HEAP` в конец выделенного блока и возвращаем `tmp`, который является начальным адресом выделенной памяти.

И последняя функция:

```C
static inline bool heap_free(size_t n)
{
	return (int)(heap_end - HEAP) >= (int)n;
}
```

которая вычитает значение `HEAP` из `heap_end` (мы вычисляли это в предыдущей [части](linux-bootstrap-2.md)) и возвращает 1, если имеется достаточно памяти для `n`.

На этом всё. Теперь у нас есть простой API для кучи и можем перейти к настройке видеорежима.

Настройка видеорежима
--------------------------------------------------------------------------------

Теперь мы можем перейти непосредственно к инициализации видеорежима. Мы остановились на вызове `RESET_HEAP()` в функции `set_video`. Далее идёт вызов `store_mode_params` который хранит параметры видеорежима в структуре `boot_params.screen_info`, определённой в [include/uapi/linux/screen_info.h](https://github.com/0xAX/linux/blob/master/include/uapi/linux/screen_info.h).

Если мы посмотрим на функцию `store_mode_params`, то увидим что она начинается с вызова `store_cursor_position`.  Как вы можете понять из названия функции, она получает информацию о курсоре и сохраняет её.

В первую очередь `store_cursor_position` инициализирует две переменные, которые имеют тип `biosregs` с `AH = 0x3`, и вызывает BIOS прерывание `0x10`. После того, как прерывание успешно выполнено, она возвращает строку и столбец в регистрах `DL` и `DH`. Строка и столбец будут сохранены в полях `orig_x` и `orig_y` структуры `boot_params.screen_info`.

После выполнения `store_cursor_position`  вызывается функция `store_video_mode`. Она просто получает текущий видеорежим  и сохраняет его в `boot_params.screen_info.orig_video_mode`. 

После этого, она проверяет текущий видеорежим и устанавливает `video_segment`. После того, как BIOS передаёт контроль в загрузочный сектор, для видеопамяти выделяются следующие адреса:

```
0xB000:0x0000 	32 Кб   Видеопамять для монохромного текста
0xB800:0x0000 	32 Кб   Видеопамять для цветного текста
```

Таким образом, мы устанавливаем переменную `video_segment` в `0xB000`, если текущий видеорежим MDA, HGC, или VGA в монохромном режиме и в `0xB800`, если текущий видеорежим цветной. После настройки адреса видеофрагмента, размер шрифта должен быть сохранён в `boot_params.screen_info.orig_video_points`:

```C
set_fs(0);
font_size = rdfs16(0x485);
boot_params.screen_info.orig_video_points = font_size;
```

В первую очередь мы устанавливаем регистр `FS` в 0 с помощью функции `set_fs`. В предыдущей части мы уже видели такие функции, как `set_fs`. Все они определены в [boot.h](https://github.com/0xAX/linux/blob/master/arch/x86/boot/boot.h). Далее мы читаем значение, которое находится по адресу `0x485` (эта область памяти используется для получения размера шрифта) и сохраняет размер шрифта `boot_params.screen_info.orig_video_points`.

```
 x = rdfs16(0x44a);
 y = (adapter == ADAPTER_CGA) ? 25 : rdfs8(0x484)+1;
```

Далее мы получаем количество столбцов по адресу `0x44a` и строк по адресу `0x484` и сохраняем их в `boot_params.screen_info.orig_video_cols` и `boot_params.screen_info.orig_video_lines`. После этого выполнение `store_mode_params` завершается.

Далее мы видим функцию `save_screen`, которая просто сохраняет содержимое экрана в куче. Эта функция собирает все данные, которые мы получили в предыдущей функции, такие как количество строк и столбцов и т.д, и сохраняет их в структуре `saved_screen`, которая определена как:

```C
static struct saved_screen {
	int x, y;
	int curx, cury;
	u16 *data;
} saved;
```

Затем она проверяет, есть ли свободное место в куче:

```C
if (!heap_free(saved.x*saved.y*sizeof(u16)+512))
		return;
```

и если места в куче достаточно, выделяет его и сохраняет в нём `saved_screen`.

Следующий вызов - `probe_cards(0)` из [arch/x86/boot/video-mode.c](https://github.com/0xAX/linux/blob/master/arch/x86/boot/video-mode.c#L33). Она проходит по всем video_cards и собирает количество режимов, предоставляемых картой. Здесь интересный момент, мы можем видеть цикл:

```C
for (card = video_cards; card < video_cards_end; card++) {
  /* Здесь собираем количество режимов */
}
```

но `video_cards` не объявлена где угодно. Ответ прост: каждый видеорежим, представленный в x86-коде настройки ядра, определён следующим образом:

```C
static __videocard video_vga = {
	.card_name	= "VGA",
	.probe		= vga_probe,
	.set_mode	= vga_set_mode,
};
```

где `__videocard` - макрос:

```C
#define __videocard struct card_info __attribute__((used,section(".videocards")))
```

который определяет структуру `card_info`:

```C
struct card_info {
	const char *card_name;
	int (*set_mode)(struct mode_info *mode);
	int (*probe)(void);
	struct mode_info *modes;
	int nmodes;
	int unsafe;
	u16 xmode_first;
	u16 xmode_n;
};
```

которая находится в сегменте `.videocards`. Давайте посмотрим в скрипт компоновщика [arch/x86/boot/setup.ld](https://github.com/0xAX/linux/blob/master/arch/x86/boot/setup.ld), в котором мы можем найти:

```
	.videocards	: {
		video_cards = .;
		*(.videocards)
		video_cards_end = .;
	}
```

Это значит, что `video_cards` это просто адрес в памяти и все структуры `card_info` размещаются в этом сегменте. Это также означает, что все структуры `card_info` размещаются между `video_cards` и `video_cards_end`, поэтому мы можем воспользоваться этим, чтобы пройтись по ним в цикле. После выполнения `probe_cards` у нас есть все структуры `static __videocard video_vga` с заполненными `nmodes` (число видеорежимов).

После завершения выполнения `probe_cards`, мы переходим в главный цикл функции `set_video`. Это бесконечный цикл, который пытается установить видеорежим с помощью функции `set_mode` и выводит меню, если установлен флаг `vid_mode=ask` командной строки ядра или видеорежим не определён. 

Функция `set_mode` определена в [video-mode.c](https://github.com/0xAX/linux/blob/master/arch/x86/boot/video-mode.c#L147) и принимает только один параметр - `mode`, который определяет количество видеорежимов (мы получили его из меню или в начале `setup_video`, из заголовка настройки ядра). 

`set_mode` проверяет `mode` и вызывает функцию `raw_set_mode`. `raw_set_mode` вызывает `set_mode` для выбранной карты, т.е.  `card->set_mode(struct mode_info*)`. Мы можем получить доступ к этой функции из структуры `card_info`. Каждый видеорежим определяет эту структуру со значениями, заполненными в зависимости от режима видео (например, для `vga` это функция `video_vga.set_mode`. См. выше пример структуры `card_info` для `vga`). `video_vga.set_mode` является `vga_set_mode`, который проверяет vga-режим и вызывает соответствующую функцию:

```C
static int vga_set_mode(struct mode_info *mode)
{
	vga_set_basic_mode();

	force_x = mode->x;
	force_y = mode->y;

	switch (mode->mode) {
	case VIDEO_80x25:
		break;
	case VIDEO_8POINT:
		vga_set_8font();
		break;
	case VIDEO_80x43:
		vga_set_80x43();
		break;
	case VIDEO_80x28:
		vga_set_14font();
		break;
	case VIDEO_80x30:
		vga_set_80x30();
		break;
	case VIDEO_80x34:
		vga_set_80x34();
		break;
	case VIDEO_80x60:
		vga_set_80x60();
		break;
	}
	return 0;
}
```

Каждая функция, которая устанавливает видеорежим, просто вызывает BIOS прерывание `0x10` с определённым значением в регистре `AH`.

После того, как мы установили видеорежим, мы передаём его в `boot_params.hdr.vid_mode`.

Далее вызывается `vesa_store_edid`. Эта функция сохраняет информацию о [EDID](https://en.wikipedia.org/wiki/Extended_Display_Identification_Data) (**E**xtended **D**isplay **I**dentification **D**ata) для использования ядром. После этого снова вызывается `store_mode_params`. И наконец, если установлен `do_restore`, экран восстанавливается в предыдущее состояние.

Теперь, когда видеорежим установлен, мы можем переключится в защищённый режим.

Последняя подготовка перед переходом в защищённый режим
--------------------------------------------------------------------------------

We can see the last function call - `go_to_protected_mode` - in [main.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/main.c#L184). As the comment says: `Do the last things and invoke protected mode`, so let's see these last things and switch into protected mode.

`go_to_protected_mode` is defined in [arch/x86/boot/pm.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/pm.c#L104). It contains some functions which make the last preparations before we can jump into protected mode, so let's look at it and try to understand what they do and how it works.

First is the call to the `realmode_switch_hook` function in `go_to_protected_mode`. This function invokes the real mode switch hook if it is present and disables [NMI](http://en.wikipedia.org/wiki/Non-maskable_interrupt). Hooks are used if the bootloader runs in a hostile environment. You can read more about hooks in the [boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt) (see **ADVANCED BOOT LOADER HOOKS**).

The `realmode_switch` hook presents a pointer to the 16-bit real mode far subroutine which disables non-maskable interrupts. After `realmode_switch` hook (it isn't present for me) is checked, disabling of Non-Maskable Interrupts(NMI) occurs:

```assembly
asm volatile("cli");
outb(0x80, 0x70);	/* Disable NMI */
io_delay();
```

At first there is an inline assembly instruction with a `cli` instruction which clears the interrupt flag (`IF`). After this, external interrupts are disabled. The next line disables NMI (non-maskable interrupt).

An interrupt is a signal to the CPU which is emitted by hardware or software. After getting the signal, the CPU suspends the current instruction sequence, saves its state and transfers control to the interrupt handler. After the interrupt handler has finished it's work, it transfers control to the interrupted instruction. Non-maskable interrupts (NMI) are interrupts which are always processed, independently of permission. It cannot be ignored and is typically used to signal for non-recoverable hardware errors. We will not dive into details of interrupts now, but will discuss it in the next posts.

Let's get back to the code. We can see that second line is writing `0x80` (disabled bit) byte to `0x70` (CMOS Address register). After that, a call to the `io_delay` function occurs. `io_delay` causes a small delay and looks like:

```C
static inline void io_delay(void)
{
	const u16 DELAY_PORT = 0x80;
	asm volatile("outb %%al,%0" : : "dN" (DELAY_PORT));
}
```

To output any byte to the port `0x80` should delay exactly 1 microsecond. So we can write any value (value from `AL` register in our case) to the `0x80` port. After this delay `realmode_switch_hook` function has finished execution and we can move to the next function.

The next function is `enable_a20`, which enables [A20 line](http://en.wikipedia.org/wiki/A20_line). This function is defined in [arch/x86/boot/a20.c](https://github.com/torvalds/linux/blob/master/arch/x86/boot/a20.c) and it tries to enable the A20 gate with different methods. The first is the `a20_test_short` function which checks if A20 is already enabled or not with the `a20_test` function:

```C
static int a20_test(int loops)
{
	int ok = 0;
	int saved, ctr;

	set_fs(0x0000);
	set_gs(0xffff);

	saved = ctr = rdfs32(A20_TEST_ADDR);

    while (loops--) {
		wrfs32(++ctr, A20_TEST_ADDR);
		io_delay();	/* Serialize and make delay constant */
		ok = rdgs32(A20_TEST_ADDR+0x10) ^ ctr;
		if (ok)
			break;
	}

	wrfs32(saved, A20_TEST_ADDR);
	return ok;
}
```

First of all we put `0x0000` in the `FS` register and `0xffff` in the `GS` register. Next we read the value in address `A20_TEST_ADDR` (it is `0x200`) and put this value into the `saved` variable and `ctr`.

Next we write an updated `ctr` value into `fs:gs` with the `wrfs32` function, then delay for 1ms, and then read the value from the `GS` register by address `A20_TEST_ADDR+0x10`, if it's not zero we already have enabled the A20 line. If A20 is disabled, we try to enable it with a different method which you can find in the `a20.c`. For example with call of `0x15` BIOS interrupt with `AH=0x2041` etc.

If the `enabled_a20` function finished with fail, print an error message and call function `die`. You can remember it from the first source code file where we started - [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/header.S):

```assembly
die:
	hlt
	jmp	die
	.size	die, .-die
```

After the A20 gate is successfully enabled, the `reset_coprocessor` function is called:
 ```C
outb(0, 0xf0);
outb(0, 0xf1);
```
This function clears the Math Coprocessor by writing `0` to `0xf0` and then resets it by writing `0` to `0xf1`.

After this, the `mask_all_interrupts` function is called:
```C
outb(0xff, 0xa1);       /* Mask all interrupts on the secondary PIC */
outb(0xfb, 0x21);       /* Mask all but cascade on the primary PIC */
```
This masks all interrupts on the secondary PIC (Programmable Interrupt Controller) and primary PIC except for IRQ2 on the primary PIC.

And after all of these preparations, we can see the actual transition into protected mode.

Set up Interrupt Descriptor Table
--------------------------------------------------------------------------------

Now we set up the Interrupt Descriptor table (IDT). `setup_idt`:

```C
static void setup_idt(void)
{
	static const struct gdt_ptr null_idt = {0, 0};
	asm volatile("lidtl %0" : : "m" (null_idt));
}
```

which sets up the Interrupt Descriptor Table (describes interrupt handlers and etc.). For now the IDT is not installed (we will see it later), but now we just the load IDT with the `lidtl` instruction. `null_idt` contains address and size of IDT, but now they are just zero. `null_idt` is a `gdt_ptr` structure, it as defined as:
```C
struct gdt_ptr {
	u16 len;
	u32 ptr;
} __attribute__((packed));
```

where we can see the 16-bit length(`len`) of the IDT and the 32-bit pointer to it (More details about the IDT and interruptions will be seen in the next posts). ` __attribute__((packed))` means that the size of `gdt_ptr` is the minimum required size. So the size of the `gdt_ptr` will be 6 bytes here or 48 bits. (Next we will load the pointer to the `gdt_ptr` to the `GDTR` register and you might remember from the previous post that it is 48-bits in size).

Set up Global Descriptor Table
--------------------------------------------------------------------------------

Next is the setup of the Global Descriptor Table (GDT). We can see the `setup_gdt` function which sets up GDT (you can read about it in the [Kernel booting process. Part 2.](linux-bootstrap-2.md#protected-mode)). There is a definition of the `boot_gdt` array in this function, which contains the definition of the three segments:

```C
	static const u64 boot_gdt[] __attribute__((aligned(16))) = {
		[GDT_ENTRY_BOOT_CS] = GDT_ENTRY(0xc09b, 0, 0xfffff),
		[GDT_ENTRY_BOOT_DS] = GDT_ENTRY(0xc093, 0, 0xfffff),
		[GDT_ENTRY_BOOT_TSS] = GDT_ENTRY(0x0089, 4096, 103),
	};
```

For code, data and TSS (Task State Segment). We will not use the task state segment for now, it was added there to make Intel VT happy as we can see in the comment line (if you're interested you can find commit which describes it - [here](https://github.com/torvalds/linux/commit/88089519f302f1296b4739be45699f06f728ec31)). Let's look at `boot_gdt`. First of all note that it has the `__attribute__((aligned(16)))` attribute. It means that this structure will be aligned by 16 bytes. Let's look at a simple example:
```C
#include <stdio.h>

struct aligned {
	int a;
}__attribute__((aligned(16)));

struct nonaligned {
	int b;
};

int main(void)
{
	struct aligned    a;
	struct nonaligned na;

	printf("Not aligned - %zu \n", sizeof(na));
	printf("Aligned - %zu \n", sizeof(a));

	return 0;
}
```

Technically a structure which contains one `int` field must be 4 bytes, but here `aligned` structure will be 16 bytes:

```
$ gcc test.c -o test && test
Not aligned - 4
Aligned - 16
```

`GDT_ENTRY_BOOT_CS` has index - 2 here, `GDT_ENTRY_BOOT_DS` is `GDT_ENTRY_BOOT_CS + 1` and etc. It starts from 2, because first is a mandatory null descriptor (index - 0) and the second is not used (index - 1).

`GDT_ENTRY` is a macro which takes flags, base and limit and builds GDT entry. For example let's look at the code segment entry. `GDT_ENTRY` takes following values:

* base  - 0
* limit - 0xfffff
* flags - 0xc09b

What does this mean? The segment's base address is 0, and the limit (size of segment) is - `0xffff` (1 MB). Let's look at the flags. It is `0xc09b` and it will be:

```
1100 0000 1001 1011
```

in binary. Let's try to understand what every bit means. We will go through all bits from left to right:

* 1    - (G) granularity bit
* 1    - (D) if 0 16-bit segment; 1 = 32-bit segment
* 0    - (L) executed in 64 bit mode if 1
* 0    - (AVL) available for use by system software
* 0000 - 4 bit length 19:16 bits in the descriptor
* 1    - (P) segment presence in memory
* 00   - (DPL) - privilege level, 0 is the highest privilege
* 1    - (S) code or data segment, not a system segment
* 101  - segment type execute/read/
* 1    - accessed bit

You can read more about every bit in the previous [post](linux-bootstrap-2.md) or in the [Intel® 64 and IA-32 Architectures Software Developer's Manuals 3A](http://www.intel.com/content/www/us/en/processors/architectures-software-developer-manuals.html).

After this we get the length of the GDT with:

```C
gdt.len = sizeof(boot_gdt)-1;
```

We get the size of `boot_gdt` and subtract 1 (the last valid address in the GDT).

Next we get a pointer to the GDT with:

```C
gdt.ptr = (u32)&boot_gdt + (ds() << 4);
```

Here we just get the address of `boot_gdt` and add it to the address of the data segment left-shifted by 4 bits (remember we're in the real mode now).

Lastly we execute the `lgdtl` instruction to load the GDT into the GDTR register:

```C
asm volatile("lgdtl %0" : : "m" (gdt));
```

Actual transition into protected mode
--------------------------------------------------------------------------------

This is the end of the `go_to_protected_mode` function. We loaded IDT, GDT, disable interruptions and now can switch the CPU into protected mode. The last step is calling the `protected_mode_jump` function with two parameters:

```C
protected_mode_jump(boot_params.hdr.code32_start, (u32)&boot_params + (ds() << 4));
```

which is defined in [arch/x86/boot/pmjump.S](https://github.com/torvalds/linux/blob/master/arch/x86/boot/pmjump.S#L26). It takes two parameters:

* address of protected mode entry point
* address of `boot_params`

Let's look inside `protected_mode_jump`. As I wrote above, you can find it in `arch/x86/boot/pmjump.S`. The first parameter will be in the `eax` register and second is in `edx`.

First of all we put the address of `boot_params` in the `esi` register and the address of code segment register `cs` (0x1000) in `bx`. After this we shift `bx` by 4 bits and add the address of label `2` to it (we will have the physical address of label `2` in the `bx` after this) and jump to label `1`. Next we put data segment and task state segment in the `cs` and `di` registers with:

```assembly
movw	$__BOOT_DS, %cx
movw	$__BOOT_TSS, %di
```

As you can read above `GDT_ENTRY_BOOT_CS` has index 2 and every GDT entry is 8 byte, so `CS` will be `2 * 8 = 16`, `__BOOT_DS` is 24 etc.

Next we set the `PE` (Protection Enable) bit in the `CR0` control register:

```assembly
movl	%cr0, %edx
orb	$X86_CR0_PE, %dl
movl	%edx, %cr0
```

and make a long jump to protected mode:

```assembly
	.byte	0x66, 0xea
2:	.long	in_pm32
	.word	__BOOT_CS
```

where
* `0x66` is the operand-size prefix which allows us to mix 16-bit and 32-bit code,
* `0xea` - is the jump opcode,
* `in_pm32` is the segment offset
* `__BOOT_CS` is the code segment.

After this we are finally in the protected mode:

```assembly
.code32
.section ".text32","ax"
```

Let's look at the first steps in protected mode. First of all we set up the data segment with:

```assembly
movl	%ecx, %ds
movl	%ecx, %es
movl	%ecx, %fs
movl	%ecx, %gs
movl	%ecx, %ss
```

If you paid attention, you can remember that we saved `$__BOOT_DS` in the `cx` register. Now we fill it with all segment registers besides `cs` (`cs` is already `__BOOT_CS`). Next we zero out all general purpose registers besides `eax` with:

```assembly
xorl	%ecx, %ecx
xorl	%edx, %edx
xorl	%ebx, %ebx
xorl	%ebp, %ebp
xorl	%edi, %edi
```

And jump to the 32-bit entry point in the end:

```
jmpl	*%eax
```

Remember that `eax` contains the address of the 32-bit entry (we passed it as first parameter into `protected_mode_jump`).

That's all. We're in the protected mode and stop at it's entry point. We will see what happens next in the next part.

Conclusion
--------------------------------------------------------------------------------

This is the end of the third part about linux kernel insides. In next part, we will see first steps in the protected mode and transition into the [long mode](http://en.wikipedia.org/wiki/Long_mode).

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes, please send me a PR with corrections at [linux-insides](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

* [VGA](http://en.wikipedia.org/wiki/Video_Graphics_Array)
* [VESA BIOS Extensions](http://en.wikipedia.org/wiki/VESA_BIOS_Extensions)
* [Data structure alignment](http://en.wikipedia.org/wiki/Data_structure_alignment)
* [Non-maskable interrupt](http://en.wikipedia.org/wiki/Non-maskable_interrupt)
* [A20](http://en.wikipedia.org/wiki/A20_line)
* [GCC designated inits](https://gcc.gnu.org/onlinedocs/gcc-4.1.2/gcc/Designated-Inits.html)
* [GCC type attributes](https://gcc.gnu.org/onlinedocs/gcc/Type-Attributes.html)
* [Previous part](linux-bootstrap-2.md)

