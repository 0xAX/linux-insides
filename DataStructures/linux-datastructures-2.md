# Kernel Data Structures - Part 2

In the [previous part](./linux-datastructures-1.md) of this chapter, we looked at the first and probably one of the most common data structure used in the Linux kernel - [linked list](https://en.wikipedia.org/wiki/Linked_list). In this part, we will continue looking at common data structures and algorithms and how they are implemented in the Linux kernel.

Linux is an operating system kernel, so it naturally deals with low-level primitives and abstractions built on top of them very often. One of such abstraction that is extensively used in the kernel, is the [bit array](https://en.wikipedia.org/wiki/Bit_array), or, as it is usually called in the kernel, the **bitmap**.

The statement that this abstraction is used very often in the kernel is not an empty claim. Just like with the linked lists, let's try to get a rough idea of how common bitmaps are in the kernel source code. The most basic operations on a bitmap are to set a bit, to clear a bit, and to test whether a bit is set. Let's see:

```bash
rg -w 'set_bit|clear_bit|test_bit' | wc -l
28340
```

Of course, the number above can be different if you are using a different version of the Linux kernel. But anyway, it should be quite visible how often it is used. So it is definitely worth looking and understanding how bitmaps are implemented in the Linux kernel.

## Bit arrays

A bitmap is just a sequence of bits where every bit represents some state, for example:

- set or clear
- available or unavailable
- enabled or disabled

This makes bitmaps especially useful when the kernel needs to keep track of a large number of objects or states and in the same time to use as little memory as possible.

As usual, before we dive into the kernel implementation, let's take a short look at this data structure in general. According to [wikipedia](https://en.wikipedia.org/wiki/Bit_array):

> A bit array (also known as bit map, bit set, bit string, or bit vector) is an array data structure that compactly stores bits. It can be used to implement a simple set data structure. A bit array is effective at exploiting bit-level parallelism in hardware to perform operations quickly.
>
> -- Wikipedia, "Bit array"

At first glance, the idea sounds relatively simple, right?

We have a sequence of bits numbered from zero, and every bit is either `0` or `1`. Since every bit has an index that identifies its position in the bit array, we can treat this index as a value and the bit itself as an answer to the question "is this value present?". This is exactly how a bit array implements the `set` mentioned in the quote above. For example, to store the set of numbers `{1, 3, 8, 12}`, we can take a bit array of sixteen bits, set the bits with indexes `1`, `3`, `8` and `12`, and leave all other bits clear. We can visualize it like this:

![bit array](./images/bit-array.svg)

Since the indexes go from zero to the size of the bit array minus one, only numbers from this range can be stored in such a set.

So what can we do with such a set? Quite a few useful things, actually. We can set a bit, clear a bit, test whether a bit is set, and find the first set or clear bit. The first three operations touch only a single bit. The last one scans the bits, but as we will see, it does it one machine word at a time.

What makes bit arrays so attractive is how compact they are. A set that may contain any number from `0` to `255` needs only `256` bits, or `32` bytes. An array of `bool` values for the same purpose takes eight times more memory, and a linked list of integers takes much more than that. The second reason is speed. Processors can operate on a whole word of bits with a single instruction, and some instructions even work with a single bit directly. All of this, we will see this in the kernel code soon.

## Bitmaps in the Linux kernel

Now that we have briefly revisited what a bit array is, let's see how the Linux kernel implements it.

Before we look at the API for manipulating bitmaps, we need to know how the Linux kernel declares them. There is no special type for a bitmap in the Linux kernel. A bitmap is just an array of `unsigned long` values. On `x86_64`, this data type is `64` bits wide, so every `64` bits of a bitmap take one word. If the number of bits is not a multiple of `64`, the remaining bits still get a whole word. For example, a bitmap of `100` bits occupies `128` bits, or `16` bytes. 

The kernel provides the `DECLARE_BITMAP` macro to declare such an array. It is defined in the [include/linux/types.h](https://github.com/torvalds/linux/blob/master/include/linux/types.h) header file and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/types.h#L9-L10 -->
```C
#define DECLARE_BITMAP(name,bits) \
	unsigned long name[BITS_TO_LONGS(bits)]
```

No big surprises here. To declare a bitmap, we only need to pass two things to the macro:

- the name of the array
- the number of bits the bitmap consists of

It expands to the definition of an array of `unsigned long` with `BITS_TO_LONGS(bits)` elements. The `BITS_TO_LONGS` macro, in turn, is defined in the [include/linux/bitops.h](https://github.com/torvalds/linux/blob/master/include/linux/bitops.h) header file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/bitops.h#L11-L11 -->
```C
#define BITS_TO_LONGS(nr)	__KERNEL_DIV_ROUND_UP(nr, BITS_PER_TYPE(long))
```

As the name suggests, it converts a number of bits into a number of `long` values. Here, the `BITS_PER_TYPE(long)` macro expands to the number of bits in a `long`, which is `64` in our case. The `__KERNEL_DIV_ROUND_UP` macro does the division and rounds the result up, so the last bits still get a word even if they do not fill it completely:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/uapi/linux/const.h#L51-L51 -->
```C
#define __KERNEL_DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
```

That is enough theory about how bitmaps are declared in the Linux kernel. It is time to take a look at a real example. 

In the beginning of this part, we have seen that bitmaps are ubiquitous in the kernel. So, we do not need to go far to find one. A good candidate is something the kernel has a fixed number of and needs to track as taken or free. [Interrupt](https://en.wikipedia.org/wiki/Interrupt) vectors are exactly that.

The `x86_64` architecture has `256` interrupt vectors, and not all of them are free for devices to use. During boot, the kernel reserves some of them for its own needs. For example, some vectors are reserved for the local [APIC](https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller) timer or the [inter-processor interrupts](https://en.wikipedia.org/wiki/Inter-processor_interrupt). Such vectors are called **system vectors**. So how does the kernel remember which vectors it has reserved? The answer, as you may have already guessed, is a bitmap.

We can find the declaration of this bitmap in the [arch/x86/kernel/traps.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/traps.c) source code file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/traps.c#L84-L84 -->
```C
DECLARE_BITMAP(system_vectors, NR_VECTORS);
```

As mentioned above, the `x86_64` architecture provides `256` interrupt vectors. The `NR_VECTORS` macro confirms this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/irq_vectors.h#L108-L108 -->
```C
#define NR_VECTORS			 256
```

We have already seen the `BITS_TO_LONGS` macro above. As a reminder, this macro calculates how many `unsigned long` values are needed to hold the given number of bits. We can try to apply the same calculation and see what array size it produces. It gives us `(256 + 64 - 1) / 64`, which is `4`, so after the preprocessor is done, the declaration above expands into a plain array of four words:

```C
unsigned long system_vectors[4];
```

In the case of the interrupt vectors, the bitmap is a global variable. Of course, a bitmap does not have to be one. Another common case is a bitmap as a field of a structure, just like any other array. For example, the set of processors that the kernel calls `cpumask` is nothing more than a structure with a single bitmap inside:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/cpumask_types.h#L9-L9 -->
```C
typedef struct cpumask { DECLARE_BITMAP(bits, NR_CPUS); } cpumask_t;
```

## Accessing a bit

Now that we know how a bitmap is declared in the Linux kernel, we can take a look at the existing API to work with bitmaps.

Since a bitmap is an array of words, to access a bit we need to translate the bit number into two values:

- the index of the word in the array
- the position of the bit inside that word

Both are relatively easy to get. To get the index of the word, we can divide the given bit number by `64`. The position inside the word is just the remainder of this division. 

For example, the local APIC timer uses the vector `0xEC`, or `236` in decimal. To find the word and the bit inside it for this vector, let's try to do the calculations:

- the index of the word is `236 / 64 = 3`
- the position of the bit inside this word is `236 % 64 = 44`

So the local APIC timer vector corresponds to bit `44` in the last word of the interrupt vector bitmap. Visually, it looks like this:

![bit number to word](./images/bitmap-words.svg)

Of course, there is no need to do these operations manually every time. The kernel has two macros for these calculations:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/bits.h#L8-L9 -->
```C
#define BIT_MASK(nr)		(UL(1) << ((nr) % BITS_PER_LONG))
#define BIT_WORD(nr)		((nr) / BITS_PER_LONG)
```

The `BIT_WORD` macro is exactly the division we just did by hand. If we pass our value `236` to `BIT_WORD`, it gives us `3`, the same result as our calculation. The `BIT_MASK` macro does a little more than returning the position within the word. It returns a whole word with only bit `44` set.

With the index of the word and the mask, we have everything we need to work with a single bit. For example, to set bit `236`, it is enough to combine the word and the mask with the [bitwise OR](https://en.wikipedia.org/wiki/Bitwise_operation#OR), for example:

```C
system_vectors[BIT_WORD(236)] |= BIT_MASK(236);
```

## Setting, clearing and testing bits

We already know how to find any bit in a bitmap and even how to set it with a single line of code. Despite this, the kernel provides an API for these operations:

- `set_bit` - the [atomic](https://en.wikipedia.org/wiki/Linearizability) variant
- `__set_bit` - the non-atomic variant

The same pair exists for every other basic operation. There are `clear_bit` and `__clear_bit`, `change_bit` and `__change_bit`, `test_and_set_bit` and `__test_and_set_bit`, and so on. The names that start with the double underscore are always the non-atomic variants.

Why does the kernel need separate operations when we already know how to set or clear a bit using the macros that we have seen in the previous section? The answer to this question is simple. It turns out that a plain `|=` is not always as innocent as it may look, and very soon we will see why.

Let's start with the most basic operation - setting a bit. But before we will take a look at the implementation of these APIs, let's figure out what does atomic mean here.

Setting a bit in memory is a [read-modify-write](https://en.wikipedia.org/wiki/Read%E2%80%93modify%E2%80%93write) operation. The processor reads the word, changes one bit in it, and writes the word back. If two processors do this with the same word at the same time, one of the changes can be lost. The atomic variant guarantees that the whole operation is executed as one indivisible step, so no other processor can touch the word in the middle. In contrast, the non-atomic variant does not give such a guarantee. It must be used only when the code knows that nobody else can access the bitmap at the same time, for example, when the bitmap is protected by a lock or is not visible to the other processors yet.

After this short introduction to what atomic means, we can go back to our `system_vectors` bitmap and find out how the kernel fills it during initialization. This job is done by the `idt_setup_from_table` function from the [arch/x86/kernel/idt.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/idt.c) source code file. Besides installing the interrupt handlers for the system vectors, it also marks them as reserved in the bitmap:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/idt.c#L196-L207 -->
```C
static __init void
idt_setup_from_table(gate_desc *idt, const struct idt_data *t, int size, bool sys)
{
	gate_desc desc;

	for (; size > 0; t++, size--) {
		idt_init_desc(&desc, t);
		write_idt_entry(idt, t->vector, &desc);
		if (sys)
			set_bit(t->vector, system_vectors);
	}
}
```

We do not need to understand everything here since this chapter is not about interrupts. What interests us here is the call to `set_bit`. Its first argument is the number of the bit, and the second is the bitmap itself. This function is defined in the [include/asm-generic/bitops/instrumented-atomic.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/bitops/instrumented-atomic.h) header file and looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/asm-generic/bitops/instrumented-atomic.h#L26-L30 -->
```C
static __always_inline void set_bit(long nr, volatile unsigned long *addr)
{
	instrument_atomic_write(addr + BIT_WORD(nr), sizeof(long));
	arch_set_bit(nr, addr);
}
```

The first line is not related to the bit operation itself. It tells the kernel sanitizers like [KASAN](https://docs.kernel.org/dev-tools/kasan.html) and [KCSAN](https://docs.kernel.org/dev-tools/kcsan.html) that the word with the index `BIT_WORD(nr)` is about to be written. All the actual work is done by `arch_set_bit`. The `arch_` prefix tells us that this function is architecture-specific. For `x86_64` architecture, this function is defined in the [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) header file. The implementation looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/bitops.h#L51-L63 -->
```C
static __always_inline void
arch_set_bit(long nr, volatile unsigned long *addr)
{
	if (__builtin_constant_p(nr)) {
		asm_inline volatile(LOCK_PREFIX "orb %b1,%0"
			: CONST_MASK_ADDR(nr, addr)
			: "iq" (CONST_MASK(nr))
			: "memory");
	} else {
		asm_inline volatile(LOCK_PREFIX __ASM_SIZE(bts) " %1,%0"
			: : RLONG_ADDR(addr), "Ir" (nr) : "memory");
	}
}
```

Let's take a closer look at the implementation of this function. It has two branches, and the compiler picks one of them at compile time, based on the result of [`__builtin_constant_p(nr)`](https://gcc.gnu.org/onlinedocs/gcc/Other-Builtins.html#index-_005f_005fbuiltin_005fconstant_005fp). This is a compiler builtin function that returns `1` if its argument is a constant known at compile time, and `0` otherwise.

In our case, `idt_setup_from_table` passes `t->vector` as the number of the bit. This value is read from a table while the loop runs, so the compiler cannot know it in advance, and `__builtin_constant_p(nr)` returns `0`. But this is not always the case. Very often, the number of the bit is just a named constant. For example, the [EFI](https://en.wikipedia.org/wiki/UEFI) code marks that the EFI runtime services can be used like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/platform/efi/efi.c#L498-L498 -->
```C
set_bit(EFI_RUNTIME_SERVICES, &efi.flags);
```

Returning to the `arch_set_but_function`, we can see that in both branches there are [inline assembly](https://en.wikipedia.org/wiki/Inline_assembler) instruction that start with the `LOCK_PREFIX` macro. This macro expands to the [lock](https://www.felixcloutier.com/x86/lock) prefix:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/alternative.h#L23-L27 -->
```C
#ifdef CONFIG_SMP
#define LOCK_PREFIX "lock "
#else
#define LOCK_PREFIX ""
#endif
```

This prefix makes the instruction that follows it atomic, and this is exactly what makes `set_bit` atomic. If the kernel is built without [SMP](https://en.wikipedia.org/wiki/Symmetric_multiprocessing) support, there is only one processor, and the prefix is obviously not needed.

So what does this inline assembly actually do? Let's start with the second branch, because it handles the general case, when the number of the bit is not known at compile time. This branch uses only one instruction - [bts](https://www.felixcloutier.com/x86/bts) that does "bit test and set" operation. This instruction takes the address of the bitmap and the number of the bit, and sets this bit to `1`. The interesting thing about the `bts` instruction is that the number of the bit is not limited to `63`. The processor itself finds the right word in memory, so `set_bit` does not need `BIT_WORD` or `BIT_MASK` at all.

Returning to the first branch, we already know that it is an optimization for the case when the number of the bit is known at compile time. Here, the compiler can calculate in advance which byte of the bitmap holds the bit and which bit of that byte it is using the following macros:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/bitops.h#L48-L49 -->
```C
#define CONST_MASK_ADDR(nr, addr)	WBYTE_ADDR((void *)(addr) + ((nr)>>3))
#define CONST_MASK(nr)			(1 << ((nr) & 7))
```

These macros do the same calculations as `BIT_WORD` and `BIT_MASK` from the previous section. The difference is only that they do it with bytes instead of 64-bit words. Shifting `nr` right by `3` is the same as dividing it by `8`, so `CONST_MASK_ADDR` gives the address of the byte that holds the bit. The `nr & 7` expression is the remainder of this division, so `CONST_MASK` gives a byte with only the needed bit set. 

This works because `x86` is a [little-endian](https://en.wikipedia.org/wiki/Endianness) architecture, so the bit `nr` of a bitmap is always stored in the byte `nr / 8`. Having the byte and the mask, a single `orb` instruction, a bitwise [or](https://en.wikipedia.org/wiki/Bitwise_operation#OR) on one byte, is enough to set the bit. 

Why does the kernel need two branches at all, if `bts` can handle any bit? With `bts`, the processor has to find the right word in memory from the number of the bit every time the instruction runs. With a constant, the compiler does this work only once, at compile time, and the processor only has to apply a simple `OR` to a byte with a known address.

Let's see how it works with our vector `236`, pretending for a moment that it is a constant. This time we need to repeat two operations to find the bit in the byte array:

- the byte that holds the bit: `236 / 8 = 29`
- the position of the bit inside this byte: `236 % 8 = 4`

So the kernel takes the byte `29` of the bitmap and combines it with the mask `1 << 4` using `OR` to set this bit. Visually, it looks like this:

![constant mask](./images/const-mask.svg)

=============

Clearing a bit is the mirror image of what we have just seen:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/bitops.h#L71-L82 -->
```C
static __always_inline void
arch_clear_bit(long nr, volatile unsigned long *addr)
{
	if (__builtin_constant_p(nr)) {
		asm_inline volatile(LOCK_PREFIX "andb %b1,%0"
			: CONST_MASK_ADDR(nr, addr)
			: "iq" (~CONST_MASK(nr)));
	} else {
		asm_inline volatile(LOCK_PREFIX __ASM_SIZE(btr) " %1,%0"
			: : RLONG_ADDR(addr), "Ir" (nr) : "memory");
	}
}
```

There are only two differences. The general case uses the [btr](https://www.felixcloutier.com/x86/btr) instruction, "bit test and reset", instead of `bts`. The byte case uses the bitwise [and](https://en.wikipedia.org/wiki/Bitwise_operation#AND) with the inverted mask instead of `or`, so the selected bit becomes `0` and all other bits of the byte stay as they were.

Now, what about the non-atomic `__set_bit`? If we look for it, we will find that it is a macro from the [include/linux/bitops.h](https://github.com/torvalds/linux/blob/master/include/linux/bitops.h) header file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/bitops.h#L53-L53 -->
```C
#define __set_bit(nr, addr)		bitop(___set_bit, nr, addr)
```

The `bitop` macro is a small optimization. If both the bit number and the content of the bitmap are known at compile time, it picks a generic implementation written in plain C, so the compiler can fold the whole operation into a constant. In all other cases, it expands to the call of `___set_bit`, which, after the same sanitizer wrapper as we saw above, ends up in the architecture-specific `arch___set_bit`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/bitops.h#L65-L69 -->
```C
static __always_inline void
arch___set_bit(unsigned long nr, volatile unsigned long *addr)
{
	asm volatile(__ASM_SIZE(bts) " %1,%0" : : ADDR, "Ir" (nr) : "memory");
}
```

This is the same `bts` instruction, but without the `lock` prefix and without the special case for a constant bit number.

The next operation is to test a bit. The `test_bit` macro from the same [include/linux/bitops.h](https://github.com/torvalds/linux/blob/master/include/linux/bitops.h) goes through the same `bitop` macro and the same sanitizer wrapper, and finally calls `arch_test_bit`:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/bitops.h#L229-L234 -->
```C
static __always_inline bool
arch_test_bit(unsigned long nr, const volatile unsigned long *addr)
{
	return __builtin_constant_p(nr) ? constant_test_bit(nr, addr) :
					  variable_test_bit(nr, addr);
}
```

Again, we see two cases that depend on whether the bit number is known at compile time. The first one is written in plain C:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/bitops.h#L199-L203 -->
```C
static __always_inline bool constant_test_bit(long nr, const volatile unsigned long *addr)
{
	return ((1UL << (nr & (BITS_PER_LONG-1))) &
		(addr[nr >> _BITOPS_LONG_SHIFT])) != 0;
}
```

Here are both of our calculations once more. The `_BITOPS_LONG_SHIFT` macro is `6` on `x86_64`, so `nr >> 6` is the index of the word, exactly like `BIT_WORD(nr)`. The `nr & 63` is the position of the bit inside this word, so `1UL << (nr & 63)` is the same mask as `BIT_MASK(nr)`. The function applies the bitwise `and` of the mask and the word, and compares the result with zero.

The second case uses the [bt](https://www.felixcloutier.com/x86/bt) instruction, "bit test":

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/bitops.h#L218-L227 -->
```C
static __always_inline bool variable_test_bit(long nr, volatile const unsigned long *addr)
{
	bool oldbit;

	asm volatile(__ASM_SIZE(bt) " %2,%1"
		     : "=@ccc" (oldbit)
		     : "m" (*(unsigned long *)addr), "Ir" (nr) : "memory");

	return oldbit;
}
```

This instruction only copies the selected bit into the `CF` flag and changes nothing in memory. The interesting part is the `"=@ccc"` output constraint. It tells the compiler that the output value of `oldbit` is the state of the carry flag after the instruction. Thanks to this, the compiler does not need to copy the flag into a register. If the result is used in a condition, it can branch on the flag directly.

As we may notice, `test_bit` has no non-atomic variant. Testing a bit does not modify anything, and a read of a single aligned word is atomic on `x86` anyway, so there is nothing to make cheaper.

The last operation that we will look at in this section combines the two previous ones. Let's take a look at the function from [arch/x86/kernel/idt.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/idt.c) that reserves one system vector at a time:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/idt.c#L353-L363 -->
```C
void __init idt_install_sysvec(unsigned int n, const void *function)
{
	if (WARN_ON(n < FIRST_SYSTEM_VECTOR))
		return;

	if (WARN_ON(idt_setup_done))
		return;

	if (!WARN_ON(test_and_set_bit(n, system_vectors)))
		set_intr_gate(n, function);
}
```

The `test_and_set_bit` function sets the bit and returns its old value in one atomic step. If the old value was `1`, the vector was already taken, and the kernel warns about it instead of installing a second handler. The two steps can not be separated here. If the kernel first tested the bit and then set it with a second call, another processor could take the same vector between these two calls. The implementation of `test_and_set_bit` in [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h) is `lock bts` again. The only difference from `set_bit` is that the value of the `CF` flag is returned to the caller, exactly like in `variable_test_bit`.

## Bitmap operations

So far we have looked at the operations that work with a single bit. Besides them, the kernel provides API that works with a whole bitmap. Most of it can be found in the [include/linux/bitmap.h](https://github.com/torvalds/linux/blob/master/include/linux/bitmap.h) header file and in the [lib/bitmap.c](https://github.com/torvalds/linux/blob/master/lib/bitmap.c) source code file. The simplest functions there are `bitmap_zero` and `bitmap_fill`, which clear all bits of a bitmap or set all of them:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/bitmap.h#L241-L249 -->
```C
static __always_inline void bitmap_zero(unsigned long *dst, unsigned int nbits)
{
	unsigned int len = bitmap_size(nbits);

	if (small_const_nbits(nbits))
		*dst = 0;
	else
		memset(dst, 0, len);
}
```

The `bitmap_size` macro converts the number of bits into the number of bytes that the bitmap occupies, that is, the number of bits rounded up to a multiple of `64` and divided by `8`. The `small_const_nbits` macro is defined in the [include/asm-generic/bitsperlong.h](https://github.com/torvalds/linux/blob/master/include/asm-generic/bitsperlong.h) header file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/asm-generic/bitsperlong.h#L45-L46 -->
```C
	(__builtin_constant_p(nbits) && (nbits) <= BITS_PER_LONG && (nbits) > 0)

```

It checks that the number of bits is known at compile time and fits into a single word. If this is the case, the whole bitmap can be cleared with a single store. Otherwise, the function falls back to [memset](https://man7.org/linux/man-pages/man3/memset.3.html). This pattern repeats in almost every function of the bitmap API. The small bitmaps with a compile-time size get a fast inline path, and everything else goes through the generic code. The `bitmap_fill` function is the same, but stores `~0UL` or `0xff` bytes instead of zeros:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/bitmap.h#L251-L259 -->
```C
static __always_inline void bitmap_fill(unsigned long *dst, unsigned int nbits)
{
	unsigned int len = bitmap_size(nbits);

	if (small_const_nbits(nbits))
		*dst = ~0UL;
	else
		memset(dst, 0xff, len);
}
```

Note that both functions work with whole words. If the number of bits is not a multiple of `64`, the bits of the last word that do not belong to the bitmap are cleared or set as well.

The more interesting part of the API is searching. The two basic functions here are `find_first_bit` and `find_next_bit` from the [include/linux/find.h](https://github.com/torvalds/linux/blob/master/include/linux/find.h) header file. The first one returns the number of the first set bit:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/find.h#L203-L213 -->
```C
static __always_inline
unsigned long find_first_bit(const unsigned long *addr, unsigned long size)
{
	if (small_const_nbits(size)) {
		unsigned long val = *addr & GENMASK(size - 1, 0);

		return val ? __ffs(val) : size;
	}

	return _find_first_bit(addr, size);
}
```

The same two paths again. In the case of a small bitmap, the single word is masked with `GENMASK(size - 1, 0)`, which is a word with the bits from `0` to `size - 1` set, so the bits beyond the bitmap can not affect the result. If anything is left after the masking, `__ffs` returns the index of the lowest set bit. Otherwise, the function returns `size`. This is the convention for the whole family of search functions. The value equal to the size of the bitmap means that nothing was found.

The `__ffs` macro, "find first set", has an architecture-specific implementation in [arch/x86/include/asm/bitops.h](https://github.com/torvalds/linux/blob/master/arch/x86/include/asm/bitops.h):

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/include/asm/bitops.h#L243-L249 -->
```C
static __always_inline __attribute_const__ unsigned long variable__ffs(unsigned long word)
{
	asm("tzcnt %1,%0"
		: "=r" (word)
		: ASM_INPUT_RM (word));
	return word;
}
```

The [tzcnt](https://www.felixcloutier.com/x86/tzcnt) instruction counts the trailing zero bits of its operand. For a non-zero word, this number is exactly the position of the lowest set bit. Here is the bit-level parallelism from the Wikipedia definition in action. One instruction examines all `64` bits of the word at once.

The general case is handled by `_find_first_bit` from the [lib/find_bit.c](https://github.com/torvalds/linux/blob/master/lib/find_bit.c) source code file:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/lib/find_bit.c#L100-L103 -->
```C
unsigned long _find_first_bit(const unsigned long *addr, unsigned long size)
{
	return FIND_FIRST_BIT(addr[idx], /* nop */, size);
}
```

The function just expands the `FIND_FIRST_BIT` macro defined in the same file. The reason for the macro is that the same loop is shared by the whole family of functions. `find_first_zero_bit`, for example, fetches `~addr[idx]` instead of `addr[idx]`, and `find_first_and_bit` fetches the `and` of the words of two bitmaps. The loop itself looks like this:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/lib/find_bit.c#L29-L42 -->
```C
#define FIND_FIRST_BIT(FETCH, MUNGE, size)					\
({										\
	unsigned long idx, val, sz = (size);					\
										\
	for (idx = 0; idx * BITS_PER_LONG < sz; idx++) {			\
		val = (FETCH);							\
		if (val) {							\
			sz = min(idx * BITS_PER_LONG + __ffs(MUNGE(val)), sz);	\
			break;							\
		}								\
	}									\
										\
	sz;									\
})
```

It walks the bitmap word by word. Words that are equal to zero are skipped as a whole, without looking at the individual bits. For the first non-zero word, `__ffs` gives the position of the lowest set bit inside the word, and `idx * BITS_PER_LONG` added to it gives the number of the bit in the whole bitmap. The `min` is needed for the last word, which may contain set bits beyond the size of the bitmap. If the loop runs to the end without finding anything, the result is `size`:

![find_first_bit](./images/find-first-bit.svg)

The `find_next_bit` function does the same, but starts the search from a given bit instead of the beginning. It is the base for the iterator macros, which are probably the most frequently used part of the bitmap API:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/include/linux/find.h#L583-L584 -->
```C
#define for_each_set_bit(bit, addr, size) \
	for ((bit) = 0; (bit) = find_next_bit((addr), (size), (bit)), (bit) < (size); (bit)++)
```

This is a regular `for` loop. The `bit` variable starts from zero. On every iteration, `find_next_bit` is called first to move `bit` to the next set bit starting from its current value, and then the result is compared with `size`. If it is less, the body of the loop is executed with `bit` equal to the number of a set bit. After the body, `bit` is incremented so the next search starts after the bit that was just visited. When `find_next_bit` returns `size`, the loop ends.

Let's return to our `system_vectors` bitmap for the last time. When the local APIC is initialized, the kernel has to tell its interrupt vector allocator which vectors are already reserved as system vectors, so they are never given to a device. This is done in [arch/x86/kernel/apic/vector.c](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/apic/vector.c) with a single loop over the set bits:

<!-- https://raw.githubusercontent.com/torvalds/linux/refs/heads/master/arch/x86/kernel/apic/vector.c#L778-L779 -->
```C
	for_each_set_bit(vector, system_vectors, NR_VECTORS)
		irq_matrix_assign_system(vector_matrix, vector, false);
```

At this point, I think we know enough to understand the basic idea behind bitmaps in the kernel. We have seen how a bitmap is declared, how a bit number is split into the word index and the position inside the word, how the atomic and non-atomic bit operations are implemented on `x86_64`, and how the kernel searches and iterates over the set bits.

The rest of the bitmap API follows the same ideas. There are functions for the bitwise `and`, `or`, and `xor` of two bitmaps, for counting the set bits, for comparing bitmaps, for shifting them, and for parsing and printing them. I will not go through each of them here. With what we already know, reading their implementation in [include/linux/bitmap.h](https://github.com/torvalds/linux/blob/master/include/linux/bitmap.h) and [lib/bitmap.c](https://github.com/torvalds/linux/blob/master/lib/bitmap.c) can be a good exercise.

## Conclusion

This is the end of the second part about the data structures used in the Linux kernel. If you have questions or suggestions, feel free to ping me on X - [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new).
