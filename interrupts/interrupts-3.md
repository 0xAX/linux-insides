Interrupts and Interrupt Handling. Part 3.
================================================================================

Interrupt handlers
--------------------------------------------------------------------------------

This is the third part of the [chapter](http://0xax.gitbooks.io/linux-insides/content/interrupts/index.html) about an interrupts and an exceptions handling and in the previous [part](http://0xax.gitbooks.io/linux-insides/content/interrupts/index.html) we stopped in the `setup_arch` function from the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blame/master/arch/x86/kernel/setup.c) on the setting of the two exceptions handlers for the two following exceptions:

* `#DB` - debug exception, transfers control from the interrupted process to the debug handler;
* `#BP` - breakpoint exception, caused by the `int 3` instruction.

These exceptions allow the `x86_64` architecture to have early exception processing for the purpose of debugging via the [kgdb](https://en.wikipedia.org/wiki/KGDB).

As you can remember we set these exceptions handlers in the `early_trap_init` function:

```C
void __init early_trap_init(void)
{
        set_intr_gate_ist(X86_TRAP_DB, &debug, DEBUG_STACK);
        set_system_intr_gate_ist(X86_TRAP_BP, &int3, DEBUG_STACK);
        load_idt(&idt_descr);
}
```

from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). We already saw implementation of the `set_intr_gate_ist` and `set_system_intr_gate_ist` functions in the previous part and now we will look on the implementation of these early exceptions handlers.

Debug and Breakpoint exceptions
--------------------------------------------------------------------------------

Ok, we set the interrupts gates in the `early_trap_init` function for the `#DB` and `#BP` exceptions and now time is to look on their handlers. But first of all let's look on these exceptions. The first exceptions - `#DB` or debug exception occurs when a debug event occurs, for example attempt to change the contents of a [debug register](http://en.wikipedia.org/wiki/X86_debug_register). Debug registers are special registers which present in processors starting from the [Intel 80386](http://en.wikipedia.org/wiki/Intel_80386) and as you can understand from its name they are used for debugging. These registers allow to set breakpoints on the code and read or write data to trace, thus tracking the place of errors. The debug registers are privileged resources available and the program in either real-address or protected mode at `CPL` is `0`, that's why we have used `set_intr_gate_ist` for the `#DB`, but not the `set_system_intr_gate_ist`. The verctor number of the `#DB` exceptions is `1` (we pass it as `X86_TRAP_DB`) and has no error code:

```
----------------------------------------------------------------------------------------------
|Vector|Mnemonic|Description         |Type |Error Code|Source                                |
----------------------------------------------------------------------------------------------
|1     | #DB    |Reserved            |F/T  |NO        |                                      |
----------------------------------------------------------------------------------------------
```

The second is `#BP` or breakpoint exception occurs when processor executes the [INT 3](http://en.wikipedia.org/wiki/INT_%28x86_instruction%29#INT_3) instruction. We can add it anywhere in our code, for example let's look on the simple program:

```C
// breakpoint.c
#include <stdio.h>

int main() {
    int i;
    while (i < 6){
	    printf("i equal to: %d\n", i);
	    __asm__("int3");
		++i;
    }
}
```

If we will compile and run this program, we will see following output:

```
$ gcc breakpoint.c -o breakpoint
i equal to: 0
Trace/breakpoint trap
```

But if will run it with gdb, we will see our breakpoint and can continue execution of our program:

```
$ gdb breakpoint
...
...
...
(gdb) run
Starting program: /home/alex/breakpoints 
i equal to: 0

Program received signal SIGTRAP, Trace/breakpoint trap.
0x0000000000400585 in main ()
=> 0x0000000000400585 <main+31>:	83 45 fc 01	add    DWORD PTR [rbp-0x4],0x1
(gdb) c
Continuing.
i equal to: 1

Program received signal SIGTRAP, Trace/breakpoint trap.
0x0000000000400585 in main ()
=> 0x0000000000400585 <main+31>:	83 45 fc 01	add    DWORD PTR [rbp-0x4],0x1
(gdb) c
Continuing.
i equal to: 2

Program received signal SIGTRAP, Trace/breakpoint trap.
0x0000000000400585 in main ()
=> 0x0000000000400585 <main+31>:	83 45 fc 01	add    DWORD PTR [rbp-0x4],0x1
...
...
...
```

Now we know a little about these two exceptions and we can move on to consideration of their handlers.

Preparation before an interrupt handler
--------------------------------------------------------------------------------

As you can note, the `set_intr_gate_ist` and `set_system_intr_gate_ist` functions takes an addresses of the exceptions handlers in the second parameter:

* `&debug`;
* `&int3`.

You will not find these functions in the C code. All that can be found in the `*.c/*.h` files only definition of this functions in the [arch/x86/include/asm/traps.h](https://github.com/torvalds/linux/tree/master/arch/x86/include/asm/traps.h): 

```C
asmlinkage void debug(void);
asmlinkage void int3(void);
```

But we can see `asmlinkage` descriptor here. The `asmlinkage` is the special specificator of the [gcc](http://en.wikipedia.org/wiki/GNU_Compiler_Collection). Actually for a `C` functions which are called from assembly, we need in explicit declaration of the function calling convention. In our case, if function maked with `asmlinkage` descriptor, then `gcc` will compile the function to retrieve parameters from stack. So, both handlers are defined in the [arch/x86/kernel/entry_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/entry_64.S) assembly source code file with the `idtentry` macro:

```assembly
idtentry debug do_debug has_error_code=0 paranoid=1 shift_ist=DEBUG_STACK
idtentry int3 do_int3 has_error_code=0 paranoid=1 shift_ist=DEBUG_STACK
```

Actually `debug` and `int3` are not interrupts handlers. Remember that before we can execute an interrupt/exception handler, we need to do some preparations as:

* When an interrupt or exception occurred, the processor uses an exception or interrupt vector as an index to a descriptor in the `IDT`;
* In legacy mode `ss:esp` registers are pushed on the stack only if privilege level changed. In 64-bit mode `ss:rsp` pushed on the stack everytime;
* During stack switching with `IST` the new `ss` selector is forced to null. Old `ss` and `rsp` are pushed on the new stack.
* The `rflags`, `cs`, `rip` and error code pushed on the stack;
* Control transferred to an interrupt handler;
* After an interrupt handler will finish its work and finishes with the `iret` instruction, old `ss` will be poped from the stack and loaded to the `ss` register.
* `ss:rsp` will be popped from the stack unconditionally in the 64-bit mode and will be popped only if there is a privilege level change in legacy mode.
* `iret` instruction will restore `rip`, `cs` and `rflags`;
* Interrupted program will continue its execution.

```
    +--------------------+
+40 |        ss          |
+32 |       rsp          |
+24 |      rflags        |
+16 |        cs          |
 +8 |       rip          |
  0 |    error code      |
    +--------------------+
```

Now we can see on the preparations before a process will transfer control to an interrupt/exception handler from practical side. As I already wrote above the first thirteen exceptions handlers defined in the [arch/x86/kernel/entry_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/entry_64.S) assembly file with the [idtentry](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/entry_64.S#L967) macro:

```assembly
.macro idtentry sym do_sym has_error_code:req paranoid=0 shift_ist=-1
ENTRY(\sym)
...
...
...
END(\sym)
.endm
```

This macro defines an exception entry point and as we can see it takes `five` arguments:

* `sym` - defines global symbol with the `.globl name`.
* `do_sym` - an interrupt handler.
* `has_error_code:req` - information about error code, The `:req` qualifier tells the assembler that the argument is required;
* `paranoid` - shows us how we need to check current mode;
* `shift_ist` - shows us what's stack to use;

As we can see our exceptions handlers are almost the same:

```assembly
idtentry debug do_debug has_error_code=0 paranoid=1 shift_ist=DEBUG_STACK
idtentry int3 do_int3 has_error_code=0 paranoid=1 shift_ist=DEBUG_STACK
```

The differences are only in the global name and name of exceptions handlers. Now let's look how `idtentry` macro implemented. It starts from the two checks:

```assembly
	.if \shift_ist != -1 && \paranoid == 0
	.error "using shift_ist requires paranoid=1"
	.endif

	.if \has_error_code
	XCPT_FRAME
	.else
	INTR_FRAME
	.endif
```

First check makes the check that an exceptions uses `Interrupt stack table` and `paranoid` is set, in other way it emits the erorr with the [.error](https://sourceware.org/binutils/docs/as/Error.html#Error) directive. The second `if` clause checks existence of an error code and calls `XCPT_FRAME` or `INTR_FRAME` macros depends on it. These macros just expand to the set of [CFI directives](https://sourceware.org/binutils/docs/as/CFI-directives.html) which are used by `GNU AS` to manage call frames. The `CFI` directives are used only to generate [dwarf2](http://en.wikipedia.org/wiki/DWARF) unwind information for better backtraces and they don't change any code, so we will not go into detail about it and from this point I will skip all code which is related to these directives. In the next step we check error code again and push it on the stack if an exception has it with the:

```assembly
.ifeq \has_error_code
	pushq_cfi $-1
.endif
```

The `pushq_cfi` macro defined in the [arch/x86/include/asm/dwarf2.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/dwarf2.h) and expands to the `pushq` instruction which pushes given error code:

```assembly
	.macro pushq_cfi reg
	pushq \reg
	CFI_ADJUST_CFA_OFFSET 8
	.endm
```

Pay attention on the `$-1`. We already know that when an exception occurs, the processor pushes `ss`, `rsp`, `rflags`, `cs` and `rip` on the stack:

```C
#define RIP		16*8
#define CS		17*8
#define EFLAGS	18*8
#define RSP		19*8
#define SS		20*8
```

With the `pushq \reg` we denote that place before the `RIP` will contain error code of an exception:

```C
#define ORIG_RAX	15*8
```

The `ORIG_RAX` will contain error code of an exception, [IRQ](http://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29) number on a hardware interrupt and system call number on [system call](http://en.wikipedia.org/wiki/System_call) entry. In the next step we can see the `ALLOC_PT_GPREGS_ON_STACK` macro which allocates space for the 15 general purpose registers on the stack:

```assembly
.macro ALLOC_PT_GPREGS_ON_STACK addskip=0
subq	$15*8+\addskip, %rsp
CFI_ADJUST_CFA_OFFSET 15*8+\addskip
.endm
```

After this we check `paranoid` and if it is set we check first three `CPL` bits. We compare it with the `3` and it allows us to know did we come from userspace or not:

```assembly
.if \paranoid
  .if \paranoid == 1
    CFI_REMEMBER_STATE
	testl $3, CS(%rsp)
	jnz 1f
  .endif
  call paranoid_entry
.else
  call error_entry
.endif
```

If we came from userspace we jump on the label `1` which starts from the `call error_entry` instruction. The `error_entry` saves all registers in the `pt_regs` structure which presents an interrupt/exception stack frame and defined in the [arch/x86/include/uapi/asm/ptrace.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/uapi/asm/ptrace.h). It saves common and extra registers on the stack with the:

```assembly
SAVE_C_REGS 8
SAVE_EXTRA_REGS 8
```

from `rdi` to `r15` and executes [swapgs](http://www.felixcloutier.com/x86/SWAPGS.html) instruction. This instruction provides a method for the Linux kernel to obtain a pointer to the kernel data structures and save the user's `gsbase`. After this we will exit from the `error_entry` with the `ret` instruction. After the `error_entry` finished to execute, since we came from userspace we need to switch on kernel interrupt stack:

```assembly
	movq %rsp,%rdi
	call sync_regs
```

We just save all registers to the `error_entry` in the `error_entry`, we put address of the `pt_regs` to the `rdi` and call `sync_regs` function from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c):

```C
asmlinkage __visible notrace struct pt_regs *sync_regs(struct pt_regs *eregs)
{
	struct pt_regs *regs = task_pt_regs(current);
	*regs = *eregs;
	return regs;
}
```

This function switchs off the `IST` stack if we came from usermode. After this we switch on the stack which we got from the `sync_regs`:

```assembly
movq %rax,%rsp
movq %rsp,%rdi
```

and put pointer of the `pt_regs` again in the `rdi`, and in the last step we call an exception handler:

```assembly
call \do_sym
```

So, real exceptions handlers are `do_debug` and `do_int3` functions. We will see these function in this part, but little later. First of all let's look on the preparations before a processor will transfer control to an interrupt handler. In another way if `paranoid` is set, but it is not 1, we call `paranoid_entry` which makes almost the same that `error_entry`, but it checks current mode with more slow but accurate way:

```assembly
ENTRY(paranoid_entry)
	SAVE_C_REGS 8
	SAVE_EXTRA_REGS 8
	...
	...
	movl $MSR_GS_BASE,%ecx
	rdmsr
	testl %edx,%edx
	js 1f	/* negative -> in kernel */
	SWAPGS
	...
	...
	ret
END(paranoid_entry)
```

If `edx` wll be negative, we are in the kernel mode. As we store all registers on the stack, check that we are in the kernel mode, we need to setup `IST` stack if it is set for a given exception, call an exception handler and restore the exception stack:

```assembly
	.if \shift_ist != -1
	subq $EXCEPTION_STKSZ, CPU_TSS_IST(\shift_ist)
	.endif

	call \do_sym

	.if \shift_ist != -1
	addq $EXCEPTION_STKSZ, CPU_TSS_IST(\shift_ist)
	.endif
```

The last step when an exception handler will finish it's work all registers will be restored from the stack with the `RESTORE_C_REGS` and `RESTORE_EXTRA_REGS` macros and control will be returned an interrupted task. That's all. Now we know about preparation before an interrupt/exception handler will start to execute and we can go directly to the implementation of the handlers.

Implementation of ainterrupts and exceptions handlers
--------------------------------------------------------------------------------

Both handlers `do_debug` and `do_int3` defined in the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c) source code file and have two similar things: All interrupts/exceptions handlers marked with the `dotraplinkage` prefix that expands to the:

```C
#define dotraplinkage __visible
#define __visible __attribute__((externally_visible))
```

which tells to compiler that something else uses this function (in our case these functions are called from the assembly interrupt preparation code). And also they takes two parameters:

* pointer to the `pt_regs` structure which contains registers of the interrupted task;
* error code.

First of all let's consider `do_debug` handler. This function starts from the getting previous state with the `ist_enter` function from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). We call it because we need to know, did we come to the interrupt handler from the kernel mode or user mode.

```C
prev_state = ist_enter(regs);
```

The `ist_enter` function returns previous state context state and executes a couple preprartions before we continue to handle an exception. It starts from the check of the previous mode with the `user_mode_vm` macro. It takes `pt_regs` structure which contains a set of registers of the interrupted task and returns `1` if we came from userspace and `0` if we came from kernel space. According to the previous mode we execute `exception_enter` if we are from the userspace or inform [RCU](https://en.wikipedia.org/wiki/Read-copy-update) if we are from krenel space:

```C
...
if (user_mode_vm(regs)) {
	prev_state = exception_enter();
} else {
	rcu_nmi_enter();
	prev_state = IN_KERNEL;
}
...
...
...
return prev_state;
```

After this we load the `DR6` debug registers to the `dr6` variable with the call of the `get_debugreg` macro from the [arch/x86/include/asm/debugreg.h](https://github.com/torvalds/linux/tree/master/arch/x86/include/asm/debugreg.h):

```C
get_debugreg(dr6, 6);
dr6 &= ~DR6_RESERVED;
```

The `DR6` debug register is debug status register contains information about the reason for stopping the `#DB` or debug exception handler. After we loaded its value to the `dr6` variable we filter out all reserved bits (`4:12` bits). In the next step we check `dr6` register and previous state with the following `if` condition expression:

```C
if (!dr6 && user_mode_vm(regs))
	user_icebp = 1;
```

If `dr6` does not show any reasons why we caught this trap we set `user_icebp` to one which means that user-code wants to get [SIGTRAP](https://en.wikipedia.org/wiki/Unix_signal#SIGTRAP) signal. In the next step we check was it [kmemcheck](https://www.kernel.org/doc/Documentation/kmemcheck.txt) trap and if yes we go to exit:

```C
if ((dr6 & DR_STEP) && kmemcheck_trap(regs))
	goto exit;
```

After we did all these checks, we clear the `dr6` register, clear the `DEBUGCTLMSR_BTF` flag which provides single-step on branches debugging, set `dr6` register for the current thread and increase `debug_stack_usage` [per-cpu]([Per-CPU variables](http://0xax.gitbooks.io/linux-insides/content/Concepts/per-cpu.html)) variable with the:

```C
set_debugreg(0, 6);
clear_tsk_thread_flag(tsk, TIF_BLOCKSTEP);
tsk->thread.debugreg6 = dr6;
debug_stack_usage_inc();
```

As we saved `dr6`, we can allow irqs:

```C
static inline void preempt_conditional_sti(struct pt_regs *regs)
{
        preempt_count_inc();
        if (regs->flags & X86_EFLAGS_IF)
                local_irq_enable();
}
```

more about `local_irq_enabled` and related stuff you can read in the second part about [interrupts handling in the Linux kernel](http://0xax.gitbooks.io/linux-insides/content/interrupts/interrupts-2.html). In the next step we check the previous mode was [virtual 8086](https://en.wikipedia.org/wiki/Virtual_8086_mode) and handle the trap:

```C
if (regs->flags & X86_VM_MASK) {
	handle_vm86_trap((struct kernel_vm86_regs *) regs, error_code, X86_TRAP_DB);
	  preempt_conditional_cli(regs);
      debug_stack_usage_dec();
	  goto exit;
}
...
...
...
exit:
	ist_exit(regs, prev_state);
```

If we came not from the virtual 8086 mode, we need to check `dr6` register and previous mode as we did it above. Here we check if step mode debugging is
enabled and we are not from the user mode, we enabled step mode debugging in the `dr6` copy in the current thread, set `TIF_SINGLE_STEP` flag and re-enable [Trap flag](https://en.wikipedia.org/wiki/Trap_flag) for the user mode:

```C
if ((dr6 & DR_STEP) && !user_mode(regs)) {
        tsk->thread.debugreg6 &= ~DR_STEP;
        set_tsk_thread_flag(tsk, TIF_SINGLESTEP);
        regs->flags &= ~X86_EFLAGS_TF;
}
```

Then we get `SIGTRAP` signal code:

```C
si_code = get_si_code(tsk->thread.debugreg6);
```

and send it for user icebp traps:

```C
if (tsk->thread.debugreg6 & (DR_STEP | DR_TRAP_BITS) || user_icebp)
	send_sigtrap(tsk, regs, error_code, si_code);
preempt_conditional_cli(regs);
debug_stack_usage_dec();
exit:
	ist_exit(regs, prev_state);
```

In the end we disable `irqs`, decrease value of the `debug_stack_usage` and exit from the exception handler with the `ist_exit` function.

The second exception handler is `do_int3` defined in the same source code file - [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). In the `do_int3` we make almost the same that in the `do_debug` handler. We get the previous state with the `ist_enter`, increase and decrease the `debug_stack_usage` per-cpu variable, enable and disable local interrupts. But of course there is one difference between these two handlers. We need to lock and then sync processor cores during breakpoint patching.

That's all.

Conclusion
--------------------------------------------------------------------------------

It is the end of the third part about interrupts and interrupt handling in the Linux kernel. We saw the initialization of the [Interrupt descriptor table](https://en.wikipedia.org/wiki/Interrupt_descriptor_table) in the previous part with the `#DB` and `#BP` gates and started to dive into preparation before control will be transferred to an exception handler and implementation of some interrupt handlers in this part. In the next part we will continue to dive into this theme and will go next by the `setup_arch` function and will try to understand interrupts handling related stuff.

If you have any questions or suggestions write me a comment or ping me at [twitter](https://twitter.com/0xAX).

**Please note that English is not my first language, And I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [Debug registers](http://en.wikipedia.org/wiki/X86_debug_register)
* [Intel 80385](http://en.wikipedia.org/wiki/Intel_80386)
* [INT 3](http://en.wikipedia.org/wiki/INT_%28x86_instruction%29#INT_3)
* [gcc](http://en.wikipedia.org/wiki/GNU_Compiler_Collection)
* [TSS](http://en.wikipedia.org/wiki/Task_state_segment)
* [GNU assembly .error directive](https://sourceware.org/binutils/docs/as/Error.html#Error)
* [dwarf2](http://en.wikipedia.org/wiki/DWARF)
* [CFI directives](https://sourceware.org/binutils/docs/as/CFI-directives.html)
* [IRQ](http://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29)
* [system call](http://en.wikipedia.org/wiki/System_call)
* [swapgs](http://www.felixcloutier.com/x86/SWAPGS.html)
* [SIGTRAP](https://en.wikipedia.org/wiki/Unix_signal#SIGTRAP)
* [Per-CPU variables](http://0xax.gitbooks.io/linux-insides/content/Concepts/per-cpu.html)
* [kgdb](https://en.wikipedia.org/wiki/KGDB)
* [ACPI](https://en.wikipedia.org/wiki/Advanced_Configuration_and_Power_Interface)
* [Previous part](http://0xax.gitbooks.io/linux-insides/content/interrupts/index.html)
