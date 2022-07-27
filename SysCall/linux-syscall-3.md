System calls in the Linux kernel. Part 3.
================================================================================

vsyscalls and vDSO
--------------------------------------------------------------------------------

This is the third part of the [chapter](https://0xax.gitbook.io/linux-insides/summary/syscall) that describes system calls in the Linux kernel and we saw preparations after a system call caused by a userspace application and process of handling of a system call in the previous [part](https://0xax.gitbook.io/linux-insides/summary/syscall/linux-syscall-2). In this part we will look at two concepts that are very close to the system call concept, they are called `vsyscall` and `vdso`.

We already know what `system call`s are. They are special routines in the Linux kernel which userspace applications ask to do privileged tasks, like to read or to write to a file, to open a socket, etc. As you may know, invoking a system call is an expensive operation in the Linux kernel, because the processor must interrupt the currently executing task and switch context to kernel mode, subsequently jumping again into userspace after the system call handler finishes its work. These two mechanisms - `vsyscall` and `vdso` are designed to speed up this process for certain system calls and in this part we will try to understand how these mechanisms work.

Introduction to vsyscalls
--------------------------------------------------------------------------------

The `vsyscall` or `virtual system call` is the first and oldest mechanism in the Linux kernel that is designed to accelerate execution of certain system calls. The principle of work of the `vsyscall` concept is simple. The Linux kernel maps into user space a page that contains some variables and the implementation of some system calls. We can find information about this memory space in the Linux kernel [documentation](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/Documentation/x86/x86_64/mm.txt) for the [x86_64](https://en.wikipedia.org/wiki/X86-64):

```
ffffffffff600000 - ffffffffffdfffff (=8 MB) vsyscalls
```

or:

```
~$ sudo cat /proc/1/maps | grep vsyscall
ffffffffff600000-ffffffffff601000 r-xp 00000000 00:00 0                  [vsyscall]
```

After this, these system calls will be executed in userspace and this means that there will not be [context switching](https://en.wikipedia.org/wiki/Context_switch). Mapping of the `vsyscall` page occurs in the `map_vsyscall` function that is defined in the [arch/x86/entry/vsyscall/vsyscall_64.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vsyscall/vsyscall_64.c) source code file. This function is called during the Linux kernel initialization in the `setup_arch` function that is defined in the [arch/x86/kernel/setup.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/setup.c) source code file (we saw this function in the fifth [part](https://0xax.gitbook.io/linux-insides/summary/initialization/linux-initialization-5) of the Linux kernel initialization process chapter).

Note that implementation of the `map_vsyscall` function depends on the `CONFIG_X86_VSYSCALL_EMULATION` kernel configuration option:

```C
#ifdef CONFIG_X86_VSYSCALL_EMULATION
extern void map_vsyscall(void);
#else
static inline void map_vsyscall(void) {}
#endif
```

As we can read in the help text, the `CONFIG_X86_VSYSCALL_EMULATION` configuration option: `Enable vsyscall emulation`. Why emulate `vsyscall`? Actually, the `vsyscall` is a legacy [ABI](https://en.wikipedia.org/wiki/Application_binary_interface) due to security reasons. Virtual system calls have fixed addresses, meaning that `vsyscall` page is still at the same location every time and the location of this page is determined in the `map_vsyscall` function. Let's look on the implementation of this function:

```C
void __init map_vsyscall(void)
{
    extern char __vsyscall_page;
    unsigned long physaddr_vsyscall = __pa_symbol(&__vsyscall_page);
	...
	...
	...
}
```

As we can see, at the beginning of the `map_vsyscall` function we get the physical address of the `vsyscall` page with the `__pa_symbol` macro (we already saw implementation if this macro in the fourth [path](https://0xax.gitbook.io/linux-insides/summary/initialization/linux-initialization-4) of the Linux kernel initialization process). The `__vsyscall_page` symbol defined in the [arch/x86/entry/vsyscall/vsyscall_emu_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vsyscall/vsyscall_emu_64.S) assembly source code file and have the following [virtual address](https://en.wikipedia.org/wiki/Virtual_address_space):

```
ffffffff81881000 D __vsyscall_page
```

in the `.data..page_aligned, aw` [section](https://en.wikipedia.org/wiki/Memory_segmentation) and contains call of the three following system calls:

* `gettimeofday`;
* `time`;
* `getcpu`.

Or:

```assembly
__vsyscall_page:
	mov $__NR_gettimeofday, %rax
	syscall
	ret

	.balign 1024, 0xcc
	mov $__NR_time, %rax
	syscall
	ret

	.balign 1024, 0xcc
	mov $__NR_getcpu, %rax
	syscall
	ret
```

Let's go back to the implementation of the `map_vsyscall` function and return to the implementation of the `__vsyscall_page` later. After we received the physical address of the `__vsyscall_page`, we check the value of the `vsyscall_mode` variable and set the [fix-mapped](https://0xax.gitbook.io/linux-insides/summary/mm/linux-mm-2) address for the `vsyscall` page with the `__set_fixmap` macro:

```C
if (vsyscall_mode != NONE)
	__set_fixmap(VSYSCALL_PAGE, physaddr_vsyscall,
                 vsyscall_mode == NATIVE
                             ? PAGE_KERNEL_VSYSCALL
                             : PAGE_KERNEL_VVAR);
```

The `__set_fixmap` takes three arguments: The first is index of the `fixed_addresses` [enum](https://en.wikipedia.org/wiki/Enumerated_type). In our case `VSYSCALL_PAGE` is the first element of the `fixed_addresses` enum for the `x86_64` architecture:

```C
enum fixed_addresses {
...
...
...
#ifdef CONFIG_X86_VSYSCALL_EMULATION
	VSYSCALL_PAGE = (FIXADDR_TOP - VSYSCALL_ADDR) >> PAGE_SHIFT,
#endif
...
...
...
```

It equal to the `511`. The second argument is the physical address of the page that has to be mapped and the third argument is the flags of the page. Note that the flags of the `VSYSCALL_PAGE` depend on the `vsyscall_mode` variable. It will be `PAGE_KERNEL_VSYSCALL` if the `vsyscall_mode` variable is `NATIVE` and the `PAGE_KERNEL_VVAR` otherwise. Both macros (the `PAGE_KERNEL_VSYSCALL` and the `PAGE_KERNEL_VVAR`) will be expanded to the following flags:

```C
#define __PAGE_KERNEL_VSYSCALL          (__PAGE_KERNEL_RX | _PAGE_USER)
#define __PAGE_KERNEL_VVAR              (__PAGE_KERNEL_RO | _PAGE_USER)
```

that represent access rights to the `vsyscall` page. Both flags have the same `_PAGE_USER` flags that means that the page can be accessed by a user-mode process running at lower privilege levels. The second flag depends on the value of the `vsyscall_mode` variable. The first flag (`__PAGE_KERNEL_VSYSCALL`) will be set in the case where `vsyscall_mode` is `NATIVE`. This means virtual system calls will be native `syscall` instructions. In other way the vsyscall will have `PAGE_KERNEL_VVAR` if the `vsyscall_mode` variable will be `emulate`. In this case virtual system calls will be turned into traps and are emulated reasonably. The `vsyscall_mode` variable gets its value in the `vsyscall_setup` function:

```C
static int __init vsyscall_setup(char *str)
{
	if (str) {
		if (!strcmp("emulate", str))
			vsyscall_mode = EMULATE;
		else if (!strcmp("native", str))
			vsyscall_mode = NATIVE;
		else if (!strcmp("none", str))
			vsyscall_mode = NONE;
		else
			return -EINVAL;

		return 0;
	}

	return -EINVAL;
}
```

That will be called during early kernel parameters parsing:

```C
early_param("vsyscall", vsyscall_setup);
```

More about `early_param` macro you can read in the sixth [part](https://0xax.gitbook.io/linux-insides/summary/initialization/linux-initialization-6) of the chapter that describes process of the initialization of the Linux kernel.

In the end of the `vsyscall_map` function we just check that virtual address of the `vsyscall` page is equal to the value of the `VSYSCALL_ADDR` with the [BUILD_BUG_ON](https://0xax.gitbook.io/linux-insides/summary/initialization/linux-initialization-1) macro:

```C
BUILD_BUG_ON((unsigned long)__fix_to_virt(VSYSCALL_PAGE) !=
             (unsigned long)VSYSCALL_ADDR);
```

That's all. `vsyscall` page is set up. The result of the all the above is the following: If we pass `vsyscall=native` parameter to the kernel command line, virtual system calls will be handled as native `syscall` instructions in the [arch/x86/entry/vsyscall/vsyscall_emu_64.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vsyscall/vsyscall_emu_64.S). The [glibc](https://en.wikipedia.org/wiki/GNU_C_Library) knows addresses of the virtual system call handlers. Note that virtual system call handlers are aligned by `1024` (or `0x400`) bytes:

```assembly
__vsyscall_page:
	mov $__NR_gettimeofday, %rax
	syscall
	ret

	.balign 1024, 0xcc
	mov $__NR_time, %rax
	syscall
	ret

	.balign 1024, 0xcc
	mov $__NR_getcpu, %rax
	syscall
	ret
```

And the start address of the `vsyscall` page is the `ffffffffff600000` every time. So, the [glibc](https://en.wikipedia.org/wiki/GNU_C_Library) knows the addresses of the all virtual system call handlers. You can find definition of these addresses in the `glibc` source code:

```C
#define VSYSCALL_ADDR_vgettimeofday   0xffffffffff600000
#define VSYSCALL_ADDR_vtime 	      0xffffffffff600400
#define VSYSCALL_ADDR_vgetcpu	      0xffffffffff600800
```

All virtual system call requests will fall into the `__vsyscall_page` + `VSYSCALL_ADDR_vsyscall_name` offset, put the number of a virtual system call to the `rax` general purpose [register](https://en.wikipedia.org/wiki/Processor_register) and the native for the x86_64 `syscall` instruction will be executed.

In the second case, if we pass `vsyscall=emulate` parameter to the kernel command line, an attempt to perform virtual system call handler will cause a [page fault](https://en.wikipedia.org/wiki/Page_fault) exception. Of course, remember, the `vsyscall` page has `__PAGE_KERNEL_VVAR` access rights that forbid execution. The `do_page_fault` function is the `#PF` or page fault handler. It tries to understand the reason of the last page fault. And one of the reason can be situation when virtual system call called and `vsyscall` mode is `emulate`. In this case `vsyscall` will be handled by the `emulate_vsyscall` function that defined in the [arch/x86/entry/vsyscall/vsyscall_64.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vsyscall/vsyscall_64.c) source code file.

The `emulate_vsyscall` function gets the number of a virtual system call, checks it, prints error and sends [segmentation fault](https://en.wikipedia.org/wiki/Segmentation_fault) simply:

```C
...
...
...
vsyscall_nr = addr_to_vsyscall_nr(address);
if (vsyscall_nr < 0) {
	warn_bad_vsyscall(KERN_WARNING, regs, "misaligned vsyscall...);
	goto sigsegv;
}
...
...
...
sigsegv:
	force_sig(SIGSEGV, current);
	return true;
```

As it checked number of a virtual system call, it does some yet another checks like `access_ok` violations and execute system call function depends on the number of a virtual system call:

```C
switch (vsyscall_nr) {
	case 0:
		ret = sys_gettimeofday(
			(struct timeval __user *)regs->di,
			(struct timezone __user *)regs->si);
		break;
	...
	...
	...
}
```

In the end we put the result of the `sys_gettimeofday` or another virtual system call handler to the `ax` general purpose register, as we did it with the normal system calls and restore the [instruction pointer](https://en.wikipedia.org/wiki/Program_counter) register and add `8` bytes to the [stack pointer](https://en.wikipedia.org/wiki/Stack_register) register. This operation emulates `ret` instruction.

```C
	regs->ax = ret;

do_ret:
	regs->ip = caller;
	regs->sp += 8;
	return true;
```

That's all. Now let's look on the modern concept - `vDSO`.

Introduction to vDSO
--------------------------------------------------------------------------------

As I already wrote above, `vsyscall` is an obsolete concept and replaced by the `vDSO` or `virtual dynamic shared object`. The main difference between the `vsyscall` and `vDSO` mechanisms is that `vDSO` maps memory pages into each process in a shared object [form](https://en.wikipedia.org/wiki/Library_%28computing%29#Shared_libraries), but `vsyscall` is static in memory and has the same address every time. For the `x86_64` architecture it is called -`linux-vdso.so.1`. All userspace applications that dynamically link to `glibc` will use the `vDSO` automatically. For example:

```
~$ ldd /bin/uname
	linux-vdso.so.1 (0x00007ffe014b7000)
	libc.so.6 => /lib64/libc.so.6 (0x00007fbfee2fe000)
	/lib64/ld-linux-x86-64.so.2 (0x00005559aab7c000)
```

Or:

```
~$ sudo cat /proc/1/maps | grep vdso
7fff39f73000-7fff39f75000 r-xp 00000000 00:00 0       [vdso]
```

Here we can see that [uname](https://en.wikipedia.org/wiki/Uname) util was linked with the three libraries:

* `linux-vdso.so.1`;
* `libc.so.6`;
* `ld-linux-x86-64.so.2`.

The first provides `vDSO` functionality, the second is `C` [standard library](https://en.wikipedia.org/wiki/C_standard_library) and the third is the program interpreter (more about this you can read in the part that describes [linkers](https://0xax.gitbook.io/linux-insides/summary/misc/linux-misc-3)). So, the `vDSO` solves limitations of the `vsyscall`. Implementation of the `vDSO` is similar to `vsyscall`.

Initialization of the `vDSO` occurs in the `init_vdso` function that defined in the [arch/x86/entry/vdso/vma.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vdso/vma.c) source code file. This function starts from the initialization of the `vDSO` images for 32-bits and 64-bits depends on the `CONFIG_X86_X32_ABI` kernel configuration option:

```C
static int __init init_vdso(void)
{
	init_vdso_image(&vdso_image_64);

#ifdef CONFIG_X86_X32_ABI
	init_vdso_image(&vdso_image_x32);
#endif
```

Both functions initialize the `vdso_image` structure. This structure is defined in the two generated source code files: the [arch/x86/entry/vdso/vdso-image-64.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vdso/vdso-image-64.c) and the [arch/x86/entry/vdso/vdso-image-32.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vdso/vdso-image-32.c). These source code files generated by the [vdso2c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vdso/vdso2c.c) program from the different source code files, represent different approaches to call a system call like `int 0x80`, `sysenter`, etc. The full set of the images depends on the kernel configuration.

For example for the `x86_64` Linux kernel it will contain `vdso_image_64`:

```C
#ifdef CONFIG_X86_64
extern const struct vdso_image vdso_image_64;
#endif
```

But for the `x86` - `vdso_image_32`:

```C
#ifdef CONFIG_X86_X32
extern const struct vdso_image vdso_image_x32;
#endif
```

If our kernel is configured for the `x86` architecture or for the `x86_64` and compatibility mode, we will have ability to call a system call with the `int 0x80` interrupt, if compatibility mode is enabled, we will be able to call a system call with the native `syscall instruction` or `sysenter` instruction in other way:

```C
#if defined CONFIG_X86_32 || defined CONFIG_COMPAT
  extern const struct vdso_image vdso_image_32_int80;
#ifdef CONFIG_COMPAT
  extern const struct vdso_image vdso_image_32_syscall;
#endif
 extern const struct vdso_image vdso_image_32_sysenter;
#endif
```

As we can understand from the name of the `vdso_image` structure, it represents image of the `vDSO` for the certain mode of the system call entry. This structure contains information about size in bytes of the `vDSO` area that's always a multiple of `PAGE_SIZE` (`4096` bytes), pointer to the text mapping, start and end address of the `alternatives` (set of instructions with better alternatives for the certain type of the processor), etc. For example `vdso_image_64` looks like this:

```C
const struct vdso_image vdso_image_64 = {
	.data = raw_data,
	.size = 8192,
	.text_mapping = {
		.name = "[vdso]",
		.pages = pages,
	},
	.alt = 3145,
	.alt_len = 26,
	.sym_vvar_start = -8192,
	.sym_vvar_page = -8192,
	.sym_hpet_page = -4096,
};
```

Where the `raw_data` contains raw binary code of the 64-bit `vDSO` system calls which are `2` page size:

```C
static struct page *pages[2];
```

or 8 Kilobytes.

The `init_vdso_image` function is defined in the same source code file and just initializes the `vdso_image.text_mapping.pages`. First of all this function calculates the number of pages and initializes each `vdso_image.text_mapping.pages[number_of_page]` with the `virt_to_page` macro that converts given address to the `page` structure:

```C
void __init init_vdso_image(const struct vdso_image *image)
{
	int i;
	int npages = (image->size) / PAGE_SIZE;

	for (i = 0; i < npages; i++)
		image->text_mapping.pages[i] =
			virt_to_page(image->data + i*PAGE_SIZE);
	...
	...
	...
}
```

The `init_vdso` function passed to the `subsys_initcall` macro adds the given function to the `initcalls` list. All functions from this list will be called in the `do_initcalls` function from the [init/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/init/main.c) source code file:

```C
subsys_initcall(init_vdso);
```

Ok, we just saw initialization of the `vDSO` and initialization of `page` structures that are related to the memory pages that contain `vDSO` system calls. But to where do their pages map? Actually they are mapped by the kernel, when it loads binary to the memory. The Linux kernel calls the `arch_setup_additional_pages` function from the [arch/x86/entry/vdso/vma.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/entry/vdso/vma.c) source code file that checks that `vDSO` enabled for the `x86_64` and calls the `map_vdso` function:

```C
int arch_setup_additional_pages(struct linux_binprm *bprm, int uses_interp)
{
	if (!vdso64_enabled)
		return 0;

	return map_vdso(&vdso_image_64, true);
}
```

The `map_vdso` function is defined in the same source code file and maps pages for the `vDSO` and for the shared `vDSO` variables. That's all. The main differences between the `vsyscall` and the `vDSO` concepts is that `vsyscall` has a static address of `ffffffffff600000` and implements three system calls, whereas the `vDSO` loads dynamically and implements five system calls, as defined in [arch/x86/entry/vdso/vma.c](https://github.com/torvalds/linux/blob/master/arch/x86/entry/vdso/vdso.lds.S):

* `__vdso_clock_gettime`;
* `__vdso_getcpu`;
* `__vdso_gettimeofday`;
* `__vdso_time`;
* `__vdso_clock_getres`.


That's all.

Conclusion
--------------------------------------------------------------------------------

This is the end of the third part about the system calls concept in the Linux kernel. In the previous [part](https://0xax.gitbook.io/linux-insides/summary/syscall/linux-syscall-2) we discussed the implementation of the preparation from the Linux kernel side, before a system call will be handled and implementation of the `exit` process from a system call handler. In this part we continued to dive into the stuff which is related to the system call concept and learned two new concepts that are very similar to the system call - the `vsyscall` and the `vDSO`.

After all of these three parts, we know almost all things that are related to system calls, we know what system call is and why user applications need them.  We also know what occurs when a user application calls a system call and how the kernel handles system calls.

The next part will be the last part in this [chapter](https://0xax.gitbook.io/linux-insides/summary/syscall) and we will see what occurs when a user runs the program.

If you have questions or suggestions, feel free to ping me in twitter [0xAX](https://twitter.com/0xAX), drop me [email](mailto:anotherworldofworld@gmail.com) or just create [issue](https://github.com/0xAX/linux-insides/issues/new).

**Please note that English is not my first language and I am really sorry for any inconvenience. If you found any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [x86_64 memory map](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/Documentation/x86/x86_64/mm.txt)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [context switching](https://en.wikipedia.org/wiki/Context_switch)
* [ABI](https://en.wikipedia.org/wiki/Application_binary_interface)
* [virtual address](https://en.wikipedia.org/wiki/Virtual_address_space)
* [Segmentation](https://en.wikipedia.org/wiki/Memory_segmentation)
* [enum](https://en.wikipedia.org/wiki/Enumerated_type)
* [fix-mapped addresses](https://0xax.gitbook.io/linux-insides/summary/mm/linux-mm-2)
* [glibc](https://en.wikipedia.org/wiki/GNU_C_Library)
* [BUILD_BUG_ON](https://0xax.gitbook.io/linux-insides/summary/initialization/linux-initialization-1)
* [Processor register](https://en.wikipedia.org/wiki/Processor_register)
* [Page fault](https://en.wikipedia.org/wiki/Page_fault)
* [segmentation fault](https://en.wikipedia.org/wiki/Segmentation_fault)
* [instruction pointer](https://en.wikipedia.org/wiki/Program_counter)
* [stack pointer](https://en.wikipedia.org/wiki/Stack_register)
* [uname](https://en.wikipedia.org/wiki/Uname)
* [Linkers](https://0xax.gitbook.io/linux-insides/summary/misc/linux-misc-3)
* [Previous part](https://0xax.gitbook.io/linux-insides/summary/syscall/linux-syscall-2)
