# Kernel Boot Process

This chapter describes the linux kernel boot process. Here you will see a
couple of posts which describes the full cycle of the kernel loading process:

* [From the bootloader to kernel](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-1.html) - describes all stages from turning on the computer to running the first instruction of the kernel.
* [First steps in the kernel setup code](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-2.html) - describes first steps in the kernel setup code. You will see heap initialization, query of different parameters like EDD, IST and etc...
* [Video mode initialization and transition to protected mode](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-3.html) - describes video mode initialization in the kernel setup code and transition to protected mode.
* [Transition to 64-bit mode](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-4.html) - describes preparation for transition into 64-bit mode and details of transition.
* [Kernel Decompression](http://0xax.gitbooks.io/linux-insides/content/Booting/linux-bootstrap-5.html) - describes preparation before kernel decompression and details of direct decompression.
