Interrupts and Interrupt Handling. Part 3.
================================================================================

Exception Handling
--------------------------------------------------------------------------------

This is the third part of the [chapter](https://0xax.gitbook.io/linux-insides/summary/interrupts) about interrupts and an exceptions handling in the Linux kernel and in the previous [part](https://0xax.gitbook.io/linux-insides/summary/interrupts) we stopped at the `setup_arch` function from the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blame/master/arch/x86/kernel/setup.c) source code file.

We already know that this function executes initialization of architecture-specific stuff. In our case the `setup_arch` function does [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture related initializations. The `setup_arch` is big function, and in the previous part we stopped on the setting of the two exception handlers for the two following exceptions:

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

from the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/tree/master/arch/x86/kernel/traps.c). We already saw implementation of the `set_intr_gate_ist` and `set_system_intr_gate_ist` functions in the previous part and now we will look on the implementation of these two exception handlers.

Debug and Breakpoint exceptions
--------------------------------------------------------------------------------

Ok, we setup exception handlers in the `early_trap_init` function for the `#DB` and `#BP` exceptions and now is time to consider their implementations. But before we will do this, first of all let's look on details of these exceptions.

The first exceptions - `#DB` or `debug` exception occurs when a debug event occurs. For example - attempt to change the contents of a [debug register](http://en.wikipedia.org/wiki/X86_debug_register). Debug registers are special registers that were presented in `x86` processors starting from the [Intel 80386](http://en.wikipedia.org/wiki/Intel_80386) processor and as you can understand from name of this CPU extension, main purpose of these registers is debugging.

These registers allow to set breakpoints on the code and read or write data to trace it. Debug registers may be accessed only in the privileged mode and an attempt to read or write the debug registers when executing at any other privilege level causes a [general protection fault](https://en.wikipedia.org/wiki/General_protection_fault) exception. That's why we have used `set_intr_gate_ist` for the `#DB` exception, but not the `set_system_intr_gate_ist`.

The vector number of the `#DB` exceptions is `1` (we pass it as `X86_TRAP_DB`) and as we may read in specification, this exception has no error code:

```
+-----------------------------------------------------+
|Vector|Mnemonic|Description         |Type |Error Code|
+-----------------------------------------------------+
|1     | #DB    |Reserved            |F/T  |NO        |
+-----------------------------------------------------+
```

The second exception is `#BP` or `breakpoint` exception occurs when processor executes the [int 3](http://en.wikipedia.org/wiki/INT_%28x86_instruction%29#INT_3) instruction. Unlike the `DB` exception, the `#BP` exception may occur in userspace. We can add it anywhere in our code, for example let's look on the simple program:

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
$ ./breakpoint
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

From this moment we know a little about these two exceptions and we can move on to consideration of their handlers.

Preparation before an exception handler
--------------------------------------------------------------------------------

As you may note before, the `set_intr_gate_ist` and `set_system_intr_gate_ist` functions takes an addresses of exceptions handlers in theirs second parameter. In or case our two exception handlers will be:

* `debug`;
* `int3`.

You will not find these functions in the C code. All of that could be found in the kernel's `*.c/*.h` files only definition of these functions which are located in the [arch/x86/include/asm/traps.h](https://github.com/torvalds/linux/tree/master/arch/x86/include/asm/traps.h) kernel header file:

```C
asmlinkage void debug(void);
```

and

```C
asmlinkage void int3(void);
```

You may note `asmlinkage` directive in definitions of these functions. The directive is the special specificator of the [gcc](http://en.wikipedia.org/wiki/GNU_Compiler_Collection). Actually for a `C` functions which are called from assembly, we need in explicit declaration of the function calling convention. In our case, if function made with `asmlinkage` descriptor, then `gcc` will compile the function to retrieve parameters from stack.

So, both handlers are defined in the [arch/x86/entry/entry_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/entry_64.S) assembly source code file with the `idtentry` macro:

```assembly
idtentry debug do_debug has_error_code=0 paranoid=1 shift_ist=DEBUG_STACK
```

and

```assembly
idtentry int3 do_int3 has_error_code=0 paranoid=1 shift_ist=DEBUG_STACK
```

Each exception handler may consists of two parts. The first part is generic part and it is the same for all exception handlers. An exception handler should to save  [general purpose registers](https://en.wikipedia.org/wiki/Processor_register) on the stack, switch to kernel stack if an exception came from userspace and transfer control to the second part of an exception handler. The second part of an exception handler does certain work depends on certain exception. For example page fault exception handler should find virtual page for given address, invalid opcode exception handler should send `SIGILL` [signal](https://en.wikipedia.org/wiki/Unix_signal) and etc.

As we just saw, an exception handler starts from definition of the `idtentry` macro from the [arch/x86/entry/entry_64.S](https://github.com/torvalds/linux/blob/master/arch/x86/entry/entry_64.S) assembly source code file, so let's look at implementation of this macro. As we may see, the `idtentry` macro takes five arguments:

* `sym` - defines global symbol with the `.globl name` which will be an an entry of exception handler;
* `do_sym` - symbol name which represents a secondary entry of an exception handler;
* `has_error_code` - information about existence of an error code of exception.

The last two parameters are optional:

* `paranoid` - shows us how we need to check current mode (will see explanation in details later);
* `shift_ist` - shows us is an exception running at `Interrupt Stack Table`.

Definition of the `.idtentry` macro looks:

```assembly
.macro idtentry sym do_sym has_error_code:req paranoid=0 shift_ist=-1
ENTRY(\sym)
...
...
...
END(\sym)
.endm
```

Before we will consider internals of the `idtentry` macro, we should to know state of stack when an exception occurs. As we may read in the [Intel® 64 and IA-32 Architectures Software Developer’s Manual 3A](http://www.intel.com/content/www/us/en/processors/architectures-software-developer-manuals.html), the state of stack when an exception occurs is following:

```
    +------------+
+40 | %SS        |
+32 | %RSP       |
+24 | %RFLAGS    |
+16 | %CS        |
 +8 | %RIP       |
  0 | ERROR CODE | <-- %RSP
    +------------+
```

Now we may start to consider implementation of the `idtmacro`. Both `#DB` and `BP` exception handlers are defined as:

```assembly
idtentry debug do_debug has_error_code=0 paranoid=1 shift_ist=DEBUG_STACK
idtentry int3 do_int3 has_error_code=0 paranoid=1 shift_ist=DEBUG_STACK
```

If we will look at these definitions, we may know that compiler will generate two routines with `debug` and `int3` names and both of these exception handlers will call `do_debug` and `do_int3` secondary handlers after some preparation. The third parameter defines existence of error code and as we may see both our exception do not have them. As we may see on the diagram above, processor pushes error code on stack if an exception provides it. In our case, the `debug` and `int3` exception do not have error codes. This may bring some difficulties because stack will look differently for exceptions which provides error code and for exceptions which not. That's why implementation of the `idtentry` macro starts from putting a fake error code to the stack if an exception does not provide it:

```assembly
.ifeq \has_error_code
    pushq	$-1
.endif
```

But it is not only fake error-code. Moreover the `-1` also represents invalid system call number, so that the system call restart logic will not be triggered.

The last two parameters of the `idtentry` macro `shift_ist` and `paranoid` allow to know do an exception handler runned at stack from `Interrupt Stack Table` or not. You already may know that each kernel thread in the system has its own stack. In addition to these stacks, there are some specialized stacks associated with each processor in the system. One of these stacks is - exception stack. The [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture provides special feature which is called - `Interrupt Stack Table`. This feature allows to switch to a new stack for designated events such as an atomic exceptions like `double fault`, etc. So the `shift_ist` parameter allows us to know do we need to switch on `IST` stack for an exception handler or not.

The second parameter - `paranoid` defines the method which helps us to know did we come from userspace or not to an exception handler. The easiest way to determine this is to via `CPL` or `Current Privilege Level` in `CS` segment register. If it is equal to `3`, we came from userspace, if zero we came from kernel space:

```
testl $3,CS(%rsp)
jnz userspace
...
...
...
// we are from the kernel space
```

But unfortunately this method does not give a 100% guarantee. As described in the kernel documentation:

> if we are in an NMI/MCE/DEBUG/whatever super-atomic entry context,
> which might have triggered right after a normal entry wrote CS to the
> stack but before we executed SWAPGS, then the only safe way to check
> for GS is the slower method: the RDMSR.

In other words for example `NMI` could happen inside the critical section of a [swapgs](http://www.felixcloutier.com/x86/SWAPGS.html) instruction. In this way we should check value of the `MSR_GS_BASE` [model specific register](https://en.wikipedia.org/wiki/Model-specific_register) which stores pointer to the start of per-cpu area. So to check if we did come from userspace or not, we should to check value of the `MSR_GS_BASE` model specific register and if it is negative we came from kernel space, in other way we came from userspace:

```assembly
movl $MSR_GS_BASE,%ecx
rdmsr
testl %edx,%edx
js 1f
```

In first two lines of code we read value of the `MSR_GS_BASE` model specific register into `edx:eax` pair. We can't set negative value to the `gs` from userspace. But from other side we know that direct mapping of the physical memory starts from the `0xffff880000000000` virtual address. In this way, `MSR_GS_BASE` will contain an address from `0xffff880000000000` to `0xffffc7ffffffffff`. After the `rdmsr` instruction will be executed, the smallest possible value in the `%edx` register will be - `0xffff8800` which is `-30720` in unsigned 4 bytes. That's why kernel space `gs` which points to start of `per-cpu` area will contain negative value.

After we push fake error code on the stack, we should allocate space for general purpose registers with:

```assembly
ALLOC_PT_GPREGS_ON_STACK
```

macro which is defined in the [arch/x86/entry/calling.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/calling.h) header file. This macro just allocates 15*8 bytes space on the stack to preserve general purpose registers:

```assembly
.macro ALLOC_PT_GPREGS_ON_STACK addskip=0
    addq	$-(15*8+\addskip), %rsp
.endm
```

So the stack will look like this after execution of the `ALLOC_PT_GPREGS_ON_STACK`:

```
     +------------+
+160 | %SS        |
+152 | %RSP       |
+144 | %RFLAGS    |
+136 | %CS        |
+128 | %RIP       |
+120 | ERROR CODE |
     |------------|
+112 |            |
+104 |            |
 +96 |            |
 +88 |            |
 +80 |            |
 +72 |            |
 +64 |            |
 +56 |            |
 +48 |            |
 +40 |            |
 +32 |            |
 +24 |            |
 +16 |            |
  +8 |            |
  +0 |            | <- %RSP
     +------------+
```

After we allocated space for general purpose registers, we do some checks to understand did an exception come from userspace or not and if yes, we should move back to an interrupted process stack or stay on exception stack:

```assembly
.if \paranoid
    .if \paranoid == 1
	    testb	$3, CS(%rsp)
	    jnz	1f
	.endif
	call	paranoid_entry
.else
	call	error_entry
.endif
```

Let's consider all of these there cases in course.

An exception occurred in userspace
--------------------------------------------------------------------------------

In the first let's consider a case when an exception has `paranoid=1` like our `debug` and `int3` exceptions. In this case we check selector from `CS` segment register and jump at `1f` label if we came from userspace or the `paranoid_entry` will be called in other way.

Let's consider first case when we came from userspace to an exception handler. As described above we should jump at `1` label. The `1` label starts from the call of the

```assembly
call	error_entry
```

routine which saves all general purpose registers in the previously allocated area on the stack:

```assembly
SAVE_C_REGS 8
SAVE_EXTRA_REGS 8
```

These both macros are defined in the  [arch/x86/entry/calling.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/calling.h) header file and just move values of general purpose registers to a certain place at the stack, for example:

```assembly
.macro SAVE_EXTRA_REGS offset=0
	movq %r15, 0*8+\offset(%rsp)
	movq %r14, 1*8+\offset(%rsp)
	movq %r13, 2*8+\offset(%rsp)
	movq %r12, 3*8+\offset(%rsp)
	movq %rbp, 4*8+\offset(%rsp)
	movq %rbx, 5*8+\offset(%rsp)
.endm
```

After execution of `SAVE_C_REGS` and `SAVE_EXTRA_REGS` the stack will look:

```
     +------------+
+160 | %SS        |
+152 | %RSP       |
+144 | %RFLAGS    |
+136 | %CS        |
+128 | %RIP       |
+120 | ERROR CODE |
     |------------|
+112 | %RDI       |
+104 | %RSI       |
 +96 | %RDX       |
 +88 | %RCX       |
 +80 | %RAX       |
 +72 | %R8        |
 +64 | %R9        |
 +56 | %R10       |
 +48 | %R11       |
 +40 | %RBX       |
 +32 | %RBP       |
 +24 | %R12       |
 +16 | %R13       |
  +8 | %R14       |
  +0 | %R15       | <- %RSP
     +------------+
```

After the kernel saved general purpose registers at the stack, we should check that we came from userspace space again with:

```assembly
testb	$3, CS+8(%rsp)
jz	.Lerror_kernelspace
```

because we may have potentially fault if as described in documentation truncated `%RIP` was reported. Anyway, in both cases the [SWAPGS](http://www.felixcloutier.com/x86/SWAPGS.html) instruction will be executed and values from `MSR_KERNEL_GS_BASE` and `MSR_GS_BASE` will be swapped. From this moment the `%gs` register will point to the base address of kernel structures. So, the `SWAPGS` instruction is called and it was main point of the `error_entry` routing.

Now we can back to the `idtentry` macro. We may see following assembler code after the call of `error_entry`:

```assembly
movq	%rsp, %rdi
call	sync_regs
```

Here we put base address of stack pointer `%rdi` register which will be first argument (according to [x86_64 ABI](https://www.uclibc.org/docs/psABI-x86_64.pdf)) of the `sync_regs` function and call this function which is defined in the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/kernel/traps.c) source code file:

```C
asmlinkage __visible notrace struct pt_regs *sync_regs(struct pt_regs *eregs)
{
	struct pt_regs *regs = task_pt_regs(current);
	*regs = *eregs;
	return regs;
}
```

This function takes the result of the `task_ptr_regs` macro which is defined in the [arch/x86/include/asm/processor.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/include/asm/processor.h) header file, stores it in the stack pointer and returns it. The `task_ptr_regs` macro expands to the address of `thread.sp0` which represents pointer to the normal kernel stack:

```C
#define task_pt_regs(tsk)       ((struct pt_regs *)(tsk)->thread.sp0 - 1)
```

As we came from userspace, this means that exception handler will run in real process context. After we got stack pointer from the `sync_regs` we switch stack:

```assembly
movq	%rax, %rsp
```

The last two steps before an exception handler will call secondary handler are:

1. Passing pointer to `pt_regs` structure which contains preserved general purpose registers to the `%rdi` register:

```assembly
movq	%rsp, %rdi
```

as it will be passed as first parameter of secondary exception handler.

2. Pass error code to the `%rsi` register as it will be second argument of an exception handler and set it to `-1` on the stack for the same purpose as we did it before - to prevent restart of a system call:

```
.if \has_error_code
	movq	ORIG_RAX(%rsp), %rsi
	movq	$-1, ORIG_RAX(%rsp)
.else
	xorl	%esi, %esi
.endif
```

Additionally you may see that we zeroed the `%esi` register above in a case if an exception does not provide error code.

In the end we just call secondary exception handler:

```assembly
call	\do_sym
```

which:

```C
dotraplinkage void do_debug(struct pt_regs *regs, long error_code);
```

will be for `debug` exception and:

```C
dotraplinkage void notrace do_int3(struct pt_regs *regs, long error_code);
```

will be for `int 3` exception. In this part we will not see implementations of secondary handlers, because they are very specific, but will see some of them in one of next parts.

We just considered first case when an exception occurred in userspace. Let's consider last two.

An exception with paranoid > 0 occurred in kernelspace
--------------------------------------------------------------------------------

In this case an exception was occurred in kernelspace and `idtentry` macro is defined with `paranoid=1` for this exception. This value of `paranoid` means that we should use slower way that we saw in the beginning of this part to check do we really came from kernelspace or not. The `paranoid_entry` routing allows us to know this:

```assembly
ENTRY(paranoid_entry)
	cld
	SAVE_C_REGS 8
	SAVE_EXTRA_REGS 8
	movl	$1, %ebx
	movl	$MSR_GS_BASE, %ecx
	rdmsr
	testl	%edx, %edx
	js	1f
	SWAPGS
	xorl	%ebx, %ebx
1:	ret
END(paranoid_entry)
```

As you may see, this function represents the same that we covered before. We use second (slow) method to get information about previous state of an interrupted task. As we checked this and executed `SWAPGS` in a case if we came from userspace, we should to do the same that we did before: We need to put pointer to a structure which holds general purpose registers to the `%rdi` (which will be first parameter of a secondary handler) and put error code if an exception provides it to the `%rsi` (which will be second parameter of a secondary handler):

```assembly
movq	%rsp, %rdi

.if \has_error_code
	movq	ORIG_RAX(%rsp), %rsi
	movq	$-1, ORIG_RAX(%rsp)
.else
	xorl	%esi, %esi
.endif
```

The last step before a secondary handler of an exception will be called is cleanup of new `IST` stack frame:

```assembly
.if \shift_ist != -1
	subq	$EXCEPTION_STKSZ, CPU_TSS_IST(\shift_ist)
.endif
```

You may remember that we passed the `shift_ist` as argument of the `idtentry` macro. Here we check its value and if its not equal to `-1`, we get pointer to a stack from `Interrupt Stack Table` by `shift_ist` index and setup it.

In the end of this second way we just call secondary exception handler as we did it before:

```assembly
call	\do_sym
```

The last method is similar to previous both, but an exception occurred with `paranoid=0` and we may use fast method determination of where we are from.

Exit from an exception handler
--------------------------------------------------------------------------------

After secondary handler will finish its works, we will return to the `idtentry` macro and the next step will be jump to the `error_exit`:

```assembly
jmp	error_exit
```

routine. The `error_exit` function defined in the same [arch/x86/entry/entry_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/entry_64.S) assembly source code file and the main goal of this function is to know where we are from (from userspace or kernelspace) and execute `SWPAGS` depends on this. Restore registers to previous state and execute `iret` instruction to transfer control to an interrupted task.

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
* [Per-CPU variables](https://0xax.gitbook.io/linux-insides/summary/concepts/linux-cpu-1)
* [kgdb](https://en.wikipedia.org/wiki/KGDB)
* [ACPI](https://en.wikipedia.org/wiki/Advanced_Configuration_and_Power_Interface)
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/interrupts)
