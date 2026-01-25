# Kernel Boot Process

Welcome to the boot journey of the Linux kernel, from power-on to the first instruction of the decompressed kernel. This chapter walks the complete boot path step by step from the moment you power on your computer to the moment the Linux kernel loaded in the memory of your machine.

## How to read

This chapter assumes you are comfortable with basic computer architecture and have a light familiarity with `C` programming language and x86_64 assembly syntax. You do not need to be a kernel expert, but being able to read short code snippets and recognize hardware terms will help.

Each part of this chapter focuses on one boot phase. Read in order the first time, then revisit individual steps as references when you want to map a specific symbol or register setup to its place in the sequence. It is quite useful to have the source code of Linux kernel on your local computer to follow the details. You can obtain the source code using the following command:

```bash
git clone git@github.com:torvalds/linux.git
```

## Notation used

During reading this and other chapters, you may encounter special notation:

- `CS`, `DS`, `SS`, `CR0`, `CR3`, `CR4`, `EFER` - refer to x86 segment and control registers
- `0x...` - denotes hexadecimal values
- `entry_*` and `startup_*` - are common prefixes for early boot symbols
- `setup code` refers to the early part of the Linux kernel which executes preparation to load the kernel code itself into memory
- `decompressor` refers to the part of the `setup code` that inflates the compressed kernel image into memory

## What you will learn

- The way a processor reaches the kernel entry point from firmware and the bootloader
- Different modes of x86_64 processors
- What the early setup code does before the kernel itself will be loaded into memory and start its work

## Reading order

1. [From the bootloader to kernel](linux-bootstrap-1.md) - from power-on to the first instruction in the kernel
2. [First steps in the kernel setup code](linux-bootstrap-2.md) - early setup, heap init, parameter discovery (EDD, IST, and more)
3. [Video mode initialization and transition to protected mode](linux-bootstrap-3.md) - video mode setup and the move to protected mode
4. [Transition to 64-bit mode](linux-bootstrap-4.md) - preparation and the jump into long mode
5. [Kernel Decompression](linux-bootstrap-5.md) - pre-decompression setup and the decompressor itself
6. [Kernel load address randomization](linux-bootstrap-6.md) - how KASLR picks a load address

## Kernel version

This chapter corresponds to `Linux kernel v6.18`.
