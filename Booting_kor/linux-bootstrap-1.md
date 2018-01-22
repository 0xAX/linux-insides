커널 부팅 과정. Part 1
================================================================================

부트로더부터 커널까지
--------------------------------------------------------------------------------

내 전 블로그를 보았다면 [blog posts](https://0xax.github.io/categories/assembler/) 알겠지만, low-level programming에 뛰어들기 시작했다. `x86_64` Linux 어셈블리 프로그래밍에 대한 포스트를 쓰기 시작했고 동시에, 리눅스 커널 소스코드를 파보기로 결심했다.

나는 low-level이 어떻게 동작하는지, 프로그램이 내컴퓨터에서 어떻게 돌아가고 메모리에 적재되는지, 커널이 메모리를 어떻게 관리하는지, 네트워크스택이 low-level에서 어떻게 작동하는지 외에 많은것들에대해 관심을 가지고 있다. 그래서 **x86_64** 리눅스 커널에대해 포스트를 작성하기로 마음먹었다.

참고로 나는 프로 커널해커도 아니며 직업으로 커널코드를 작성하는 사람도 아니다. 그저 취미일 뿐이며, low-level 한것들과 이것의 동작방식에 대해 관심이 있을 뿐이다. 따라서 뭔가 이상하거나 질문이 있다면 Twitter [0xAX](https://twitter.com/0xAX), [email](anotherworldofworld@gmail.com)을 통해 연락하거나 github issue[issue](https://github.com/0xAX/linux-insides/issues/new)를 작성해주면 감사하겠다.

모든 포스트는 [github repo](https://github.com/0xAX/linux-insides) 에서 볼 수 있고, 이상한 점을 발견한다면 pull request를 날려주길 바란다.

*이 문서는 공식 문서가 아니며 그저 지식공유의 목적임을 밝힌다*

**필요 지식**

* C언어에 대한 이해
* AT&T 문법의 assembly언어의 이해

만약 이러한 도구들을 이제 막배우기 시작했다면, 포스트내에서 이것에대해 설명해 보도록 할것이다. 자, 이제 간단한 서두를 끝내고 리눅스 커널과 low-level의 세계로 빠져보자.

이 책은 `3.18` 리눅스 커널을 기반으로 작성되었다. 시간이지나 많은 변경이 생겼을 것이다. 만약 변경이 있다면 이 포스트를 업데이트 할것이다.

마법의 전원 버튼. 그 다음은?
--------------------------------------------------------------------------------

물론 이포스트는 리눅스 커널에 관한 것이지만, 이문단부터 바로 커널코드에 대해 시작하지는 않을 것이다. 네가 노트북 이나 PC의 전원버튼을 누르자마자, 컴퓨터는 동작하기 시작한다. 메인보드는 [power supply](https://en.wikipedia.org/wiki/Power_supply)로 신호를 보낸다. 파워가 신호를 받으면 적정량의 전기를 컴퓨터에 보내게 된다. 메인보드가 [power good signal](https://en.wikipedia.org/wiki/Power_good_signal)을 받으면 CPU를 시작시키고 CPU는 레지스터를 초기화한 뒤, 초기값들을 입력한다.

[80386](https://en.wikipedia.org/wiki/Intel_80386) CPU와 그후 모델들은 컴퓨터가 리셋된 뒤 다음처럼 미리 정의된 값들을 레지스터에 입력한다.

```
IP          0xfff0
CS selector 0xf000
CS base     0xffff0000
```

CPU는 [real mode](https://en.wikipedia.org/wiki/Real_mode)에서 동작하기 시작한다. 이 모드의 [memory segmentation](https://en.wikipedia.org/wiki/Memory_segmentation)에 대해서 설명을 하자면, Real-mode는 [8086](https://en.wikipedia.org/wiki/Intel_8086) CPU부터 현대의 Intel 64-bit CPU들까지 모든 x86-호환 프로세서에서 지원된다. `8086`CPU는 20-bit address-bus를 가지고 있다. 즉, 2^20만큼의 주소, `0xFFFFF` 또는 `1 MB`만큼의 주소공간을 가지고 있다. 하지만 레지스터는 `16-bit` 레지스터를 사용한다. 즉, 2^16 만큼의 주소, `0xffff` 또는 `64 KB`만큼의 주소공간을 가진다.

[Memory segmentation](http://en.wikipedia.org/wiki/Memory_segmentation)은 모든 주소공간을 접근하기위해 사용된다. 모든 메모리는 고정 64KB 세그멘트로 나누어진다. 이때 64KB이상의 주소는 접근 할 수 없으므로 대안이 발명되었다.

주소는 두가지 파트로 구성된다: Base주소를 갖고있는 segment selector, 그리고 이 베이스주소로 부터 떨어저있는 offset. Real mode에서는 segment selector가 갖고있는 base addresss를 `Segment Selector * 16`으로 계산한다. 따라서 메모리의 물리주소는 segment selector에 `16`을 곱한뒤 offset을 더해서 구한다:

```
PhysicalAddress = Segment Selector * 16 + Offset
```

예를들어, 만약 `CS:IP`가 `0x2000:0x0010`이라면, 상응하는 물리주소는 다음과 같다:

```python
>>> hex((0x2000 << 4) + 0x0010)
'0x20010'
```

하지만 우리가 최대 segement selector와 offset을 취한다면 `0xffff:0xffff`, 결과는 다음과 같다:

```python
>>> hex((0xffff << 4) + 0xffff)
'0x10ffef'
```

이는 1 MB에서 `65520` byte만큼 더 큰 값이다. Real mode 에서는 1 MB만 접근 가능하므로, [A20 line](https://en.wikipedia.org/wiki/A20_line)이 비활성화 된 상태에서 `0x10ffef`는 `0x00ffef`가 된다.

자 이제 real mode에서 메모리 주소처리 방식에대해 조금 알게되었으니 다시 리셋 이후의 레지스터 값으로 돌아가보자.

`CS`레지스터는 두 파트로 구성되어 있다: 보이는 segment selector, 그리고 숨겨진 base address. 보통 base address는 segment selector값에 16을 곱해 얻어진다. 하지만 하드웨어 리셋 후 CS register의 segment selector에는 `0xf000`값이 들어가고 base address에는 `0xffff0000`값이 들어간다; 프로세서는 `CS`값이 바뀌기 전까지 이 특별한 base address를 사용한다.

시작 주소는 base address에 EIP레지스터의 값을 더하는 것으로 구해진다:

```python
>>> 0xffff0000 + 0xfff0
'0xfffffff0'
```

`0xfffffff0`은 4GB에서 16 byte만큼 밑에있다. 이 지점은 [Reset vector](http://en.wikipedia.org/wiki/Reset_vector)라고 불린다. 이 지점은 CPU가 리셋된 뒤에 첫 명령어를 찾는 곳이다. 보통 BIOS entry point를 가리키는 [jump](http://en.wikipedia.org/wiki/JMP_%28x86_instruction%29) (`jmp`) 명령어로 되어있다. 예를 들어, [coreboot](http://www.coreboot.org/)소스 코드(`src/cpu/x86/16bit/reset16.inc`)는 이렇게 되어있다:

```assembly
    .section ".reset"
    .code16
.globl  reset_vector
reset_vector:
    .byte  0xe9
    .int   _start - ( . + 2 )
    ...
```

여기서 우리는 `0xe9`인 `jmp`명령어 [opcode](http://ref.x86asm.net/coder32.html#xE9)와 도착 주소 `_start - ( . + 2 )`를 볼 수 있다. 

또한 우리는 `reset` 섹션이 `16` byte로 이루어져 있고 시작주소가 `0xfffffff0`으로 컴파일 된 것을 알 수 있다 (`src/cpu/x86/16bit/reset16.lds`).

```
SECTIONS {
    _ROMTOP = 0xfffffff0;
    . = _ROMTOP;
    .reset . : {
        *(.reset)
        . = 15 ;
        BYTE(0x00);
    }
}
```

이제 BIOS가 시작한다: 하드웨어를 초기화하고 체크한뒤, BIOS는 부팅 가능한 장치를 찾아야한다. 어떤 장치를 BIOS가 부팅 시도할지 부트 순서는 BIOS설정에 저장되어 있다. 하드디스크에 부팅시도를 할 때 BIOS는 boot sector를 찾으려고 한다. [MBR partition layout](https://en.wikipedia.org/wiki/Master_boot_record)로 파티션 되어있는 하드디스크에는, 한섹터가 512byte인 첫 섹터의 첫446byte에 boot sector가 있다. 마지막 두바이트는 `0x55`, `0xaa`로 이를통해 BIOS에게 이장비가 부팅가능하다고 알려준다.

예를들어:

```assembly
;
; Note: this example is written in Intel Assembly syntax
;
[BITS 16]

boot:
    mov al, '!'
    mov ah, 0x0e
    mov bh, 0x00
    mov bl, 0x07

    int 0x10
    jmp $

times 510-($-$$) db 0

db 0x55
db 0xaa
```

이 어셈블리를 다음명령어로 빌드해 보아라:

```
nasm -f bin boot.nasm && qemu-system-x86_64 boot
```

[QEMU](http://qemu.org)는 우리가 빌드한 `boot` binary를 disk image로 사용할 것이다. 위 어셈블리 코드로 빌드한 이미지는 boot sector의 요구사항(origin이 `0x7c00`으로 세팅되어있고 마지막이 0x55, 0xaa로 끝나는 것)을 만족하므로, QEMU는 바이너리를 disk image의 master boot record(MBR)로 인식할 것이다.

다음 예를 보자:

![`!`를 프린트하는 간단한 부트로더](http://oi60.tinypic.com/2qbwup0.jpg)

이 예제애서, 우리는 코드가 `16-bit` real mode에서 실행되고 `0x7c00`주소에서 시작하는 것을 볼 수 있다. 그후 [0x10](http://www.ctyme.com/intr/rb-0106.htm) 인터럽트를 통해 `!`를 출력한다; 나머지 510 byte는 0으로 채워져있고 마지막 두 magic byte `0xaa`, `0x55`로 마무리 된다.

binary dump는 `objdump` utility를 통해 볼 수 있다:

```
nasm -f bin boot.nasm
objdump -D -b binary -mi386 -Maddr16,data16,intel boot
```

실제 boot sector는 0으로채워지고 느낌표를 출력하는 대신 부팅과정 코드와 partition table로 이루어져 있다 :) 이후로부터, BIOS는 부트로더에게 제어를 넘겨준다.

**참고**: 위에 설명되어있듯이, CPU는 real mode에 있다; real mode에서는 메모리의 물리주소 계산법이 다음과 같이 이루어 진다.

```
PhysicalAddress = Segment Selector * 16 + Offset
```

Real mode에서는 오직 16-bit 범용 레지스터만 갖고있다; 16-bit 레지스터의 최대값은 `0xffff`이다, 따라서 우리가 최대 주소를 대입한다면 결과는 다음과 같다.

```python
>>> hex((0xffff * 16) + 0xffff)
'0x10ffef'
```

`0x10ffef` 는 `1MB + 64KB - 16byte`이다. [8086](https://en.wikipedia.org/wiki/Intel_8086) 프로세서는 (real mode를 탑재한 첫 프로세서), 반대로, 20-bit 주소를 사용한다. `2^20 = 1048576` 는 1MB이므로, 실제 사용가능한 메모리 주소는 1MB라는 뜻이 된다.

보통, real mode의 memory map은 다음과 같다:

```
0x00000000 - 0x000003FF - Real Mode Interrupt Vector Table
0x00000400 - 0x000004FF - BIOS Data Area
0x00000500 - 0x00007BFF - Unused
0x00007C00 - 0x00007DFF - Our Bootloader
0x00007E00 - 0x0009FFFF - Unused
0x000A0000 - 0x000BFFFF - Video RAM (VRAM) Memory
0x000B0000 - 0x000B7777 - Monochrome Video Memory
0x000B8000 - 0x000BFFFF - Color Video Memory
0x000C0000 - 0x000C7FFF - Video ROM BIOS
0x000C8000 - 0x000EFFFF - BIOS Shadow Area
0x000F0000 - 0x000FFFFF - System BIOS
```

이 포스트의 시작점에서, 나는 CPU의 첫 명령어가 `0xFFFFFFF0`에 위치한다고 했었다, 이 주소는 `0xFFFFF` (1MB)보다 큰값이다. 어떻게 CPU가 real mode에서 이 주소에 접근할 수 있을까? 정답은 [coreboot](http://www.coreboot.org/Developer_Manual/Memory_map) 문서에 있다:

```
0xFFFE_0000 - 0xFFFF_FFFF: 128 kilobyte ROM mapped into address space
```

실행이 시작할 때, BIOS는 RAM에 있지않다, ROM에 위치해 있는 것이다.

부트로더
--------------------------------------------------------------------------------

[GRUB 2](https://www.gnu.org/software/grub/) 이나 [syslinux](http://www.syslinux.org/wiki/index.php/The_Syslinux_Project)처럼 Linux를 부트할 수 있는 부트로더는 많다. Linux 커널은 [Boot protocol](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/Documentation/x86/boot.txt) 요구사항을 명시해 부트로더가 Linux support를 구현할 수 있게했다. 다음 예시는 GRUB 2를 설명할 것이다. 

이전과 이어서, 이제 `BIOS`는 boot 장비를 선택했고 boot sector code로 제어를 넘겼다, 실행은 [boot.img](http://git.savannah.gnu.org/gitweb/?p=grub.git;a=blob;f=grub-core/boot/i386/pc/boot.S;hb=HEAD) 에서 시작한다. 이 코드는 제한된 메모리 공간때문에 간단하며, GRUB 2의 core image로 점프할 포인터를 갖고있다. 코어이미지는 [diskboot.img](http://git.savannah.gnu.org/gitweb/?p=grub.git;a=blob;f=grub-core/boot/i386/pc/diskboot.S;hb=HEAD)로 시작하며, 보통 첫 sector의 바로 다음이나 첫 partition의 사용되지 않은 공간에 저장되어 있다. 나머지 core image를 메모리에 올린 뒤에, [grub_main](http://git.savannah.gnu.org/gitweb/?p=grub.git;a=blob;f=grub-core/kern/main.c) 함수를 실행시킨다.

`grub_main` 함수는 콘솔을 초기화하고, module들의 base address를 구하고, root device를 세팅하고 grub 설정을 불러오고, module를 로딩하는 등의 작업을 한다. 실행의 마지막 부분에서 `grub_main` 함수는 grub을 normal mode(CPU의 모드와 무관)로 옮긴다. `grub_normal_execute` (`grub-core/normal/main.c`) 함수는 마지막 준비를 끝내고 OS선택 메뉴를 보여준다. 우리가 grub menu entry중 하나를 선택하면, `grub_menu_execute_entry` 함수가 grub `boot`명령어를 실행해 선택된 OS를 부팅한다.

Kernal boot protocol을 읽어보면, 부트로더는 커널 setup code의 `0x01f1` offset에 위치한 kernal setup header를 읽고 채워야 한다. [linker script](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/setup.ld#L16) 를 보면 오프셋값을 확인할 수 있다. 커널 헤더 [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/header.S) 는 다음과 같이 시작한다:

```assembly
    .globl hdr
hdr:
    setup_sects: .byte 0
    root_flags:  .word ROOT_RDONLY
    syssize:     .long 0
    ram_size:    .word 0
    vid_mode:    .word SVGA_MODE
    root_dev:    .word 0
    boot_flag:   .word 0xAA55
```

부트로더는 이 부분과 나머지 헤더(Linux boot protocol이 [예제](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/Documentation/x86/boot.txt#L354)에서 처럼 `write` type으로 마크돼있다.)를 커맨드라인에서 받거나 부트과정에서 계산된 값으로 채워야 한다. 우리는 지금 kernel setup header의 각필드를 모두 설명하지는 않을 것 이다. 다만 커널이 그 값들을 어떻게 쓰는지 알아볼 때 설명할 것이다;  [Boot protocol](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/Documentation/x86/boot.txt#L156) 필드에 대한 모든설명은 링크에서 찾아볼 수 있다.

Kernel boot protocol에서 볼 수 있듯이, 커널을 로드하고 나면 메모리는 다음과 같이 매핑된다.

```shell
         | Protected-mode kernel  |
100000   +------------------------+
         | I/O memory hole        |
0A0000   +------------------------+
         | Reserved for BIOS      | Leave as much as possible unused
         ~                        ~
         | Command line           | (Can also be below the X+10000 mark)
X+10000  +------------------------+
         | Stack/heap             | For use by the kernel real-mode code.
X+08000  +------------------------+
         | Kernel setup           | The kernel real-mode code.
         | Kernel boot sector     | The kernel legacy boot sector.
       X +------------------------+
         | Boot loader            | <- Boot sector entry point 0x7C00
001000   +------------------------+
         | Reserved for MBR/BIOS  |
000800   +------------------------+
         | Typically used by MBR  |
000600   +------------------------+
         | BIOS use only          |
000000   +------------------------+

```

따라서 부트로더가 커널에게 제어를 넘길때, 다음 주소에서 시작된다:

```
X + sizeof(KernelBootSector) + 1
```

`X`는 커널 부트섹터가 로드된 장소이다. 나의경우엔 memory dump에서 볼 수 있듯이 `X`는 `0x10000`이다:

![커널 첫 주소](http://oi57.tinypic.com/16bkco2.jpg)

부트로더는 이제 Linux커널을 메모리에 로드했고, 헤더필드를 채웠고, 상응하는 주소(`X + sizeof(KernelBootSector) + 1`)로 점프했다. 이제 우린 바로 커널 setup code를 살펴볼 것이다.

Kernel Setup 단계의 시작
--------------------------------------------------------------------------------

드디어 우린 커널로 입성했다! 엄밀히 말하면, 커널은 아직 실행되지 않았다; 일단 커널 setup 단계는 압축해제나 메모리 관리와 관련된 것들을 설정해야한다. 그런 작업을 모두 마치고 나면, 커널 setup 단계는 진짜 커널을 압축 해제하고 그곳으로 점프한다. 커널 setup 단계는 [arch/x86/boot/header.S](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/header.S) 의 [\_start](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/header.S#L292)에서 실행을 시작한다. 처음보는 명령어 때문에 당황할 수 있다.

옛날에는, Linux커널이 자체 부트로더를 사용했었다. 하지만 예를들어, 현재 다음 명령어를 실행시키면:

```
qemu-system-x86_64 vmlinuz-3.18-generic
```

다음을 보게된다.:

![Try vmlinuz in qemu](http://oi60.tinypic.com/r02xkz.jpg)

사실 `header.S`파일은 magic number [MZ](https://en.wikipedia.org/wiki/DOS_MZ_executable)(위 이미지를 보라), 에러메세지, 그다음 [PE](https://en.wikipedia.org/wiki/Portable_Executable) 헤더로 시작한다:

```assembly
#ifdef CONFIG_EFI_STUB
# "MZ", MS-DOS header
.byte 0x4d
.byte 0x5a
#endif
...
...
...
pe_header:
    .ascii "PE"
    .word 0
```

이렇게 운영체제를 로드할때는 [UEFI](https://en.wikipedia.org/wiki/Unified_Extensible_Firmware_Interface)지원이 필요하다. 우린 지금 이 내부작업은 살펴보지 않을것이고, 다음 추후 챕터에서 살펴볼 예정이다.

실제 커널 setup 진입점은 다음과 같다.

```assembly
// header.S line 292
.globl _start
_start:
```

부트로더(grub2나 다른것들)는 `header.S`가 에러메세지를 출력하는 `.bstext`섹션부터 시작하지만 진입점(`MZ`로부터 `0x200`오프셋 만큼)을 알고있고 바로 점프한다.

```
//
// arch/x86/boot/setup.ld
//
. = 0;                    // current position
.bstext : { *(.bstext) }  // put .bstext section to position 0
.bsdata : { *(.bsdata) }
```

The kernel setup entry point is:

```assembly
    .globl _start
_start:
    .byte  0xeb
    .byte  start_of_setup-1f
1:
    //
    // rest of the header
    //
```

Here we can see a `jmp` instruction opcode (`0xeb`) that jumps to the `start_of_setup-1f` point. In `Nf` notation, `2f`, for example, refers to the local label `2:`; in our case, it is the label `1` that is present right after the jump, and it contains the rest of the setup [header](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/Documentation/x86/boot.txt#L156). Right after the setup header, we see the `.entrytext` section, which starts at the `start_of_setup` label.

This is the first code that actually runs (aside from the previous jump instructions, of course). After the kernel setup part receives control from the bootloader, the first `jmp` instruction is located at the `0x200` offset from the start of the kernel real mode, i.e., after the first 512 bytes. This can be seen in both the Linux kernel boot protocol and the grub2 source code:

```C
segment = grub_linux_real_target >> 4;
state.gs = state.fs = state.es = state.ds = state.ss = segment;
state.cs = segment + 0x20;
```

This means that segment registers will have the following values after kernel setup starts:

```
gs = fs = es = ds = ss = 0x10000
cs = 0x10200
```

In my case, the kernel is loaded at `0x10000` address.

After the jump to `start_of_setup`, the kernel needs to do the following:

* Make sure that all segment register values are equal
* Set up a correct stack, if needed
* Set up [bss](https://en.wikipedia.org/wiki/.bss)
* Jump to the C code in [main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/main.c)

Let's look at the implementation.

Aligning the Segment Registers 
--------------------------------------------------------------------------------

First of all, the kernel ensures that the `ds` and `es` segment registers point to the same address. Next, it clears the direction flag using the `cld` instruction:

```assembly
    movw    %ds, %ax
    movw    %ax, %es
    cld
```

As I wrote earlier, `grub2` loads kernel setup code at address `0x10000` by default and `cs` at `0x10200` because execution doesn't start from the start of file, but from the jump here:

```assembly
_start:
    .byte 0xeb
    .byte start_of_setup-1f
```

which is at a `512` byte offset from [4d 5a](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/header.S#L46). We also need to align `cs` from `0x10200` to `0x10000`, as well as all other segment registers. After that, we set up the stack:

```assembly
    pushw   %ds
    pushw   $6f
    lretw
```

which pushes the value of `ds` to the stack, followed by the address of the [6](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/header.S#L494) label and executes the `lretw` instruction. When the `lretw` instruction is called, it loads the address of label `6` into the [instruction pointer](https://en.wikipedia.org/wiki/Program_counter) register and loads `cs` with the value of `ds`. Afterward, `ds` and `cs` will have the same values.

Stack Setup
--------------------------------------------------------------------------------

Almost all of the setup code is in preparation for the C language environment in real mode. The next [step](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/header.S#L569) is checking the `ss` register value and making a correct stack if `ss` is wrong:

```assembly
    movw    %ss, %dx
    cmpw    %ax, %dx
    movw    %sp, %dx
    je      2f
```

This can lead to 3 different scenarios:

* `ss` has a valid value `0x1000` (as do all the other segment registers beside `cs`)
* `ss` is invalid and the `CAN_USE_HEAP` flag is set     (see below)
* `ss` is invalid and the `CAN_USE_HEAP` flag is not set (see below)

Let's look at all three of these scenarios in turn:

* `ss` has a correct address (`0x1000`). In this case, we go to label [2](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/header.S#L584):

```assembly
2:  andw    $~3, %dx
    jnz     3f
    movw    $0xfffc, %dx
3:  movw    %ax, %ss
    movzwl  %dx, %esp
    sti
```

Here we set the alignment of `dx` (which contains the value of `sp` as given by the bootloader) to `4` bytes and a check for whether or not it is zero. If it is zero, we put `0xfffc` (4 byte aligned address before the maximum segment size of 64 KB) in `dx`. If it is not zero, we continue to use the value of `sp` given by the bootloader (0xf7f4 in my case). After this, we put the value of `ax` into `ss`, which stores the correct segment address of `0x1000` and sets up a correct `sp`. We now have a correct stack:

![stack](http://oi58.tinypic.com/16iwcis.jpg)

* In the second scenario, (`ss` != `ds`). First, we put the value of [\_end](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/setup.ld#L52) (the address of the end of the setup code) into `dx` and check the `loadflags` header field using the `testb` instruction to see whether we can use the heap. [loadflags](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/header.S#L321) is a bitmask header which is defined as:

```C
#define LOADED_HIGH     (1<<0)
#define QUIET_FLAG      (1<<5)
#define KEEP_SEGMENTS   (1<<6)
#define CAN_USE_HEAP    (1<<7)
```

and, as we can read in the boot protocol:

```
Field name: loadflags

  This field is a bitmask.

  Bit 7 (write): CAN_USE_HEAP
    Set this bit to 1 to indicate that the value entered in the
    heap_end_ptr is valid.  If this field is clear, some setup code
    functionality will be disabled.
```

If the `CAN_USE_HEAP` bit is set, we put `heap_end_ptr` into `dx` (which points to `_end`) and add `STACK_SIZE` (minimum stack size, `1024` bytes) to it. After this, if `dx` is not carried (it will not be carried, `dx = _end + 1024`), jump to label `2` (as in the previous case) and make a correct stack.

![stack](http://oi62.tinypic.com/dr7b5w.jpg)

* When `CAN_USE_HEAP` is not set, we just use a minimal stack from `_end` to `_end + STACK_SIZE`:

![minimal stack](http://oi60.tinypic.com/28w051y.jpg)

BSS Setup
--------------------------------------------------------------------------------

The last two steps that need to happen before we can jump to the main C code are setting up the [BSS](https://en.wikipedia.org/wiki/.bss) area and checking the "magic" signature. First, signature checking:

```assembly
    cmpl    $0x5a5aaa55, setup_sig
    jne     setup_bad
```

This simply compares the [setup_sig](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/setup.ld#L39) with the magic number `0x5a5aaa55`. If they are not equal, a fatal error is reported.

If the magic number matches, knowing we have a set of correct segment registers and a stack, we only need to set up the BSS section before jumping into the C code.

The BSS section is used to store statically allocated, uninitialized data. Linux carefully ensures this area of memory is first zeroed using the following code:

```assembly
    movw    $__bss_start, %di
    movw    $_end+3, %cx
    xorl    %eax, %eax
    subw    %di, %cx
    shrw    $2, %cx
    rep; stosl
```

First, the [__bss_start](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/setup.ld#L47) address is moved into `di`. Next, the `_end + 3` address (+3 - aligns to 4 bytes) is moved into `cx`. The `eax` register is cleared (using a `xor` instruction), and the bss section size (`cx`-`di`) is calculated and put into `cx`. Then, `cx` is divided by four (the size of a 'word'), and the `stosl` instruction is used repeatedly, storing the value of `eax` (zero) into the address pointed to by `di`, automatically increasing `di` by four, repeating until `cx` reaches zero). The net effect of this code is that zeros are written through all words in memory from `__bss_start` to `_end`:

![bss](http://oi59.tinypic.com/29m2eyr.jpg)

Jump to main
--------------------------------------------------------------------------------

That's all - we have the stack and BSS, so we can jump to the `main()` C function:

```assembly
    calll main
```

The `main()` function is located in [arch/x86/boot/main.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/arch/x86/boot/main.c). You can read about what this does in the next part.

Conclusion
--------------------------------------------------------------------------------

This is the end of the first part about Linux kernel insides. If you have questions or suggestions, ping me on Twitter [0xAX](https://twitter.com/0xAX), drop me an [email](anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-internals/issues/new). In the next part, we will see the first C code that executes in the Linux kernel setup, the implementation of memory routines such as `memset`, `memcpy`, `earlyprintk`, early console implementation and initialization, and much more.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-internals).**

Links
--------------------------------------------------------------------------------

  * [Intel 80386 programmer's reference manual 1986](http://css.csail.mit.edu/6.858/2014/readings/i386.pdf)
  * [Minimal Boot Loader for Intel® Architecture](https://www.cs.cmu.edu/~410/doc/minimal_boot.pdf)
  * [8086](http://en.wikipedia.org/wiki/Intel_8086)
  * [80386](http://en.wikipedia.org/wiki/Intel_80386)
  * [Reset vector](http://en.wikipedia.org/wiki/Reset_vector)
  * [Real mode](http://en.wikipedia.org/wiki/Real_mode)
  * [Linux kernel boot protocol](https://www.kernel.org/doc/Documentation/x86/boot.txt)
  * [CoreBoot developer manual](http://www.coreboot.org/Developer_Manual)
  * [Ralf Brown's Interrupt List](http://www.ctyme.com/intr/int.htm)
  * [Power supply](http://en.wikipedia.org/wiki/Power_supply)
  * [Power good signal](http://en.wikipedia.org/wiki/Power_good_signal)
