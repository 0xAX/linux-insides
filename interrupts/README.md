# Interrupts and Interrupt Handling

In the following posts, we will cover interrupts and exceptions handling in the linux kernel.

* [Interrupts and Interrupt Handling. Part 1.](interrupts-1.md) - describes interrupts and interrupt handling theory.
* [Interrupts in the Linux Kernel](interrupts-2.md) - describes stuffs related to interrupts and exceptions handling from the early stage.
* [Early interrupt handlers](interrupts-3.md) - describes early interrupt handlers.
* [Interrupt handlers](interrupts-4.md) - describes first non-early interrupt handlers.
* [Implementation of exception handlers](interrupts-5.md) - describes implementation of some exception handlers such as double fault, divide by zero etc.
* [Handling non-maskable interrupts](interrupts-6.md) - describes handling of non-maskable interrupts and remaining interrupt handlers from the architecture-specific part.
* [External hardware interrupts](interrupts-7.md) - describes early initialization of code which is related to handling external hardware interrupts.
* [Non-early initialization of the IRQs](interrupts-8.md) - describes non-early initialization of code which is related to handling external hardware interrupts.
* [Softirq, Tasklets and Workqueues](interrupts-9.md) - describes softirqs, tasklets and workqueues concepts.
* [Last part](interrupts-10.md) - this is the last part of the `Interrupts and Interrupt Handling` chapter and here we will see a real hardware driver and some interrupts related stuff.
