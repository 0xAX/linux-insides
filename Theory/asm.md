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

The basic form consists of only two things: the `__asm__` keyword and the string with valid assembler instructions. For example it may look something like this:

```C
__asm__("movq    $3, %rax\t\n"
        "movq    %rsi, %rdi");
```

The `asm` keyword may be used in place of `__asm__`, however `__asm__` is portable whereas `asm` is the `GNU`-specific [extension](https://gcc.gnu.org/onlinedocs/gcc/C-Extensions.html). Further I will use only `__asm__` variant in examples.

If you know assembly programming language this looks pretty easy. The main problem is in the second form of inline assembly statements: `extended`. This form allows us to pass parameters to an assembly statement, perform [jumps](https://en.wikipedia.org/wiki/Branch_%28computer_science%29), etc. Not so hard, but this leads to the need to know the additional extended rules as well as having knowledge of assembly language. Every time I see yet another piece of inline assembly code in the Linux kernel, I need to refer to the official [documentation](https://gcc.gnu.org/onlinedocs/) of `GCC` to remember how a particular `qualifier` behaves or what the meaning of the `=&r` is, for example.

I've decided to write this to consolidate my knowledge related to inline assembly here. As inline assembly statements are quite common in the Linux kernel and we may see them in [linux-insides](https://0xax.gitbooks.io/linux-insides/content/) parts sometimes, I thought that it would be useful if we would have a special part which contains descriptions of the more important aspects of inline assembly. Of course you may find comprehensive information about inline assembly in the official [documentation](https://gcc.gnu.org/onlinedocs/gcc/Using-Assembly-Language-with-C.html#Using-Assembly-Language-with-C), but I like the rules all in one place.

** Note: This part will not provide a guide for assembly programming. It is not intended to teach you to write programs with assembler and to know what one or another assembler instruction means. Just a little memo for extended asm. **

Introduction to extended inline assembly
--------------------------------------------------------------------------------

So, let's start. As I already wrote above, the `basic` assembly statement consists of the `asm` or `__asm__` keyword and a set of assembly instructions. If you are familiar with assembly programming language, there is no sense in writing something additional about it. The most interesting part of inline assembly are those statements in the extended syntax, or those with operands. An extended assembly statement looks a little more complicated and consists of these parts:

```assembly
__asm__ [volatile] [goto] (AssemblerTemplate
                           [ : OutputOperands ]
                           [ : InputOperands  ]
                           [ : Clobbers       ]
                           [ : GotoLabels     ]);
```

All parameters which are marked with squared brackets are optional. You may notice that if we skip all the optional parameters and also the `volatile` and `goto` qualifiers, we get the `basic` form. Let's start to consider this in order. The first optional `qualifier` is `volatile`. This specifier tells the compiler that an assembly statement may produce `side effects`. In this case we need to prevent the compiler's optimization related to the given assembly statement. In simple words, the `volatile` specifier tells to compiler not to touch this statement and to put it in the same place where it was in the original code. For example let's look at the following function from the [Linux kernel](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/desc.h):

```C
static inline void native_load_gdt(const struct desc_ptr *dtr)
{
	asm volatile("lgdt %0"::"m" (*dtr));
}
```

Here we see the `native_load_gdt` function which loads the base address of the [Global Descriptor Table](https://en.wikipedia.org/wiki/Global_Descriptor_Table) to the `GDTR` register with the `lgdt` instruction. This assembly statement is marked with the `volatile` qualifier. It is very important that the compiler will not change the original place of this assembly statement in the resulting code, otherwise the `GDTR` register may contain an invalid address for the `Global Descriptor Table` or the address may be correct, but the structure isn't filled yet. In this way an exception will be generated and the kernel will not boot correctly.

The second optional `qualifier` is the `goto`. This qualifier tells to the compiler that the given assembly statement may perform a jump to one of the labels which are listed in the `GotoLabels`. For example:

```C
__asm__ goto("jmp %l[label]" : : : label);
```

As we finish with these two qualifiers, let's consider the main part of an assembly statement body. As we can see, the main part of an assembly statement consists of the following four parts:

* set of assembly instructions;
* output parameters;
* input parameters;
* clobbers.

The first represents a string which contains a set of valid assembly instructions which may be separated by the `\t\n` sequence. Names of processor [registers](https://en.wikipedia.org/wiki/Processor_register) must be prefixed with the `%%` sequence in `extended` form and other symbols like immediates must start from the `$` symbol. The `OutputOperands` and `InputOperands` are comma-separated lists of [C](https://en.wikipedia.org/wiki/C_%28programming_language%29) variables which may be provided with `constraints` and the `Clobbers` is a list of registers or other values which are changed by the assembler instructions from the `AssemblerTemplate` beyond those listed in the `OutputOperands`. But before we can consider the first example again we must also know about `constraints`. A constraint is a string which specifies placement of an operand. For example the value of an operand may be written to a processor register, can be read from memory, etc.

Now let's consider the following simple example:

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

Before we consider this example, let's compile and run it to be sure that it works as expected:

```
$ gcc test.c -o test
./test
a + b = 15
```

Ok, great. It works. Now let's consider this example. Here we see a simple `C` program which calculates sum of two variables and puts the result into the `sum` variable. In the end we just print the result. This example consists of three parts: The first is an assembly statement with the [add](http://x86.renejeschke.de/html/file_module_x86_id_5.html) instruction which adds the value of the source operand to the value of the destination operand and stores the result in the destination operand. In our case:

```assembly
addl %1, %2
```

will be expanded to the:

```assembly
addl a, b
```

Variables and expressions which are listed in the `OutputOperands` and `InputOperands` may be matched in the `AssemblerTemplate`. An input/output operand is designated as `%N` where the `N` is the number of the operand from left to right starting at `zero`. The second part of the our assembly statement is located after the first `:` symbol and represents the definition of the output value:

```assembly
"=r" (sum)
```

Notice that `sum` is marked with two special symbols: `=r`. This is the first constraint that we have encountered. Actually the constraint here is only `r`. The `=` symbol is a `modifier` which denotes the output value. This tells the compiler that the previous value will be discarded and replaced by the new data. Besides the `=` modifier, `GCC` provides support for the following three modifiers:

* `+` - an operand is read and written by an instruction;
* `&` - output register shouldn't overlap an input register and should be used only for output;
* `%` - tells the compiler that operands may be [commutative](https://en.wikipedia.org/wiki/Commutative_property).

Now let's back to the `r` qualifier. As I already wrote above, a qualifier denotes placement of an operand. The `r` symbol means a value will be stored in one of the [general purpose register](https://en.wikipedia.org/wiki/Processor_register). The last part of our assembly statement:

```assembly
"r" (a), "0" (b)
```

are input operands - `a` and `b` variables. We already know what the `r` qualifier mean. Now we may notice a new constraint before the `b` variable. A `0` or any other digit from `1` to `9` is called a `matching constraint`. With this the assembler may use only one a single operand that fills two roles. As you may guess, here the value of the constraint provides the number order of operands. In our case `0` will match `sum`. If we look at assembly output of our program:

```C
0000000000400400 <main>:
  400401:       ba 05 00 00 00          mov    $0x5,%edx
  400406:       b8 0a 00 00 00          mov    $0xa,%eax
  40040b:       01 d0                   add    %edx,%eax
```

we will see that only two general purpose registers are used: `%edx` and `%eax`. In this way the `%eax` register is used to store the value of the `b` variable as the result of calculation. We have considered input and output parameters of an inline assembly statement but before we meet other constraints supported by `gcc`, there is still another part of inline assembly statements we must consider: `clobbers`.

Clobbers
--------------------------------------------------------------------------------

As I wrote above, the `clobbered` part should contain a comma-separated list of registers which will be changed in the `AssemblerTemplate`. This may be useful when our assembly expression needs an additional register for calculation and only the output parameter will be changed. If we add a clobbered register to the inline assembly statement, the compiler will take this into account and the register will not be reused in an incorrect manner.

Let's consider the same example, but let's add an additional simple assembler expression:

```C
__asm__("movq $100, %%rdx\t\n"
        "addl %1,%2" : "=r" (sum) : "r" (a), "0" (b));
```

If we look at the assembly output:

```C
0000000000400400 <main>:
  400400:       ba 05 00 00 00          mov    $0x5,%edx
  400405:       b8 0a 00 00 00          mov    $0xa,%eax
  40040a:       48 c7 c2 64 00 00 00    mov    $0x64,%rdx
  400411:       01 d0                   add    %edx,%eax
```

We will see that the `%edx` register will be overwritten with a value of `0x64` or `100` and the result will be `115` instead of `15`. Now if we add the `%rdx` register to the list of `clobbered` registers:

```C
__asm__("movq $100, %%rdx\t\n"
        "addl %1,%2" : "=r" (sum) : "r" (a), "0" (b) : "%rdx");
```

and look at the assembler output again:

```C
0000000000400400 <main>:
  400400:       b9 05 00 00 00          mov    $0x5,%ecx
  400405:       b8 0a 00 00 00          mov    $0xa,%eax
  40040a:       48 c7 c2 64 00 00 00    mov    $0x64,%rdx
  400411:       01 c8                   add    %ecx,%eax
```

Now we see that the `%ecx` register will be used for the `sum` calculation. Besides general purpose registers, we may pass two special specifiers. They are:

* `cc`;
* `memory`.

The first - `cc` indicates that an assembler statement modifies the [flags](https://en.wikipedia.org/wiki/FLAGS_register) register. It is common to pass `cc` to clobbers list for arithmetic or logic instructions:

```C
__asm__("incq %0" ::""(variable): "cc");
```

The second specifier, `memory`, tells the compiler that the given inline assembly statement executes arbitrary write or read operations in memory which is not pointed to by operands listed in output list. This allows the compiler to prevent values loaded from memory from being cached in registers. Let's take a look at the following example:

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

Of course, this example may seem artificial... Ok, this is in fact the case, but it may help show us the main concept. Here we have an array of integer numbers and one integer variable. The example is pretty simple: We take the first element of the `a` array and increment its value. After this we subtract the value of the `b` variable from the just incremented value of the first element in the `a` array. In the end we just print the result. If we compile and run this simple example, the result may surprise us:

```
~$ gcc -O3  test.c -o test
~$ ./test
a[0] - b = 5
```

The result is `5` here, but why? We increased the value of the first element of the `a` array, so the result must be `6` here. Let's look at the assembler output of this example:

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

At the first line we see that the first element of the `a` array contains `0xa` or `10` value. The last two lines of code are actual calculations. We increment value of the first item of our array with `incl` instruction and just put `5` into the `%eax` register. This looks strange. We have passed the `-O3` flag to `gcc`, so the compiler removed calculations. The problem here is that `GCC` has a copy of the array element in a register (`rsp` in our case) that was loaded from memory, but in the same way that `GCC` does not associate actual calculations with calculation in the assembly statement, it just puts the calculated result of `a[0] - b` directly into the `%eax` register.

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

Now the result is correct. If we look at the assembly output now:

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

we will see one difference here. The difference is in the following piece of code:

```assembly
  400512:       8b 44 24 f0             mov    -0x10(%rsp),%eax
  400516:       83 e8 05                sub    $0x5,%eax
```

Instead of direct calculation, `GCC` now associates calculation from the assembly statement and puts the value of `a[0]` into the `%eax` register after this. In the end it just subtracts the value of the `b` variable. Besides the `memory` specifier, we see a new constraint here - `m`. This constraint tells the compiler to deal with the address of the `a[0]`, instead of its value. So, now we have finished with `clobbers` and we may continue to consider other constraints supported by `GCC` besides `r` and `m`.

Constraints
---------------------------------------------------------------------------------

Now as we have finished with all three possible parts of an inline assembly statement, let's return to constraints. We already saw some constraints in this part, like the `r` constraint which represents a `register` operand, the `m` constraint represents a memory operand and `0-9` constraints which represent an operand that matches specified the operand number from an inline assembly statement. Besides these constraints, the `GCC` provides support for other constraints: The `i` constraint represents an `immediate` integer operand with known value:

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

Or for example the `I` constraint which represents a `32-bit` integer. The difference between the `i` and `I` constraints is that `i` is more general, while `I` is for strictly `32-bit` integer data. For example if you try to compile the following example:

```C
int test_asm(int nr)
{
        unsigned long a = 0;

        __asm__("movq %1, %0" : "=r"(a) : "I"(0xffffffffffff));
        return a;
}
```

you will get the following error:

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

`GCC` also supports `J`, `K`, and `N` constraints for integer constants in the range `0...63` bits, signed `8-bit` integer constants and unsigned `8-bit` integer constants respectively. The `o` constraint represents a memory operand which represents an `offsetable` memory address. For example:

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

The result, as expected:

```
~$ gcc -O3 test.c -o test
~$ ./test
2
```

All of these constraints may be combined (of course actually not all of them). In this way the compiler will choose the best one for a given situation. For example:

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

That's about all there is to commonly used constraints in inline assembly statements. You may find more in the [documentation](https://gcc.gnu.org/onlinedocs/gcc/Simple-Constraints.html#Simple-Constraints).

Architecture specific constraints
--------------------------------------------------------------------------------

Before this part is finished, let's look at the set of special constraints. These constrains are architecture specific and as this book is [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture specific, we will consider constraints related to it. First of all the set of `a` ... `d` and also `S` and `D` constraints represent [generic purpose](https://en.wikipedia.org/wiki/Processor_register) registers. In this case the `a` constraint corresponds to the `%al`, `%ax`, `%eax` or `%rax` register depending on instruction size. The `S` and `D` constraints are the `%si` and `%di` registers respectively. Let's take another look at our previous example. We may see in its assembly output that the value of the `a` variable is stored in the `%eax` register. Now let's look at the assembly output of the same example, but with a different constraint: 

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

Now we see that value of the `a` variable will be stored in the `%edx` register:

```assembly
0000000000400400 <main>:
  400400:       8b 15 26 0c 20 00       mov    0x200c26(%rip),%edx        # 60102c <a>
```

The `f` and `t` constraints represent any floating point stack register - `%st` and the top of the floating point stack respectively. The `u` constraint represents the second value from the top of the floating point stack.

That's all. You may find more details about [x86_64](https://en.wikipedia.org/wiki/X86-64) and constraints, including architecture specific ones, in the official [documentation](https://gcc.gnu.org/onlinedocs/gcc/Machine-Constraints.html#Machine-Constraints).

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
