# Toolchain and binaries

Welcome to the chapter about the toolchain behind the Linux kernel. This chapter describes the tools which are used to build the kernel and the format of the binaries they produce - from the moment you execute `make` in the root of the kernel source tree, through linking of object files, to the resulting `ELF` binaries and the assembly code embedded in the kernel sources.

## How to read

This chapter assumes you are comfortable with the `C` programming language and with building programs from the command line. You do not need previous experience with kernel development, but being able to read short code snippets and makefile fragments will help.

Each part of this chapter focuses on one tool or format. The parts build on each other, so read in order the first time, then revisit individual parts as references when you need to recall how a specific tool or format works. It is quite useful to have the source code of Linux kernel on your local computer to follow the details. You can obtain the source code using the following command:

```bash
git clone git@github.com:torvalds/linux.git
```
You can also obtain the source code through the Github CLI:

```bash
gh repo clone torvalds/linux
```

## Notation used

During reading this and other chapters, you may encounter special notation:

- `make` and `Makefile` - refer to the build tool which drives the kernel compilation and its input files
- `vmlinux` and `bzImage` - are the resident kernel image and the compressed bootable kernel image
- `*.o` - denotes object files produced by the compiler before linking
- `ELF` - is the Executable and Linkable Format, the standard binary format on Linux
- `__asm__` - marks inline assembly statements embedded in `C` code
- `0x...` - denotes hexadecimal values

## What you will learn

- What happens when you execute `make` in the root directory of the Linux kernel source code and how the `bzImage` is produced
- How the linker combines object files into an executable and how linker scripts control this process
- The structure of `ELF` binaries and how the Linux kernel describes them in its source code
- How to read and write inline assembly statements in both their basic and extended forms

## Reading order

This chapter does not have a special reading order since the majority of the concepts described in this chapter are not tightly depend on each other. You can read in any order. The following parts are presented in this chapter:

- [How the kernel is compiled](linux-toolchain-1.md) - from the `make` execution to the building of the `bzImage`
- [Linkers](linux-toolchain-2.md) - the linking process, object files and linker scripts
- [Executable and Linkable Format](linux-toolchain-3.md) - the structure of `ELF` binaries and their representation in the kernel
- [Inline assembly](linux-toolchain-4.md) - basic and extended forms of inline assembly with examples
