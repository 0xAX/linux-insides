Inline assembly
================================================================================

Introduction
--------------------------------------------------------------------------------

During reading of source code of the [Linux kernel](https://github.com/torvalds/linux), often I see something statements like that:

```C
__asm__("andq %%rsp,%0; ":"=r" (ti) : "0" (CURRENT_MASK));
```

Yes, this is [inline assembly](https://en.wikipedia.org/wiki/Inline_assembler) or in other words assembler code which is integrated in a high level programming language. In my case this high level programming language is [C](https://en.wikipedia.org/wiki/C_%28programming_language%29). Yeah, the `C` programming language is not very high-level, but still.

If you are familiar with [assembly](https://en.wikipedia.org/wiki/Assembly_language) programming language, you may notice that `inline assembly` is not very different from the usual. Moreover, the special form of inline assembly which is called `basic form` is the same. For example:

```C
__asm__("movq %rax, %rsp");
```

or

```C
__asm__("hlt");
```

The same code (of course without `__asm__` prefix) you might see in plain assembly code. Yes, this is very similar, but not so simple as it might seem at first glance. Actually, the [GCC](https://en.wikipedia.org/wiki/GNU_Compiler_Collection) supports two forms of inline assembly statements:

* `basic`;
* `extended`.

The basic form consists only from two things: the `__asm__` keyword and the string with valid assembler instructions. For example it may looks something like this:

```C
__asm__("movq    $3, %rax\t\n"
        "movq    %rsi, %rdi");
```

Instead of the `__asm__` keyword, also the `asm` keyword may be used, but the `__asm__` is portable whereas the `asm` keyword is the `GNU` [extension](https://gcc.gnu.org/onlinedocs/gcc/C-Extensions.html). Further I will use only `__asm__` variant in examples.

If you know assembly programming language this looks pretty easy. The main problem is in the second form of inline assembly statements - `extended`. This form allows us to pass parameters to an assembly statement, perform [jumps](https://en.wikipedia.org/wiki/Branch_%28computer_science%29) and etc. Not so hard, but this leads to the need to know the additional rules in addition to the knowledge of assembly language. Every time, when I see yet another piece of inline assembly code in the Linux kernel, I need to refer to the official [documentation](https://gcc.gnu.org/onlinedocs/) of `GCC` to remember how behaves a particular `qualifier` or what is the meaning of the `=&r` for example.

I've decided to write this part to consolidate my knowledge related to the inline assembly here. As inline assembly statements are quite common in the Linux kernel and we may see them in [linux-insides](https://0xax.gitbooks.io/linux-insides/content/) parts sometimes, I thought that it will be useful if we will have a special part which contains description of more important aspects of the inline assembly. Of course you may find comprehensive information about inline assembly in the official [documentation](https://gcc.gnu.org/onlinedocs/gcc/Using-Assembly-Language-with-C.html#Using-Assembly-Language-with-C), but I like the rule all in one place.

** Note: This part will not provide guide for assembly programming. It is not intended to teach you to write programs with assembler and to know that one or another assembler instruction means. Just a little memo for extended asm. **

Introduction to extended inline assembly
--------------------------------------------------------------------------------

So, let's start. As I already wrote above, the `basic` assembly statement consists from the `asm` or `__asm__` keyword and set of assembly instructions. If you are familiar with assembly programming language, there is no sense to write something additional about it. Most interesting part is inline assembler with operands or `extended` assembler. An extended assembly statement looks a little harder and consists not only from two parts:

```assembly
__asm__ [volatile] [goto] (AssemblerTemplate
                           [ : OutputOperands ]
                           [ : InputOperands  ]
                           [ : Clobbers       ]
                           [ : GotoLabels     ]);
```

All parameters which are marked with squared brackets are optional. You may notice that if we will skip all optional parameters and also `volatile` and `goto` qualifiers, we will get `basic` form. Let's start to consider this in order. The first optional `qualifier` is `volatile`. This specifier tells to compiler that an assembly statement may produce `side effects`. In this case we need to prevent compiler's optimization related to the given assembly statement. In simple words, the `volatile` specifier tells to compiler to not touch this statement and put it in the same place where it was in the original code. For example let's look at the following function from the [Linux kernel](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/desc.h):

```C
static inline void native_load_gdt(const struct desc_ptr *dtr)
{
	asm volatile("lgdt %0"::"m" (*dtr));
}
```

Here we may see the `native_load_gdt` function which loads base address of the [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table) to the `GDTR` register with the `lgdt` instruction. This assembly statement is marked with `volatile` qualifier. It is very important that compiler will not change original place of this assembly statement in the resulted code. In other way the `GDTR` register may contain wrong address of the `Global Descriptor Table` or an address may be correct, but the structure isn't filled yet. In this way an exception will be generated and the kernel will not booted correctly.

The second optional `qualifier` is the `goto`. This qualifier tells to the compiler that the given assembly statement may perform a jump to one of the labels which are listed in the `GotoLabels`. For example:

```C
__asm__ goto("jmp %l[label]" : : : label);
```

As we finished with these two qualifiers, let's consider the main part of an assembly statement body. As we may see, the main part of assembly statement consists from the following four parts:

* set of assembly instructions;
* output parameters;
* input parameters;
* clobbers.

The first represents a string which contains a set of valid assembly instructions which may be separated by the `\t\n` sequence. Names of processor [registers](https://en.wikipedia.org/wiki/Processor_register) must be prefixed with the `%%` sequence in `extended` form and other symbols like immediates must start from the `$` symbol. The `OutputOperands` and `InputOperands` are comma-separated lists of [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) variables which may be provided with `constraints` and the `Clobbers` is a list of registers or other values which are changed by the assembler instructions from the `AssemblerTemplate` beyond those listed in the `OutputOperands`. After we considered format of an `extended` we may look at first example. But before this we must know about `constraints`. A constraint is a string which specifies placement of an operand. For example value of an operand may be written to processor register or it can be read from memory and etc.

Now let's consider following simple example:

```C
#include <stdio.h>

int main(void)
{
        int a = 5;
        int b = 10;
        int sum = 0;

        __asm__("addl %1,%2" : "=r" (sum) : "r" (a), "0" (b));
        printf("a + b = %d\n", sum);
        return 0;
}
```

Before we will consider this example, let's compile and run it to be sure that it works as expected:

```
$ gcc test.c -o test
./test
a + b = 15
```

Ok, great. It works. Now let's consider this example. Here we may see simple `C` program which calculates sum of two variables and put the result into `sum` variable. In the end we just print the result. This example consists from three parts. The first is assembly statement with [add](http://x86.renejeschke.de/html/file_module_x86_id_5.html) instruction which adds value of the source operand to the value of the destination operand and stores the result in the destination operand. In our case:

```assembly
addl %1, %2
```

will be expanded to the:

```assembly
addl a, b
```

Variables and expressions which are listed in the `OutputOperands` and `InputOperands` may be matched in the `AssemblerTemplate`. An input/output operand is designated as `%N` where the `N` is the number of operand from left to right beginning from `zero`. The second part of the our assembly statement is located after the first `:` symbol and represents definition of the output value:

```assembly
"=r" (sum)
```

Notice that the `sum` is marked with two special symbols: `=r`. This is first constraint that we have encountered. Actually constraint here is only `r`. The `=` symbol is `modifier` which denotes output value. This tells to compiler that the previous value will be discarded and replaced by the new data. Besides the `=` modifier, `GCC` provides support for following three modifiers:

* `+` - an operand is read and written by an instruction;
* `&` - output register shouldn't overlap an input register and should be used only for output;
* `%` - tells the compiler that operands may be [commutative](https://en.wikipedia.org/wiki/Commutative_property).

Now let's back to the `r` qualifier. As I already wrote above, a qualifier denotes placement of an operand. The `r` symbol means a value will be stored in one of the [general purpose register](https://en.wikipedia.org/wiki/Processor_register). The last part of our assembly statement:

```assembly
"r" (a), "0" (b)
```

are input operands - `a` and `b` variables. We already know what does `r` qualifier mean. Now we may notice new constraint before `b` variable. The `0` or any other digit from `1` to `9` is called - `matching constraint`. With this assembler may use only one single operand that fills two roles. As you may guess, here the value of the constraint provides the order number of operands. In our case `0` will match `sum`. If we will look at assembly output of our program:

```C
0000000000400400 <main>:
  400401:       ba 05 00 00 00          mov    $0x5,%edx
  400406:       b8 0a 00 00 00          mov    $0xa,%eax
  40040b:       01 d0                   add    %edx,%eax
```

we will see that only two general purpose registers are used: `%edx` and `%eax`. In this way the `%eax` register is used as for storing value of `b` variable as for storing result of calculation. We considered input and output parameters of an inline assembly statement. Before we will meet other constraints supported by `gcc`, there is still to consider last possible part of an inline assembly statement - `clobbers`.

Clobbers
--------------------------------------------------------------------------------

As I wrote above, the `clobbered` part should contain a comma-separated list of registers which will be changed in the `AssemblerTemplate`. This may be useful when our assembly expression needs in additional register for calculation and only output parameter will be changed. If we will add clobbered register to the inline assembly statement, the compiler will take into account this and the register will not be reused in a wrong way.

Let's consider the same example, but will add additional simple assembler expression:

```C
__asm__("movq $100, %%rdx\t\n"
        "addl %1,%2" : "=r" (sum) : "r" (a), "0" (b));
```

If we will look at the assembly output:

```C
0000000000400400 <main>:
  400400:       ba 05 00 00 00          mov    $0x5,%edx
  400405:       b8 0a 00 00 00          mov    $0xa,%eax
  40040a:       48 c7 c2 64 00 00 00    mov    $0x64,%rdx
  400411:       01 d0                   add    %edx,%eax
```

We will see that `%edx` register will be overwritten with `0x64` or `100` value and the result will be `115` instead of `15`. Now if we will add the `%rdx` register to the list of `clobbered` registers:

```C
__asm__("movq $100, %%rdx\t\n"
        "addl %1,%2" : "=r" (sum) : "r" (a), "0" (b) : "%rdx");
```

and will look at the assembler output again:

```C
0000000000400400 <main>:
  400400:       b9 05 00 00 00          mov    $0x5,%ecx
  400405:       b8 0a 00 00 00          mov    $0xa,%eax
  40040a:       48 c7 c2 64 00 00 00    mov    $0x64,%rdx
  400411:       01 c8                   add    %ecx,%eax
```

Now we may see that the `%ecx` register will be used for `sum` calculation. Besides general purpose registers, we may pass two special specifiers. They are:

* `cc`;
* `memory`.

The first - `cc` indicates that an assembler code modifies [flags](https://en.wikipedia.org/wiki/FLAGS_register) register. This is common way to pass `cc` to clobbers list due to the arithmetic or logic instructions:

```C
__asm__("incq %0" ::""(variable): "cc");
```

The second `memory` specifier tells to the compiler that the given inline assembly statement executes arbitrary write or read operations in memory which is not pointed by operands listed in output list. This allows compiler to prevent keeping of values loaded from memory to be cached in registers. Let's take a look at the following example:

```C
#include <stdio.h>

int main(void)
{
        int a[3] = {10,20,30};
        int b = 5;
        
        __asm__ volatile("incl %0" :: "m" (a[0]));
        printf("a[0] - b = %d\n", a[0] - b);
        return 0;
}
```

Of course, this example may seem artificial... Ok, in fact this is the case. But it may show us main concept. Here we have an array of integer numbers and one integer variable. The example is pretty simple, we take first element of the `a` array and increment its value. After this we subtract the value of the `b` variable from the just incremented value of the first element the `a` array. In the end we just print result. If we will compile and run this simple example, the result may surprise us:

```
~$ gcc -O3  test.c -o test
~$ ./test
a[0] - b = 5
```

The result is `5` here, but why? We increased value of the first element of the `a` array, so the result must be `6` here. Let's look at the assembler output of this example:

```assembly
00000000004004f6 <main>:
  4004f6:       c7 44 24 f0 0a 00 00    movl   $0xa,-0x10(%rsp)
  4004fd:       00 
  4004fe:       c7 44 24 f4 14 00 00    movl   $0x14,-0xc(%rsp)
  400505:       00 
  400506:       c7 44 24 f8 1e 00 00    movl   $0x1e,-0x8(%rsp)
  40050d:       00 
  40050e:       ff 44 24 f0             incl   -0x10(%rsp)
  400512:       b8 05 00 00 00          mov    $0x5,%eax
```

At the first line we may see that first element of the `a` array contains `0xa` or `10` value. The last two lines of code are actual calculations. We increment value of the first of our array with `incl` instruction and just put `5` to the `%eax` register. This looks strange. We have passed `-O3` flag to `gcc`, so the compiler removed calculations. The problem here that `GCC` has a copy of the element of array in a register (`rsp` in our case) that was loaded from memory, but in the same way `GCC` does not associates actual calculation with calculation in the assembly statement and just puts directly calculated result of the `a[0] - b` to the `%eax` register.

Let's now add `memory` to the clobbers list:

```C
__asm__ volatile("incl %0" :: "m" (a[0]) : "memory");
```

and the new result will be:

```
~$ gcc -O3  test.c -o test
~$ ./test
a[0] - b = 6
```

Now the result is correct. If we will look at the assembly output now:

```assembly
00000000004004f6 <main>:
  4004f6:       c7 44 24 f0 0a 00 00    movl   $0xa,-0x10(%rsp)
  4004fd:       00 
  4004fe:       c7 44 24 f4 14 00 00    movl   $0x14,-0xc(%rsp)
  400505:       00 
  400506:       c7 44 24 f8 1e 00 00    movl   $0x1e,-0x8(%rsp)
  40050d:       00 
  40050e:       ff 44 24 f0             incl   -0x10(%rsp)
  400512:       8b 44 24 f0             mov    -0x10(%rsp),%eax
  400516:       83 e8 05                sub    $0x5,%eax
  400519:       c3                      retq
```

we will see one difference here. This difference in the following piece code:

```assembly
  400512:       8b 44 24 f0             mov    -0x10(%rsp),%eax
  400516:       83 e8 05                sub    $0x5,%eax
```

Instead of direct calculation, `GCC` now associates calculation from the assembly statement and put the value of the `a[0]` to the `%eax` register after this. In the end it just subtracts value of the `b` variable. Besides `memory` specifier, we may see new constraint here - `m`. This constraint tells to compiler to deal with address of the `a[0]`, instead of its value. So, now we finished with `clobbers` and now we may continue to consider other constraints supported by `GCC` besides `r` and `m` that we already seen.

Constraints
---------------------------------------------------------------------------------

Now as we finished with all three possible parts of an inline assembly statement, let's return to constraints. We already saw some constraints in this part, like `r` constraint which represents `register` operand, `m` constraint represents memory operand and `0-9` constraints which are represent an operand that matches specified operand number from an inline assembly statement. Besides this constraints, the `GCC` provides support for other constraints. For example - `i` constraint represents an `immediate` integer operand with know value:

```C
#include <stdio.h>

int main(void)
{
        int a = 0;

        __asm__("movl %1, %0" : "=r"(a) : "i"(100));
        printf("a = %d\n", a);
        return 0;
}
```

The result is:

```
~$ gcc test.c -o test
~$ ./test
a = 100
```

Or for example `I` constraint which represents `32-bit` integer. The difference between `i` and `I` constraints is that the `i` is more general, when `I` is for strictly `32-bit` integer data. For example if you will try compile following example:

```C
int test_asm(int nr)
{
        unsigned long a = 0;

        __asm__("movq %1, %0" : "=r"(a) : "I"(0xffffffffffff));
        return a;
}
```

you will get following error:

```
$ gcc -O3 test.c -o test
test.c: In function ‘test_asm’:
test.c:7:9: warning: asm operand 1 probably doesn’t match constraints
         __asm__("movq %1, %0" : "=r"(a) : "I"(0xffffffffffff));
         ^
test.c:7:9: error: impossible constraint in ‘asm’
```

when:

```C
int test_asm(int nr)
{
        unsigned long a = 0;

        __asm__("movq %1, %0" : "=r"(a) : "i"(0xffffffffffff));
        return a;
}
```

works perfectly:

```
~$ gcc -O3 test.c -o test
~$ echo $?
0
```

`GCC` also supports `J`, `K`, `N` constraints for integer constants in the range `0...63` bits, signed `8-bit` integer constants and unsigned `8-bit` integer constants respectively. The `o` constraint represents memory operand which represents `offsetable` memory address. For example:

```C
#include <stdio.h>

int main(void)
{
        static unsigned long arr[3] = {0, 1, 2};
        static unsigned long element;
        
        __asm__ volatile("movq 16+%1, %0" : "=r"(element) : "o"(arr));
        printf("%d\n", element);
        return 0;
}
```

The result as expected:

```
~$ gcc -O3 test.c -o test
~$ ./test
2
```

All of these constraints may be combined (of course actually not all). In this way the compiler will choose the best one for the certain situation. For example:

```C
#include <stdio.h>

int a = 1;

int main(void)
{
        int b;
        __asm__ ("movl %1,%0" : "=r"(b) : "r"(a));
        return b;
}
```

will use memory operand:

```assembly
0000000000400400 <main>:
  400400:       8b 05 26 0c 20 00       mov    0x200c26(%rip),%eax        # 60102c <a>
```

That's all about commonly used constraints in inline assembly statements. More you may find in the [documentation](https://gcc.gnu.org/onlinedocs/gcc/Simple-Constraints.html#Simple-Constraints).

Architecture specific constraints
--------------------------------------------------------------------------------

Before this part will be finished, let's look at the set of special constraints. This constrains are architecture specific and as this book is [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture specific, we will consider constraints related to it. First of all the set of `a` ... `d` and also `S` and `D` constraints represent [generic purpose](https://en.wikipedia.org/wiki/Processor_register) registers. In this case the `a` constraint corresponds to `%al`, `%ax`, `%eax` or `%rax` register depending on instruction size. The `S` and `D` constraints are `%si` and `%di` registers respectively. For example let's take our previous example. We may see in the its assembly output that value of the `a` variable is stored in the `%eax` register. Now let's look at the assembly output of the same example, but with other constraint: 

```C
#include <stdio.h>

int a = 1;

int main(void)
{
        int b;
        __asm__ ("movl %1,%0" : "=r"(b) : "d"(a));
        return b;
}
```

Now may see that value of the `a` variable will be stored in the `%edx` register:

```assembly
0000000000400400 <main>:
  400400:       8b 15 26 0c 20 00       mov    0x200c26(%rip),%edx        # 60102c <a>
```

The `f` and `t` constraints represents any floating point stack register - `%st` and the top of the floating point stack respectively. The `u` constraint represents the second value from the top of the floating point stack.

That's all. You may find more details about [x86_64](https://en.wikipedia.org/wiki/X86-64) and not only architectures specific constraints in the official [documentation](https://gcc.gnu.org/onlinedocs/gcc/Machine-Constraints.html#Machine-Constraints).

Links
--------------------------------------------------------------------------------

* [Linux kernel source code](https://github.com/torvalds/linux)
* [assembly programming language](https://en.wikipedia.org/wiki/Assembly_language) 
* [GCC](https://en.wikipedia.org/wiki/GNU_Compiler_Collection)
* [GNU extension](https://gcc.gnu.org/onlinedocs/gcc/C-Extensions.html)
* [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table)
* [Processor registers](https://en.wikipedia.org/wiki/Processor_register)
* [add instruction](http://x86.renejeschke.de/html/file_module_x86_id_5.html)
* [flags register](https://en.wikipedia.org/wiki/FLAGS_register)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [constraints](https://gcc.gnu.org/onlinedocs/gcc/Machine-Constraints.html#Machine-Constraints)
