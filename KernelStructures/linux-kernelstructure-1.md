interrupt-descriptor table (IDT)
================================================================================

Three general interrupt & exceptions sources:

* Exceptions - sync;
* Software interrupts - sync;
* External interrupts - async.

Types of Exceptions:

* Faults - are precise exceptions reported on the boundary `before` the instruction causing the exception. The saved `%rip` points to the faulting instruction;
* Traps - are precise exceptions reported on the boundary `following` the instruction causing the exception. The same with `%rip`;
* Aborts - are imprecise exceptions. Because they are imprecise, aborts typically do not allow reliable program restart.

`Maskable` interrupts trigger the interrupt-handling mechanism only when RFLAGS.IF=1. Otherwise they are held pending for as long as the RFLAGS.IF bit is cleared to 0.

`Nonmaskable` interrupts (NMI) are unaffected by the value of the rFLAGS.IF bit. However, the occurrence of an NMI masks further NMIs until an IRET instruction is executed.

Specific exception and interrupt sources are assigned a fixed vector-identification number (also called an “interrupt vector” or simply “vector”). The interrupt vector is used by the interrupt-handling mechanism to locate the system-software service routine assigned to the exception or interrupt. Up to
256 unique interrupt vectors are available. The first 32 vectors are reserved for predefined exception and interrupt conditions. They are defined in the [arch/x86/include/asm/traps.h](http://lxr.free-electrons.com/source/arch/x86/include/asm/traps.h#L121) header file:

```
/* Interrupts/Exceptions */
enum {
	X86_TRAP_DE = 0,	/*  0, Divide-by-zero */
	X86_TRAP_DB,		/*  1, Debug */
	X86_TRAP_NMI,		/*  2, Non-maskable Interrupt */
	X86_TRAP_BP,		/*  3, Breakpoint */
	X86_TRAP_OF,		/*  4, Overflow */
	X86_TRAP_BR,		/*  5, Bound Range Exceeded */
	X86_TRAP_UD,		/*  6, Invalid Opcode */
	X86_TRAP_NM,		/*  7, Device Not Available */
	X86_TRAP_DF,		/*  8, Double Fault */
	X86_TRAP_OLD_MF,	/*  9, Coprocessor Segment Overrun */
	X86_TRAP_TS,		/* 10, Invalid TSS */
	X86_TRAP_NP,		/* 11, Segment Not Present */
	X86_TRAP_SS,		/* 12, Stack Segment Fault */
	X86_TRAP_GP,		/* 13, General Protection Fault */
	X86_TRAP_PF,		/* 14, Page Fault */
	X86_TRAP_SPURIOUS,	/* 15, Spurious Interrupt */
	X86_TRAP_MF,		/* 16, x87 Floating-Point Exception */
	X86_TRAP_AC,		/* 17, Alignment Check */
	X86_TRAP_MC,		/* 18, Machine Check */
	X86_TRAP_XF,		/* 19, SIMD Floating-Point Exception */
	X86_TRAP_IRET = 32,	/* 32, IRET Exception */
};
```

Error Codes
--------------------------------------------------------------------------------

The processor exception-handling mechanism reports error and status information for some exceptions using an error code. The error code is pushed onto the stack by the exception-mechanism during the control transfer into the exception handler. The error code has two formats:

* most error-reporting exceptions format;
* page fault format.

Here is format of selector error code:

```
31                           16 15                                  3   2   1   0
+-------------------------------------------------------------------------------+
|                              |                                    | T | I | E |
|           Reserved           |             Selector Index         | - | D | X |
|                              |                                    | I | T | T |
+-------------------------------------------------------------------------------+
```

Where:

* `EXT` - If this bit is set to 1, the exception source is external to the processor. If cleared to 0, the exception source is internal to the processor;
* `IDT` - If this bit is set to 1, the error-code selector-index field references a gate descriptor located in the `interrupt-descriptor table`. If cleared to 0, the selector-index field references a descriptor in either the `global-descriptor table` or local-descriptor table `LDT`, as indicated by the `TI` bit;
* `TI` - If this bit is set to 1, the error-code selector-index field references a descriptor in the `LDT`. If cleared to 0, the selector-index field references a descriptor in the `GDT`.
* `Selector Index` - The selector-index field specifies the index into either the `GDT`, `LDT`, or `IDT`, as specified by the `IDT` and `TI` bits.

Page-Fault Error Code format is:

```
31                                                              4   3   2   1   0
+-------------------------------------------------------------------------------+
|                                                         |     | R | U | R | - |
|                       Reserved                          | I/D | S | - | - | P |
|                                                         |     | V | S | W | - |
+-------------------------------------------------------------------------------+
```

Where:

* `I/D` - If this bit is set to 1, it indicates that the access that caused the page fault was an instruction fetch;
* `RSV` - If this bit is set to 1, the page fault is a result of the processor reading a 1 from a reserved field within a page-translation-table entry;
* `U/S` - If this bit is cleared to 0, an access in supervisor mode (`CPL=0, 1, or 2`) caused the page fault. If this bit is set to 1, an access in user mode (CPL=3) caused the page fault;
* `R/W` - If this bit is cleared to 0, the access that caused the page fault is a memory read. If this bit is set to 1, the memory access that caused the page fault was a write;
* `P` - If this bit is cleared to 0, the page fault was caused by a not-present page. If this bit is set to 1, the page fault was caused by a page-protection violation.

Interrupt Control Transfers
--------------------------------------------------------------------------------

The IDT may contain any of three kinds of gate descriptors:

* `Task Gate` - contains the segment selector for a TSS for an exception and/or interrupt handler task;
* `Interrupt Gate` - contains segment selector and offset that the processor uses to transfer program execution to a handler procedure in an interrupt handler code segment;
* `Trap Gate` - contains segment selector and offset that the processor uses to transfer program execution to a handler procedure in an exception handler code segment.

General format of gates is:

```
127                                                                             96
+-------------------------------------------------------------------------------+
|                                                                               |
|                                Reserved                                       |
|                                                                               |
+--------------------------------------------------------------------------------
95                                                                              64
+-------------------------------------------------------------------------------+
|                                                                               |
|                               Offset 63..32                                   |
|                                                                               |
+-------------------------------------------------------------------------------+
63                               48 47      46  44   42    39             34    32
+-------------------------------------------------------------------------------+
|                                  |       |  D  |   |     |      |   |   |     |
|       Offset 31..16              |   P   |  P  | 0 |Type |0 0 0 | 0 | 0 | IST |
|                                  |       |  L  |   |     |      |   |   |     |
 -------------------------------------------------------------------------------+
31                                   16 15                                      0
+-------------------------------------------------------------------------------+
|                                      |                                        |
|          Segment Selector            |                 Offset 15..0           |
|                                      |                                        |
+-------------------------------------------------------------------------------+
```

Where

* `Selector` - Segment Selector for destination code segment;
* `Offset` - Offset to handler procedure entry point;
* `DPL` - Descriptor Privilege Level;
* `P` - Segment Present flag;
* `IST` - Interrupt Stack Table;
* `TYPE` - one of: Local descriptor-table (LDT) segment descriptor, Task-state segment (TSS) descriptor, Call-gate descriptor, Interrupt-gate descriptor, Trap-gate descriptor or Task-gate descriptor.

An `IDT` descriptor is represented by the following structure in the Linux kernel (only for `x86_64`):

```C
struct gate_struct64 {
	u16 offset_low;
	u16 segment;
	unsigned ist : 3, zero0 : 5, type : 5, dpl : 2, p : 1;
	u16 offset_middle;
	u32 offset_high;
	u32 zero1;
} __attribute__((packed));
```

which is defined in the [arch/x86/include/asm/desc_defs.h](http://lxr.free-electrons.com/source/arch/x86/include/asm/desc_defs.h#L51) header file.

A task gate descriptor does not contain `IST` field and its format differs from interrupt/trap gates:

```C
struct ldttss_desc64 {
	u16 limit0;
	u16 base0;
	unsigned base1 : 8, type : 5, dpl : 2, p : 1;
	unsigned limit1 : 4, zero0 : 3, g : 1, base2 : 8;
	u32 base3;
	u32 zero1;
} __attribute__((packed));
```

Exceptions During a Task Switch
--------------------------------------------------------------------------------

An exception can occur during a task switch while loading a segment selector. Page faults can also occur when accessing a TSS. In these cases, the hardware task-switch mechanism completes loading the new task state from the TSS, and then triggers the appropriate exception mechanism.

**In long mode, an exception cannot occur during a task switch, because the hardware task-switch mechanism is disabled.**

Nonmaskable interrupt
--------------------------------------------------------------------------------

**TODO**

API
--------------------------------------------------------------------------------

**TODO**

Interrupt Stack Table
--------------------------------------------------------------------------------

**TODO**
