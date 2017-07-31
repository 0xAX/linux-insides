Timers and time management in the Linux kernel. Part 6.
================================================================================

x86_64 related clock sources
--------------------------------------------------------------------------------

This is sixth part of the [chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html) which describes timers and time management related stuff in the Linux kernel. In the previous [part](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-5.html) we saw `clockevents` framework and now we will continue to dive into time management related stuff in the Linux kernel. This part will describe implementation of [x86](https://en.wikipedia.org/wiki/X86) architecture related clock sources (more about `clocksource` concept you can read in the [second part](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-2.html) of this chapter).

First of all we must know what clock sources may be used at `x86` architecture. It is easy to know from the [sysfs](https://en.wikipedia.org/wiki/Sysfs) or from content of the `/sys/devices/system/clocksource/clocksource0/available_clocksource`. The `/sys/devices/system/clocksource/clocksourceN` provides two special files to achieve this:

* `available_clocksource` - provides information about available clock sources in the system;
* `current_clocksource`   - provides information about currently used clock source in the system.

So, let's look:

```
$ cat /sys/devices/system/clocksource/clocksource0/available_clocksource 
tsc hpet acpi_pm 
```

We can see that there are three registered clock sources in my system:

* `tsc` - [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter);
* `hpet` - [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer);
* `acpi_pm` - [ACPI Power Management Timer](http://uefi.org/sites/default/files/resources/ACPI_5.pdf).

Now let's look at the second file which provides best clock source (a clock source which has the best rating in the system):

```
$ cat /sys/devices/system/clocksource/clocksource0/current_clocksource 
tsc
```

For me it is [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter). As we may know from the [second part](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-2.html) of this chapter, which describes internals of the `clocksource` framework in the Linux kernel, the best clock source in a system is a clock source with the best (highest) rating or in other words with the highest [frequency](https://en.wikipedia.org/wiki/Frequency).

Frequency of the [ACPI](https://en.wikipedia.org/wiki/Advanced_Configuration_and_Power_Interface) power management timer is `3.579545 MHz`. Frequency of the [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer) is at least `10 MHz`. And the frequency of the [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter) depends on processor. For example On older processors, the `Time Stamp Counter` was counting internal processor clock cycles. This means its frequency changed when the processor's frequency scaling changed. The situation has changed for newer processors. Newer processors have an `invariant Time Stamp counter` that increments at a constant rate in all operational states of processor. Actually we can get its frequency in the output of the `/proc/cpuinfo`. For example for the first processor in the system:

```
$ cat /proc/cpuinfo
...
model name	: Intel(R) Core(TM) i7-4790K CPU @ 4.00GHz
...
```

And although Intel manual says that the frequency of the `Time Stamp Counter`, while constant, is not necessarily the maximum qualified frequency of the processor, or the frequency given in the brand string, anyway we may see that it will be much more than frequency of the `ACPI PM` timer or `High Precision Event Timer`. And we can see that the clock source with the best rating or highest frequency is current in the system.

You can note that besides these three clock source, we don't see yet another two familiar us clock sources in the output of the `/sys/devices/system/clocksource/clocksource0/available_clocksource`. These clock sources are `jiffy` and `refined_jiffies`. We don't see them because this filed maps only high resolution clock sources or in other words clock sources with the [CLOCK_SOURCE_VALID_FOR_HRES](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/clocksource.h#L113) flag.

As I already wrote above, we will consider all of these three clock sources in this part. We will consider it in order of their initialization or:

* `hpet`;
* `acpi_pm`;
* `tsc`.

We can make sure that the order is exactly like this in the output of the [dmesg](https://en.wikipedia.org/wiki/Dmesg) util:

```
$ dmesg | grep clocksource
[    0.000000] clocksource: refined-jiffies: mask: 0xffffffff max_cycles: 0xffffffff, max_idle_ns: 1910969940391419 ns
[    0.000000] clocksource: hpet: mask: 0xffffffff max_cycles: 0xffffffff, max_idle_ns: 133484882848 ns
[    0.094369] clocksource: jiffies: mask: 0xffffffff max_cycles: 0xffffffff, max_idle_ns: 1911260446275000 ns
[    0.186498] clocksource: Switched to clocksource hpet
[    0.196827] clocksource: acpi_pm: mask: 0xffffff max_cycles: 0xffffff, max_idle_ns: 2085701024 ns
[    1.413685] tsc: Refined TSC clocksource calibration: 3999.981 MHz
[    1.413688] clocksource: tsc: mask: 0xffffffffffffffff max_cycles: 0x73509721780, max_idle_ns: 881591102108 ns
[    2.413748] clocksource: Switched to clocksource tsc
```

The first clock source is the [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer), so let's start from it.

High Precision Event Timer
--------------------------------------------------------------------------------

The implementation of the `High Precision Event Timer` for the [x86](https://en.wikipedia.org/wiki/X86) architecture is located in the [arch/x86/kernel/hpet.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/hpet.c) source code file. Its initialization starts from the call of the `hpet_enable` function. This function is called during Linux kernel initialization. If we will look into `start_kernel` function from the [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c) source code file, we will see that after the all architecture-specific stuff initialized, early console is disabled and time management subsystem already ready, call of the following function:

```C
if (late_time_init)
	late_time_init();
```

which does initialization of the late architecture specific timers after early jiffy counter already initialized. The definition of the `late_time_init` function for the `x86` architecture is located in the [arch/x86/kernel/time.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/time.c) source code file. It looks pretty easy:

```C
static __init void x86_late_time_init(void)
{
	x86_init.timers.timer_init();
	tsc_init();
}
```

As we may see, it does initialization of the `x86` related timer and initialization of the `Time Stamp Counter`. The seconds we will see in the next paragraph, but now let's consider the call of the `x86_init.timers.timer_init` function. The `timer_init` points to the `hpet_time_init` function from the same source code file. We can verify this by looking on the definition of the `x86_init` structure from the [arch/x86/kernel/x86_init.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/x86_init.c):

```C
struct x86_init_ops x86_init __initdata = {
   ...
   ...
   ...
   .timers = {
		.setup_percpu_clockev	= setup_boot_APIC_clock,
		.timer_init		= hpet_time_init,
		.wallclock_init		= x86_init_noop,
   },
   ...
   ...
   ...
```

The `hpet_time_init` function does setup of the [programmable interval timer](https://en.wikipedia.org/wiki/Programmable_interval_timer) if we can not enable `High Precision Event Timer` and setups default timer [IRQ](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29) for the enabled timer:

```C
void __init hpet_time_init(void)
{
	if (!hpet_enable())
		setup_pit_timer();
	setup_default_timer_irq();
}
```

First of all the `hpet_enable` function check we can enable `High Precision Event Timer` in the system by the call of the `is_hpet_capable` function and if we can, we map a virtual address space for it:

```C
int __init hpet_enable(void)
{
	if (!is_hpet_capable())
		return 0;

    hpet_set_mapping();
}
```

The `is_hpet_capable` function checks that we didn't pass `hpet=disable` to the kernel command line and the `hpet_address` is received from the [ACPI HPET](https://en.wikipedia.org/wiki/Advanced_Configuration_and_Power_Interface) table. The `hpet_set_mapping` function just maps the virtual address spaces for the timer registers:

```C
hpet_virt_address = ioremap_nocache(hpet_address, HPET_MMAP_SIZE);
```

As we can read in the  [IA-PC HPET (High Precision Event Timers) Specification](http://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/software-developers-hpet-spec-1-0a.pdf):

> The timer register space is 1024 bytes

So, the `HPET_MMAP_SIZE` is `1024` bytes too:

```C
#define HPET_MMAP_SIZE		1024
```

After we mapped virtual space for the `High Precision Event Timer`, we read `HPET_ID` register to get number of the timers:

```C
id = hpet_readl(HPET_ID);

last = (id & HPET_ID_NUMBER) >> HPET_ID_NUMBER_SHIFT;
```

We need to get this number to allocate correct amount of space for the `General Configuration Register` of the `High Precision Event Timer`:

```C
cfg = hpet_readl(HPET_CFG);

hpet_boot_cfg = kmalloc((last + 2) * sizeof(*hpet_boot_cfg), GFP_KERNEL);
```

After the space is allocated for the configuration register of the `High Precision Event Timer`, we allow to main counter to run, and allow timer interrupts if they are enabled by the setting of `HPET_CFG_ENABLE` bit in the configuration register for all timers. In the end we just register new clock source by the call of the `hpet_clocksource_register` function:

```C
if (hpet_clocksource_register())
	goto out_nohpet;
```

which just calls already familiar

```C
clocksource_register_hz(&clocksource_hpet, (u32)hpet_freq);
```

function. Where the `clocksource_hpet` is the `clocksource` structure with the rating `250` (remember rating of the previous `refined_jiffies` clock source was `2`), name - `hpet` and `read_hpet` callback for the reading of atomic counter provided by the `High Precision Event Timer`:

```C
static struct clocksource clocksource_hpet = {
	.name		= "hpet",
	.rating		= 250,
	.read		= read_hpet,
	.mask		= HPET_MASK,
	.flags		= CLOCK_SOURCE_IS_CONTINUOUS,
	.resume		= hpet_resume_counter,
	.archdata	= { .vclock_mode = VCLOCK_HPET },
};
```

After the `clocksource_hpet` is registered, we can return to the `hpet_time_init()` function from the [arch/x86/kernel/time.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/time.c) source code file. We can remember that the last step is the call of the:

```C
setup_default_timer_irq();
```

function in the `hpet_time_init()`. The `setup_default_timer_irq` function checks existence of `legacy` IRQs or in other words support for the [i8259](https://en.wikipedia.org/wiki/Intel_8259) and setups [IRQ0](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29#Master_PIC) depends on this.

That's all. From this moment the [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer) clock source registered in the Linux kernel `clock source` framework and may be used from generic kernel code via the `read_hpet`:
```C
static cycle_t read_hpet(struct clocksource *cs)
{
	return (cycle_t)hpet_readl(HPET_COUNTER);
}
```

function which just reads and returns atomic counter from the `Main Counter Register`.

ACPI PM timer
--------------------------------------------------------------------------------

The seconds clock source is [ACPI Power Management Timer](http://uefi.org/sites/default/files/resources/ACPI_5.pdf). Implementation of this clock source is located in the [drivers/clocksource/acpi_pm.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/drivers/clocksource_acpi_pm.c) source code file and starts from the call of the `init_acpi_pm_clocksource` function during `fs` [initcall](http://www.compsoc.man.ac.uk/~moz/kernelnewbies/documents/initcall/kernel.html).

If we will look at implementation of the `init_acpi_pm_clocksource` function, we will see that it starts from the check of the value of `pmtmr_ioport` variable:

```C
static int __init init_acpi_pm_clocksource(void)
{
    ...
    ...
    ...
	if (!pmtmr_ioport)
		return -ENODEV;
    ...
    ...
    ...
```

This `pmtmr_ioport` variable contains extended address of the `Power Management Timer Control Register Block`. It gets its value in the `acpi_parse_fadt` function which is defined in the [arch/x86/kernel/acpi/boot.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/acpi/boot.c) source code file. This function parses `FADT` or `Fixed ACPI Description Table` [ACPI](https://en.wikipedia.org/wiki/Advanced_Configuration_and_Power_Interface) table and tries to get the values of the `X_PM_TMR_BLK` field which contains extended address of the `Power Management Timer Control Register Block`, represented in `Generic Address Structure` format:

```C
static int __init acpi_parse_fadt(struct acpi_table_header *table)
{
#ifdef CONFIG_X86_PM_TIMER
        ...
        ...
        ...
		pmtmr_ioport = acpi_gbl_FADT.xpm_timer_block.address;
        ...
        ...
        ...
#endif
	return 0;
}
```

So, if the `CONFIG_X86_PM_TIMER` Linux kernel configuration option is disabled or something going wrong in the `acpi_parse_fadt` function, we can't access the `Power Management Timer` register and return from the `init_acpi_pm_clocksource`. In other way, if the value of the `pmtmr_ioport` variable is not zero, we check rate of this timer and register this clock source by the call of the:

```C
clocksource_register_hz(&clocksource_acpi_pm, PMTMR_TICKS_PER_SEC);
```
    
function. After the call of the `clocksource_register_hs`, the `acpi_pm` clock source will be registered in the `clocksource` framework of the Linux kernel:

```C
static struct clocksource clocksource_acpi_pm = {
	.name		= "acpi_pm",
	.rating		= 200,
	.read		= acpi_pm_read,
	.mask		= (cycle_t)ACPI_PM_MASK,
	.flags		= CLOCK_SOURCE_IS_CONTINUOUS,
};
```

with the rating - `200` and the `acpi_pm_read` callback to read atomic counter provided by the `acpi_pm` clock source. The `acpi_pm_read` function just executes `read_pmtmr` function:

```C
static cycle_t acpi_pm_read(struct clocksource *cs)
{
	return (cycle_t)read_pmtmr();
}
```

which reads value of the `Power Management Timer` register. This register has following structure:

```
+-------------------------------+----------------------------------+
|                               |                                  |
|  upper eight bits of a        |      running count of the        |
| 32-bit power management timer |     power management timer       |
|                               |                                  |
+-------------------------------+----------------------------------+
31          E_TMR_VAL           24               TMR_VAL           0
```

Address of this register is stored in the `Fixed ACPI Description Table` [ACPI](https://en.wikipedia.org/wiki/Advanced_Configuration_and_Power_Interface) table and we already have it in the `pmtmr_ioport`. So, the implementation of the `read_pmtmr` function is pretty easy:

```C
static inline u32 read_pmtmr(void)
{
	return inl(pmtmr_ioport) & ACPI_PM_MASK;
}
```

We just read the value of the `Power Management Timer` register and mask its `24` bits.

That's all. Now we move to the last clock source in this part - `Time Stamp Counter`.

Time Stamp Counter
--------------------------------------------------------------------------------

The third and last clock source in this part is - [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter) clock source and its implementation is located in the [arch/x86/kernel/tsc.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/tsc.c) source code file. We already saw the `x86_late_time_init` function in this part and initialization of the [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter) starts from this place. This function calls the `tsc_init()` function from the [arch/x86/kernel/tsc.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/tsc.c) source code file.

At the beginning of the `tsc_init` function we can see check, which checks that a processor has support of the `Time Stamp Counter`:

```C
void __init tsc_init(void)
{
	u64 lpj;
	int cpu;

	if (!cpu_has_tsc) {
		setup_clear_cpu_cap(X86_FEATURE_TSC_DEADLINE_TIMER);
		return;
	}
    ...
    ...
    ...
```

The `cpu_has_tsc` macro expands to the call of the `cpu_has` macro:

```C
#define cpu_has_tsc		boot_cpu_has(X86_FEATURE_TSC)

#define boot_cpu_has(bit)	cpu_has(&boot_cpu_data, bit)

#define cpu_has(c, bit)							\
	(__builtin_constant_p(bit) && REQUIRED_MASK_BIT_SET(bit) ? 1 :	\
	 test_cpu_cap(c, bit))
```

which check the given bit (the `X86_FEATURE_TSC_DEADLINE_TIMER` in our case) in the `boot_cpu_data` array which is filled during early Linux kernel initialization. If the processor has support of the `Time Stamp Counter`, we get the frequency of the `Time Stamp Counter` by the call of the `calibrate_tsc` function from the same source code file which tries to get frequency from the different source like [Model Specific Register](https://en.wikipedia.org/wiki/Model-specific_register), calibrate over [programmable interval timer](https://en.wikipedia.org/wiki/Programmable_interval_timer) and etc, after this we initialize frequency and scale factor for the all processors in the system:

```C
tsc_khz = x86_platform.calibrate_tsc();
cpu_khz = tsc_khz;

for_each_possible_cpu(cpu) {
	cyc2ns_init(cpu);
	set_cyc2ns_scale(cpu_khz, cpu);
}
```

because only first bootstrap processor will call the `tsc_init`. After this we check hat `Time Stamp Counter` is not disabled:

```
if (tsc_disabled > 0)
	return;
...
...
...
check_system_tsc_reliable();
```

and call the `check_system_tsc_reliable` function which sets the `tsc_clocksource_reliable` if bootstrap processor has the `X86_FEATURE_TSC_RELIABLE` feature. Note that we went through the `tsc_init` function, but did not register our clock source. Actual registration of the `Time Stamp Counter` clock source occurs in the:

```C
static int __init init_tsc_clocksource(void)
{
	if (!cpu_has_tsc || tsc_disabled > 0 || !tsc_khz)
		return 0;
    ...
    ...
    ...
    if (boot_cpu_has(X86_FEATURE_TSC_RELIABLE)) {
		clocksource_register_khz(&clocksource_tsc, tsc_khz);
		return 0;
	}
```

function. This function called during the `device` [initcall](http://www.compsoc.man.ac.uk/~moz/kernelnewbies/documents/initcall/kernel.html). We do it to be sure that the `Time Stamp Counter` clock source will be registered after the  [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer) clock source.

After these all three clock sources will be registered in the `clocksource` framework and the `Time Stamp Counter` clock source will be selected as active, because it has the highest rating among other clock sources:

```C
static struct clocksource clocksource_tsc = {
	.name                   = "tsc",
	.rating                 = 300,
	.read                   = read_tsc,
	.mask                   = CLOCKSOURCE_MASK(64),
	.flags                  = CLOCK_SOURCE_IS_CONTINUOUS | CLOCK_SOURCE_MUST_VERIFY,
	.archdata               = { .vclock_mode = VCLOCK_TSC },
};
```

That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the sixth part of the [chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html) that describes timers and timer management related stuff in the Linux kernel. In the previous part got acquainted with the `clockevents` framework. In this part we continued to learn time management related stuff in the Linux kernel and saw a little about three different clock sources which are used in the [x86](https://en.wikipedia.org/wiki/X86) architecture. The next part will be last part of this [chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html) and we will see some user space related stuff, i.e. how some time related [system calls](https://en.wikipedia.org/wiki/System_call) implemented in the Linux kernel.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [x86](https://en.wikipedia.org/wiki/X86)
* [sysfs](https://en.wikipedia.org/wiki/Sysfs)
* [Time Stamp Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter)
* [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer)
* [ACPI Power Management Timer (PDF)](http://uefi.org/sites/default/files/resources/ACPI_5.pdf)
* [frequency](https://en.wikipedia.org/wiki/Frequency).
* [dmesg](https://en.wikipedia.org/wiki/Dmesg)
* [programmable interval timer](https://en.wikipedia.org/wiki/Programmable_interval_timer)
* [IRQ](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29) 
* [IA-PC HPET (High Precision Event Timers) Specification](http://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/software-developers-hpet-spec-1-0a.pdf)
* [IRQ0](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29#Master_PIC)
* [i8259](https://en.wikipedia.org/wiki/Intel_8259)
* [initcall](http://www.compsoc.man.ac.uk/~moz/kernelnewbies/documents/initcall/kernel.html)
* [previous part](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-5.html)
