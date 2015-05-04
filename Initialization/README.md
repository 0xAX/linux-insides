# Kernel initialization process

You will find here a couple of posts which describe the full cycle of kernel initialization from its first steps after the kernel has decompressed to the start of the first process run by the kernel itself.

* [First steps after kernel decompression](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-1.md) - describes first steps in the kernel.
* [Early interrupt and exception handling](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-2.md) - describes early interrupts initialization and early page fault handler.
* [Last preparations before the kernel entry point](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-3.md) - describes the last preparations before the call of the `start_kernel`.
* [Kernel entry point](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-4.md) - describes first steps in the kernel generic code.
* [Continue of architecture-specific initializations](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-5.md) - describes architecture-specific initialization.
* [Architecture-specific initializations, again...](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-6.md) - describes continue of the architecture-specific initialization process.
* [The End of the architecture-specific initializations, almost...](https://github.com/0xAX/linux-insides/blob/master/Initialization/linux-initialization-7.md) - describes the end of the `setup_arch` related stuff.
