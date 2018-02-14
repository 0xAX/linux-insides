Timers and time management in the Linux kernel. Part 5.
================================================================================

Introduction to the `clockevents` framework
--------------------------------------------------------------------------------

This is fifth part of the [chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html) which describes timers and time management related stuff in the Linux kernel. As you might noted from the title of this part, the `clockevents` framework will be discussed. We already saw one framework in the [second](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-2.html) part of this chapter. It was `clocksource` framework. Both of these frameworks represent timekeeping abstractions in the Linux kernel.

At first let's refresh your memory and try to remember what is it `clocksource` framework and and what its purpose. The main goal of the `clocksource` framework is to provide `timeline`. As described in the [documentation](https://github.com/0xAX/linux/blob/0a07b238e5f488b459b6113a62e06b6aab017f71/Documentation/timers/timekeeping.txt):

> For example issuing the command 'date' on a Linux system will eventually read the clock source to determine exactly what time it is.

The Linux kernel supports many different clock sources. You can find some of them in the [drivers/closksource](https://github.com/torvalds/linux/tree/master/drivers/clocksource). For example old good [Intel 8253](https://en.wikipedia.org/wiki/Intel_8253) - [programmable interval timer](https://en.wikipedia.org/wiki/Programmable_interval_timer) with `1193182` Hz frequency, yet another one - [ACPI PM](http://uefi.org/sites/default/files/resources/ACPI_5.pdf) timer with `3579545` Hz frequency. Besides the [drivers/closksource](https://github.com/torvalds/linux/tree/master/drivers/clocksource) directory, each architecture may provide own architecture-specific clock sources. For example [x86](https://en.wikipedia.org/wiki/X86) architecture provides [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer), or for example [powerpc](https://en.wikipedia.org/wiki/PowerPC) provides access to the processor timer through `timebase` register.

Each clock source provides monotonic atomic counter. As I already wrote, the Linux kernel supports a huge set of different clock source and each clock source has own parameters like [frequency](https://en.wikipedia.org/wiki/Frequency). The main goal of the `clocksource` framework is to provide [API](https://en.wikipedia.org/wiki/Application_programming_interface) to select best available clock source in the system i.e. a clock source with the highest frequency. Additional goal of the `clocksource` framework is to represent an atomic counter provided by a clock source in human units. In this time, nanoseconds are the favorite choice for the time value units of the given clock source in the Linux kernel.

The `clocksource` framework represented by the `clocksource` structure which is defined in the [include/linux/clocksource.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/clocksource.h) header code file which contains `name` of a clock source, rating of certain clock source in the system (a clock source with the higher frequency has the biggest rating in the system), `list` of all registered clock source in the system, `enable` and `disable` fields to enable and disable a clock source, pointer to the `read` function which must return an atomic counter of a clock source and etc.

Additionally the `clocksource` structure provides two fields: `mult` and `shift` which are needed for translation of an atomic counter which is provided by a certain clock source to the human units, i.e. [nanoseconds](https://en.wikipedia.org/wiki/Nanosecond). Translation occurs via following formula:

```
ns ~= (clocksource * mult) >> shift
```

As we already know, besides the `clocksource` structure, the `clocksource` framework provides an API for registration of clock source with different frequency scale factor:

```C
static inline int clocksource_register_hz(struct clocksource *cs, u32 hz)
static inline int clocksource_register_khz(struct clocksource *cs, u32 khz)
```

A clock source unregistration:

```C
int clocksource_unregister(struct clocksource *cs)
```

and etc.

Additionally to the `clocksource` framework, the Linux kernel provides `clockevents` framework. As described in the [documentation](https://github.com/0xAX/linux/blob/0a07b238e5f488b459b6113a62e06b6aab017f71/Documentation/timers/timekeeping.txt):

> Clock events are the conceptual reverse of clock sources

Main goal of the is to manage clock event devices or in other words - to manage devices that allow to register an event or in other words [interrupt](https://en.wikipedia.org/wiki/Interrupt) that is going to happen at a defined point of time in the future.

Now we know a little about the `clockevents` framework in the Linux kernel, and now time is to see on it [API](https://en.wikipedia.org/wiki/Application_programming_interface).

API of `clockevents` framework
-------------------------------------------------------------------------------

The main structure which described a clock event device is `clock_event_device` structure. This structure is defined in the [include/linux/clockchips.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/clockchips.h) header file and contains a huge set of fields. as well as the `clocksource` structure it has `name` fields which contains human readable name of a clock event device, for example [local APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller) timer:

```C
static struct clock_event_device lapic_clockevent = {
    .name                   = "lapic",
    ...
    ...
    ...
}
```

Addresses of the `event_handler`, `set_next_event`, `next_event` functions for a certain clock event device which are an [interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler), setter of next event and local storage for next event respectively. Yet another field of the `clock_event_device` structure is - `features` field. Its value maybe on of the following generic features:

```C
#define CLOCK_EVT_FEAT_PERIODIC	0x000001
#define CLOCK_EVT_FEAT_ONESHOT		0x000002
```

Where the `CLOCK_EVT_FEAT_PERIODIC` represents device which may be programmed to generate events periodically. The `CLOCK_EVT_FEAT_ONESHOT` represents device which may generate an event only once. Besides these two features, there are also architecture-specific features. For example [x86_64](https://en.wikipedia.org/wiki/X86-64) supports two additional features:

```C
#define CLOCK_EVT_FEAT_C3STOP		0x000008
```

The first `CLOCK_EVT_FEAT_C3STOP` means that a clock event device will be stopped in the [C3](https://en.wikipedia.org/wiki/Advanced_Configuration_and_Power_Interface#Device_states) state. Additionally the `clock_event_device` structure has `mult` and `shift` fields as well as `clocksource` structure. The `clocksource` structure also contains other fields, but we will consider it later.

After we considered part of the `clock_event_device` structure, time is to look at the `API` of the `clockevents` framework. To work with a clock event device, first of all we need to initialize `clock_event_device` structure and register a clock events device. The `clockevents` framework provides following `API` for registration of clock event devices:

```C
void clockevents_register_device(struct clock_event_device *dev)
{
   ...
   ...
   ...
}
```

This function defined in the [kernel/time/clockevents.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/time/clockevents.c) source code file and as we may see, the `clockevents_register_device` function takes only one parameter:

* address of a `clock_event_device` structure which represents a clock event device.

So, to register a clock event device, at first we need to initialize `clock_event_device` structure with parameters of a certain clock event device. Let's take a look at one random clock event device in the Linux kernel source code. We can find one in the [drivers/closksource](https://github.com/torvalds/linux/tree/master/drivers/clocksource) directory or try to take a look at an architecture-specific clock event device. Let's take for example - [Periodic Interval Timer (PIT) for at91sam926x](http://www.atmel.com/Images/doc6062.pdf). You can find its implementation in the [drivers/closksource](https://github.com/torvalds/linux/tree/master/drivers/clocksource/timer-atmel-pit.c).

First of all let's look at initialization of the `clock_event_device` structure. This occurs in the `at91sam926x_pit_common_init` function:

```C
struct pit_data {
    ...
    ...
    struct clock_event_device       clkevt;
    ...
    ...
};

static void __init at91sam926x_pit_common_init(struct pit_data *data)
{
    ...
    ...
    ...
    data->clkevt.name = "pit";
    data->clkevt.features = CLOCK_EVT_FEAT_PERIODIC;
    data->clkevt.shift = 32;
    data->clkevt.mult = div_sc(pit_rate, NSEC_PER_SEC, data->clkevt.shift);
    data->clkevt.rating = 100;
    data->clkevt.cpumask = cpumask_of(0);

    data->clkevt.set_state_shutdown = pit_clkevt_shutdown;
    data->clkevt.set_state_periodic = pit_clkevt_set_periodic;
    data->clkevt.resume = at91sam926x_pit_resume;
    data->clkevt.suspend = at91sam926x_pit_suspend;
    ...
}
```

Here we can see that `at91sam926x_pit_common_init` takes one parameter - pointer to the `pit_data` structure which contains `clock_event_device` structure which will contain clock event related information of the `at91sam926x` [periodic Interval Timer](https://en.wikipedia.org/wiki/Programmable_interval_timer). At the start we fill `name` of the timer device and its `features`. In our case we deal with periodic timer which as we already know may be programmed to generate events periodically.

The next two fields `shift` and `mult` are familiar to us. They will be used to translate counter of our timer to nanoseconds. After this we set rating of the timer  to `100`. This means if there will not be timers with higher rating in the system, this timer will be used for timekeeping. The next field - `cpumask` indicates for which processors in the system the device will work. In our case, the device will work for the first processor. The `cpumask_of` macro defined in the [include/linux/cpumask.h](https://github.com/torvalds/linux/tree/master/include/linux/cpumask.h) header file and just expands to the call of the:

```C
#define cpumask_of(cpu) (get_cpu_mask(cpu))
```

Where the `get_cpu_mask` returns the cpumask containing just a given `cpu` number. More about `cpumasks` concept you may read in the [CPU masks in the Linux kernel](https://0xax.gitbooks.io/linux-insides/content/Concepts/cpumask.html) part. In the last four lines of code we set callbacks for the clock event device suspend/resume, device shutdown and update of the clock event device state.

After we finished with the initialization of the `at91sam926x` periodic timer, we can register it by the call of the following functions:

```C
clockevents_register_device(&data->clkevt);
```

Now we can consider implementation of the `clockevent_register_device` function. As I already wrote above, this function is defined in the [kernel/time/clockevents.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/time/clockevents.c) source code file and starts from the initialization of the initial event device state:

```C
clockevent_set_state(dev, CLOCK_EVT_STATE_DETACHED);
```

Actually, an event device may be in one of this states:

```C
enum clock_event_state {
	CLOCK_EVT_STATE_DETACHED,
	CLOCK_EVT_STATE_SHUTDOWN,
	CLOCK_EVT_STATE_PERIODIC,
	CLOCK_EVT_STATE_ONESHOT,
	CLOCK_EVT_STATE_ONESHOT_STOPPED,
};
```

Where:

* `CLOCK_EVT_STATE_DETACHED` - a clock event device is not not used by `clockevents` framework. Actually it is initial state of all clock event devices;
* `CLOCK_EVT_STATE_SHUTDOWN` - a clock event device is powered-off;
* `CLOCK_EVT_STATE_PERIODIC` - a clock event device may be programmed to generate event periodically;
* `CLOCK_EVT_STATE_ONESHOT`  - a clock event device may be programmed to generate event only once;
* `CLOCK_EVT_STATE_ONESHOT_STOPPED` - a clock event device was programmed to generate event only once and now it is temporary stopped.

The implementation of the `clock_event_set_state` function is pretty easy:

```C
static inline void clockevent_set_state(struct clock_event_device *dev,
					enum clock_event_state state)
{
	dev->state_use_accessors = state;
}
```

As we can see, it just fills the `state_use_accessors` field of the given `clock_event_device` structure with the given value which is in our case is `CLOCK_EVT_STATE_DETACHED`. Actually all clock event devices has this initial state during registration. The `state_use_accessors` field of the `clock_event_device` structure provides `current` state of the clock event device.

After we have set initial state of the given `clock_event_device` structure we check that the `cpumask` of the given clock event device is not zero:

```C
if (!dev->cpumask) {
	WARN_ON(num_possible_cpus() > 1);
	dev->cpumask = cpumask_of(smp_processor_id());
}
```

Remember that we have set the `cpumask` of the `at91sam926x` periodic timer to first processor. If the `cpumask` field is zero, we check the number of possible processors in the system and print warning message if it is less than on. Additionally we set the `cpumask` of the given clock event device to the current processor. If you are interested in how the `smp_processor_id` macro is implemented, you can read more about it in the fourth [part](https://0xax.gitbooks.io/linux-insides/content/Initialization/linux-initialization-4.html) of the Linux kernel initialization process chapter.

After this check we lock the actual code of the clock event device registration by the call following macros:

```C
raw_spin_lock_irqsave(&clockevents_lock, flags);
...
...
...
raw_spin_unlock_irqrestore(&clockevents_lock, flags);
```

Additionally the `raw_spin_lock_irqsave` and the `raw_spin_unlock_irqrestore` macros disable local interrupts, however interrupts on other processors still may occur. We need to do it to prevent potential [deadlock](https://en.wikipedia.org/wiki/Deadlock) if we adding new clock event device to the list of clock event devices and an interrupt occurs from other clock event device.

We can see following code of clock event device registration between the `raw_spin_lock_irqsave` and `raw_spin_unlock_irqrestore` macros:

```C
list_add(&dev->list, &clockevent_devices);
tick_check_new_device(dev);
clockevents_notify_released();
```

First of all we add the given clock event device to the list of clock event devices which is represented by the `clockevent_devices`:

```C
static LIST_HEAD(clockevent_devices);
```

At the next step we call the `tick_check_new_device` function which is defined in the [kernel/time/tick-common.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/time/tick-common.c) source code file and checks do the new registered clock event device should be used or not. The `tick_check_new_device` function checks the given `clock_event_device` gets the current registered tick device which is represented by the `tick_device` structure and compares their ratings and features. Actually `CLOCK_EVT_STATE_ONESHOT` is preferred:

```C
static bool tick_check_preferred(struct clock_event_device *curdev,
				 struct clock_event_device *newdev)
{
	if (!(newdev->features & CLOCK_EVT_FEAT_ONESHOT)) {
		if (curdev && (curdev->features & CLOCK_EVT_FEAT_ONESHOT))
			return false;
		if (tick_oneshot_mode_active())
			return false;
	}

	return !curdev ||
		newdev->rating > curdev->rating ||
	       !cpumask_equal(curdev->cpumask, newdev->cpumask);
}
```

If the new registered clock event device is more preferred than old tick device, we exchange old and new registered devices and install new device:

```C
clockevents_exchange_device(curdev, newdev);
tick_setup_device(td, newdev, cpu, cpumask_of(cpu));
```

The `clockevents_exchange_device` function releases or in other words deleted the old clock event device from the `clockevent_devices` list. The next function - `tick_setup_device` as we may understand from its name, setups new tick device. This function check the mode of the new registered clock event device and call the `tick_setup_periodic` function or the `tick_setup_oneshot` depends on the tick device mode:

```C
if (td->mode == TICKDEV_MODE_PERIODIC)
	tick_setup_periodic(newdev, 0);
else
	tick_setup_oneshot(newdev, handler, next_event);
```

Both of this functions calls the `clockevents_switch_state` to change state of the clock event device and the `clockevents_program_event` function to set next event of clock event device based on delta between the maximum and minimum difference current time and time for the next event. The `tick_setup_periodic`:

```C
clockevents_switch_state(dev, CLOCK_EVT_STATE_PERIODIC);
clockevents_program_event(dev, next, false))
```

and the `tick_setup_oneshot_periodic`:

```C
clockevents_switch_state(newdev, CLOCK_EVT_STATE_ONESHOT);
clockevents_program_event(newdev, next_event, true);
```

The `clockevents_switch_state` function checks that the clock event device is not in the given state and calls the `__clockevents_switch_state` function from the same source code file:

```C
if (clockevent_get_state(dev) != state) {
	if (__clockevents_switch_state(dev, state))
		return;
```

The `__clockevents_switch_state` function just makes a call of the certain callback depends on the given state:

```C
static int __clockevents_switch_state(struct clock_event_device *dev,
				      enum clock_event_state state)
{
	if (dev->features & CLOCK_EVT_FEAT_DUMMY)
		return 0;

	switch (state) {
	case CLOCK_EVT_STATE_DETACHED:
	case CLOCK_EVT_STATE_SHUTDOWN:
		if (dev->set_state_shutdown)
			return dev->set_state_shutdown(dev);
		return 0;

	case CLOCK_EVT_STATE_PERIODIC:
		if (!(dev->features & CLOCK_EVT_FEAT_PERIODIC))
			return -ENOSYS;
		if (dev->set_state_periodic)
			return dev->set_state_periodic(dev);
		return 0;
    ...
    ...
    ...
```

In our case for `at91sam926x` periodic timer, the state is the `CLOCK_EVT_FEAT_PERIODIC`:

```C
data->clkevt.features = CLOCK_EVT_FEAT_PERIODIC;
data->clkevt.set_state_periodic = pit_clkevt_set_periodic;
```

So, for the `pit_clkevt_set_periodic` callback will be called. If we will read the documentation of the [Periodic Interval Timer (PIT) for at91sam926x](http://www.atmel.com/Images/doc6062.pdf), we will see that there is `Periodic Interval Timer Mode Register` which allows us to control of periodic interval timer.

It looks like:

```
31                                                   25        24
+---------------------------------------------------------------+
|                                          |  PITIEN  |  PITEN  |
+---------------------------------------------------------------+
23                            19                               16
+---------------------------------------------------------------+
|                             |               PIV               |
+---------------------------------------------------------------+
15                                                              8
+---------------------------------------------------------------+
|                            PIV                                |
+---------------------------------------------------------------+
7                                                               0
+---------------------------------------------------------------+
|                            PIV                                |
+---------------------------------------------------------------+
```

Where `PIV` or `Periodic Interval Value` - defines the value compared with the primary `20-bit` counter of the Periodic Interval Timer. The `PITEN` or `Period Interval Timer Enabled` if the bit is `1` and the `PITIEN` or `Periodic Interval Timer Interrupt Enable` if the bit is `1`. So, to set periodic mode, we need to set `24`, `25` bits in the `Periodic Interval Timer Mode Register`. And we are doing it in the `pit_clkevt_set_periodic` function:

```C
static int pit_clkevt_set_periodic(struct clock_event_device *dev)
{
        struct pit_data *data = clkevt_to_pit_data(dev);
        ...
        ...
        ...
        pit_write(data->base, AT91_PIT_MR,
                  (data->cycle - 1) | AT91_PIT_PITEN | AT91_PIT_PITIEN);

        return 0;
}
```

Where the `AT91_PT_MR`, `AT91_PT_PITEN` and the `AT91_PIT_PITIEN` are declared as:

```C
#define AT91_PIT_MR             0x00
#define AT91_PIT_PITIEN       BIT(25)
#define AT91_PIT_PITEN        BIT(24)
```

After the setup of the new clock event device is finished, we can return to the `clockevents_register_device` function. The last function in the `clockevents_register_device` function is:

```C
clockevents_notify_released();
```

This function checks the `clockevents_released` list which contains released clock event devices (remember that they may occur after the call of the ` clockevents_exchange_device` function). If this list is not empty, we go through clock event devices from the `clock_events_released` list and delete it from the `clockevent_devices`:

```C
static void clockevents_notify_released(void)
{
	struct clock_event_device *dev;

	while (!list_empty(&clockevents_released)) {
		dev = list_entry(clockevents_released.next,
				 struct clock_event_device, list);
		list_del(&dev->list);
		list_add(&dev->list, &clockevent_devices);
		tick_check_new_device(dev);
	}
}
```

That's all. From this moment we have registered new clock event device. So the usage of the `clockevents` framework is simple and clear. Architectures registered their clock event devices, in the clock events core. Users of the clockevents core can get clock event devices for their use. The `clockevents` framework provides notification mechanisms for various clock related management events like a clock event device registered or unregistered, a processor is offlined in system which supports [CPU hotplug](https://www.kernel.org/doc/Documentation/cpu-hotplug.txt) and etc.

We saw implementation only of the `clockevents_register_device` function. But generally, the clock event layer [API](https://en.wikipedia.org/wiki/Application_programming_interface) is small. Besides the `API` for clock event device registration, the `clockevents` framework provides functions to schedule the next event interrupt, clock event device notification service and support for suspend and resume for clock event devices.

If you want to know more about `clockevents` API you can start to research following source code and header files: [kernel/time/tick-common.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/time/tick-common.c), [kernel/time/clockevents.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/time/clockevents.c) and [include/linux/clockchips.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/clockchips.h).

That's all.

Conclusion
-------------------------------------------------------------------------------

This is the end of the fifth part of the [chapter](https://0xax.gitbooks.io/linux-insides/content/Timers/index.html) that describes timers and timer management related stuff in the Linux kernel. In the previous part got acquainted with the `timers` concept. In this part we continued to learn time management related stuff in the Linux kernel and saw a little about yet another framework - `clockevents`.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
-------------------------------------------------------------------------------

* [timekeeping documentation](https://github.com/0xAX/linux/blob/0a07b238e5f488b459b6113a62e06b6aab017f71/Documentation/timers/timekeeping.txt)
* [Intel 8253](https://en.wikipedia.org/wiki/Intel_8253)
* [programmable interval timer](https://en.wikipedia.org/wiki/Programmable_interval_timer)
* [ACPI pdf](http://uefi.org/sites/default/files/resources/ACPI_5.pdf)
* [x86](https://en.wikipedia.org/wiki/X86)
* [High Precision Event Timer](https://en.wikipedia.org/wiki/High_Precision_Event_Timer)
* [powerpc](https://en.wikipedia.org/wiki/PowerPC)
* [frequency](https://en.wikipedia.org/wiki/Frequency)
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [nanoseconds](https://en.wikipedia.org/wiki/Nanosecond)
* [interrupt](https://en.wikipedia.org/wiki/Interrupt)
* [interrupt handler](https://en.wikipedia.org/wiki/Interrupt_handler)
* [local APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller)
* [C3 state](https://en.wikipedia.org/wiki/Advanced_Configuration_and_Power_Interface#Device_states) 
* [Periodic Interval Timer (PIT) for at91sam926x](http://www.atmel.com/Images/doc6062.pdf)
* [CPU masks in the Linux kernel](https://0xax.gitbooks.io/linux-insides/content/Concepts/cpumask.html)
* [deadlock](https://en.wikipedia.org/wiki/Deadlock)
* [CPU hotplug](https://www.kernel.org/doc/Documentation/cpu-hotplug.txt)
* [previous part](https://0xax.gitbooks.io/linux-insides/content/Timers/timers-3.html)
