# Kernel mechanisms

Welcome to the chapter about core mechanisms of the Linux kernel. This chapter describes fundamental infrastructure which is not tied to one particular subsystem but is used all over the kernel - from variables with a separate copy for each processor to the way subsystems notify each other about events.

## How to read

This chapter assumes you are comfortable with the `C` programming language and have basic understanding of what the kernel does. You do not need to be a kernel expert, but being able to read short code snippets with macros and data structures will help.

Each part of this chapter focuses on one mechanism and the parts are mostly independent from each other, so you can read them in any order. Still, the suggested order below goes from simpler mechanisms to more complex ones. It is quite useful to have the source code of Linux kernel on your local computer to follow the details. You can obtain the source code using the following command:

```bash
git clone git@github.com:torvalds/linux.git
```
You can also obtain the source code through the Github CLI:

```bash
gh repo clone torvalds/linux
```

## Notation used

During reading this and other chapters, you may encounter special notation:

- `DEFINE_PER_CPU` and `per_cpu` - are macros for defining and accessing per-cpu variables
- `cpumask` - is a bitmap which represents a set of processors in the system
- `*_initcall` - are macros like `early_initcall` or `fs_initcall` which register a callback for a certain kernel initialization stage
- `notifier_block` - is the main data structure of the notification chains mechanism
- `0x...` - denotes hexadecimal values

## What you will learn

- How the kernel creates variables where each processor core has its own copy
- How the kernel keeps track of possible, present, online and active processors in the system
- How the kernel determines the correct order of initialization of its built-in subsystems
- How kernel subsystems subscribe to asynchronous events from other subsystems

## Reading order

This chapter does not have a special reading order since the majority of the concepts described in this chapter are not tightly depend on each other. You can read in any order. The following parts are presented in this chapter:

- [Per-CPU variables](linux-cpu-1.md) - how per-cpu variables are implemented and how to work with them
- [CPU masks](linux-cpu-2.md) - the bitmaps which describe sets of processors and the API around them
- [The initcall mechanism](linux-cpu-3.md) - the ordering of built-in modules and subsystems initialization
- [Notification Chains](linux-cpu-4.md) - how subsystems subscribe to and publish asynchronous events
