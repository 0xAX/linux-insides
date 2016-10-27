Timers and time management in the Linux kernel. Part 1.
================================================================================

Introduction
--------------------------------------------------------------------------------

This is yet another post that opens new chapter in the [linux-insides](http://0xax.gitbooks.io/linux-insides/content/) book. The previous [part](https://0xax.gitbooks.io/linux-insides/content/SysCall/syscall-4.html) was a list part of the chapter that describes [system call](https://en.wikipedia.org/wiki/System_call) concept and now time is to start new chapter. As you can understand from the post's title, this chapter will be devoted to the `timers` and `time management` in the Linux kernel. The choice of topic for the current chapter is not accidental. Timers and generally time management are very important and widely used in the Linux kernel. The Linux kernel uses timers for various tasks, different timeouts for example in [TCP](https://en.wikipedia.org/wiki/Transmission_Control_Protocol) implementation, the kernel must know current time, scheduling asynchronous functions, next event interrupt scheduling and many many more.

So, we will start to learn implementation of the different time management related stuff in this part. We will see different types of timers and how do different Linux kernel subsystems use them. As always we will start from the earliest part of the Linux kernel and will go through initialization process of the Linux kernel. We already did it in the special [chapter](https://0xax.gitbooks.io/linux-insides/content/Initialization/index.html) which describes initialization process of the Linux kernel, but as you may remember we missed some things there. And one of them is the initialization of timers.

Let's start.

Initialization of non-standard PC hardware clock
--------------------------------------------------------------------------------

After the Linux kernel was decompressed (more about this you can read in the [Kernel decompression](https://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-5.html) part) the architecture non-specific code starts to work in the [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c) source code file. After initialization of the [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt), initialization of [cgroups](https://en.wikipedia.org/wiki/Cgroups) and setting [canary](https://en.wikipedia.org/wiki/Buffer_overflow_protection) value we can see the call of the `setup_arch` function.

As you may remember this function defined in the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c#L842) source code file and prepares/initializes architecture-specific stuff (for example it reserves place for [bss](https://en.wikipedia.org/wiki/.bss) section, reserves place for [initrd](https://en.wikipedia.org/wiki/Initrd), parses kernel command line and many many other things). Besides this, we can find some time management related functions there.

The first is:

```C
x86_init.timers.wallclock_init();
```

We already saw `x86_init` structure in the chapter that describes initialization of the Linux kernel. This structure contains pointers to the default setup functions for the different platforms like [Intel MID](https://en.wikipedia.org/wiki/Mobile_Internet_device#Intel_MID_platforms), [Intel CE4100](http://www.wpgholdings.com/epaper/US/newsRelease_20091215/255874.pdf) and etc. The `x86_init` structure defined in the [arch/x86/kernel/x86_init.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/x86_init.c#L36) and as you can see it determines standard PC hardware by default.

As we can see, the `x86_init` structure has `x86_init_ops` type that provides a set of functions for platform specific setup like reserving standard resources, platform specific memory setup, initialization of interrupt handlers and etc. This structure looks like:

```C
struct x86_init_ops {
	struct x86_init_resources       resources;
    struct x86_init_mpparse         mpparse;
    struct x86_init_irqs            irqs;
    struct x86_init_oem             oem;
    struct x86_init_paging          paging;
    struct x86_init_timers          timers;
    struct x86_init_iommu           iommu;
    struct x86_init_pci             pci;
};
```

We can note `timers` field that has `x86_init_timers` type and as we can understand by its name - this field is related to time management and timers. The `x86_init_timers` contains four fields which are all functions that returns pointer on [void](https://en.wikipedia.org/wiki/Void_type):

* `setup_percpu_clockev` - set up the per cpu clock event device for the boot cpu;
* `tsc_pre_init` - platform function called before [TSC](https://en.wikipedia.org/wiki/Time_Stamp_Counter) init;
* `timer_init` - initialize the platform timer;
* `wallclock_init` - initialize the wallclock device.

So, as we already know, in our case the `wallclock_init` executes initialization of the wallclock device. If we will look on the `x86_init` structure, we will see that `wallclock_init` points to the `x86_init_noop`:

```C
struct x86_init_ops x86_init __initdata = {
	...
	...
	...
	.timers = {
		.wallclock_init		    = x86_init_noop,
	},
	...
	...
	...
}
```

Where the `x86_init_noop` is just a function that does nothing:

```C
void __cpuinit x86_init_noop(void) { }
```

for the standard PC hardware. Actually, the `wallclock_init` function is used in the [Intel MID](https://en.wikipedia.org/wiki/Mobile_Internet_device#Intel_MID_platforms) platform. Initialization of the `x86_init.timers.wallclock_init` located in the [arch/x86/platform/intel-mid/intel-mid.c](https://github.com/torvalds/linux/blob/master/arch/x86/platform/intel-mid/intel-mid.c) source code file in the `x86_intel_mid_early_setup` function:

```C
void __init x86_intel_mid_early_setup(void)
{
	...
	...
	...
	x86_init.timers.wallclock_init = intel_mid_rtc_init;
	...
	...
	...
}
```

Implementation of the `intel_mid_rtc_init` function is in the [arch/x86/platform/intel-mid/intel_mid_vrtc.c](https://github.com/torvalds/linux/blob/master/arch/x86/platform/intel-mid/intel_mid_vrtc.c) source code file and looks pretty easy. First of all, this function parses [Simple Firmware Interface](https://en.wikipedia.org/wiki/Simple_Firmware_Interface) M-Real-Time-Clock table for the getting such devices to the `sfi_mrtc_array` array and initialization of the `set_time` and `get_time` functions:

```C
void __init intel_mid_rtc_init(void)
{
	unsigned long vrtc_paddr;

	sfi_table_parse(SFI_SIG_MRTC, NULL, NULL, sfi_parse_mrtc);

	vrtc_paddr = sfi_mrtc_array[0].phys_addr;
	if (!sfi_mrtc_num || !vrtc_paddr)
		return;

	vrtc_virt_base = (void __iomem *)set_fixmap_offset_nocache(FIX_LNW_VRTC,
								vrtc_paddr);

    x86_platform.get_wallclock = vrtc_get_time;
	x86_platform.set_wallclock = vrtc_set_mmss;
}
```

That's all, after this a device based on `Intel MID` will be able to get time from hardware clock. As I already wrote, the standard PC [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture does not support `x86_init_noop` and just do nothing during call of this function. We just saw initialization of the [real time clock](https://en.wikipedia.org/wiki/Real-time_clock) for the [Intel MID](https://en.wikipedia.org/wiki/Mobile_Internet_device#Intel_MID_platforms) architecture and now times to return to the general `x86_64` architecture and will look on the time management related stuff there.

Acquainted with jiffies
--------------------------------------------------------------------------------

If we will return to the `setup_arch` function which is located as you remember in the  [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c#L842) source code file, we will see the next call of the time management related function:

```C
register_refined_jiffies(CLOCK_TICK_RATE);
```

Before we will look on the implementation of this function, we must know about [jiffy](https://en.wikipedia.org/wiki/Jiffy_%28time%29). As we can read on wikipedia:

```
Jiffy is an informal term for any unspecified short period of time
```

This definition is very similar to the `jiffy` in the Linux kernel. There is global variable with the `jiffies` which holds the number of ticks that have occurred since the system booted. The Linux kernel sets this variable to zero:

```C
extern unsigned long volatile __jiffy_data jiffies;
```

during initialization process. This global variable will be increased each time during timer interrupt. Besides this, near the `jiffies` variable we can see definition of the similar variable

```C
extern u64 jiffies_64;
```

Actually only one of these variables is in use in the Linux kernel. And it depends on the processor type. For the [x86_64](https://en.wikipedia.org/wiki/X86-64) it will be `u64` use and for the [x86](https://en.wikipedia.org/wiki/X86) is `unsigned long`. We will see this if we will look on the [arch/x86/kernel/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S) linker script:

```
#ifdef CONFIG_X86_32
...
jiffies = jiffies_64;
...
#else
...
jiffies_64 = jiffies;
...
#endif
```

In the case of `x86_32` the `jiffies` will be lower `32` bits of the `jiffies_64` variable. Schematically, we can imagine it as follows

```
                    jiffies_64
+-----------------------------------------------------+
|                       |                             |
|                       |                             |
|                       |       jiffies on `x86_32`   |
|                       |                             |
|                       |                             |
+-----------------------------------------------------+
63                     31                             0
```

Now we know a little theory about `jiffies` and we can return to the our function. There is no architecture-specific implementation for our function - the `register_refined_jiffies`. This function located in the generic kernel code - [kernel/time/jiffies.c](https://github.com/torvalds/linux/blob/master/kernel/time/jiffies.c) source code file. Main point of the `register_refined_jiffies` is registration of the jiffy `clocksource`. Before we will look on the implementation of the `register_refined_jiffies` function, we must know what is it `clocksource`. As we can read in the comments:

```
The `clocksource` is hardware abstraction for a free-running counter.
```

I'm not sure about you, but that description didn't give a good understanding about the `clocksource` concept. Let's try to understand what is it, but we will not go deeper because this topic will be described in a separate part in much more detail. The main point of the `clocksource` is timekeeping abstraction or in very simple words - it provides a time value to the kernel. We already know about `jiffies` interface that represents number of ticks that have occurred since the system booted. It represented by the global variable in the Linux kernel and increased each timer interrupt. The Linux kernel can use `jiffies` for time measurement. So why do we need in separate context like the `clocksource`? Actually different hardware devices provide different clock sources that are widely in their capabilities. The availability of more precise techniques for time intervals measurement is hardware-dependent.

For example `x86` has on-chip a 64-bit counter that is called [Time Stamp  Counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter) and its frequency can be equal to processor frequency. Or for example [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer) that consists of a `64-bit` counter of at least `10 MHz` frequency. Two different timers and they are both for `x86`. If we will add timers from other architectures, this only makes this problem more complex. The Linux kernel provides `clocksource` concept to solve the problem.

The clocksource concept represented by the `clocksource` structure in the Linux kernel. This structure defined in the [include/linux/clocksource.h](https://github.com/torvalds/linux/blob/master/include/linux/clocksource.h) header file and contains a couple of fields that describe a time counter. For example it contains - `name` field which is the name of a counter, `flags` field that describes different properties of a counter, pointers to the `suspend` and `resume` functions, and many more.

Let's look on the `clocksource` structure for jiffies that defined in the [kernel/time/jiffies.c](https://github.com/torvalds/linux/blob/master/kernel/time/jiffies.c) source code file:

```C
static struct clocksource clocksource_jiffies = {
	.name		= "jiffies",
	.rating		= 1,
	.read		= jiffies_read,
	.mask		= 0xffffffff,
	.mult		= NSEC_PER_JIFFY << JIFFIES_SHIFT,
	.shift		= JIFFIES_SHIFT,
	.max_cycles	= 10,
};
```

We can see definition of the default name here - `jiffies`, the next is `rating` field allows the best registered clock source to be chosen by the clock source management code available for the specified hardware. The `rating` may have following value:

* `1-99`    - Only available for bootup and testing purposes;
* `100-199` - Functional for real use, but not desired.
* `200-299` - A correct and usable clocksource.
* `300-399` - A reasonably fast and accurate clocksource.
* `400-499` - The ideal clocksource. A must-use where available;

For example rating of the [time stamp counter](https://en.wikipedia.org/wiki/Time_Stamp_Counter) is `300`, but rating of the [high precision event timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer) is `250`. The next field is `read` - is pointer to the function that allows to read clocksource's cycle value or in other words it just returns `jiffies` variable with `cycle_t` type:

```C
static cycle_t jiffies_read(struct clocksource *cs)
{
        return (cycle_t) jiffies;
}
```

that is just 64-bit unsigned type:

```C
typedef u64 cycle_t;
```

The next field is the `mask` value ensures that subtraction between counters values from non `64 bit` counters do not need special overflow logic. In our case the mask is `0xffffffff` and it is `32` bits. This means that `jiffy` wraps around to zero after `42` seconds:

```python
>>> 0xffffffff
4294967295
# 42 nanoseconds
>>> 42 * pow(10, -9)
4.2000000000000006e-08
# 43 nanoseconds
>>> 43 * pow(10, -9)
4.3e-08
```

The next two fields `mult` and `shift` are used to convert the clocksource's period to nanoseconds per cycle. When the kernel calls the `clocksource.read` function, this function returns value in `machine` time units represented with `cycle_t` data type that we saw just now. To convert this return value to the [nanoseconds](https://en.wikipedia.org/wiki/Nanosecond) we need in these two fields: `mult` and `shift`. The `clocksource` provides `clocksource_cyc2ns` function that will do it for us with the following expression:

```C
((u64) cycles * mult) >> shift;
```

As we can see the `mult` field is equal:

```C
NSEC_PER_JIFFY << JIFFIES_SHIFT

#define NSEC_PER_JIFFY  ((NSEC_PER_SEC+HZ/2)/HZ)
#define NSEC_PER_SEC    1000000000L
```

by default, and the `shift` is

```C
#if HZ < 34
  #define JIFFIES_SHIFT   6
#elif HZ < 67
  #define JIFFIES_SHIFT   7
#else
  #define JIFFIES_SHIFT   8
#endif
```

The `jiffies` clock source uses the `NSEC_PER_JIFFY` multiplier conversion to specify the nanosecond over cycle ratio. Note that values of the  `JIFFIES_SHIFT` and `NSEC_PER_JIFFY` depend on `HZ` value. The `HZ` represents the frequency of the system timer. This macro defined in the [include/asm-generic/param.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/param.h) and depends on the `CONFIG_HZ` kernel configuration option. The value of `HZ` differs for each supported architecture, but for `x86` it's defined like:

```C
#define HZ		CONFIG_HZ
```

Where `CONFIG_HZ` can be one of the following values:

![HZ](http://s9.postimg.org/xy85r3jrj/image.png)

This means that in our case the timer interrupt frequency is `250 HZ` or occurs `250` times per second or one timer interrupt each `4ms`.

The last field that we can see in the definition of the `clocksource_jiffies` structure is the - `max_cycles` that holds the maximum cycle value that can safely be multiplied without potentially causing an overflow.

	Ok, we just saw definition of the `clocksource_jiffies` structure, also we know a little about `jiffies` and `clocksource`, now is time to get back to the implementation of the our function. In the beginning of this part we have stopped on the call of the:

```C
register_refined_jiffies(CLOCK_TICK_RATE);
```

function from the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c#L842) source code file.

As I already wrote, the main purpose of the `register_refined_jiffies` function is to register `refined_jiffies` clocksource. We already saw the `clocksource_jiffies` structure represents standard `jiffies` clock source. Now, if you look in the [kernel/time/jiffies.c](https://github.com/torvalds/linux/blob/master/kernel/time/jiffies.c) source code file, you will find yet another clock source definition:

```C
struct clocksource refined_jiffies;
```

There is one different between `refined_jiffies` and `clocksource_jiffies`: The standard `jiffies` based clock source is the lowest common denominator clock source which should function on all systems. As we already know, the `jiffies` global variable will be increased during each timer interrupt. This means that standard `jiffies` based clock source has the same resolution as the timer interrupt frequency. From this we can understand that standard `jiffies` based clock source may suffer from inaccuracies. The `refined_jiffies` uses `CLOCK_TICK_RATE` as the base of `jiffies` shift.

Let's look on the implementation of this function. First of all we can see that the `refined_jiffies` clock source based on the `clocksource_jiffies` structure:

```C
int register_refined_jiffies(long cycles_per_second)
{
	u64 nsec_per_tick, shift_hz;
	long cycles_per_tick;

	refined_jiffies = clocksource_jiffies;
	refined_jiffies.name = "refined-jiffies";
	refined_jiffies.rating++;
	...
	...
	...
```

Here we can see that we update the name of the `refined_jiffies` to `refined-jiffies` and increase the rating of this structure. As you remember, the `clocksource_jiffies` has rating - `1`, so our `refined_jiffies` clocksource will have rating - `2`. This means that the `refined_jiffies` will be best selection for clock source management code.

In the next step we need to calculate number of cycles per one tick:

```C
cycles_per_tick = (cycles_per_second + HZ/2)/HZ;
```

Note that we have used `NSEC_PER_SEC` macro as the base of the standard `jiffies` multiplier. Here we are using the `cycles_per_second` which is the first parameter of the `register_refined_jiffies` function. We've passed the `CLOCK_TICK_RATE` macro to the `register_refined_jiffies` function. This macro definied in the [arch/x86/include/asm/timex.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/timex.h) header file and expands to the:

```C
#define CLOCK_TICK_RATE         PIT_TICK_RATE
```

where the `PIT_TICK_RATE` macro expands to the frequency of the [Intel 8253](Programmable interval timer):

```C
#define PIT_TICK_RATE 1193182ul
```

After this we calculate `shift_hz` for the `register_refined_jiffies` that will store `hz << 8` or in other words frequency of the system timer. We shift left the `cycles_per_second` or frequency of the programmable interval timer on `8` in order to get extra accuracy:

```C
shift_hz = (u64)cycles_per_second << 8;
shift_hz += cycles_per_tick/2;
do_div(shift_hz, cycles_per_tick);
```

In the next step we calculate the number of seconds per one tick by shifting left the `NSEC_PER_SEC` on `8` too as we did it with the `shift_hz` and do the same calculation as before:

```C
nsec_per_tick = (u64)NSEC_PER_SEC << 8;
nsec_per_tick += (u32)shift_hz/2;
do_div(nsec_per_tick, (u32)shift_hz);
```

```C
refined_jiffies.mult = ((u32)nsec_per_tick) << JIFFIES_SHIFT;
```

In the end of the `register_refined_jiffies` function we register new clock source with the `__clocksource_register` function that defined in the [include/linux/clocksource.h](https://github.com/torvalds/linux/blob/master/include/linux/clocksource.h) header file and return:

```C
__clocksource_register(&refined_jiffies);
return 0;
```

The clock source management code provides the API for clock source registration and selection. As we can see, clock sources are registered by calling the  `__clocksource_register` function during kernel initialization or from a kernel module. During registration, the clock source management code will choose the best clock source available in the system using the `clocksource.rating` field which we already saw when we initialized `clocksource` structure for `jiffies`.

Using the jiffies
--------------------------------------------------------------------------------

We just saw initialization of two `jiffies` based clock sources in the previous paragraph:

* standard `jiffies` based clock source;
* refined  `jiffies` based clock source;

Don't worry if you don't understand the calculations here. They look frightening at first. Soon, step by step we will learn these things. So, we just saw initialization of `jffies` based clock sources and also we know that the Linux kernel has the global variable `jiffies` that holds the number of ticks that have occurred since the kernel started to work. Now, let's look how to use it. To use `jiffies` we just can use `jiffies` global variable by its name or with the call of the `get_jiffies_64` function. This function defined in the [kernel/time/jiffies.c](https://github.com/torvalds/linux/blob/master/kernel/time/jiffies.c) source code file and just returns full `64-bit` value of the `jiffies`:

```C
u64 get_jiffies_64(void)
{
	unsigned long seq;
	u64 ret;

	do {
		seq = read_seqbegin(&jiffies_lock);
		ret = jiffies_64;
	} while (read_seqretry(&jiffies_lock, seq));
	return ret;
}
EXPORT_SYMBOL(get_jiffies_64);
```

Note that the `get_jiffies_64` function does not implemented as `jiffies_read` for example:

```C
static cycle_t jiffies_read(struct clocksource *cs)
{
	return (cycle_t) jiffies;
}
```

We can see that implementation of the `get_jiffies_64` is more complex. The reading of the `jiffies_64` variable is implemented using [seqlocks](https://en.wikipedia.org/wiki/Seqlock). Actually this is done for machines that cannot atomically read the full 64-bit values.

If we can access the `jiffies` or the `jiffies_64` variable we can convert it to `human` time units. To get one second we can use following expression:

```C
jiffies / HZ
```

So, if we know this, we can get any time units. For example:

```C
/* Thirty seconds from now */
jiffies + 30*HZ

/* Two minutes from now */
jiffies + 120*HZ

/* One millisecond from now */
jiffies + HZ / 1000
```

That's all.

Conclusion
--------------------------------------------------------------------------------

This concludes the first part covering time and time management related concepts in the Linux kernel. We met first two concepts and its initialization in this part: `jiffies` and `clocksource`. In the next part we will continue to dive into this interesting theme and as I already wrote in this part we will acquainted and try to understand insides of these and other time management concepts in the Linux kernel.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [system call](https://en.wikipedia.org/wiki/System_call)
* [TCP](https://en.wikipedia.org/wiki/Transmission_Control_Protocol)
* [lock validator](https://www.kernel.org/doc/Documentation/locking/lockdep-design.txt)
* [cgroups](https://en.wikipedia.org/wiki/Cgroups)
* [bss](https://en.wikipedia.org/wiki/.bss)
* [initrd](https://en.wikipedia.org/wiki/Initrd)
* [Intel MID](https://en.wikipedia.org/wiki/Mobile_Internet_device#Intel_MID_platforms)
* [TSC](https://en.wikipedia.org/wiki/Time_Stamp_Counter)
* [void](https://en.wikipedia.org/wiki/Void_type)
* [Simple Firmware Interface](https://en.wikipedia.org/wiki/Simple_Firmware_Interface)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [real time clock](https://en.wikipedia.org/wiki/Real-time_clock)
* [Jiffy](https://en.wikipedia.org/wiki/Jiffy_%28time%29)
* [high precision event timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer)
* [nanoseconds](https://en.wikipedia.org/wiki/Nanosecond)
* [Intel 8253](https://en.wikipedia.org/wiki/Intel_8253)
* [seqlocks](https://en.wikipedia.org/wiki/Seqlock)
* [cloksource documentation](https://www.kernel.org/doc/Documentation/timers/timekeeping.txt)
* [Previous chapter](https://0xax.gitbooks.io/linux-insides/content/SysCall/index.html)
