# x86-64 fundamentals

Welcome to the chapter on [`x86_64`](https://en.wikipedia.org/wiki/X86-64) fundamentals and the core data structures used by the Linux kernel on this architecture. The concepts introduced here provide the foundation for understanding the Linux kernel source code throughout the rest of this book.

Most of the information is taken from the following official manuals:

- [Intel® 64 and IA-32 Architectures Software Developer Manuals](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)
- [AMD64 Architecture Programmer's Manual, Volumes 1-5](https://docs.amd.com/v/u/en-US/40332_4.09_APM_PUB)

Of course, I'm also basing this chapter on the Linux kernel [source code](https://github.com/torvalds/linux).

## How to read

This chapter assumes you are comfortable with basic computer architecture and have a light familiarity with the `C` programming language and x86_64 assembly syntax. You do not need to be a kernel expert, but being able to read short code snippets and recognize hardware terms will help.

Each part of this chapter covers one concept of the Intel 64-bit architecture and explains how it is used and implemented in the Linux kernel. It is quite useful to have the source code of the Linux kernel on your local computer to follow the details. You can get the source code using the following command:

```bash
git clone git@github.com:torvalds/linux.git
```

Alternatively, you can get the source code through the GitHub CLI:

```bash
gh repo clone torvalds/linux
```

## Notation used

When reading this and other chapters, you may encounter special notation:

- `CS`, `DS`, `SS`, `CR0`, `CR3`, `CR4`, `EFER` - refer to x86 segment and control registers
- `0x...` - denotes hexadecimal values
- `entry_*` and `startup_*` - common prefixes for early boot symbols
- `setup code` refers to the early part of the Linux kernel which executes preparation to load the kernel code itself into memory
- `decompressor` refers to the part of the `setup code` that inflates the compressed kernel image into memory

## What you will learn

- Fundamental x86_64 structures like GDT, IDT and others
- Paging structure and kernel API

## Reading order

The topics in this chapter are independent of one another, so you can read the sections in any order. The chapter covers the following topics:

- [Paging](linux-x86-1.md)
- [Interrupt Descriptor Table](linux-x86-2.md)

## Kernel version

This chapter corresponds to `Linux kernel v7.1.0`.
