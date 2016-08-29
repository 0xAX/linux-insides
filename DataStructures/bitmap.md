Data Structures in the Linux Kernel
================================================================================

Bit arrays and bit operations in the Linux kernel
--------------------------------------------------------------------------------

Besides different [linked](https://en.wikipedia.org/wiki/Linked_data_structure) and [tree](https://en.wikipedia.org/wiki/Tree_%28data_structure%29) based data structures, the Linux kernel provides [API](https://en.wikipedia.org/wiki/Application_programming_interface) for [bit arrays](https://en.wikipedia.org/wiki/Bit_array) or `bitmap`. Bit arrays are heavily used in the Linux kernel and following source code files contain common `API` for work with such structures:

* [lib/bitmap.c](https://github.com/torvalds/linux/blob/master/lib/bitmap.c)
* [include/linux/bitmap.h](https://github.com/torvalds/linux/blob/master/include/linux/bitmap.h)

Besides these two files, there is also architecture-specific header file which provides optimized bit operations for certain architecture. We consider [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture, so in our case it will be: 

* [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h)

header file. As I just wrote above, the `bitmap` is heavily used in the Linux kernel. For example a `bit array` is used to store set of online/offline processors for systems which support [hot-plug](https://www.kernel.org/doc/Documentation/cpu-hotplug.txt) cpu (more about this you can read in the [cpumasks](https://0xax.gitbooks.io/linux-insides/content/Concepts/cpumask.html) part), a `bit array` stores set of allocated [irqs](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29) during initialization of the Linux kernel and etc.

So, the main goal of this part is to see how `bit arrays` are implemented in the Linux kernel. Let's start.

Declaration of bit array
================================================================================

Before we will look on `API` for bitmaps manipulation, we must know how to declare it in the Linux kernel. There are two common method to declare own bit array. The first simple way to declare a bit array is to array of `unsigned long`. For example:

```C
unsigned long my_bitmap[8]
```

The second way is to use the `DECLARE_BITMAP` macro which is defined in the [include/linux/types.h](https://github.com/torvalds/linux/blob/master/include/linux/types.h) header file:

```C
#define DECLARE_BITMAP(name,bits) \
    unsigned long name[BITS_TO_LONGS(bits)]
```

We can see that `DECLARE_BITMAP` macro takes two parameters:

* `name` - name of bitmap;
* `bits` - amount of bits in bitmap;

and just expands to the definition of `unsigned long` array with `BITS_TO_LONGS(bits)` elements, where the `BITS_TO_LONGS` macro converts a given number of bits to number of `longs` or in other words it calculates how many `8` byte elements in `bits`:

```C
#define BITS_PER_BYTE           8
#define DIV_ROUND_UP(n,d) (((n) + (d) - 1) / (d))
#define BITS_TO_LONGS(nr)       DIV_ROUND_UP(nr, BITS_PER_BYTE * sizeof(long))
```

So, for example `DECLARE_BITMAP(my_bitmap, 64)` will produce:

```python
>>> (((64) + (64) - 1) / (64))
1
```

and:

```C
unsigned long my_bitmap[1];
```

After we are able to declare a bit array, we can start to use it.

Architecture-specific bit operations
================================================================================

We already saw above a couple of source code and header files which provide [API](https://en.wikipedia.org/wiki/Application_programming_interface) for manipulation of bit arrays. The most important and widely used API of bit arrays is architecture-specific and located as we already know in the [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) header file.

First of all let's look at the two most important functions:

* `set_bit`;
* `clear_bit`.

I think that there is no need to explain what these function do. This is already must be clear from their name. Let's look on their implementation. If you will look into the [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) header file, you will note that each of these functions represented by two variants: [atomic](https://en.wikipedia.org/wiki/Linearizability) and not. Before we will start to dive into implementations of these functions, first of all we must to know a little about `atomic` operations.

In simple words atomic operations guarantees that two or more operations will not be performed on the same data concurrently. The `x86` architecture provides a set of atomic instructions, for example [xchg](http://x86.renejeschke.de/html/file_module_x86_id_328.html) instruction, [cmpxchg](http://x86.renejeschke.de/html/file_module_x86_id_41.html) instruction and etc. Besides atomic instructions, some of non-atomic instructions can be made atomic with the help of the [lock](http://x86.renejeschke.de/html/file_module_x86_id_159.html) instruction. It is enough to know about atomic operations for now, so we can begin to consider implementation of `set_bit` and `clear_bit` functions.

First of all, let's start to consider `non-atomic` variants of this function. Names of non-atomic `set_bit` and `clear_bit` starts from double underscore. As we already know, all of these functions are defined in the [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) header file and the first function is `__set_bit`:

```C
static inline void __set_bit(long nr, volatile unsigned long *addr)
{
	asm volatile("bts %1,%0" : ADDR : "Ir" (nr) : "memory");
}
```

As we can see it takes two arguments:

* `nr` - number of bit in a bit array.
* `addr` - address of a bit array where we need to set bit.

Note that the `addr` parameter is defined with `volatile` keyword which tells to compiler that value maybe changed by the given address. The implementation of the `__set_bit` is pretty easy. As we can see, it just contains one line of [inline assembler](https://en.wikipedia.org/wiki/Inline_assembler) code. In our case we are using the [bts](http://x86.renejeschke.de/html/file_module_x86_id_25.html) instruction which selects a bit which is specified with the first operand (`nr` in our case) from the bit array, stores the value of the selected bit in the [CF](https://en.wikipedia.org/wiki/FLAGS_register) flags register and set this bit.

Note that we can see usage of the `nr`, but there is `addr` here. You already might guess that the secret is in `ADDR`. The `ADDR` is the macro which is defined in the same header code file and expands to the string which contains value of the given address and `+m` constraint:

```C
#define ADDR				BITOP_ADDR(addr)
#define BITOP_ADDR(x) "+m" (*(volatile long *) (x))
```

Besides the `+m`, we can see other constraints in the `__set_bit` function. Let's look on they and try to understand what do they mean:

* `+m` - represents memory operand where `+` tells that the given operand will be input and output operand;
* `I` - represents integer constant;
* `r` - represents register operand

Besides these constraint, we also can see - the `memory` keyword which tells compiler that this code will change value in memory. That's all. Now let's look at the same function but at `atomic` variant. It looks more complex that its `non-atomic` variant:

```C
static __always_inline void
set_bit(long nr, volatile unsigned long *addr)
{
	if (IS_IMMEDIATE(nr)) {
		asm volatile(LOCK_PREFIX "orb %1,%0"
			: CONST_MASK_ADDR(nr, addr)
			: "iq" ((u8)CONST_MASK(nr))
			: "memory");
	} else {
		asm volatile(LOCK_PREFIX "bts %1,%0"
			: BITOP_ADDR(addr) : "Ir" (nr) : "memory");
	}
}
```

First of all note that this function takes the same set of parameters that `__set_bit`, but additionally marked with the `__always_inline` attribute. The `__always_inline` is macro which defined in the [include/linux/compiler-gcc.h](https://github.com/torvalds/linux/blob/master/include/linux/compiler-gcc.h) and just expands to the `always_inline` attribute:

```C
#define __always_inline inline __attribute__((always_inline))
```

which means that this function will be always inlined to reduce size of the Linux kernel image. Now let's try to understand implementation of the `set_bit` function. First of all we check a given number of bit at the beginning of the `set_bit` function. The `IS_IMMEDIATE` macro defined in the same [header](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) file and expands to the call of the builtin [gcc](https://en.wikipedia.org/wiki/GNU_Compiler_Collection) function:

```C
#define IS_IMMEDIATE(nr)		(__builtin_constant_p(nr))
```

The `__builtin_constant_p` builtin function returns `1` if the given parameter is known to be constant at compile-time and returns `0` in other case. We no need to use slow `bts` instruction to set bit if the given number of bit is known in compile time constant. We can just apply [bitwise or](https://en.wikipedia.org/wiki/Bitwise_operation#OR) for byte from the give address which contains given bit and masked number of bits where high bit is `1` and other is zero. In other case if the given number of bit is not known constant at compile-time, we do the same as we did in the `__set_bit` function. The `CONST_MASK_ADDR` macro:

```C
#define CONST_MASK_ADDR(nr, addr)	BITOP_ADDR((void *)(addr) + ((nr)>>3))
```

expands to the give address with offset to the byte which contains a given bit. For example we have address `0x1000` and the number of bit is `0x9`. So, as `0x9` is `one byte + one bit` our address with be `addr + 1`:

```python
>>> hex(0x1000 + (0x9 >> 3))
'0x1001'
```

The `CONST_MASK` macro represents our given number of bit as byte where high bit is `1` and other bits are `0`:

```C
#define CONST_MASK(nr)			(1 << ((nr) & 7))
```

```python
>>> bin(1 << (0x9 & 7))
'0b10'
```

In the end we just apply bitwise `or` for these values. So, for example if our address will be `0x4097` and we need to set `0x9` bit:

```python
>>> bin(0x4097)
'0b100000010010111'
>>> bin((0x4097 >> 0x9) | (1 << (0x9 & 7)))
'0b100010'
```

the `ninth` bit will be set.

Note that all of these operations are marked with `LOCK_PREFIX` which is expands to the [lock](http://x86.renejeschke.de/html/file_module_x86_id_159.html) instruction which guarantees atomicity of this operation.

As we already know, besides the `set_bit` and `__set_bit` operations, the Linux kernel provides two inverse functions to clear bit in atomic and non-atomic context. They are `clear_bit` and `__clear_bit`. Both of these functions are defined in the same [header file](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) and takes the same set of arguments. But not only arguments are similar. Generally these functions are very similar on the `set_bit` and `__set_bit`. Let's look on the implementation of the non-atomic `__clear_bit` function:

```C
static inline void __clear_bit(long nr, volatile unsigned long *addr)
{
	asm volatile("btr %1,%0" : ADDR : "Ir" (nr));
}
```

Yes. As we see, it takes the same set of arguments and contains very similar block of inline assembler. It just uses the [btr](http://x86.renejeschke.de/html/file_module_x86_id_24.html) instruction instead of `bts`. As we can understand form the function's name, it clears a given bit by the given address. The `btr` instruction acts like `bts`. This instruction also selects a given bit which is specified in the first operand, stores its value in the `CF` flag register and clears this bit in the given bit array which is specified with second operand.

The atomic variant of the `__clear_bit` is `clear_bit`:

```C
static __always_inline void
clear_bit(long nr, volatile unsigned long *addr)
{
	if (IS_IMMEDIATE(nr)) {
		asm volatile(LOCK_PREFIX "andb %1,%0"
			: CONST_MASK_ADDR(nr, addr)
			: "iq" ((u8)~CONST_MASK(nr)));
	} else {
		asm volatile(LOCK_PREFIX "btr %1,%0"
			: BITOP_ADDR(addr)
			: "Ir" (nr));
	}
}
```

and as we can see it is very similar on `set_bit` and just contains two differences. The first difference it uses `btr` instruction to clear bit when the `set_bit` uses `bts` instruction to set bit. The second difference it uses negated mask and `and` instruction to clear bit in the given byte when the `set_bit` uses `or` instruction.

That's all. Now we can set and clear bit in any bit array and and we can go to other operations on bitmasks.

Most widely used operations on a bit arrays are set and clear bit in a bit array in the Linux kernel. But besides this operations it is useful to do additional operations on a bit array. Yet another widely used operation in the Linux kernel - is to know is a given bit set or not in a bit array. We can achieve this with the help of the `test_bit` macro. This macro is defined in the [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) header file and expands to the call of the `constant_test_bit` or `variable_test_bit` depends on bit number:

```C
#define test_bit(nr, addr)			\
	(__builtin_constant_p((nr))                 \
	 ? constant_test_bit((nr), (addr))	        \
	 : variable_test_bit((nr), (addr)))
```

So, if the `nr` is known in compile time constant, the `test_bit` will be expanded to the call of the `constant_test_bit` function or `variable_test_bit` in other case. Now let's look at implementations of these functions. Let's start from the `variable_test_bit`:

```C
static inline int variable_test_bit(long nr, volatile const unsigned long *addr)
{
	int oldbit;

	asm volatile("bt %2,%1\n\t"
		     "sbb %0,%0"
		     : "=r" (oldbit)
		     : "m" (*(unsigned long *)addr), "Ir" (nr));

	return oldbit;
}
```

The `variable_test_bit` function takes similar set of arguments as `set_bit` and other function take. We also may see inline assembly code here which executes [bt](http://x86.renejeschke.de/html/file_module_x86_id_22.html) and [sbb](http://x86.renejeschke.de/html/file_module_x86_id_286.html) instruction. The `bt` or `bit test` instruction selects a given bit which is specified with first operand from the bit array which is specified with the second operand and stores its value in the [CF](https://en.wikipedia.org/wiki/FLAGS_register) bit of flags register. The second `sbb` instruction subtracts first operand from second and subtracts value of the `CF`. So, here write a value of a given bit number from a given bit array to the `CF` bit of flags register and execute `sbb` instruction which calculates: `00000000 - CF` and writes the result to the `oldbit`.

The `constant_test_bit` function does the same as we saw in the `set_bit`:

```C
static __always_inline int constant_test_bit(long nr, const volatile unsigned long *addr)
{
	return ((1UL << (nr & (BITS_PER_LONG-1))) &
		(addr[nr >> _BITOPS_LONG_SHIFT])) != 0;
}
```

It generates a byte where high bit is `1` and other bits are `0` (as we saw in `CONST_MASK`) and applies bitwise [and](https://en.wikipedia.org/wiki/Bitwise_operation#AND) to the byte which contains a given bit number.

The next widely used bit array related operation is to change bit in a bit array. The Linux kernel provides two helper for this:

* `__change_bit`;
* `change_bit`.

As you already can guess, these two variants are atomic and non-atomic as for example `set_bit` and `__set_bit`. For the start, let's look at the implementation of the `__change_bit` function:

```C
static inline void __change_bit(long nr, volatile unsigned long *addr)
{
    asm volatile("btc %1,%0" : ADDR : "Ir" (nr));
}
```

Pretty easy, is not it? The implementation of the `__change_bit` is the same as `__set_bit`, but instead of `bts` instruction, we are using [btc](http://x86.renejeschke.de/html/file_module_x86_id_23.html). This instruction selects a given bit from a given bit array, stores its value in the `CF` and changes its value by the applying of complement operation. So, a bit with value `1` will be `0` and vice versa:

```python
>>> int(not 1)
0
>>> int(not 0)
1
```

The atomic version of the `__change_bit` is the `change_bit` function:

```C
static inline void change_bit(long nr, volatile unsigned long *addr)
{
	if (IS_IMMEDIATE(nr)) {
		asm volatile(LOCK_PREFIX "xorb %1,%0"
			: CONST_MASK_ADDR(nr, addr)
			: "iq" ((u8)CONST_MASK(nr)));
	} else {
		asm volatile(LOCK_PREFIX "btc %1,%0"
			: BITOP_ADDR(addr)
			: "Ir" (nr));
	}
}
```

It is similar on `set_bit` function, but also has two differences. The first difference is `xor` operation instead of `or` and the second is `btc` instead of `bts`.

For this moment we know the most important architecture-specific operations with bit arrays. Time to look at generic bitmap API.

Common bit operations
================================================================================

Besides the architecture-specific API from the [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) header file, the Linux kernel provides common API for manipulation of bit arrays. As we know from the beginning of this part, we can find it in the  [include/linux/bitmap.h](https://github.com/torvalds/linux/blob/master/include/linux/bitmap.h) header file and additionally in the * [lib/bitmap.c](https://github.com/torvalds/linux/blob/master/lib/bitmap.c)  source code file. But before these source code files let's look into the [include/linux/bitops.h](https://github.com/torvalds/linux/blob/master/include/linux/bitops.h) header file which provides a set of useful macro. Let's look on some of they.

First of all let's look at following four macros:

* `for_each_set_bit`
* `for_each_set_bit_from`
* `for_each_clear_bit`
* `for_each_clear_bit_from`

All of these macros provide iterator over certain set of bits in a bit array. The first macro iterates over bits which are set, the second does the same, but starts from a certain bits. The last two macros do the same, but iterates over clear bits. Let's look on implementation of the `for_each_set_bit` macro:

```C
#define for_each_set_bit(bit, addr, size) \
	for ((bit) = find_first_bit((addr), (size));		\
	     (bit) < (size);					\
	     (bit) = find_next_bit((addr), (size), (bit) + 1))
```

As we may see it takes three arguments and expands to the loop from first set bit which is returned as result of the `find_first_bit` function and to the last bit number while it is less than given size.

Besides these four macros, the [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) provides API for rotation of `64-bit` or `32-bit` values and etc.

The next [header](https://github.com/torvalds/linux/blob/master/include/linux/bitmap.h) file which provides API for manipulation with a bit arrays. For example it provides two functions:

* `bitmap_zero`;
* `bitmap_fill`.

To clear a bit array and fill it with `1`. Let's look on the implementation of the `bitmap_zero` function:

```C
static inline void bitmap_zero(unsigned long *dst, unsigned int nbits)
{
	if (small_const_nbits(nbits))
		*dst = 0UL;
	else {
		unsigned int len = BITS_TO_LONGS(nbits) * sizeof(unsigned long);
		memset(dst, 0, len);
	}
}
```

First of all we can see the check for `nbits`. The `small_const_nbits` is macro which defined in the same header [file](https://github.com/torvalds/linux/blob/master/include/linux/bitmap.h) and looks:

```C
#define small_const_nbits(nbits) \
	(__builtin_constant_p(nbits) && (nbits) <= BITS_PER_LONG)
```

As we may see it checks that `nbits` is known constant in compile time and `nbits` value does not overflow `BITS_PER_LONG` or `64`. If bits number does not overflow amount of bits in a `long` value we can just set to zero. In other case we need to calculate how many `long` values do we need to fill our bit array and fill it with [memset](http://man7.org/linux/man-pages/man3/memset.3.html).

The implementation of the `bitmap_fill` function is similar on implementation of the `biramp_zero` function, except we fill a given bit array with `0xff` values or `0b11111111`:

```C
static inline void bitmap_fill(unsigned long *dst, unsigned int nbits)
{
	unsigned int nlongs = BITS_TO_LONGS(nbits);
	if (!small_const_nbits(nbits)) {
		unsigned int len = (nlongs - 1) * sizeof(unsigned long);
		memset(dst, 0xff,  len);
	}
	dst[nlongs - 1] = BITMAP_LAST_WORD_MASK(nbits);
}
```

Besides the `bitmap_fill` and `bitmap_zero` functions, the [include/linux/bitmap.h](https://github.com/torvalds/linux/blob/master/include/linux/bitmap.h) header file provides `bitmap_copy` which is similar on the `bitmap_zero`, but just uses [memcpy](http://man7.org/linux/man-pages/man3/memcpy.3.html) instead of [memset](http://man7.org/linux/man-pages/man3/memset.3.html). Also it provides bitwise operations for bit array like `bitmap_and`, `bitmap_or`, `bitamp_xor` and etc. We will not consider implementation of these functions because it is easy to understand implementations of these functions if you understood all from this part. Anyway if you are interested how did these function implemented, you may open [include/linux/bitmap.h](https://github.com/torvalds/linux/blob/master/include/linux/bitmap.h) header file and start to research.

That's all.

Links
================================================================================

* [bitmap](https://en.wikipedia.org/wiki/Bit_array)
* [linked data structures](https://en.wikipedia.org/wiki/Linked_data_structure)
* [tree data structures](https://en.wikipedia.org/wiki/Tree_%28data_structure%29) 
* [hot-plug](https://www.kernel.org/doc/Documentation/cpu-hotplug.txt)
* [cpumasks](https://0xax.gitbooks.io/linux-insides/content/Concepts/cpumask.html)
* [IRQs](https://en.wikipedia.org/wiki/Interrupt_request_%28PC_architecture%29)
* [API](https://en.wikipedia.org/wiki/Application_programming_interface)
* [atomic operations](https://en.wikipedia.org/wiki/Linearizability)
* [xchg instruction](http://x86.renejeschke.de/html/file_module_x86_id_328.html)
* [cmpxchg instruction](http://x86.renejeschke.de/html/file_module_x86_id_41.html)
* [lock instruction](http://x86.renejeschke.de/html/file_module_x86_id_159.html)
* [bts instruction](http://x86.renejeschke.de/html/file_module_x86_id_25.html)
* [btr instruction](http://x86.renejeschke.de/html/file_module_x86_id_24.html)
* [bt instruction](http://x86.renejeschke.de/html/file_module_x86_id_22.html)
* [sbb instruction](http://x86.renejeschke.de/html/file_module_x86_id_286.html)
* [btc instruction](http://x86.renejeschke.de/html/file_module_x86_id_23.html)
* [man memcpy](http://man7.org/linux/man-pages/man3/memcpy.3.html) 
* [man memset](http://man7.org/linux/man-pages/man3/memset.3.html)
* [CF](https://en.wikipedia.org/wiki/FLAGS_register)
* [inline assembler](https://en.wikipedia.org/wiki/Inline_assembler)
* [gcc](https://en.wikipedia.org/wiki/GNU_Compiler_Collection)
