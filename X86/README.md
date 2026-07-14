# x86-64 fundamentals

Welcome to the chapter about the x86-64 fundamentals and the fundamental structures used by the Linux kernel for this architecture.

This chapter describes fundamental concepts and structures of the [`x86_64`](https://en.wikipedia.org/wiki/X86-64) architecture which are useful to know before and during diving into the Linux kernel source code.

Most of the information is taken from the following official manuals:

- [Intel® 64 and IA-32 Architectures Software Developer Manuals](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)
- [AMD64 Architecture Programmer's Manual, Volumes 1-5](https://docs.amd.com/v/u/en-US/40332_4.09_APM_PUB)

and of course from the Linux kernel [source code](https://github.com/torvalds/linux).

Each part of this chapter one concept of the Intel 64-bit architecture and how it is used or implemented in the Linux kernel. It is quite useful to have the source code of Linux kernel on your local computer to follow the details. You can obtain the source code using the following command:

```bash
git clone git@github.com:torvalds/linux.git
```
You can also obtain the source code through the Github CLI:

```bash
gh repo clone torvalds/linux
```

## How to read

This chapter assumes you are comfortable with basic computer architecture and have a light familiarity with `C` programming language and x86_64 assembly syntax. You do not need to be a kernel expert, but being able to read short code snippets and recognize hardware terms will help.

## Notation used

During reading this and other chapters, you may encounter special notation:

- `CS`, `DS`, `SS`, `CR0`, `CR3`, `CR4`, `EFER` - refer to x86 segment and control registers
- `0x...` - denotes hexadecimal values
- `entry_*` and `startup_*` - are common prefixes for early boot symbols
- `setup code` refers to the early part of the Linux kernel which executes preparation to load the kernel code itself into memory
- `decompressor` refers to the part of the `setup code` that inflates the compressed kernel image into memory

## What you will learn

## Reading order

This chapter does not have a special reading order since the majority of the concepts described in this chapter are not tightly depend on each other. You can read in any order. The following parts are presented in this chapter:

- [Paging](linux-x86-1.md)
- [Interrupt Descriptor Table](linux-x86-2.md)

## Kernel version

This chapter corresponds to `Linux kernel v7.1.0`.
