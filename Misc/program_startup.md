Program startup process in userspace
================================================================================

Introduction
--------------------------------------------------------------------------------

Despite the [linux-insides](https://www.gitbook.com/book/0xax/linux-insides/details) described mostly Linux kernel related stuff, I have decided to write this one part which mostly related to userspace.

There is already fourth [part](https://0xax.gitbooks.io/linux-insides/content/SysCall/syscall-4.html) of [system calls](https://en.wikipedia.org/wiki/System_call) chapter which describes what does the Linux kernel do when we want to start a program. In this part I want to explore what happens when we run a program on Linux machine from userspace perspective.

I don't know how about you, but I learned in my university that a `C` program starts to execute from the function which is called `main`. And that's partly true. Everytime, when we are starting to write new program, we start our program from the following lines of code:

```C
int main(int argc, char *argv[]) {
	// Entry point is here
}
```

But if you interested in low-level programming, maybe you already know that the `main` function isn't actual entry point of a program. We can make sure in this, if we will look at this simple program:

```C
int main(int argc, char *argv[]) {
	return 0;
}
```

in debugger. Let's compile this and run in [gdb](https://www.gnu.org/software/gdb/):

```
$ gcc -ggdb program.c -o program
$ gdb ./program
The target architecture is assumed to be i386:x86-64:intel
Reading symbols from ./program...done.
```

Let's execute gdb `info` subcommand with `files` argument. The `info files` must print information about debugging targets and memory spaces occupied by different sections.

```
(gdb) info files
Symbols from "/home/alex/program".
Local exec file:
	`/home/alex/program', file type elf64-x86-64.
	Entry point: 0x400430
	0x0000000000400238 - 0x0000000000400254 is .interp
	0x0000000000400254 - 0x0000000000400274 is .note.ABI-tag
	0x0000000000400274 - 0x0000000000400298 is .note.gnu.build-id
	0x0000000000400298 - 0x00000000004002b4 is .gnu.hash
	0x00000000004002b8 - 0x0000000000400318 is .dynsym
	0x0000000000400318 - 0x0000000000400357 is .dynstr
	0x0000000000400358 - 0x0000000000400360 is .gnu.version
	0x0000000000400360 - 0x0000000000400380 is .gnu.version_r
	0x0000000000400380 - 0x0000000000400398 is .rela.dyn
	0x0000000000400398 - 0x00000000004003c8 is .rela.plt
	0x00000000004003c8 - 0x00000000004003e2 is .init
	0x00000000004003f0 - 0x0000000000400420 is .plt
	0x0000000000400420 - 0x0000000000400428 is .plt.got
	0x0000000000400430 - 0x00000000004005e2 is .text
	0x00000000004005e4 - 0x00000000004005ed is .fini
	0x00000000004005f0 - 0x0000000000400610 is .rodata
	0x0000000000400610 - 0x0000000000400644 is .eh_frame_hdr
	0x0000000000400648 - 0x000000000040073c is .eh_frame
	0x0000000000600e10 - 0x0000000000600e18 is .init_array
	0x0000000000600e18 - 0x0000000000600e20 is .fini_array
	0x0000000000600e20 - 0x0000000000600e28 is .jcr
	0x0000000000600e28 - 0x0000000000600ff8 is .dynamic
	0x0000000000600ff8 - 0x0000000000601000 is .got
	0x0000000000601000 - 0x0000000000601028 is .got.plt
	0x0000000000601028 - 0x0000000000601034 is .data
	0x0000000000601034 - 0x0000000000601038 is .bss
```

Note on `Entry point: 0x400430` line. Now we know the actual address of entry point of our program. Let's put breakpoint by this address, run our program and will see what happens:

```
(gdb) break *0x400430
Breakpoint 1 at 0x400430
(gdb) run
Starting program: /home/alex/program 

Breakpoint 1, 0x0000000000400430 in _start ()
```

Interesting. We don't see execution of `main` function here, but we may see that another function is called. This function is - `_start` and as debugger showed us, it is actual entry point of our program. Where is this function come from? Who does call `main` and when it will be called. I will try to answer all of these questions in this post.

How kernel does start new program
--------------------------------------------------------------------------------

First of all, let's take following simple `C` program:

```C
// program.c

#include <stdlib.h>
#include <stdio.h>

static int x = 1;

int y = 2;

int main(int argc, char *argv[]) {
	int z = 3;

	printf("x + y + z = %d\n", x + y + z);

	return EXIT_SUCCESS;
}
```

We can be sure that this program works as we expect. Let's compile it:

```
$ gcc -Wall program.c -o sum
```

and run:

```
./sum
x + y + z = 6
```

Ok, everything looks pretty good for now. You already may know that there is special family of [system calls](https://en.wikipedia.org/wiki/System_call) - [exec*](http://man7.org/linux/man-pages/man3/execl.3.html) system calls. As we may read in the man page:

> The exec() family of functions replaces the current process image with a new process image.

If you have read fourth [part](https://0xax.gitbooks.io/linux-insides/content/SysCall/syscall-4.html) of the chapter which describes [system calls](https://en.wikipedia.org/wiki/System_call), you may know that for example [execve](http://linux.die.net/man/2/execve) system call is defined in the [files/exec.c](https://github.com/torvalds/linux/blob/master/fs/exec.c#L1859) source code file and looks like:

```C
SYSCALL_DEFINE3(execve,
		const char __user *, filename,
		const char __user *const __user *, argv,
		const char __user *const __user *, envp)
{
	return do_execve(getname(filename), argv, envp);
}
```

It takes executable file name, set of command line arguments and set of enviroment variables. As you may guess, everything is done by the `do_execve` function. I will not describe implementation of the `do_execve` function in details because you can read about this in [here](https://0xax.gitbooks.io/linux-insides/content/SysCall/syscall-4.html). But in short words, the `do_execve` function does many checks like `filename` is valid, limit of launched processes is not exceed in our system and etc. After all of these checks, this function parses our executable file which is represented in [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) format, creates memory descriptor for newly executed executable file and fills it with the appropriate values like area for the stack, heap and etc. As the setup of new binary image is done, the `start_thread` function which will execute setup of new process. This function is architecture-specific and for the [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture, its definition will be located in the [arch/x86/kernel/process_64.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/process_64.c#L231) source code file.

The `start_thread` function sets new value of [segment registers](https://en.wikipedia.org/wiki/X86_memory_segmentation) and program execution address. From this point, new process is ready to start. Once the [context switch](https://en.wikipedia.org/wiki/Context_switch) will be done, control will be returned to the userspace with new values of registers and new executable will be started to execute.

That's all from the kernel side. The Linux kernel prepares binary image for execution and its execution starts right after context switch will return controll to userspace. But it does not answer on questions like where is from `_start` come and others. Let's try to answer on these questions in the next paragraph.

How does program start in userspace
--------------------------------------------------------------------------------

In the previous paragraph we saw how an executable file is prepared to run by the Linux kernel. Let's look at the same, but from userspace side. We already know that entry point of each program is `_start` function. But where is this function from? It may came from a library. But if you remember correctly we didn't link our program with any libraries during compilation of our program:

```
$ gcc -Wall program.c -o sum
```

You may guess that `_start` comes from [stanard libray](https://en.wikipedia.org/wiki/Standard_library) and that's true. If try to compile our program again and pass `-v` option to gcc which will enable `verbose mode`, we will see following long output. Full output is not intereing for us, let's look at the following steps: First of all our program will be compiled with `cc`:

```
$ gcc -v -ggdb program.c -o sum
...
...
...
/usr/libexec/gcc/x86_64-redhat-linux/6.1.1/cc1 -quiet -v program.c -quiet -dumpbase program.c -mtune=generic -march=x86-64 -auxbase test -ggdb -version -o /tmp/ccvUWZkF.s
...
...
...
```

The `cc1` compiler will compile our `C` source code and produce assembly `/tmp/ccvUWZkF.s` file. After this we may see that our assembly file will be compiled into object file with `GNU as` assembler:

```
$ gcc -v -ggdb program.c -o sum
...
...
...
as -v --64 -o /tmp/cc79wZSU.o /tmp/ccvUWZkF.s
...
...
...
```

And in the end our object file will be linked with `collect2`:

```
$ gcc -v -ggdb program.c -o sum
...
...
...
/usr/libexec/gcc/x86_64-redhat-linux/6.1.1/collect2 -plugin /usr/libexec/gcc/x86_64-redhat-linux/6.1.1/liblto_plugin.so -plugin-opt=/usr/libexec/gcc/x86_64-redhat-linux/6.1.1/lto-wrapper -plugin-opt=-fresolution=/tmp/ccLEGYra.res -plugin-opt=-pass-through=-lgcc -plugin-opt=-pass-through=-lgcc_s -plugin-opt=-pass-through=-lc -plugin-opt=-pass-through=-lgcc -plugin-opt=-pass-through=-lgcc_s --build-id --no-add-needed --eh-frame-hdr --hash-style=gnu -m elf_x86_64 -dynamic-linker /lib64/ld-linux-x86-64.so.2 -o test /usr/lib/gcc/x86_64-redhat-linux/6.1.1/../../../../lib64/crt1.o /usr/lib/gcc/x86_64-redhat-linux/6.1.1/../../../../lib64/crti.o /usr/lib/gcc/x86_64-redhat-linux/6.1.1/crtbegin.o -L/usr/lib/gcc/x86_64-redhat-linux/6.1.1 -L/usr/lib/gcc/x86_64-redhat-linux/6.1.1/../../../../lib64 -L/lib/../lib64 -L/usr/lib/../lib64 -L. -L/usr/lib/gcc/x86_64-redhat-linux/6.1.1/../../.. /tmp/cc79wZSU.o -lgcc --as-needed -lgcc_s --no-as-needed -lc -lgcc --as-needed -lgcc_s --no-as-needed /usr/lib/gcc/x86_64-redhat-linux/6.1.1/crtend.o /usr/lib/gcc/x86_64-redhat-linux/6.1.1/../../../../lib64/crtn.o
...
...
...
```

Yes, we may see long set of command line options which are passed to the linker. Let's go the other way. We know that our program depends on `stdlib`:

```
~$ ldd program
	linux-vdso.so.1 (0x00007ffc9afd2000)
	libc.so.6 => /lib64/libc.so.6 (0x00007f56b389b000)
	/lib64/ld-linux-x86-64.so.2 (0x0000556198231000)
```

as we use some stuff from there like `printf` and etc. But not only. That's why we will get error if we will pass `-nostdlib` option to the compiler:

```
~$ gcc -nostdlib program.c -o program
/usr/bin/ld: warning: cannot find entry symbol _start; defaulting to 000000000040017c
/tmp/cc02msGW.o: In function `main':
/home/alex/program.c:11: undefined reference to `printf'
collect2: error: ld returned 1 exit status
```

Besides other errors, we also see that `_start` symbol is undefined. So now we are sure that the `_start` function comes from standard library. But even if we will link it with standard library, it will not be compiled successfully anyway:

```
~$ gcc -nostdlib -lc -ggdb program.c -o program
/usr/bin/ld: warning: cannot find entry symbol _start; defaulting to 0000000000400350
```

Ok, compiler will not complains about undefined reference of standard library functions as we linked our program with `/usr/lib64/libc.so.6`, but the `_start` symbol isn't resolved yet. Let's return to the verbose output of `gcc` and look at the parameters of `collect2`. First important thing that we may see is our program is linked not only with standard library, but also with some object files. The first object file is: `/lib64/crt1.o`. And if we will look inside this object file with `objdump` util, we will see the `_start` symbol: 

```
$ objdump -d /lib64/crt1.o 

/lib64/crt1.o:     file format elf64-x86-64


Disassembly of section .text:

0000000000000000 <_start>:
   0:	31 ed                	xor    %ebp,%ebp
   2:	49 89 d1             	mov    %rdx,%r9
   5:	5e                   	pop    %rsi
   6:	48 89 e2             	mov    %rsp,%rdx
   9:	48 83 e4 f0          	and    $0xfffffffffffffff0,%rsp
   d:	50                   	push   %rax
   e:	54                   	push   %rsp
   f:	49 c7 c0 00 00 00 00 	mov    $0x0,%r8
  16:	48 c7 c1 00 00 00 00 	mov    $0x0,%rcx
  1d:	48 c7 c7 00 00 00 00 	mov    $0x0,%rdi
  24:	e8 00 00 00 00       	callq  29 <_start+0x29>
  29:	f4                   	hlt    
```

As `crt1.o` is a shared object file, we see only stubs here instead of real calls. Let's look at the source code of the `_start` function. As this function is architecture specific, implementation for `_start` will be located in the [sysdeps/x86_64/start.S](https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/x86_64/start.S;h=f1b961f5ba2d6a1ebffee0005f43123c4352fbf4;hb=HEAD) assembly file.

The `_start` starts from the clearing of `%ebp` register as [ABI](https://software.intel.com/sites/default/files/article/402129/mpx-linux64-abi.pdf) suggests

```assembly
xorl %ebp, %ebp
```

And after this we put the address of termination function to the `%r9` register:

```assembly
mov %RDX_LP, %R9_LP
```

As described in the [ELF](http://flint.cs.yale.edu/cs422/doc/ELF_Format.pdf) specification:

> After the dynamic linker has built the process image and performed the relocations, each shared object
> gets the opportunity to execute some initialization code.
> ...
> Similarly, shared objects may have termination functions, which are executed with the atexit (BA_OS)
> mechanism after the base process begins its termination sequence.

So we need to put address of termination function to the `%r9` register as it will be passed `__libc_start_main` in future as sixth argument. Note that initially, address of the termination function is located in the `%rdx` register. Other registers besides `%rdx` and `%rsp` contain unspecified values. Actually main point of the `_start` function is to call `__libc_start_main`. So the next actions will be preparations to call this function.

The signature of the `__libc_start_main` function is located in the [csu/libc-start.c](https://sourceware.org/git/?p=glibc.git;a=blob;f=csu/libc-start.c;h=0fb98f1606bab475ab5ba2d0fe08c64f83cce9df;hb=HEAD) source code file. Let's look on it:

```C
STATIC int LIBC_START_MAIN (int (*main) (int, char **, char **),
 			                int argc,
			                char **argv,
 			                __typeof (main) init,
			                void (*fini) (void),
			                void (*rtld_fini) (void),
			                void *stack_end)
```

It takes address of the `main` function of a program, `argc` and `argv`. `init` and `fini` functions are constructor and destructor of the program. The `rtld_fini` is termination function which will be called after the program will be exited to terminate and free dynamic section. The last parameter of the `__libc_start_main` is the pointer to the stack of the program. Before we can call the `__libc_start_main` function, all of these parameters must be prepared and passed to it. Let's return to the [sysdeps/x86_64/start.S](https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/x86_64/start.S;h=f1b961f5ba2d6a1ebffee0005f43123c4352fbf4;hb=HEAD) assembly file and continue to see what happens before the `__libc_start_main` function will be called from there.

All of we need for the `__libc_start_main` function, we can get from the stack. As `_start` is called, our stack is looks like:

```
+-----------------+
|       NULL      |
+-----------------+ 
|       envp      |
+-----------------+ 
|       NULL      |
+------------------
|       argv      | <- %rsp
+------------------
|       argc      |
+-----------------+ 
```

At the next step as we cleared `%ebp` register and save address of the termination function in the `%r9` register, we pop element from the stack to the `%rsi` register, so after this `%rsp` will point to the `argv` array and `%rsi` will contain count of command line arguemnts passed to the program:

```
+-----------------+
|       NULL      |
+-----------------+ 
|       envp      |
+-----------------+ 
|       NULL      |
+------------------
|       argv      | <- %rsp
+-----------------+
```

And after this we may move address of the `argv` array to the `%rdx` register

```assembly
popq %rsi
mov %RSP_LP, %RDX_LP
```

From this moment we have `argc`, `argv`. Still to put pointers to the construtor, destructor in appropriate registers and pass pointer to the stack. At the first following three lines we align stack to `16` bytes boundary as suggested in [ABI](https://software.intel.com/sites/default/files/article/402129/mpx-linux64-abi.pdf) and push `%rax` which contains garbage:

```assembly
and  $~15, %RSP_LP
pushq %rax

pushq %rsp
mov $__libc_csu_fini, %R8_LP
mov $__libc_csu_init, %RCX_LP
mov $main, %RDI_LP
```

After stack aligning we push address of the stack, addresses of contstructor and destructor to the `%r8` and `%rcx` registers and address of the `main` symbol to the `%rdi`. From this moment we may call the `__libc_start_main` function from the [csu/libc-start.c](https://sourceware.org/git/?p=glibc.git;a=blob;f=csu/libc-start.c;h=0fb98f1606bab475ab5ba2d0fe08c64f83cce9df;hb=HEAD).

Before we will look at the `__libc_start_main` function let's add the `/lib64/crt1.o` and try to compile our program again:

```
$ gcc -nostdlib /lib64/crt1.o -lc -ggdb program.c -o program
/lib64/crt1.o: In function `_start':
(.text+0x12): undefined reference to `__libc_csu_fini'
/lib64/crt1.o: In function `_start':
(.text+0x19): undefined reference to `__libc_csu_init'
collect2: error: ld returned 1 exit status
```

Now we see another error that both `__libc_csu_fini` and `__libc_csu_init` functions are not found. We know that addresses of both of these functions are passed to the `__libc_start_main` as parameters and also these functions are constructor and destructor of our programs. But what are `constructor` and `destructor` in terms of `C` program means? We already saw the quote from the [ELF](http://flint.cs.yale.edu/cs422/doc/ELF_Format.pdf) specification:

> After the dynamic linker has built the process image and performed the relocations, each shared object
> gets the opportunity to execute some initialization code.
> ...
> Similarly, shared objects may have termination functions, which are executed with the atexit (BA_OS)
> mechanism after the base process begins its termination sequence.

So the linker besides usual sections like `.text`, `.data` and others, creates two special sections:

* `.init`
* `.fini`

We can find it with `readelf` util:

```
~$ readelf -e test | grep init
  [11] .init             PROGBITS         00000000004003c8  000003c8

~$ readelf -e test | grep fini
  [15] .fini             PROGBITS         0000000000400504  00000504
```

Both of these sections will be placed at the start and end of binary image and contain routines which are called constructor and destructor respectively. The main point of these routines is to do some initialization/finalization like initialization of global variables like [errno](http://man7.org/linux/man-pages/man3/errno.3.html), allocation and deallocation of memory for system routines and etc., before actual code of a program will be executed.

As you may understand from names of these functions, they will be called before `main` and after the `main` function will be finished. Definition of `.init` and `.fini` sections located in the `/lib64/crti.o` and if we will add this object file:

```
$ gcc -nostdlib /lib64/crt1.o /lib64/crti.o  -lc -ggdb program.c -o program
```

we will not get any errors. But let's try to run our program and see what happens:

```
$ ./program
Segmentation fault (core dumped)
```

Yeah, we got segmentation fault. Let's look inside of the `lib64/crti.o` with `objdump` util:

```
~$ objdump -D /lib64/crti.o

/lib64/crti.o:     file format elf64-x86-64


Disassembly of section .init:

0000000000000000 <_init>:
   0:	48 83 ec 08          	sub    $0x8,%rsp
   4:	48 8b 05 00 00 00 00 	mov    0x0(%rip),%rax        # b <_init+0xb>
   b:	48 85 c0             	test   %rax,%rax
   e:	74 05                	je     15 <_init+0x15>
  10:	e8 00 00 00 00       	callq  15 <_init+0x15>

Disassembly of section .fini:

0000000000000000 <_fini>:
   0:	48 83 ec 08          	sub    $0x8,%rsp
```

As I wrote above, the `/lib64/crti.o` object file contains definition of the `.init` and `.fini` section, but also we can see here the stub for function. Let's look at the source code which is placed in the [sysdeps/x86_64/crti.S](https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/x86_64/crti.S;h=e9d86ed08ab134a540e3dae5f97a9afb82cdb993;hb=HEAD) source code file:

```assembly
	.section .init,"ax",@progbits
	.p2align 2
	.globl _init
	.type _init, @function
_init:
	subq $8, %rsp
	movq PREINIT_FUNCTION@GOTPCREL(%rip), %rax
	testq %rax, %rax
	je .Lno_weak_fn
	call *%rax
.Lno_weak_fn:
	call PREINIT_FUNCTION
```

It contains definition of the `.init` section and assembly code does 16-byte stack alignment and next we move address of the `PREINIT_FUNCTION` and if it is zero we don't call it:

```
00000000004003c8 <_init>:
  4003c8:       48 83 ec 08             sub    $0x8,%rsp
  4003cc:       48 8b 05 25 0c 20 00    mov    0x200c25(%rip),%rax        # 600ff8 <_DYNAMIC+0x1d0>
  4003d3:       48 85 c0                test   %rax,%rax
  4003d6:       74 05                   je     4003dd <_init+0x15>
  4003d8:       e8 43 00 00 00          callq  400420 <__libc_start_main@plt+0x10>
  4003dd:       48 83 c4 08             add    $0x8,%rsp
  4003e1:       c3                      retq
```

where the `PREINIT_FUNCTION` is the `__gmon_start__` which does setup for profiling. You may note that we have no return instruction in the [sysdeps/x86_64/crti.S](https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/x86_64/crti.S;h=e9d86ed08ab134a540e3dae5f97a9afb82cdb993;hb=HEAD). Actually that's why we got segmentation fault. Prolog of `_init` and `_fini` is placed in the [sysdeps/x86_64/crtn.S](https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/x86_64/crtn.S;h=e9d86ed08ab134a540e3dae5f97a9afb82cdb993;hb=HEAD) assembly file:

```assembly
.section .init,"ax",@progbits
addq $8, %rsp
ret

.section .fini,"ax",@progbits
addq $8, %rsp
ret
```

and if we will add it to the compilation, our program will be successfully compiled and runned!

```
~$ gcc -nostdlib /lib64/crt1.o /lib64/crti.o /lib64/crtn.o  -lc -ggdb program.c -o program

~$ ./program
x + y + z = 6
```

Conclusion
--------------------------------------------------------------------------------

Now let's return to the `_start` function and try to go through a full chain of calls before the `main` of our program will be called.

The `_start` is always placed at the beginning of the `.text` section in our programs by the linked which is used default `ld` script:

```
~$ ld --verbose | grep ENTRY
ENTRY(_start)
```

The `_start` function defined in the [sysdeps/x86_64/start.S](https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/x86_64/start.S;h=f1b961f5ba2d6a1ebffee0005f43123c4352fbf4;hb=HEAD) assembly file and does preparation like getting `argc/argv` from the stack, stack preparation and etc., before the `__libc_start_main` function will be called. The `__libc_start_main` function from the [csu/libc-start.c](https://sourceware.org/git/?p=glibc.git;a=blob;f=csu/libc-start.c;h=0fb98f1606bab475ab5ba2d0fe08c64f83cce9df;hb=HEAD) source code file does a registration of the constructor and destructor of application which are will be called before `main` and after it, starts up threading, does some security related actions like setting stack canary if need, calls initialization reltad routines and in the end it calls `main` function of our application and exit with its result:

```C
result = main (argc, argv, __environ MAIN_AUXVEC_PARAM);
exit (result);
```

That's all.

Links
--------------------------------------------------------------------------------

* [system call](https://en.wikipedia.org/wiki/System_call)
* [gdb](https://www.gnu.org/software/gdb/)
* [execve](http://linux.die.net/man/2/execve)
* [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [segment registers](https://en.wikipedia.org/wiki/X86_memory_segmentation)
* [context switch](https://en.wikipedia.org/wiki/Context_switch)
* [System V ABI](https://software.intel.com/sites/default/files/article/402129/mpx-linux64-abi.pdf)
