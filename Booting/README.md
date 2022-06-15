# Kernel Boot Process

This chapter describes the linux kernel boot process. Here you will see a series of posts which describes the full cycle of the kernel loading process:

* [From the bootloader to kernel](linux-bootstrap-1.md) - describes all stages from turning on the computer to running the first instruction of the kernel.
* [First steps in the kernel setup code](linux-bootstrap-2.md) - describes first steps in the kernel setup code. You will see heap initialization, query of different parameters like EDD, IST and etc...
* [Video mode initialization and transition to protected mode](linux-bootstrap-3.md) - describes video mode initialization in the kernel setup code and transition to protected mode.
* [Transition to 64-bit mode](linux-bootstrap-4.md) - describes preparation for transition into 64-bit mode and details of transition.
* [Kernel Decompression](linux-bootstrap-5.md) - describes preparation before kernel decompression and details of direct decompression.
* [Kernel load address randomization](linux-bootstrap-6.md) - describes randomization of the Linux kernel load address.

This chapter coincides with `Linux kernel v4.17`.
