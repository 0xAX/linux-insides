Interrupts and Interrupt Handling. Part 10.
================================================================================

Last part
-------------------------------------------------------------------------------

This is the tenth part of the [chapter](http://0xax.gitbooks.io/linux-insides/content/interrupts/index.html) about interrupts and interrupt handling in the Linux kernel and in the previous [part](http://0xax.gitbooks.io/linux-insides/content/interrupts/interrupts-9.html) we saw a little about deferred interrupts and related concepts like `softirq`, `tasklet` and `workqeue`. In this part we will continue to dive into this theme and now it's time to look at real hardware driver.

Let's consider serial driver of the [StrongARM** SA-110/21285 Evaluation Board](http://netwinder.osuosl.org/pub/netwinder/docs/intel/datashts/27813501.pdf) board for example and will look how this driver requests an [IRQ](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29) line, 
what happens when an interrupt is triggered and etc. The source code of this driver is placed in the [drivers/tty/serial/21285.c](https://github.com/torvalds/linux/blob/master/drivers/tty/serial/21285.c) source code file. Ok, we have source code, let's start.

Initialization of a kernel module
--------------------------------------------------------------------------------

We will start to consider this driver as we usually did it with all new concepts that we saw in this book. We will start to consider it from the intialization. As you already may know, the Linux kernel provides two macros for initialization and finalization of a driver or a kernel module:

* `module_init`;
* `module_exit`.

And we can find usage of these macros in our driver source code:

```C
module_init(serial21285_init);
module_exit(serial21285_exit);
```

The most part of device drivers can be compiled as a loadable kernel [module](https://en.wikipedia.org/wiki/Loadable_kernel_module) or in another way they can be statically linked into the Linux kernel. In the first case initialization of a device driver will be produced via the `module_init` and `module_exit` macros that are defined in the [include/linux/init.h](https://github.com/torvalds/linux/blob/master/include/linux/init.h):

```C
#define module_init(initfn)                                     \
        static inline initcall_t __inittest(void)               \
        { return initfn; }                                      \
        int init_module(void) __attribute__((alias(#initfn)));

#define module_exit(exitfn)                                     \
        static inline exitcall_t __exittest(void)               \
        { return exitfn; }                                      \
        void cleanup_module(void) __attribute__((alias(#exitfn)));
```

and will be called by the [initcall](http://kernelnewbies.org/Documents/InitcallMechanism) functions:

* `early_initcall`
* `pure_initcall`
* `core_initcall`
* `postcore_initcall`
* `arch_initcall`
* `subsys_initcall`
* `fs_initcall`
* `rootfs_initcall`
* `device_initcall`
* `late_initcall`

that are called in the `do_initcalls` from the [init/main.c](https://github.com/torvalds/linux/blob/master/init/main.c). Otherwise, if a device driver is statically linked into the Linux kernel, implementation of these macros will be following:

```C
#define module_init(x)  __initcall(x);
#define module_exit(x)  __exitcall(x);
```

In this way implementation of module loading placed in the [kernel/module.c](https://github.com/torvalds/linux/blob/master/kernel/module.c) source code file and initialization occurs in the `do_init_module` function. We will not dive into details about loadable modules in this chapter, but will see it in the special chapter that will describe Linux kernel modules. Ok, the `module_init` macro takes one parameter - the `serial21285_init` in our case. As we can understand from function's name, this function does stuff related to the driver initialization. Let's look at it:

```C
static int __init serial21285_init(void)
{
	int ret;

	printk(KERN_INFO "Serial: 21285 driver\n");

	serial21285_setup_ports();

	ret = uart_register_driver(&serial21285_reg);
	if (ret == 0)
		uart_add_one_port(&serial21285_reg, &serial21285_port);

	return ret;
}
```

As we can see, first of all it prints information about the driver to the kernel buffer and the call of the `serial21285_setup_ports` function. This function setups the base [uart](https://en.wikipedia.org/wiki/Universal_asynchronous_receiver/transmitter) clock of the `serial21285_port` device:

```C
unsigned int mem_fclk_21285 = 50000000;

static void serial21285_setup_ports(void)
{
	serial21285_port.uartclk = mem_fclk_21285 / 4;
}
```

Here the `serial21285` is the structure that describes `uart` driver:

```C
static struct uart_driver serial21285_reg = {
	.owner			= THIS_MODULE,
	.driver_name	= "ttyFB",
	.dev_name		= "ttyFB",
	.major			= SERIAL_21285_MAJOR,
	.minor			= SERIAL_21285_MINOR,
	.nr			    = 1,
	.cons			= SERIAL_21285_CONSOLE,
};
```

If the driver registered successfully we attach the driver-defined port `serial21285_port` structure with the `uart_add_one_port` function from the [drivers/tty/serial/serial_core.c](https://github.com/torvalds/linux/blob/master/drivers/tty/serial/serial_core.c) source code file and return from the `serial21285_init` function:

```C
if (ret == 0)
	uart_add_one_port(&serial21285_reg, &serial21285_port);

return ret;
```

That's all. Our driver is initialized. When an `uart` port will be opened with the call of the `uart_open` function from the [drivers/tty/serial/serial_core.c](https://github.com/torvalds/linux/blob/master/drivers/tty/serial/serial_core.c), it will call the `uart_startup` function to start up the serial port. This function will call the `startup` function that is part of the `uart_ops` structure. Each `uart` driver has the definition of this structure, in our case it is:

```C
static struct uart_ops serial21285_ops = {
	...
	.startup	= serial21285_startup,
	...
}
```

`serial21285` structure. As we can see the `.strartup` field references on the `serial21285_startup` function. Implementation of this function is very interesting for us, because it is related to the interrupts and interrupt handling.

Requesting irq line
--------------------------------------------------------------------------------

Let's look at the implementation of the `serial21285` function:

```C
static int serial21285_startup(struct uart_port *port)
{
	int ret;

	tx_enabled(port) = 1;
	rx_enabled(port) = 1;

	ret = request_irq(IRQ_CONRX, serial21285_rx_chars, 0,
			  serial21285_name, port);
	if (ret == 0) {
		ret = request_irq(IRQ_CONTX, serial21285_tx_chars, 0,
				  serial21285_name, port);
		if (ret)
			free_irq(IRQ_CONRX, port);
	}

	return ret;
}
```

First of all about `TX` and `RX`. A serial bus of a device consists of just two wires: one for sending data and another for receiving. As such, serial devices should have two serial pins: the receiver - `RX`, and the transmitter - `TX`. With the call of first two macros: `tx_enabled` and `rx_enabled`, we enable these wires. The following part of these function is the greatest interest for us. Note on `request_irq` functions. This function registers an interrupt handler and enables a given interrupt line. Let's look at the implementation of this function and get into the details. This function defined in the [include/linux/interrupt.h](https://github.com/torvalds/linux/blob/master/include/linux/interrupt.h) header file and looks as:

```C
static inline int __must_check
request_irq(unsigned int irq, irq_handler_t handler, unsigned long flags,
            const char *name, void *dev)
{
        return request_threaded_irq(irq, handler, NULL, flags, name, dev);
}
```

As we can see, the `request_irq` function takes five parameters:

* `irq` - the interrupt number that being requested;
* `handler` - the pointer to the interrupt handler;
* `flags` - the bitmask options;
* `name` - the name of the owner of an interrupt;
* `dev` - the pointer used for shared interrupt lines;

Now let's look at the calls of the `request_irq` functions in our example. As we can see the first parameter is `IRQ_CONRX`. We know that it is number of the interrupt, but what is it `CONRX`? This macro defined in the [arch/arm/mach-footbridge/include/mach/irqs.h](https://github.com/torvalds/linux/blob/master/arch/arm/mach-footbridge/include/mach/irqs.h) header file. We can find the full list of interrupts that the `21285` board can generate. Note that in the second call of the `request_irq` function we pass the `IRQ_CONTX` interrupt number. Both these interrupts will handle `RX` and `TX` event in our driver. Implementation of these macros is easy:

```C
#define IRQ_CONRX               _DC21285_IRQ(0)
#define IRQ_CONTX               _DC21285_IRQ(1)
...
...
...
#define _DC21285_IRQ(x)         (16 + (x))
```

The [ISA](https://en.wikipedia.org/wiki/Industry_Standard_Architecture) IRQs on this board are from `0` to `15`, so, our interrupts will have first two numbers: `16` and `17`. Second parameters for two calls of the `request_irq` functions are `serial21285_rx_chars` and `serial21285_tx_chars`. These functions will be called when an `RX` or `TX` interrupt occurred. We will not dive in this part into details of these functions, because this chapter covers the interrupts and interrupts handling but not device and drivers. The next parameter - `flags` and as we can see, it is zero in both calls of the `request_irq` function. All acceptable flags are defined as `IRQF_*` macros in the [include/linux/interrupt.h](https://github.com/torvalds/linux/blob/master/include/linux/interrupt.h). Some of it:

* `IRQF_SHARED` - allows sharing the irq among several devices;
* `IRQF_PERCPU` - an interrupt is per cpu;
* `IRQF_NO_THREAD` - an interrupt cannot be threaded;
* `IRQF_NOBALANCING` - excludes this interrupt from irq balancing;
* `IRQF_IRQPOLL` - an interrupt is used for polling;
* and etc.

In our case we pass `0`, so it will be `IRQF_TRIGGER_NONE`. This flag means that it does not imply any kind of edge or level triggered interrupt behaviour. To the fourth parameter (`name`), we pass the `serial21285_name` that defined as:

```C
static const char serial21285_name[] = "Footbridge UART";
```

and will be displayed in the output of the `/proc/interrupts`. And in the last parameter we pass the pointer to the our main `uart_port` structure. Now we know a little about `request_irq` function and its parameters, let's look at its implemenetation. As we can see above, the `request_irq` function just makes a call of the `request_threaded_irq` function inside. The `request_threaded_irq` function defined in the [kernel/irq/manage.c](https://github.com/torvalds/linux/blob/master/kernel/irq/manage.c) source code file and allocates a given interrupt line. If we will look at this function, it starts from the definition of the `irqaction` and the `irq_desc`:

```C
int request_threaded_irq(unsigned int irq, irq_handler_t handler,
                         irq_handler_t thread_fn, unsigned long irqflags,
                         const char *devname, void *dev_id)
{
        struct irqaction *action;
        struct irq_desc *desc;
        int retval;
		...
		...
		...
}
```

We arelady saw the `irqaction` and the `irq_desc` structures in this chapter. The first structure represents per interrupt action descriptor and contains pointers to the interrupt handler, name of the device, interrupt number, etc. The second structure represents a descriptor of an interrupt and contains pointer to the `irqaction`, interrupt flags, etc. Note that the `request_threaded_irq` function called by the `request_irq` with the additioanal parameter: `irq_handler_t thread_fn`. If this parameter is not `NULL`, the `irq` thread will be created and the given `irq` handler will be executed in this thread. In the next step we need to make following checks:

```C
if (((irqflags & IRQF_SHARED) && !dev_id) ||
            (!(irqflags & IRQF_SHARED) && (irqflags & IRQF_COND_SUSPEND)) ||
            ((irqflags & IRQF_NO_SUSPEND) && (irqflags & IRQF_COND_SUSPEND)))
               return -EINVAL;
```

First of all we check that real `dev_id` is passed for the shared interrupt and the `IRQF_COND_SUSPEND` only makes sense for shared interrupts. Otherwise we exit from this function with the `-EINVAL` error. After this we convert the given `irq` number to the `irq` descriptor wit the help of the `irq_to_desc` function that defined in the [kernel/irq/irqdesc.c](https://github.com/torvalds/linux/blob/master/kernel/irq/irqdesc.c) source code file and exit from this function with the `-EINVAL` error if it was not successful:

```C
desc = irq_to_desc(irq);
if (!desc)
    return -EINVAL;
```

The `irq_to_desc` function checks that given `irq` number is less than maximum number of IRQs and returns the irq descriptor where the `irq` number is offset from the `irq_desc` array:

```C
struct irq_desc *irq_to_desc(unsigned int irq)
{
        return (irq < NR_IRQS) ? irq_desc + irq : NULL;
}
```

As we have converted `irq` number to the `irq` descriptor we make the check the status of the descriptor that an interrupt can be requested:

```C
if (!irq_settings_can_request(desc) || WARN_ON(irq_settings_is_per_cpu_devid(desc)))
    return -EINVAL;
```

and exit with the `-EINVAL` in othre way. After this we check the given interrupt handler. If it was not passed to the `request_irq` function, we check the `thread_fn`. If both handlers are `NULL`, we return with the `-EINVAL`. If an interrupt handler was not passed to the `request_irq` function, but the `thread_fn` is not null, we set handler to the `irq_default_primary_handler`:

```C
if (!handler) {
    if (!thread_fn)
        return -EINVAL;
	handler = irq_default_primary_handler;
}
```

In the next step we allocate memory for our `irqaction` with the `kzalloc` function and return from the function if this operation was not successful:

```C
action = kzalloc(sizeof(struct irqaction), GFP_KERNEL);
if (!action)
    return -ENOMEM;
```

More about `kzalloc` will be in the separate chapter about [memory management](http://0xax.gitbooks.io/linux-insides/content/mm/index.html) in the Linux kernel. As we allocated space for the `irqaction`, we start to initialize this structure with the values of interrupt handler, interrupt flags, device name, etc:

```C
action->handler = handler;
action->thread_fn = thread_fn;
action->flags = irqflags;
action->name = devname;
action->dev_id = dev_id;
```

In the end of the `request_threaded_irq` function we call the `__setup_irq` function from the [kernel/irq/manage.c](https://github.com/torvalds/linux/blob/master/kernel/irq/manage.c) and registers a given `irqaction`. Release memory for the `irqaction` and return:

```C
chip_bus_lock(desc);
retval = __setup_irq(irq, desc, action);
chip_bus_sync_unlock(desc);

if (retval)
	kfree(action);

return retval;
```

Note that the call of the `__setup_irq` function is placed between the `chip_bus_lock` and the `chip_bus_sync_unlock` functions. These functions locl/unlock access to slow bus (like [i2c](https://en.wikipedia.org/wiki/I%C2%B2C)) chips. Now let's look at the implementation of the `__setup_irq` function. In the beginning of the `__setup_irq` function we can see a couple of different checks. First of all we check that the given interrupt descriptor is not `NULL`, `irqchip` is not `NULL` and that given interrupt descriptor module owner is not `NULL`. After this we check is interrupt nest into another interrupt thread or not, and if it is nested we replace the `irq_default_primary_handler` with the `irq_nested_primary_handler`.

In the next step we create an irq handler thread with the `kthread_create` function, if the given interrupt is not nested and the `thread_fn` is not `NULL`:

```C
if (new->thread_fn && !nested) {
	struct task_struct *t;
	t = kthread_create(irq_thread, new, "irq/%d-%s", irq, new->name);
	...
}
```

And fill the rest of the given interrupt descriptor fields in the end. So, our `16` and `17` interrupt request lines are registered and the `serial21285_rx_chars` and `serial21285_tx_chars` functions will be invoked when an interrupt controller will get event releated to these interrupts. Now let's look at what happens when an interrupt occurs. 

Prepare to handle an interrupt
--------------------------------------------------------------------------------

In the previous paragraph we saw the requesting of the irq line for the given interrupt descriptor and registration of the `irqaction` structure for the given interrupt. We already know that when an interrupt event occurs, an interrupt controller notifies the processor about this event and processor tries to find appropriate interrupt gate for this interrupt. If you have read the eighth [part](http://0xax.gitbooks.io/linux-insides/content/interrupts/interrupts-8.html) of this chapter, you may remember the `native_init_IRQ` function. This function makes initialization of the local [APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller). The following part of this function is the most interesting part for us right now: 

```C
for_each_clear_bit_from(i, used_vectors, first_system_vector) {
	set_intr_gate(i, irq_entries_start +
		8 * (i - FIRST_EXTERNAL_VECTOR));
}
```

Here we iterate over all the cleared bit of the `used_vectors` bitmap starting at `first_system_vector` that is:

```C
int first_system_vector = FIRST_SYSTEM_VECTOR; // 0xef
```

and set interrupt gates with the `i` vector number and the `irq_entries_start + 8 * (i - FIRST_EXTERNAL_VECTOR)` start address. Only one things is unclear here - the `irq_entries_start`. This symbol defined in the [arch/x86/entry/entry_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/entry_entry_64.S) assembly file and provides `irq` entries. Let's look at it:

```assembly
	.align 8
ENTRY(irq_entries_start)
    vector=FIRST_EXTERNAL_VECTOR
    .rept (FIRST_SYSTEM_VECTOR - FIRST_EXTERNAL_VECTOR)
	pushq	$(~vector+0x80)
    vector=vector+1
	jmp	common_interrupt
	.align	8
    .endr
END(irq_entries_start)
```

Here we can see the [GNU assembler](https://en.wikipedia.org/wiki/GNU_Assembler) `.rept` instruction which repeats the sequence of lines that are before `.endr` - `FIRST_SYSTEM_VECTOR - FIRST_EXTERNAL_VECTOR` times. As we already know, the `FIRST_SYSTEM_VECTOR` is `0xef`, and the `FIRST_EXTERNAL_VECTOR` is equal to `0x20`. So, it will work:

```python
>>> 0xef - 0x20
207
```

times. In the body of the `.rept` instruction we push entry stubs on the stack (note that we use negative numbers for the interrupt vector numbers, because positive numbers already reserved to identify [system calls](https://en.wikipedia.org/wiki/System_call)), increase the `vector` variable and jump on the `common_interrupt` label. In the `common_interrupt` we adjust vector number on the stack and execute `interrupt` number with the `do_IRQ` parameter:

```assembly
common_interrupt:
	addq	$-0x80, (%rsp)
	interrupt do_IRQ
```

The macro `interrupt` defined in the same source code file and saves [general purpose](https://en.wikipedia.org/wiki/Processor_register) registers on the stack, change the userspace `gs` on the kernel with the `SWAPGS` assembler instruction if need, increase [per-cpu](http://0xax.gitbooks.io/linux-insides/content/Concepts/per-cpu.html) - `irq_count` variable that shows that we are in interrupt and call the `do_IRQ` function. This function defined in the [arch/x86/kernel/irq.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/irq.c) source code file and handles our device interrupt. Let's look at this function. The `do_IRQ` function takes one parameter - `pt_regs` structure that stores values of the userspace registers:

```C
__visible unsigned int __irq_entry do_IRQ(struct pt_regs *regs)
{
    struct pt_regs *old_regs = set_irq_regs(regs);
    unsigned vector = ~regs->orig_ax;
    unsigned irq;

	irq_enter();
    exit_idle();
	...
	...
	...
}
```

At the beginning of this function we can see call of the `set_irq_regs` function that returns saved `per-cpu` irq register pointer and the calls of the `irq_enter` and `exit_idle` functions. The first function `irq_enter` enters to an interrupt context with the updating `__preempt_count` variable and the second function - `exit_idle` checks that current process is `idle` with [pid](https://en.wikipedia.org/wiki/Process_identifier) - `0` and notify the `idle_notifier` with the `IDLE_END`.

In the next step we read the `irq` for the current cpu and call the `handle_irq` function:

```C
irq = __this_cpu_read(vector_irq[vector]);

if (!handle_irq(irq, regs)) {
	...
	...
	...
}
...
...
...
```

The `handle_irq` function defined in the [arch/x86/kernel/irq_64.c](https://github.com/torvalds/linux/blob/arch/x86/kernel/irq_64.c) source code file, checks the given interrupt descriptor and call the `generic_handle_irq_desc`:

```C
desc = irq_to_desc(irq);
	if (unlikely(!desc))
		return false;
generic_handle_irq_desc(irq, desc);
```

Where the `generic_handle_irq_desc` calls the interrupt handler:

```C
static inline void generic_handle_irq_desc(unsigned int irq, struct irq_desc *desc)
{
       desc->handle_irq(irq, desc);
}
```

But stop... What is it `handle_irq` and why do we call our interrupt handler from the interrupt descriptor when we know that `irqaction` points to the actual interrupt handler? Actually the `irq_desc->handle_irq` is a high-level API for the calling interrupt handler routine. It setups during initialization of the [device tree](https://en.wikipedia.org/wiki/Device_tree) and [APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller) initialization. The kernel selects correct function and call chain of the `irq->action(s)` there. In this way, the `serial21285_tx_chars` or the `serial21285_rx_chars` function will be executed after an interrupt will occur.

In the end of the `do_IRQ` function we call the `irq_exit` function that will exit from the interrupt context, the `set_irq_regs` with the old userspace registers and return:

```C
irq_exit();
set_irq_regs(old_regs);
return 1;
```

We already know that when an `IRQ` finishes its work, deferred interrupts will be executed if they exist.

Exit from interrupt
--------------------------------------------------------------------------------

Ok, the interrupt handler finished its execution and now we must return from the interrupt. When the work of the `do_IRQ` function will be finsihed, we will return back to the assembler code in the [arch/x86/entry/entry_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/entry_entry_64.S) to the `ret_from_intr` label. First of all we disable interrupts with the `DISABLE_INTERRUPTS` macro that expands to the `cli` instruction and decreases value of the `irq_count` [per-cpu](http://0xax.gitbooks.io/linux-insides/content/Concepts/per-cpu.html) variable. Remember, this variable had value - `1`, when we were in interrupt context:

```assembly
DISABLE_INTERRUPTS(CLBR_NONE)
TRACE_IRQS_OFF
decl	PER_CPU_VAR(irq_count)
```

In the last step we check the previous context (user or kernel), restore it in a correct way and exit from an interrupt with the:

```assembly
INTERRUPT_RETURN
```

where the `INTERRUPT_RETURN` macro is:

```C
#define INTERRUPT_RETURN	jmp native_iret
```

and

```assembly
ENTRY(native_iret)

.global native_irq_return_iret
native_irq_return_iret:
	iretq
```

That's all.

Conclusion
--------------------------------------------------------------------------------

It is the end of the tenth part of the [Interrupts and Interrupt Handling](http://0xax.gitbooks.io/linux-insides/content/interrupts/index.html) chapter and as you have read in the beginning of this part - it is the last part of this chapter. This chapter started from the explanation of the theory of interrupts and we have learned what is it interrupt and kinds of interrupts, then we saw exceptions and handling of this kind of interrupts, deferred interrupts and finally we looked on the hardware interrupts and the handling of theirs in this part. Of course, this part and even this chapter does not cover full aspects of interrupts and interrupt handling in the Linux kernel. It is not realistic to do this. At least for me. It was the big part, I don't know how about you, but it was really big for me. This theme is much bigger than this chapter and I am not sure that somewhere there is a book that covers it. We have missed many part and aspects of interrupts and interrupt handling, but I think it will be good point to dive in the kernel code related to the interrupts and interrupts handling.

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Serial driver documentation](https://www.kernel.org/doc/Documentation/serial/driver)
* [StrongARM** SA-110/21285 Evaluation Board](http://netwinder.osuosl.org/pub/netwinder/docs/intel/datashts/27813501.pdf)
* [IRQ](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29)
* [module](https://en.wikipedia.org/wiki/Loadable_kernel_module)
* [initcall](http://kernelnewbies.org/Documents/InitcallMechanism)
* [uart](https://en.wikipedia.org/wiki/Universal_asynchronous_receiver/transmitter) 
* [ISA](https://en.wikipedia.org/wiki/Industry_Standard_Architecture) 
* [memory management](http://0xax.gitbooks.io/linux-insides/content/mm/index.html)
* [i2c](https://en.wikipedia.org/wiki/I%C2%B2C)
* [APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller)
* [GNU assembler](https://en.wikipedia.org/wiki/GNU_Assembler)
* [Processor register](https://en.wikipedia.org/wiki/Processor_register)
* [per-cpu](http://0xax.gitbooks.io/linux-insides/content/Concepts/per-cpu.html)
* [pid](https://en.wikipedia.org/wiki/Process_identifier)
* [device tree](https://en.wikipedia.org/wiki/Device_tree)
* [system calls](https://en.wikipedia.org/wiki/System_call)
* [Previous part](http://0xax.gitbooks.io/linux-insides/content/interrupts/interrupts-9.html)
