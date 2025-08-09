How does the `open` system call work
--------------------------------------------------------------------------------

Introduction
--------------------------------------------------------------------------------

This is the fifth part of the chapter that describes [system calls](https://en.wikipedia.org/wiki/System_call) mechanism in the Linux kernel. Previous parts of this chapter described the mechanism of system calls in general. I will now try to describe the implementation of different system calls in the Linux kernel. Previous parts from this chapter and parts of other chapters of the book mostly described deep parts of the Linux kernel that are barely visible or  invisible from userspace. However, the greatness of the Linux kernel is not its singular existence, but its ability to enable our code to perform various useful functions such as reading/writing from/to files without the knowledge of details such as sectors, tracks and other nitty gritties of the disk layout. For eg., the kernel allows programs to send data over networks without our having to encapsulate network packets by hand etc.

I don't know how about you, but the inner workings of the operating system both fascinate and excite my curiosity greatly. As you may know, our programs interact with the kernel through a special mechanism called [system call](https://en.wikipedia.org/wiki/System_call). I will hence attempt to describe the implementation and behavior of system calls such as `read`, `write`, `open`, `close`, `dup` etc. in a series of articles.

Let me start with the description of the simplest (and commonly used) [open](http://man7.org/linux/man-pages/man2/open.2.html) system call. if you have done any `C` programming at all, you should know that a file must be opened using the `open` system call before we are able to read/write to it.

```C
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>

int main(int argc, char *argv) {
        int fd = open("test", O_RDONLY);

        if fd < 0 {
                perror("Opening of the file is failed\n");
        }
        else {
                printf("file successfully opened\n");
        }

        close(fd);
        return 0;
}
```

In this case, `open` is a function from standard library, but not the system call. The standard library will call the related system call for us. The `open` call will return a [file descriptor](https://en.wikipedia.org/wiki/File_descriptor) which is just a unique number within our process which is associated with the opened file. Now as we opened a file and got file descriptor as result of `open` call, we may start to interact with this file. We can write into, read from it and etc. List of opened file by a process is available via [proc](https://en.wikipedia.org/wiki/Procfs) filesystem: 

```
$ sudo ls /proc/1/fd/

0  10  12  14  16  2   21  23  25  27  29  30  32  34  36  38  4   41  43  45  47  49  50  53  55  58  6   61  63  67  8
1  11  13  15  19  20  22  24  26  28  3   31  33  35  37  39  40  42  44  46  48  5   51  54  57  59  60  62  65  7   9
```

I am not going to describe more details about the `open` routine from the userspace view in this post, but mostly from the kernel side. If you are not very familiar with, you can get more info in the [man page](http://man7.org/linux/man-pages/man2/open.2.html).

So let's start.

Definition of the open system call
--------------------------------------------------------------------------------

If you have read the [fourth part](https://github.com/0xAX/linux-insides/blob/master/SysCall/linux-syscall-4.md) of the [linux-insides](https://github.com/0xAX/linux-insides/blob/master/SUMMARY.md) book, you should know that system calls are defined with the help of `SYSCALL_DEFINE` macro. So, the `open` system call is no exception.

Definition of the `open` system call is located in the [fs/open.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/open.c) source code file and looks pretty small for the first view:

```C
SYSCALL_DEFINE3(open, const char __user *, filename, int, flags, umode_t, mode)
{
	if (force_o_largefile())
		flags |= O_LARGEFILE;

	return do_sys_open(AT_FDCWD, filename, flags, mode);
}
```

As you may guess, the `do_sys_open` function from the [same](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/open.c) source code file does the main job. But before this function is called, let's consider the `if` clause from which the implementation of the `open` system call starts:

```C
if (force_o_largefile())
	flags |= O_LARGEFILE;
```

Here we apply the `O_LARGEFILE` flag to the flags which were passed to `open` system call in a case when the `force_o_largefile()` will return true.
What is `O_LARGEFILE`? We may read this in the [man page](http://man7.org/linux/man-pages/man2/open.2.html) for the `open(2)` system call:

> O_LARGEFILE
>
> (LFS) Allow files whose sizes cannot be represented in an off_t (but can be represented in an off64_t) to be opened.

As we may read in the [GNU C Library Reference Manual](https://www.gnu.org/software/libc/manual/html_mono/libc.html#File-Position-Primitive):

> off_t
>
>    This is a signed integer type used to represent file sizes.
>    In the GNU C Library, this type is no narrower than int.
>    If the source is compiled with _FILE_OFFSET_BITS == 64 this
>    type is transparently replaced by off64_t.

and

> off64_t
>
>    This type is used similar to off_t. The difference is that
>    even on 32 bit machines, where the off_t type would have 32 bits,
>    off64_t has 64 bits and so is able to address files up to 2^63 bytes
>    in length. When compiling with _FILE_OFFSET_BITS == 64 this type
>    is available under the name off_t.

So it is not hard to guess that the `off_t`, `off64_t` and `O_LARGEFILE` are about a file size. In the case of the Linux kernel, the `O_LARGEFILE` is used  to disallow opening large files on 32bit systems if the caller didn't specify `O_LARGEFILE` flag during opening of a file. On 64bit systems we force on this flag in open system call. And the `force_o_largefile` macro from the [include/linux/fcntl.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/fcntl.h#L7) Linux kernel header file confirms this:

```C
#ifndef force_o_largefile
#define force_o_largefile() (BITS_PER_LONG != 32)
#endif
```

This macro may be architecture-specific as for example for [IA-64](https://en.wikipedia.org/wiki/IA-64) architecture, but in our case the [x86_64](https://en.wikipedia.org/wiki/X86-64) does not provide definition of the `force_o_largefile` and it will be used from [include/linux/fcntl.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/fcntl.h#L7).

So, as we may see the `force_o_largefile` is just a macro which expands to the `true` value in our case of [x86_64](https://en.wikipedia.org/wiki/X86-64) architecture. As we are considering 64-bit architecture, the `force_o_largefile` will be expanded to `true` and the `O_LARGEFILE` flag will be added to the set of flags which were passed to the `open` system call.

Now as we considered meaning of the `O_LARGEFILE` flag and `force_o_largefile` macro, we can proceed to the consideration of the implementation of the `do_sys_open` function. As I wrote above, this function is defined in the [same](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/open.c) source code file and looks:

```C
long do_sys_open(int dfd, const char __user *filename, int flags, umode_t mode)
{
	struct open_flags op;
	int fd = build_open_flags(flags, mode, &op);
	struct filename *tmp;

	if (fd)
		return fd;

	tmp = getname(filename);
	if (IS_ERR(tmp))
		return PTR_ERR(tmp);

	fd = get_unused_fd_flags(flags);
	if (fd >= 0) {
		struct file *f = do_filp_open(dfd, tmp, &op);
		if (IS_ERR(f)) {
			put_unused_fd(fd);
			fd = PTR_ERR(f);
		} else {
			fsnotify_open(f);
			fd_install(fd, f);
		}
	}
	putname(tmp);
	return fd;
}
```

Let's try to understand how the `do_sys_open` works step by step.

open(2) flags
--------------------------------------------------------------------------------

As you know the `open` system call takes set of `flags` as second argument that control opening a file and `mode` as third argument that specifies permission the permissions of a file if it is created. The `do_sys_open` function starts from the call of the `build_open_flags` function which does some checks that set of the given flags is valid and handles different conditions of flags and mode.

Let's look at the implementation of the `build_open_flags`. This function is defined in the [same](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/open.c) kernel file and takes three arguments:

* flags - flags that control opening of a file;
* mode - permissions for newly created file;

The last argument - `op` is represented with the `open_flags` structure:

```C
struct open_flags {
        int open_flag;
        umode_t mode;
        int acc_mode;
        int intent;
        int lookup_flags;
};
```

which is defined in the [fs/internal.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/internal.h#L99) header file and as we may see it holds information about flags and access mode for internal kernel purposes. As you already may guess the main goal of the `build_open_flags` function is to fill an instance of this structure.

Implementation of the `build_open_flags` function starts from the definition of local variables and one of them is:

```C
int acc_mode = ACC_MODE(flags);
```

This local variable represents access mode and its initial value will be equal to the value of expanded `ACC_MODE` macro. This macro is defined in the [include/linux/fs.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/fs.h) and looks pretty interesting:

```C
#define ACC_MODE(x) ("\004\002\006\006"[(x)&O_ACCMODE])
#define O_ACCMODE   00000003
```

The `"\004\002\006\006"` is an array of four chars:

```
"\004\002\006\006" == {'\004', '\002', '\006', '\006'}
```

So, the `ACC_MODE` macro just expands to the accession to this array by `[(x) & O_ACCMODE]` index. As we just saw, the `O_ACCMODE` is `00000003`. By applying `x & O_ACCMODE` we will take the two least significant bits which are represents `read`, `write` or `read/write` access modes:

```C
#define O_RDONLY        00000000
#define O_WRONLY        00000001
#define O_RDWR          00000002
```

After getting value from the array by the calculated index, the `ACC_MODE` will be expanded to access mode mask of a file which will hold `MAY_WRITE`, `MAY_READ` and other information.

We may see following condition after we have calculated initial access mode:

```C
if (flags & (O_CREAT | __O_TMPFILE))
	op->mode = (mode & S_IALLUGO) | S_IFREG;
else
	op->mode = 0;
```

Here we reset permissions in `open_flags` instance if an open file wasn't temporary and wasn't open for creation. This is because:

> if  neither O_CREAT nor O_TMPFILE is specified, then mode is ignored.

In other case if `O_CREAT` or `O_TMPFILE` were passed we canonicalize it to a regular file because a directory should be created with the [opendir](http://man7.org/linux/man-pages/man3/opendir.3.html) system call.

At the next step we check that a file is not tried to be opened via [fanotify](http://man7.org/linux/man-pages/man7/fanotify.7.html) and without the `O_CLOEXEC` flag:

```C
flags &= ~FMODE_NONOTIFY & ~O_CLOEXEC;
```

We do this to not leak a [file descriptor](https://en.wikipedia.org/wiki/File_descriptor). By default, the new file descriptor is set to remain open across an `execve` system call, but the `open` system call supports `O_CLOEXEC` flag that can be used to change this default behaviour. So we do this to prevent leaking of a file descriptor when one thread opens a file to set `O_CLOEXEC` flag and in the same time the second process does a [fork](https://en.wikipedia.org/wiki/Fork_(system_call)) + [execve](https://en.wikipedia.org/wiki/Exec_(system_call)) and as you may remember that child will have copies of the parent's set of open file descriptors.

At the next step we check that if our flags contains `O_SYNC` flag, we apply `O_DSYNC` flag too:

```
if (flags & __O_SYNC)
	flags |= O_DSYNC;
```

The `O_SYNC` flag guarantees that the any write call will not return before all data has been transferred to the disk. The `O_DSYNC` is like `O_SYNC` except that there is no requirement to wait for any metadata (like `atime`, `mtime` and etc.) changes will be written. We apply `O_DSYNC` in a case of `__O_SYNC` because it is implemented as `__O_SYNC|O_DSYNC` in the Linux kernel.

After this we must be sure that if a user wants to create temporary file, the flags should contain `O_TMPFILE_MASK` or in other words it should contain or `O_CREAT` or `O_TMPFILE` or both and also it should be writeable:

```C
if (flags & __O_TMPFILE) {
	if ((flags & O_TMPFILE_MASK) != O_TMPFILE)
		return -EINVAL;
	if (!(acc_mode & MAY_WRITE))
		return -EINVAL;
} else if (flags & O_PATH) {
       	flags &= O_DIRECTORY | O_NOFOLLOW | O_PATH;
        acc_mode = 0;
}
```

as it is written in in the manual page:

> O_TMPFILE  must  be  specified  with one of O_RDWR or O_WRONLY

If we didn't pass `O_TMPFILE` for creation of a temporary file, we check the `O_PATH` flag at the next condition. The `O_PATH` flag allows us to obtain a file descriptor that may be used for two following purposes:

* to indicate a location in the filesystem tree;
* to perform operations that act purely at the file descriptor level.

So, in this case the file itself is not opened, but operations like `dup`, `fcntl` and other can be used. So, if all file content related operations like `read`, `write` and other are not permitted, only `O_DIRECTORY | O_NOFOLLOW | O_PATH` flags can be used. We have finished with flags for this moment in the `build_open_flags` for this moment and we may fill our `open_flags->open_flag` with them:

```C
op->open_flag = flags;
```

Now we have filled `open_flag` field which represents flags that will control opening of a file and `mode` that will represent `umask` of a new file if we open file for creation. There are still to fill last flags in our `open_flags` structure. The next is `op->acc_mode` which represents access mode to a opened file. We already filled the `acc_mode` local variable with the initial value at the beginning of the `build_open_flags` and now we check last two flags related to access mode:

```C
if (flags & O_TRUNC)
        acc_mode |= MAY_WRITE;
if (flags & O_APPEND)
	acc_mode |= MAY_APPEND;
op->acc_mode = acc_mode;
```

These flags are - `O_TRUNC` that will truncate an opened file to length `0` if it existed before we open it and the `O_APPEND` flag allows to open a file in `append mode`. So the opened file will be appended during write but not overwritten.

The next field of the `open_flags` structure is - `intent`. It allows us to know about our intention or in other words what do we really want to do with file, open it, create, rename it or something else. So we set it to zero if our flags contains the `O_PATH` flag as we can't do anything related to a file content with this flag:

```C
op->intent = flags & O_PATH ? 0 : LOOKUP_OPEN;
```

or just to `LOOKUP_OPEN` intention. Additionally we set `LOOKUP_CREATE` intention if we want to create new file and to be sure that a file didn't exist before with `O_EXCL` flag:

```C
if (flags & O_CREAT) {
	op->intent |= LOOKUP_CREATE;
	if (flags & O_EXCL)
		op->intent |= LOOKUP_EXCL;
}
```

The last flag of the `open_flags` structure is the `lookup_flags`:

```C
if (flags & O_DIRECTORY)
	lookup_flags |= LOOKUP_DIRECTORY;
if (!(flags & O_NOFOLLOW))
	lookup_flags |= LOOKUP_FOLLOW;
op->lookup_flags = lookup_flags;

return 0;
```

We fill it with `LOOKUP_DIRECTORY` if we want to open a directory and `LOOKUP_FOLLOW` if we don't want to follow (open) [symlink](https://en.wikipedia.org/wiki/Symbolic_link). That's all. It is the end of the `build_open_flags` function. The `open_flags` structure is filled with modes and flags for a file opening and we can return back to the `do_sys_open`.

Actual opening of a file
--------------------------------------------------------------------------------

At the next step after `build_open_flags` function is finished and we have formed flags and modes for our file we should get the `filename` structure with the help of the `getname` function by name of a file which was passed to the `open` system call:

```C
tmp = getname(filename);
if (IS_ERR(tmp))
	return PTR_ERR(tmp);
```

The `getname` function is defined in the [fs/namei.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/namei.c) source code file and looks:

```C
struct filename *
getname(const char __user * filename)
{
        return getname_flags(filename, 0, NULL);
}
```

So, it just calls the `getname_flags` function and returns its result. The main goal of the `getname_flags` function is to copy a file path given from userland to kernel space. The `filename` structure is defined in the [include/linux/fs.h](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/include/linux/fs.h) Linux kernel header file and contains following fields:

* name - pointer to a file path in kernel space;
* uptr - original pointer from userland;
* aname - filename from [audit](https://linux.die.net/man/8/auditd) context;
* refcnt - reference counter;
* iname - a filename in a case when it will be less than `PATH_MAX`.

As I already wrote above, the main goal of the `getname_flags` function is to copy name of a file which was passed to the `open` system call from user space to kernel space with the strncpy_from_user function. The next step after a filename will be copied to kernel space is getting of new non-busy file descriptor:

```C
fd = get_unused_fd_flags(flags);
```

The `get_unused_fd_flags` function takes table of open files of the current process, minimum (`0`) and maximum (`RLIMIT_NOFILE`) possible number of a file descriptor in the system and flags that we have passed to the `open` system call and allocates file descriptor and mark it busy in the file descriptor table of the current process. The `get_unused_fd_flags` function sets or clears the `O_CLOEXEC` flag depends on its state in the passed flags.

The last and main step in the `do_sys_open` is the `do_filp_open` function:

```C
struct file *f = do_filp_open(dfd, tmp, &op);

if (IS_ERR(f)) {
	put_unused_fd(fd);
	fd = PTR_ERR(f);
} else {
	fsnotify_open(f);
	fd_install(fd, f);
}
```

The main goal of this function is to resolve given path name into `file` structure which represents an opened file of a process. If something going wrong and execution of the `do_filp_open` function will be failed, we should free new file descriptor with the `put_unused_fd` or in other way the `file` structure returned by the `do_filp_open` will be stored in the file descriptor table of the current process.

Now let's take a short look at the implementation of the `do_filp_open` function. This function is defined in the [fs/namei.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/namei.c) Linux kernel source code file and starts from initialization of the `nameidata` structure. This structure will provide a link to a file [inode](https://en.wikipedia.org/wiki/Inode). Actually this is one of the main point of the `do_filp_open` function to acquire an `inode` by the filename given to `open` system call. After the `nameidata` structure will be initialized, the `path_openat` function will be called:

```C
filp = path_openat(&nd, op, flags | LOOKUP_RCU);

if (unlikely(filp == ERR_PTR(-ECHILD)))
	filp = path_openat(&nd, op, flags);
if (unlikely(filp == ERR_PTR(-ESTALE)))
	filp = path_openat(&nd, op, flags | LOOKUP_REVAL);
```

Note that it is called three times. Actually, the Linux kernel will open the file in [RCU](https://www.kernel.org/doc/Documentation/RCU/whatisRCU.txt) mode. This is the most efficient way to open a file. If this try will be failed, the kernel enters the normal mode. The third call is relatively rare, only in the [nfs](https://en.wikipedia.org/wiki/Network_File_System) file system is likely to be used. The `path_openat` function executes `path lookup` or in other words it tries to find a `dentry` (what the Linux kernel uses to keep track of the hierarchy of files in directories) corresponding to a path.

The `path_openat` function starts from the call of the `get_empty_flip()` function that allocates a new `file` structure with some additional checks like do we exceed amount of opened files in the system or not and etc. After we have got allocated new `file` structure we call the `do_tmpfile` or `do_o_path` functions in a case if we have passed `O_TMPFILE | O_CREATE` or `O_PATH` flags during call of the `open` system call. Both these cases are quite specific, so let's consider quite usual case when we want to open already existed file and want to read/write from/to it.

In this case the `path_init` function will be called. This function performs some preparatory work before actual path lookup. This includes search of start position of path traversal and its metadata like `inode` of the path, `dentry inode` and etc. This can be `root` directory - `/` or current directory as in our case, because we use `AT_CWD` as starting point (see call of the `do_sys_open` at the beginning of the post).

The next step after the `path_init` is the [loop](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/namei.c#L3457) which executes the `link_path_walk` and `do_last`. The first function executes name resolution or in other words this function starts process of walking along a given path. It handles everything step by step except the last component of a file path. This handling includes checking of a permissions and getting a file component. As a file component is gotten, it is passed to `walk_component` that updates current directory entry from the `dcache` or asks underlying filesystem. This repeats before all path's components will not be handled in such way. After the `link_path_walk` will be executed, the `do_last` function will populate a `file` structure based on the result of the `link_path_walk`. As we reached last component of the given file path the `vfs_open` function from the `do_last` will be called.

This function is defined in the [fs/open.c](https://github.com/torvalds/linux/blob/16f73eb02d7e1765ccab3d2018e0bd98eb93d973/fs/open.c) Linux kernel source code file and the main goal of this function is to call an `open` operation of underlying filesystem.

That's all for now. We didn't consider **full** implementation of the `open` system call. We skip some parts like handling case when we want to open a file from other filesystem with different mount point, resolving symlinks and etc., but it should be not so hard to follow this stuff. This stuff does not included in **generic** implementation of open system call and depends on underlying filesystem. If you are interested in, you may lookup the `file_operations.open` callback function for a certain [filesystem](https://github.com/torvalds/linux/tree/master/fs).

Conclusion
--------------------------------------------------------------------------------

This is the end of the fifth part of the implementation of different system calls in the Linux kernel. If you have questions or suggestions, ping me on twitter [0xAX](https://twitter.com/0xAX), drop me an [email](mailto:anotherworldofworld@gmail.com), or just create an [issue](https://github.com/0xAX/linux-insides/issues/new). In the next part, we will continue to dive into system calls in the Linux kernel and see the implementation of the [read](http://man7.org/linux/man-pages/man2/read.2.html) system call.

**Please note that English is not my first language and I am really sorry for any inconvenience. If you find any mistakes please send me PR to [linux-insides](https://github.com/0xAX/linux-insides).**

Links
--------------------------------------------------------------------------------

* [system call](https://en.wikipedia.org/wiki/System_call)
* [open](http://man7.org/linux/man-pages/man2/open.2.html)
* [file descriptor](https://en.wikipedia.org/wiki/File_descriptor)
* [proc](https://en.wikipedia.org/wiki/Procfs)
* [GNU C Library Reference Manual](https://www.gnu.org/software/libc/manual/html_mono/libc.html#File-Position-Primitive)
* [IA-64](https://en.wikipedia.org/wiki/IA-64)
* [x86_64](https://en.wikipedia.org/wiki/X86-64)
* [opendir](http://man7.org/linux/man-pages/man3/opendir.3.html)
* [fanotify](http://man7.org/linux/man-pages/man7/fanotify.7.html)
* [fork](https://en.wikipedia.org/wiki/Fork_\(system_call\))
* [execve](https://en.wikipedia.org/wiki/Exec_\(system_call\))
* [symlink](https://en.wikipedia.org/wiki/Symbolic_link)
* [audit](https://linux.die.net/man/8/auditd)
* [inode](https://en.wikipedia.org/wiki/Inode)
* [RCU](https://www.kernel.org/doc/Documentation/RCU/whatisRCU.txt)
* [read](http://man7.org/linux/man-pages/man2/read.2.html)
* [previous part](https://0xax.gitbook.io/linux-insides/summary/syscall/linux-syscall-4)
