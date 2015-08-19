Executable and Linkable Format
================================================================================

ELF (Executable and Linkable Format) is a standard file format for executable files, object code, shared libraries, and core dumps. Linux, as well as, many other UNIX-like operating systems uses this format. Let's look on the structure of ELF-64 File Format and some defintions in the linux kernel source code related with it.

An ELF file consists of the following parts:

* ELF header - describes the main characteristics of the object file: type, CPU architecture, virtual address of the entry point, size and offset of the remaining parts, etc...;
* Program header table - lists the available segments and their attributes. Program header table needs loaders for placing sections of this file as virtual memory segments;
* Section header table - contains the description of sections.

Now let's look closer on these components.

**ELF header**

It's located in the beginning of the object file. Its main point is to locate all other parts of the object file. ELF header contains following fields:

* ELF identification - array of bytes which helps identify this file as an ELF file and also provides information about general object file characteristics;
* Object file type - identifies the object file type. This field can describe whether this file is a relocatable file or executable file, etc...;
* Target architecture;
* Version of the object file format;
* Virtual address of the program entry point;
* File offset of the program header table;
* File offset of the section header table;
* Size of the ELF header;
* Size of the program header table entry;
* and other fields...

You can find `elf64_hdr` structure which presents ELF64 header in the linux kernel source code:

```C
typedef struct elf64_hdr {
	unsigned char	e_ident[EI_NIDENT];
	Elf64_Half e_type;
	Elf64_Half e_machine;
	Elf64_Word e_version;
	Elf64_Addr e_entry;
	Elf64_Off e_phoff;
	Elf64_Off e_shoff;
	Elf64_Word e_flags;
	Elf64_Half e_ehsize;
	Elf64_Half e_phentsize;
	Elf64_Half e_phnum;
	Elf64_Half e_shentsize;
	Elf64_Half e_shnum;
	Elf64_Half e_shstrndx;
} Elf64_Ehdr;
```

This structure defines in the [elf.h](https://github.com/torvalds/linux/blob/master/include/uapi/linux/elf.h)

**Sections**

All data is stored in sections in an Elf file. Sections are identified by index in the section header table. Section header contains following fields:

* Section name;
* Section type;
* Section attributes;
* Virtual address in memory;
* Offset in file;
* Size of section;
* Link to other section;
* Miscellaneous information;
* Address alignment boundary;
* Size of entries, if section has table;

And presented with the following `elf64_shdr` structure in the linux kernel source code:

```C
typedef struct elf64_shdr {
	Elf64_Word sh_name;
	Elf64_Word sh_type;
	Elf64_Xword sh_flags;
	Elf64_Addr sh_addr;
	Elf64_Off sh_offset;
	Elf64_Xword sh_size;
	Elf64_Word sh_link;
	Elf64_Word sh_info;
	Elf64_Xword sh_addralign;
	Elf64_Xword sh_entsize;
} Elf64_Shdr;
```

**Program header table**

All sections are grouped into segments in an executable file or shared library. Program header table is an array of structures which describe every segment. It looks like:

```C
typedef struct elf64_phdr {
	Elf64_Word p_type;
	Elf64_Word p_flags;
	Elf64_Off p_offset;
	Elf64_Addr p_vaddr;
	Elf64_Addr p_paddr;
	Elf64_Xword p_filesz;
	Elf64_Xword p_memsz;
	Elf64_Xword p_align;
} Elf64_Phdr;
```

`elf64_phdr` structure defines in the same [elf.h](https://github.com/torvalds/linux/blob/master/include/uapi/linux/elf.h).

And ELF file also contains other fields/structures which you can find in the [Documentation](http://www.uclibc.org/docs/elf-64-gen.pdf). Now let's look on the `vmlinux`.

vmlinux
--------------------------------------------------------------------------------

`vmlinux` is an ELF file too. So we can look at it with the `readelf` util. First of all, let's look on the elf header of vmlinux:

```
$ readelf -h  vmlinux
ELF Header:
  Magic:   7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00 
  Class:                             ELF64
  Data:                              2's complement, little endian
  Version:                           1 (current)
  OS/ABI:                            UNIX - System V
  ABI Version:                       0
  Type:                              EXEC (Executable file)
  Machine:                           Advanced Micro Devices X86-64
  Version:                           0x1
  Entry point address:               0x1000000
  Start of program headers:          64 (bytes into file)
  Start of section headers:          381608416 (bytes into file)
  Flags:                             0x0
  Size of this header:               64 (bytes)
  Size of program headers:           56 (bytes)
  Number of program headers:         5
  Size of section headers:           64 (bytes)
  Number of section headers:         73
  Section header string table index: 70
```

Here we can see that `vmlinux` is 64-bit executable file.

We can read from the [Documentation/x86/x86_64/mm.txt](https://github.com/torvalds/linux/blob/master/Documentation/x86/x86_64/mm.txt):

```
ffffffff80000000 - ffffffffa0000000 (=512 MB)  kernel text mapping, from phys 0
```

So we can find it in the `vmlinux` with:

```
$ readelf -s vmlinux | grep ffffffff81000000
     1: ffffffff81000000     0 SECTION LOCAL  DEFAULT    1 
 65099: ffffffff81000000     0 NOTYPE  GLOBAL DEFAULT    1 _text
 90766: ffffffff81000000     0 NOTYPE  GLOBAL DEFAULT    1 startup_64
```

Note that ,the address of `startup_64` routine is not `ffffffff80000000`, but `ffffffff81000000`. Now I'll explain why.

We can see the following definition in the [arch/x86/kernel/vmlinux.lds.S](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/vmlinux.lds.S):

```
    . = __START_KERNEL;
	...
	...
	..
	/* Text and read-only data */
	.text :  AT(ADDR(.text) - LOAD_OFFSET) {
		_text = .;
		...
		...
		...
	}
```

Where `__START_KERNEL` is:

```
#define __START_KERNEL		(__START_KERNEL_map + __PHYSICAL_START)
```

`__START_KERNEL_map` is the value from documentation - `ffffffff80000000` and `__PHYSICAL_START` is `0x1000000`. That's why address of the `startup_64` is `ffffffff81000000`.

At last we can get program headers from `vmlinux` with the following command:

```

$ readelf -l vmlinux

Elf file type is EXEC (Executable file)
Entry point 0x1000000
There are 5 program headers, starting at offset 64

Program Headers:
  Type           Offset             VirtAddr           PhysAddr
                 FileSiz            MemSiz              Flags  Align
  LOAD           0x0000000000200000 0xffffffff81000000 0x0000000001000000
                 0x0000000000cfd000 0x0000000000cfd000  R E    200000
  LOAD           0x0000000001000000 0xffffffff81e00000 0x0000000001e00000
                 0x0000000000100000 0x0000000000100000  RW     200000
  LOAD           0x0000000001200000 0x0000000000000000 0x0000000001f00000
                 0x0000000000014d98 0x0000000000014d98  RW     200000
  LOAD           0x0000000001315000 0xffffffff81f15000 0x0000000001f15000
                 0x000000000011d000 0x0000000000279000  RWE    200000
  NOTE           0x0000000000b17284 0xffffffff81917284 0x0000000001917284
                 0x0000000000000024 0x0000000000000024         4

 Section to Segment mapping:
  Segment Sections...
   00     .text .notes __ex_table .rodata __bug_table .pci_fixup .builtin_fw
          .tracedata __ksymtab __ksymtab_gpl __kcrctab __kcrctab_gpl
		  __ksymtab_strings __param __modver 
   01     .data .vvar 
   02     .data..percpu 
   03     .init.text .init.data .x86_cpu_dev.init .altinstructions
          .altinstr_replacement .iommu_table .apicdrivers .exit.text
		  .smp_locks .data_nosave .bss .brk
```

Here we can see five segments with sections list. All of these sections you can find in the generated linker script at - `arch/x86/kernel/vmlinux.lds`.

That's all. Of course it's not a full description of ELF(Executable and	Linkable Format), but if you are interested in it, you can find documentation - [here](http://www.uclibc.org/docs/elf-64-gen.pdf)
