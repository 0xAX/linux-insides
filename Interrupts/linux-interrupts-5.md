Interrupts and Interrupt Handling. Part 5.
================================================================================

Implementation of exception handlers
--------------------------------------------------------------------------------

This is the fifth part about an interrupts and exceptions handling in the Linux kernel and in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-4) we stopped on the setting of interrupt gates to the [Interrupt descriptor Table](https://en.wikipedia.org/wiki/Interrupt_descriptor_table). We did it in the `trap_init` function from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c) source code file. We saw only setting of these interrupt gates in the previous part and in the current part we will see implementation of the exception handlers for these gates. The preparation before an exception handler will be executed is in the [arch/x86/entry/entry_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/entry_64.S) assembly file and occurs in the [idtentry](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/entry_64.S#L820) macro that defines exceptions entry points:

```assembly
idtentry divide_error		     do_divide_error		    has_error_code=0
idtentry overflow		     do_overflow		    has_error_code=0
idtentry invalid_op		     do_invalid_op		    has_error_code=0
idtentry bounds			     do_bounds			    has_error_code=0
idtentry device_not_available	     do_device_not_available	    has_error_code=0
idtentry coprocessor_segment_overrun do_coprocessor_segment_overrun has_error_code=0
idtentry invalid_TSS		     do_invalid_TSS		    has_error_code=1
idtentry segment_not_present	     do_segment_not_present	    has_error_code=1
idtentry spurious_interrupt_bug	     do_spurious_interrupt_bug      has_error_code=0
idtentry coprocessor_error	     do_coprocessor_error	    has_error_code=0
idtentry alignment_check	     do_alignment_check		    has_error_code=1
idtentry simd_coprocessor_error	     do_simd_coprocessor_error      has_error_code=0
```

The `idtentry` macro does following preparation before an actual exception handler (`do_divide_error` for the `divide_error`, `do_overflow` for the `overflow`, etc.) will get control. In another words the `idtentry` macro allocates place for the registers ([pt_regs](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/uapi/asm/ptrace.h#L43) structure) on the stack, pushes dummy error code for the stack consistency if an interrupt/exception has no error code, checks the segment selector in the `cs` segment register and switches depends on the previous state (userspace or kernelspace). After all of these preparations it makes a call to an actual interrupt/exception handler:

```assembly
.macro idtentry sym do_sym has_error_code:req paranoid=0 shift_ist=-1
ENTRY(\sym)
	...
	...
	...
	call	\do_sym
	...
	...
	...
END(\sym)
.endm
```

After an exception handler will finish its work, the `idtentry` macro restores stack and general purpose registers of an interrupted task and executes [iret](http://x86.renejeschke.de/html/file_module_x86_id_145.html) instruction:

```assembly
ENTRY(paranoid_exit)
	...
	...
	...
	RESTORE_EXTRA_REGS
	RESTORE_C_REGS
	REMOVE_PT_GPREGS_FROM_STACK 8
	INTERRUPT_RETURN
END(paranoid_exit)
```

where `INTERRUPT_RETURN` is:

```assembly
#define INTERRUPT_RETURN	jmp native_iret
...
ENTRY(native_iret)
.global native_irq_return_iret
native_irq_return_iret:
iretq
```

More about the `idtentry` macro you can read in the third part of the [https://0xax.gitbooks.io/linux-insides/content/Interrupts/linux-interrupts-3.html](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-3) chapter. Ok, now we saw the preparation before an exception handler will be executed and now time to look on the handlers. First of all let's look on the following handlers:

* divide_error
* overflow
* invalid_op
* coprocessor_segment_overrun
* invalid_TSS
* segment_not_present
* stack_segment
* alignment_check

All these handlers defined in the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/traps.c) source code file with the `DO_ERROR` macro:

```C
DO_ERROR(X86_TRAP_DE,     SIGFPE,  "divide error",                divide_error)
DO_ERROR(X86_TRAP_OF,     SIGSEGV, "overflow",                    overflow)
DO_ERROR(X86_TRAP_UD,     SIGILL,  "invalid opcode",              invalid_op)
DO_ERROR(X86_TRAP_OLD_MF, SIGFPE,  "coprocessor segment overrun", coprocessor_segment_overrun)
DO_ERROR(X86_TRAP_TS,     SIGSEGV, "invalid TSS",                 invalid_TSS)
DO_ERROR(X86_TRAP_NP,     SIGBUS,  "segment not present",         segment_not_present)
DO_ERROR(X86_TRAP_SS,     SIGBUS,  "stack segment",               stack_segment)
DO_ERROR(X86_TRAP_AC,     SIGBUS,  "alignment check",             alignment_check)
```

As we can see the `DO_ERROR` macro takes 4 parameters:

* Vector number of an interrupt;
* Signal number which will be sent to the interrupted process;
* String which describes an exception;
* Exception handler entry point.

This macro defined in the same source code file and expands to the function with the `do_handler` name:

```C
#define DO_ERROR(trapnr, signr, str, name)                              \
dotraplinkage void do_##name(struct pt_regs *regs, long error_code)     \
{                                                                       \
        do_error_trap(regs, error_code, str, trapnr, signr);            \
}
```

Note on the `##` tokens. This is special feature - [GCC macro Concatenation](https://gcc.gnu.org/onlinedocs/cpp/Concatenation.html#Concatenation) which concatenates two given strings. For example, first `DO_ERROR` in our example will expands to the:

```C
dotraplinkage void do_divide_error(struct pt_regs *regs, long error_code)     \
{
	...
}
```

We can see that all functions which are generated by the `DO_ERROR` macro just make a call to the `do_error_trap` function from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). Let's look on implementation of the `do_error_trap` function.

Trap handlers
--------------------------------------------------------------------------------

The `do_error_trap` function starts and ends from the two following functions:

```C
enum ctx_state prev_state = exception_enter();
...
...
...
exception_exit(prev_state);
```

from the [include/linux/context_tracking.h](https://github.com/torvalds/linux/tree/master/include/linux/context_tracking.h). The context tracking in the Linux kernel subsystem which provide kernel boundaries probes to keep track of the transitions between level contexts with two basic initial contexts: `user` or `kernel`. The `exception_enter` function checks that context tracking is enabled. After this if it is enabled, the `exception_enter` reads previous context and compares it with the `CONTEXT_KERNEL`. If the previous context is `user`, we call `context_tracking_exit` function from the [kernel/context_tracking.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/context_tracking.c) which inform the context tracking subsystem that a processor is exiting user mode and entering the kernel mode:

```C
if (!context_tracking_is_enabled())
	return 0;

prev_ctx = this_cpu_read(context_tracking.state);
if (prev_ctx != CONTEXT_KERNEL)
	context_tracking_exit(prev_ctx);

return prev_ctx;
```

If previous context is non `user`, we just return it. The `pre_ctx` has `enum ctx_state` type which defined in the [include/linux/context_tracking_state.h](https://github.com/torvalds/linux/tree/master/include/linux/context_tracking_state.h) and looks as:

```C
enum ctx_state {
	CONTEXT_KERNEL = 0,
	CONTEXT_USER,
	CONTEXT_GUEST,
} state;
```

The second function is `exception_exit` defined in the same [include/linux/context_tracking.h](https://github.com/torvalds/linux/tree/master/include/linux/context_tracking.h) file and checks that context tracking is enabled and call the `context_tracking_enter` function if the previous context was `user`:

```C
static inline void exception_exit(enum ctx_state prev_ctx)
{
	if (context_tracking_is_enabled()) {
		if (prev_ctx != CONTEXT_KERNEL)
			context_tracking_enter(prev_ctx);
	}
}
```

The `context_tracking_enter` function informs the context tracking subsystem that a processor is going to enter to the user mode from the kernel mode. We can see the following code between the `exception_enter` and `exception_exit`:

```C
if (notify_die(DIE_TRAP, str, regs, error_code, trapnr, signr) !=
		NOTIFY_STOP) {
	conditional_sti(regs);
	do_trap(trapnr, signr, str, regs, error_code,
		fill_trap_info(regs, signr, trapnr, &info));
}
```

First of all it calls the `notify_die` function which defined in the [kernel/notifier.c](https://github.com/torvalds/linux/tree/master/kernel/notifier.c). To get notified for [kernel panic](https://en.wikipedia.org/wiki/Kernel_panic), [kernel oops](https://en.wikipedia.org/wiki/Linux_kernel_oops), [Non-Maskable Interrupt](https://en.wikipedia.org/wiki/Non-maskable_interrupt) or other events the caller needs to insert itself in the `notify_die` chain and the `notify_die` function does it. The Linux kernel has special mechanism that allows kernel to ask when something happens and this mechanism called `notifiers` or `notifier chains`. This mechanism used for example for the `USB` hotplug events (look on the [drivers/usb/core/notify.c](https://github.com/torvalds/linux/tree/master/drivers/usb/core/notify.c)), for the memory [hotplug](https://en.wikipedia.org/wiki/Hot_swapping) (look on the [include/linux/memory.h](https://github.com/torvalds/linux/tree/master/include/linux/memory.h), the `hotplug_memory_notifier` macro, etc...), system reboots, etc. A notifier chain is thus a simple, singly-linked list. When a Linux kernel subsystem wants to be notified of specific events, it fills out a special `notifier_block` structure and passes it to the `notifier_chain_register` function. An event can be sent with the call of the `notifier_call_chain` function. First of all the `notify_die` function fills `die_args` structure with the trap number, trap string, registers and other values:

```C
struct die_args args = {
       .regs   = regs,
       .str    = str,
       .err    = err,
       .trapnr = trap,
       .signr  = sig,
}
```

and returns the result of the `atomic_notifier_call_chain` function with the `die_chain`:

```C
static ATOMIC_NOTIFIER_HEAD(die_chain);
return atomic_notifier_call_chain(&die_chain, val, &args);
```

which just expands to the `atomic_notifier_head` structure that contains lock and `notifier_block`:

```C
struct atomic_notifier_head {
        spinlock_t lock;
        struct notifier_block __rcu *head;
};
```

The `atomic_notifier_call_chain` function calls each function in a notifier chain in turn and returns the value of the last notifier function called. If the `notify_die` in the `do_error_trap` does not return `NOTIFY_STOP` we execute `conditional_sti` function from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/traps.c) that checks the value of the [interrupt flag](https://en.wikipedia.org/wiki/Interrupt_flag) and enables interrupt depends on it:

```C
static inline void conditional_sti(struct pt_regs *regs)
{
        if (regs->flags & X86_EFLAGS_IF)
                local_irq_enable();
}
```

more about `local_irq_enable` macro you can read in the second [part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-2) of this chapter. The next and last call in the `do_error_trap` is the `do_trap` function. First of all the `do_trap` function defined the `tsk` variable which has `task_struct` type and represents the current interrupted process. After the definition of the `tsk`, we can see the call of the `do_trap_no_signal` function:

```C
struct task_struct *tsk = current;

if (!do_trap_no_signal(tsk, trapnr, str, regs, error_code))
	return;
```

The `do_trap_no_signal` function makes two checks:

* Did we come from the [Virtual 8086](https://en.wikipedia.org/wiki/Virtual_8086_mode) mode;
* Did we come from the kernelspace.

```C
if (v8086_mode(regs)) {
	...
}

if (!user_mode(regs)) {
	...
}

return -1;
```

We will not consider first case because the [long mode](https://en.wikipedia.org/wiki/Long_mode) does not support the [Virtual 8086](https://en.wikipedia.org/wiki/Virtual_8086_mode) mode. In the second case we invoke `fixup_exception` function which will try to recover a fault and `die` if we can't:

```C
if (!fixup_exception(regs)) {
	tsk->thread.error_code = error_code;
	tsk->thread.trap_nr = trapnr;
	die(str, regs, error_code);
}
```

The `die` function defined in the [arch/x86/kernel/dumpstack.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/dumpstack.c) source code file, prints useful information about stack, registers, kernel modules and caused kernel [oops](https://en.wikipedia.org/wiki/Linux_kernel_oops). If we came from the userspace the `do_trap_no_signal` function will return `-1` and the execution of the `do_trap` function will continue. If we passed through the `do_trap_no_signal` function and did not exit from the `do_trap` after this, it means that previous context was - `user`.  Most exceptions caused by the processor are interpreted by Linux as error conditions, for example division by zero, invalid opcode, etc. When an exception occurs the Linux kernel sends a [signal](https://en.wikipedia.org/wiki/Unix_signal) to the interrupted process that caused the exception to notify it of an incorrect condition. So, in the `do_trap` function we need to send a signal with the given number (`SIGFPE` for the divide error, `SIGILL` for a illegal instruction, etc.). First of all we save error code and vector number in the current interrupts process with the filling `thread.error_code` and `thread_trap_nr`:

```C
tsk->thread.error_code = error_code;
tsk->thread.trap_nr = trapnr;
```

After this we make a check do we need to print information about unhandled signals for the interrupted process. We check that `show_unhandled_signals` variable is set, that `unhandled_signal` function from the [kernel/signal.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/kernel/signal.c) will return unhandled signal(s) and [printk](https://en.wikipedia.org/wiki/Printk) rate limit:

```C
#ifdef CONFIG_X86_64
	if (show_unhandled_signals && unhandled_signal(tsk, signr) &&
	    printk_ratelimit()) {
		pr_info("%s[%d] trap %s ip:%lx sp:%lx error:%lx",
			tsk->comm, tsk->pid, str,
			regs->ip, regs->sp, error_code);
		print_vma_addr(" in ", regs->ip);
		pr_cont("\n");
	}
#endif
```

And send a given signal to interrupted process:

```C
force_sig_info(signr, info ?: SEND_SIG_PRIV, tsk);
```

This is the end of the `do_trap`. We just saw generic implementation for eight different exceptions which are defined with the `DO_ERROR` macro. Now let's look at other exception handlers.

Double fault
--------------------------------------------------------------------------------

The next exception is `#DF` or `Double fault`. This exception occurs when the processor detected a second exception while calling an exception handler for a prior exception. We set the trap gate for this exception in the previous part:

```C
set_intr_gate_ist(X86_TRAP_DF, &double_fault, DOUBLEFAULT_STACK);
```

Note that this exception runs on the `DOUBLEFAULT_STACK` [Interrupt Stack Table](https://www.kernel.org/doc/Documentation/x86/kernel-stacks) which has index - `1`:

```C
#define DOUBLEFAULT_STACK 1
```

The `double_fault` is handler for this exception and defined in the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). The `double_fault` handler starts from the definition of two variables: string that describes exception and interrupted process, as other exception handlers:

```C
static const char str[] = "double fault";
struct task_struct *tsk = current;
```

The handler of the double fault exception split on two parts. The first part is the check which checks that a fault is a `non-IST` fault on the `espfix64` stack. Actually the `iret` instruction restores only the bottom `16` bits when returning to a `16` bit segment. The `espfix` feature solves this problem. So if the `non-IST` fault on the espfix64 stack we modify the stack to make it look like `General Protection Fault`:

```C
struct pt_regs *normal_regs = task_pt_regs(current);

memmove(&normal_regs->ip, (void *)regs->sp, 5*8);
ormal_regs->orig_ax = 0;
regs->ip = (unsigned long)general_protection;
regs->sp = (unsigned long)&normal_regs->orig_ax;
return;
```

In the second case we do almost the same that we did in the previous exception handlers. The first is the call of the `ist_enter` function that discards previous context, `user` in our case:

```C
ist_enter(regs);
```

And after this we fill the interrupted process with the vector number of the `Double fault` exception and error code as we did it in the previous handlers:

```C
tsk->thread.error_code = error_code;
tsk->thread.trap_nr = X86_TRAP_DF;
```

Next we print useful information about the double fault ([PID](https://en.wikipedia.org/wiki/Process_identifier) number, registers content):

```C
#ifdef CONFIG_DOUBLEFAULT
	df_debug(regs, error_code);
#endif
```

And die:

```
	for (;;)
		die(str, regs, error_code);
```

That's all.

Device not available exception handler
--------------------------------------------------------------------------------

The next exception is the `#NM` or `Device not available`. The `Device not available` exception can occur depending on these things:

* The processor executed an [x87 FPU](https://en.wikipedia.org/wiki/X87) floating-point instruction while the EM flag in [control register](https://en.wikipedia.org/wiki/Control_register) `cr0` was set;
* The processor executed a `wait` or `fwait` instruction while the `MP` and `TS` flags of register `cr0` were set;
* The processor executed an [x87 FPU](https://en.wikipedia.org/wiki/X87), [MMX](https://en.wikipedia.org/wiki/MMX_%28instruction_set%29) or [SSE](https://en.wikipedia.org/wiki/Streaming_SIMD_Extensions) instruction while the `TS` flag in control register `cr0` was set and the `EM` flag is clear.

The handler of the `Device not available` exception is the `do_device_not_available` function and it defined in the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c) source code file too. It starts and ends from the getting of the previous context, as other traps which we saw in the beginning of this part:

```C
enum ctx_state prev_state;
prev_state = exception_enter();
...
...
...
exception_exit(prev_state);
```

In the next step we check that `FPU` is not eager:

```C
BUG_ON(use_eager_fpu());
```

When we switch into a task or interrupt we may avoid loading the `FPU` state. If a task will use it, we catch `Device not Available exception` exception. If we loading the `FPU` state during task switching, the `FPU` is eager. In the next step we check `cr0` control register on the `EM` flag which can show us is `x87` floating point unit present (flag clear) or not (flag set):

```C
#ifdef CONFIG_MATH_EMULATION
	if (read_cr0() & X86_CR0_EM) {
		struct math_emu_info info = { };

		conditional_sti(regs);

		info.regs = regs;
		math_emulate(&info);
		exception_exit(prev_state);
		return;
	}
#endif
```

If the `x87` floating point unit not presented, we enable interrupts with the `conditional_sti`, fill the `math_emu_info` (defined in the [arch/x86/include/asm/math_emu.h](https://github.com/torvalds/linux/tree/master/arch/x86/include/asm/math_emu.h)) structure with the registers of an interrupt task and call `math_emulate` function from the [arch/x86/math-emu/fpu_entry.c](https://github.com/torvalds/linux/tree/master/arch/x86/math-emu/fpu_entry.c). As you can understand from function's name, it emulates `X87 FPU` unit (more about the `x87` we will know in the special chapter). In other way, if `X86_CR0_EM` flag is clear which means that `x87 FPU` unit is presented, we call the `fpu__restore` function from the [arch/x86/kernel/fpu/core.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/fpu/core.c) which copies the `FPU` registers from the `fpustate` to the live hardware registers. After this `FPU` instructions can be used:

```C
fpu__restore(&current->thread.fpu);
```

General protection fault exception handler
--------------------------------------------------------------------------------

The next exception is the `#GP` or `General protection fault`. This exception occurs when the processor detected one of a class of protection violations called `general-protection violations`. It can be:

* Exceeding the segment limit when accessing the `cs`, `ds`, `es`, `fs` or `gs` segments;
* Loading the `ss`, `ds`, `es`, `fs` or `gs` register with a segment selector for a system segment.;
* Violating any of the privilege rules;
* and other...

The exception handler for this exception is the `do_general_protection` from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). The `do_general_protection` function starts and ends as other exception handlers from the getting of the previous context:

```C
prev_state = exception_enter();
...
exception_exit(prev_state);
```

After this we enable interrupts if they were disabled and check that we came from the [Virtual 8086](https://en.wikipedia.org/wiki/Virtual_8086_mode) mode:

```C
conditional_sti(regs);

if (v8086_mode(regs)) {
	local_irq_enable();
	handle_vm86_fault((struct kernel_vm86_regs *) regs, error_code);
	goto exit;
}
```

As long mode does not support this mode, we will not consider exception handling for this case. In the next step check that previous mode was kernel mode and try to fix the trap. If we can't fix the current general protection fault exception we fill the interrupted process with the vector number and error code of the exception and add it to the `notify_die` chain:

```C
if (!user_mode(regs)) {
	if (fixup_exception(regs))
		goto exit;

	tsk->thread.error_code = error_code;
	tsk->thread.trap_nr = X86_TRAP_GP;
	if (notify_die(DIE_GPF, "general protection fault", regs, error_code,
		       X86_TRAP_GP, SIGSEGV) != NOTIFY_STOP)
		die("general protection fault", regs, error_code);
	goto exit;
}
```

If we can fix exception we go to the `exit` label which exits from exception state:

```C
exit:
	exception_exit(prev_state);
```

If we came from user mode we send `SIGSEGV` signal to the interrupted process from user mode as we did it in the `do_trap` function:

```C
if (show_unhandled_signals && unhandled_signal(tsk, SIGSEGV) &&
		printk_ratelimit()) {
	pr_info("%s[%d] general protection ip:%lx sp:%lx error:%lx",
		tsk->comm, task_pid_nr(tsk),
		regs->ip, regs->sp, error_code);
	print_vma_addr(" in ", regs->ip);
	pr_cont("\n");
}

force_sig_info(SIGSEGV, SEND_SIG_PRIV, tsk);
```

That's all.

Conclusion
--------------------------------------------------------------------------------

It is the end of the fifth part of the [Interrupts and Interrupt Handling](https://0xax.gitbook.io/linux-insides/summary/interrupts) chapter and we saw implementation of some interrupt handlers in this part. In the next part we will continue to dive into interrupt and exception handlers and will see handler for the [Non-Maskable Interrupts](https://en.wikipedia.org/wiki/Non-maskable_interrupt), handling of the math [coprocessor](https://en.wikipedia.org/wiki/Coprocessor) and [SIMD](https://en.wikipedia.org/wiki/SIMD) coprocessor exceptions and many many more.

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Interrupt descriptor Table](https://en.wikipedia.org/wiki/Interrupt_descriptor_table)
* [iret instruction](http://x86.renejeschke.de/html/file_module_x86_id_145.html)
* [GCC macro Concatenation](https://gcc.gnu.org/onlinedocs/cpp/Concatenation.html#Concatenation)
* [kernel panic](https://en.wikipedia.org/wiki/Kernel_panic)
* [kernel oops](https://en.wikipedia.org/wiki/Linux_kernel_oops)
* [Non-Maskable Interrupt](https://en.wikipedia.org/wiki/Non-maskable_interrupt)
* [hotplug](https://en.wikipedia.org/wiki/Hot_swapping)
* [interrupt flag](https://en.wikipedia.org/wiki/Interrupt_flag)
* [long mode](https://en.wikipedia.org/wiki/Long_mode)
* [signal](https://en.wikipedia.org/wiki/Unix_signal)
* [printk](https://en.wikipedia.org/wiki/Printk)
* [coprocessor](https://en.wikipedia.org/wiki/Coprocessor)
* [SIMD](https://en.wikipedia.org/wiki/SIMD)
* [Interrupt Stack Table](https://www.kernel.org/doc/Documentation/x86/kernel-stacks)
* [PID](https://en.wikipedia.org/wiki/Process_identifier)
* [x87 FPU](https://en.wikipedia.org/wiki/X87)
* [control register](https://en.wikipedia.org/wiki/Control_register)
* [MMX](https://en.wikipedia.org/wiki/MMX_%28instruction_set%29)
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/interrupts/linux-interrupts-4)
