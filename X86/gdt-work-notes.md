# GDT chapter - working notes

Temporary handoff file from the session on 2026-11-27. Not part of the book, not in `SUMMARY.md`. Do not commit, delete when the GDT part is done.

Branch: `concepts/gdt`. Last commit: `c9f0d4c structure: move existing concepts to have room for GDT`. Everything below that line is uncommitted.

## Goal

Write a new part about the Global Descriptor Table as the first part of the `X86` chapter, covering every aspect of the GDT in the kernel with a clear structure.

## What was done and why

1. **Renumbered the X86 chapter** (committed in `c9f0d4c`). Order is now GDT = 1, IDT = 2, Paging = 3. Only Paging had to move: `X86/linux-x86-1.md` -> `X86/linux-x86-3.md`. `SUMMARY.md`, `X86/README.md` and the three gitbook links in `MM/linux-mm-2.md` and `MM/linux-mm-3.md` were updated.

2. **Started `X86/linux-x86-1.md`**. It holds the title plus the segmentation reference text from boot part 2, moved verbatim: `GDTR`/`lgdt`, descriptor layout, flags, both `Type` tables, segment selector, the three translation steps. The two figures `segment-descriptor.svg` and `segment-selector.svg` moved from `Booting/images` to `X86/images`. The part is linked from `SUMMARY.md` and `X86/README.md`.

3. **Boot part 2 lost all protected mode theory.** Reason: everything in part 2 runs in real mode and never uses a descriptor, the first real use is `setup_gdt` in part 3.
   - The bit-level descriptor reference went to the GDT part (step 2).
   - The rest of the "Protected mode" section went to boot part 3.
   - The introduction was rewritten by Alex, the `##` heading became "The main function", and it got a new two-paragraph opening (ordinary `main` vs. the setup code's `main`).
   - Part 2 is finished, no `TODO` left. About 3100 words now.

4. **Boot part 3 received two blocks from part 2**, both unchanged in wording:
   - a `## Protected mode` section, placed right before `## Entering protected mode`
   - the short segmentation text (`gdtr`/`lgdt`, selectors, translation steps), placed inside `### Set up the Global Descriptor Table`
   - the link "previous part" in that section was repointed to `../X86/linux-x86-1.md`

5. Later parts that mention the GDT (boot 3, 4, 5, initialization 1) stay as they are. Decision by Alex.

## Done: boot part 3 (2026-11-28)

All eight `TODO:` lines are resolved and removed, the changes are uncommitted.

- The `## Protected mode` section moved in front of `## Last preparation before transition into protected mode`. The end of the video mode section now announces it.
- "the previous part" in that section became "the first part", with a link to part 1.
- The section's last paragraph says only segmentation matters because the x86_64 kernel does not use paging in protected mode, and that segmentation comes "later in this part".
- In `### Set up the Global Descriptor Table`: the pointer to the GDT part is a `[!NOTE]` with the link text "dedicated part", the overlapping paragraph "Instead of fixed segment bases and limits..." is deleted.
- The selector paragraph defines `Index` in one sentence, no figure and no `TI`/`RPL` list.
- Translation steps: step 1 got "if it is not already there", step 2 says the CPU caches the descriptor, the term "hidden part" is not used in part 3.
- `setup_gdt` is introduced with "After this short reminder about segmentation, we can get back to the code."
- `## Entering protected mode` was renamed to `## Setting up the descriptor tables`, so it no longer reads like `## Transition into protected mode`. No links pointed at the old anchor.
- Full re-read after the changes: the paging sentence now says "when the kernel prepares the switch into 64-bit long mode", the register is `gdtr` in code font everywhere, the descriptor's properties are listed once.

## Later: boot part 4, after the GDT part is done

Checked on 2026-11-28, still correct, left as is by Alex's decision. Two places to revisit:

- Line 288 uses `CS.L = 1` and `CS.D = 0`. The `L` and `D` flags are defined only in the GDT part now, a link to `../X86/linux-x86-1.md` would cover it.
- Line 305 says "the hidden part of the segment registers". Part 3 no longer uses that term (it says the CPU caches the descriptor). The sentence explains itself, probably fine.

## Open: the GDT part itself

Proposed structure for `X86/linux-x86-1.md`. Alex has not confirmed it yet.

1. Introduction - why a flat-memory 64-bit kernel still needs a GDT
2. Segmentation basics - already in the file (moved from boot part 2)
3. What changes in long mode - base/limit ignored for `CS`/`DS`/`ES`/`SS`, `L`/`D`/`DPL` still count, `FS`/`GS` bases come from MSRs, system descriptors are 16 bytes, `GDTR` is 10 bytes
4. How the kernel represents it - `struct desc_struct`, `GDT_ENTRY_INIT`, `DESC_*` flags, `struct ldttss_desc`, `struct desc_ptr`, `GDT_ENTRY_*` and selectors in `segment.h`, `struct gdt_page`
5. The 64-bit GDT entry by entry - one table of all 16 slots, then:
   - code and data segments: mode and privilege
   - why this order: `MSR_STAR` and `syscall`/`sysret`
   - TSS descriptor
   - LDT descriptor
   - TLS entries
   - `CPUNODE` entry
6. One GDT per CPU, mapped twice - per-CPU `gdt_page`, read-only alias in `cpu_entry_area`, `load_direct_gdt()`/`load_fixmap_gdt()`, the `ltr` busy-bit switch in `native_load_tr_desc()`
7. The GDTs the kernel loads on the way up - REDUCED on 2026-11-28 to one or two sentences with links, see "Overlap with init-1" below. Research list kept for reference: `boot_gdt` (`arch/x86/boot/pm.c`), `gdt` and `gdt64` (`arch/x86/boot/compressed/head_64.S`), `startup_64_setup_gdt_idt()` and `.Lsetup_gdt` (`head_64.S`), `switch_gdt_and_percpu_base()`, `cpu_init_exception_handling()` ending in `load_fixmap_gdt()`, `tr_gdt` for secondary CPUs (`arch/x86/realmode/rm/trampoline_64.S`)
8. Who touches the GDT at runtime - interrupt delivery and `iret`, context switch (`load_TLS()`, LDT reload), KVM after VM exit with `invalidate_tss_limit()`/`force_reload_TR()`, suspend/resume (`fix_processor_context()` in `arch/x86/power/cpu.c`), FRED
9. Conclusion and Links

If the file gets too long, the natural cut is after section 5.

### Source references checked in the local tree

Local tree `/home/alex/disk/dev/linux` was at `v7.4-rc4`. Line numbers must be rechecked against GitHub `master` when annotating snippets.

| What | Where |
| --- | --- |
| GDT indices and selectors, `SYSRET` layout comment | `arch/x86/include/asm/segment.h` ~169-225 |
| `vdso_read_cpunode()` with `lsl` / `rdpid` | `arch/x86/include/asm/segment.h` ~245 |
| `gdt_page` definition | `arch/x86/kernel/cpu/common.c:211` |
| `load_direct_gdt()` / `load_fixmap_gdt()` | `arch/x86/kernel/cpu/common.c:760`, `:771` |
| `switch_gdt_and_percpu_base()` | `arch/x86/kernel/cpu/common.c:790` |
| `syscall_init()`, `MSR_STAR` | `arch/x86/kernel/cpu/common.c:2306` |
| `setup_getcpu()` | `arch/x86/kernel/cpu/common.c:2358` |
| `cpu_init_exception_handling()` | `arch/x86/kernel/cpu/common.c:2414` |
| `struct desc_struct`, `GDT_ENTRY_INIT`, `struct ldttss_desc`, `struct desc_ptr` | `arch/x86/include/asm/desc_defs.h` |
| `struct gdt_page`, `get_cpu_gdt_rw()`, `get_cpu_gdt_ro()` | `arch/x86/include/asm/desc.h:44-71` |
| `native_set_ldt()` | `arch/x86/include/asm/desc.h:192` |
| `native_load_tr_desc()` | `arch/x86/include/asm/desc.h:254` |
| `native_load_tls()` | `arch/x86/include/asm/desc.h:292` |
| `force_reload_TR()`, `invalidate_tss_limit()` | `arch/x86/include/asm/desc.h:303`, `:343` |
| Read-only GDT mapping | `arch/x86/mm/cpu_entry_area.c:181-199` |
| `INTG` gate with `__KERNEL_CS` | `arch/x86/kernel/idt.c:33` |
| `pt_regs` frame built with `__USER_DS` / `__USER_CS` | `arch/x86/entry/entry_64.S:101` |
| `LOAD_CPU_AND_NODE_SEG_LIMIT` | `arch/x86/entry/calling.h:401` |
| FRED loads `SS` with `__KERNEL_DS` | `arch/x86/kernel/fred.c:42` |
| KVM restores GDT after VM exit | `arch/x86/kvm/vmx/vmx.c:1439-1443` |
| Suspend/resume | `arch/x86/power/cpu.c:95-186` |

Slot table facts: slot 0 is null, slot 7 is unused, TSS takes slots 8-9, LDT takes 10-11, TLS is 12-14, `CPUNODE` is 15, `GDT_ENTRIES` is 16.

### Claims from the original notes not confirmed from source

- GDT limit becomes `0xffff` after VM exit - needs an SDM reference, the code only shows KVM calling `load_fixmap_gdt()` and `invalidate_tss_limit()`.
- Wine and DOSEMU still use `modify_ldt()`.
- The paranoid entry path uses the `CPUNODE` lookup only when FSGSBASE is on - the `lsl` macro exists, its callers were not read.

### Overlap with init-1 - decided 2026-11-28

`Initialization/linux-initialization-1.md`, section "Setup of the kernel GDT", already lists the six code/data entries and quotes `gdt_page`. Decision by Alex: it stays as is, in general. The GDT part describes the GDT on its own and in general, not how the kernel sets it up at a concrete stage.

Consequence for section 7 of the proposed structure ("The GDTs the kernel loads on the way up"), decided by Alex on 2026-11-28: no per-stage timeline. The GDT part only mentions, in one sentence or a couple, that the kernel loads temporary tables during boot, with links to boot parts 3, 4, 5 and initialization part 1.
